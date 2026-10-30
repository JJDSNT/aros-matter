/*
 * ipv6test - AROSTCP IPv6 conformance cases (aros-matter tests/ipv6, S0).
 *
 * Runs on AROS. Usage:  ipv6test IFNAME [CASE...]
 * With no CASE every case runs. Results are one line per check:
 *
 *   ok <case> <check> [# detail]
 *   not ok <case> <check> [# detail]
 *   host <case> <expectation>      checked on the host by run.py
 *   info <case> <text>
 *
 * The host side (run.py) multicasts "H:<seq>" to ff02::fb:5353 on the link
 * twice a second, records what AROS sends, and captures MLD with tcpdump.
 * References for each case are in README.md.
 */
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/bsdsocket.h>
#include <proto/miami.h>
#include <bsdsocket/socketbasetags.h>
#include <bsdsocket/netcontrol.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <sys/time.h>
#include <net/if.h>
#include <netinet/in.h>
#include <netinet/in_var.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

/* struct pktinfo6's layout (RFC 3542 section 6.1) under a name of our own:
 * <netinet/in.h> declares it only since AROS #1947, and this file builds
 * against SDKs from before and after. */
struct pktinfo6 {
    struct in6_addr ipi6_addr;
    unsigned int    ipi6_ifindex;
};

struct Library *SocketBase, *MiamiBase;

static const char *g_if;
static unsigned g_idx;
static struct in6_addr g_ll;      /* link-local of g_if */
static int g_have_ll;
static int g_fail;
static const char *g_case;

#define PORT_MDNS 5353

/* ---------------------------------------------------------------- output */

static void res(int ok, const char *check, const char *fmt, ...)
    __attribute__((format(printf, 3, 4)));
static void res(int ok, const char *check, const char *fmt, ...)
{
    char d[200] = "";
    if (fmt) { va_list ap; va_start(ap, fmt); vsnprintf(d, sizeof(d), fmt, ap); va_end(ap); }
    printf("%s %s %s%s%s\n", ok ? "ok" : "not ok", g_case, check, d[0] ? " # " : "", d);
    if (!ok) g_fail++;
}
#define ERR strerror(errno)
/* check a call: the errno text is taken after it ran, and shown only on failure */
#define CHK(expr, check) do { int ok_ = (expr); int e_ = errno; \
        res(ok_, check, ok_ ? NULL : "%s", strerror(e_)); } while (0)
static void host(const char *what) { printf("host %s %s\n", g_case, what); }
static void info(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void info(const char *fmt, ...)
{
    char d[200]; va_list ap; va_start(ap, fmt); vsnprintf(d, sizeof(d), fmt, ap); va_end(ap);
    printf("info %s %s\n", g_case, d);
}

/* --------------------------------------------------------------- helpers */

static void sa6(struct sockaddr_in6 *a, const char *txt, int port, unsigned scope)
{
    memset(a, 0, sizeof(*a));
    a->sin6_len = sizeof(*a); a->sin6_family = AF_INET6;
    a->sin6_port = htons(port); a->sin6_scope_id = scope;
    inet_pton(AF_INET6, (char *)txt, &a->sin6_addr);
}

static const char *ntop(const struct in6_addr *a)
{
    static char b[4][INET6_ADDRSTRLEN]; static int i;
    i = (i + 1) & 3; inet_ntop(AF_INET6, (void *)a, b[i], sizeof(b[i])); return b[i];
}

static int udp6(int reuse)
{
    int on = 1, s = socket(AF_INET6, SOCK_DGRAM, 0);
    if (s < 0) return -1;
    setsockopt(s, IPPROTO_IPV6, IPV6_V6ONLY, &on, sizeof(on));
    if (reuse) {
        setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on));
        setsockopt(s, SOL_SOCKET, SO_REUSEPORT, &on, sizeof(on));
    }
    return s;
}

static int bind_any(int s, int port)
{
    struct sockaddr_in6 a; sa6(&a, "::", port, 0);
    return bind(s, (struct sockaddr *)&a, sizeof(a));
}

static int group(int s, int opt, const char *grp, unsigned idx)
{
    struct ipv6_mreq mr; memset(&mr, 0, sizeof(mr));
    inet_pton(AF_INET6, (char *)grp, &mr.ipv6mr_multiaddr); mr.ipv6mr_interface = idx;
    return setsockopt(s, IPPROTO_IPV6, opt, &mr, sizeof(mr));
}

static int readable(int s, int ms)
{
    fd_set r; struct timeval tv; tv.tv_sec = ms / 1000; tv.tv_usec = (ms % 1000) * 1000;
    FD_ZERO(&r); FD_SET(s, &r);
    return WaitSelect(s + 1, &r, NULL, NULL, &tv, NULL) > 0;
}

struct rx {
    int n; char buf[128];
    struct sockaddr_in6 from;
    int have_pi; struct pktinfo6 pi;
};

/* Receive until a datagram starting with prefix arrives or ms elapse. */
static int rx_prefix(int s, const char *prefix, int ms, struct rx *r)
{
    int waited = 0;
    while (waited < ms) {
        if (!readable(s, 250)) { waited += 250; continue; }
        {
            struct iovec iov; struct msghdr mh; struct cmsghdr *c;
            union { struct cmsghdr h; char b[CMSG_SPACE(sizeof(struct pktinfo6)) + 64]; } cb;
            memset(r, 0, sizeof(*r)); memset(&mh, 0, sizeof(mh));
            iov.iov_base = r->buf; iov.iov_len = sizeof(r->buf) - 1;
            mh.msg_name = &r->from; mh.msg_namelen = sizeof(r->from);
            mh.msg_iov = &iov; mh.msg_iovlen = 1;
            mh.msg_control = &cb; mh.msg_controllen = sizeof(cb);
            r->n = recvmsg(s, &mh, 0);
            if (r->n < 0) return 0;
            r->buf[r->n] = 0;
            if (mh.msg_controllen > 0)
                for (c = CMSG_FIRSTHDR(&mh); c; c = CMSG_NXTHDR(&mh, c))
                    if (c->cmsg_level == IPPROTO_IPV6 && c->cmsg_type == IPV6_PKTINFO) {
                        memcpy(&r->pi, CMSG_DATA(c), sizeof(r->pi)); r->have_pi = 1;
                    }
            if (!strncmp(r->buf, prefix, strlen(prefix))) return 1;
        }
    }
    return 0;
}

static void drain(int s) { char b[256]; while (readable(s, 0)) recv(s, b, sizeof(b), 0); }

static int find_linklocal(const char *ifn, struct in6_addr *ll)
{
    struct in6_ifreq req[32]; struct in6_ifconf ifc; int s = udp6(0), i, n, found = 0;
    memset(&ifc, 0, sizeof(ifc)); ifc.ifc6_len = sizeof(req); ifc.ifc6_req = req;
    if (IoctlSocket(s, SIOCGLIFADDR, (char *)&ifc) == 0) {
        n = ifc.ifc6_len / sizeof(req[0]);
        for (i = 0; i < n; i++) {
            struct sockaddr_in6 *a = &req[i].ifr_ifru.ifru_addr;
            if (!strcmp(req[i].ifr_name, ifn) && IN6_IS_ADDR_LINKLOCAL(&a->sin6_addr)) {
                *ll = a->sin6_addr; found = 1;
            }
        }
    }
    CloseSocket(s);
    return found;
}

static int send_to(int s, const char *payload, const char *dst, unsigned scope)
{
    struct sockaddr_in6 d; sa6(&d, dst, PORT_MDNS, scope);
    return sendto(s, (char *)payload, strlen(payload), 0, (struct sockaddr *)&d, sizeof(d));
}

/* ------------------------------------------------------------------ cases */

/* local.unicast: AF_INET6 UDP on ::1 with WaitSelect. RFC 3493 §3. */
static void c_local_unicast(void)
{
    struct sockaddr_in6 a; struct rx r; int s = udp6(0), n;
    { int e = errno; res(s >= 0, "socket", s < 0 ? "%s" : NULL, strerror(e)); }
    if (s < 0) return;
    sa6(&a, "::1", 40001, 0);
    CHK(bind(s, (struct sockaddr *)&a, sizeof(a)) == 0, "bind-::1");
    n = sendto(s, "U:1", 3, 0, (struct sockaddr *)&a, sizeof(a));
    { int e = errno; res(n == 3, "sendto-::1", n < 0 ? "%s" : NULL, strerror(e)); }
    res(rx_prefix(s, "U:", 2000, &r), "recv-::1", NULL);
    CloseSocket(s);
}

/* local.join-semantics: RFC 3493 §5.2 option behaviour. */
static void c_local_join(void)
{
    int s = udp6(1);
    bind_any(s, PORT_MDNS);
    CHK(group(s, IPV6_JOIN_GROUP, "ff12::4d54:10", g_idx) == 0, "join");
    { int rc = group(s, IPV6_JOIN_GROUP, "ff12::4d54:10", g_idx), e = errno;
      res(rc != 0 && e == EADDRINUSE, "join-twice-EADDRINUSE", "rc=%d errno=%d", rc, e); }
    CHK(group(s, IPV6_LEAVE_GROUP, "ff12::4d54:10", g_idx) == 0, "leave");
    { int rc = group(s, IPV6_LEAVE_GROUP, "ff12::4d54:10", g_idx), e = errno;
      res(rc != 0 && e == EADDRNOTAVAIL, "leave-again-EADDRNOTAVAIL", "rc=%d errno=%d", rc, e); }
    CloseSocket(s);
}

/* local.reuseport-bind: two sockets share the mDNS port. */
static void c_local_reuseport(void)
{
    int a = udp6(1), b = udp6(1);
    CHK(bind_any(a, PORT_MDNS) == 0, "bind-first");
    CHK(bind_any(b, PORT_MDNS) == 0, "bind-second");
    CloseSocket(a); CloseSocket(b);
}

/* link.linklocal: the interface has an autoconfigured link-local (RFC 4862 §5.3). */
static void c_link_ll(void)
{
    res(g_idx > 0, "if_nametoindex", "%s=%u", g_if, g_idx);
    res(g_have_ll, "has-link-local", g_have_ll ? "%s" : NULL, ntop(&g_ll));
}

/* link.send-mcast-if: send to ff02::fb from a [::] socket that chose the
 * interface with IPV6_MULTICAST_IF (Readme §6.6, RFC 3493 §5.2). */
static void c_send_mcast_if(void)
{
    int s = udp6(1), n;
    bind_any(s, PORT_MDNS);
    CHK(setsockopt(s, IPPROTO_IPV6, IPV6_MULTICAST_IF, &g_idx, sizeof(g_idx)) == 0, "MULTICAST_IF");
    n = send_to(s, "A:send-mcast-if", "ff02::fb", 0);
    { int e = errno; res(n > 0, "sendto", n < 0 ? "%s" : NULL, strerror(e)); }
    host("received A:send-mcast-if from-port 5353");
    CloseSocket(s);
}

/* link.send-scopeid: the destination's sin6_scope_id alone names the link
 * (Readme §6.6, RFC 4007 §11, RFC 3493 §3.3). */
static void c_send_scopeid(void)
{
    int s = udp6(1), n;
    bind_any(s, PORT_MDNS);
    n = send_to(s, "A:send-scopeid", "ff02::fb", g_idx);
    { int e = errno; res(n > 0, "sendto", n < 0 ? "%s" : NULL, strerror(e)); }
    host("received A:send-scopeid from-port 5353");
    CloseSocket(s);
}

/* link.recv-joined: a socket that joined ff02::fb receives the host's
 * datagrams (RFC 3493 §5.2; RFC 4291 §2.7 group delivery). */
static void c_recv_joined(void)
{
    struct rx r; int s = udp6(1);
    bind_any(s, PORT_MDNS);
    CHK(group(s, IPV6_JOIN_GROUP, "ff02::fb", g_idx) == 0, "join");
    { int got = rx_prefix(s, "H:", 4000, &r);
      res(got, "recv", got ? "%s from %s" : NULL, r.buf, ntop(&r.from.sin6_addr)); }
    CloseSocket(s);
}

/* link.recv-fanout: every socket bound to the port gets a copy, as IPv4
 * udp_input() does in this stack (netinet/udp_usrreq.c). */
static void c_recv_fanout(void)
{
    struct rx r; int a = udp6(1), b = udp6(1), ga, gb;
    char sa[sizeof(((struct rx *)0)->buf)] = "", sb[sizeof(sa)] = "";
    bind_any(a, PORT_MDNS); bind_any(b, PORT_MDNS);
    group(a, IPV6_JOIN_GROUP, "ff02::fb", g_idx);
    group(b, IPV6_JOIN_GROUP, "ff02::fb", g_idx);
    ga = rx_prefix(a, "H:", 4000, &r); if (ga) strncpy(sa, r.buf, sizeof(sa) - 1);
    gb = rx_prefix(b, "H:", 1000, &r); if (gb) strncpy(sb, r.buf, sizeof(sb) - 1);
    res(ga, "recv-first", NULL);
    res(gb, "recv-second", NULL);
    if (ga && gb) info("first=%s second=%s", sa, sb);
    CloseSocket(a); CloseSocket(b);
}

/* link.recv-port-parity: a socket on the port that joined nothing still
 * receives a group the host is a member of on that link - IPv4 parity
 * (udp_input matches port and addresses, not memberships). */
static void c_recv_parity(void)
{
    struct rx r; int member = udp6(1), plain = udp6(1);
    bind_any(member, PORT_MDNS); bind_any(plain, PORT_MDNS);
    group(member, IPV6_JOIN_GROUP, "ff02::fb", g_idx);
    res(rx_prefix(plain, "H:", 4000, &r), "recv-without-membership", NULL);
    CloseSocket(member); CloseSocket(plain);
}

/* link.pktinfo: IPV6_RECVPKTINFO gives destination and interface (RFC 3542 §6). */
static void c_pktinfo(void)
{
    struct rx r; int on = 1, s = udp6(1), got;
    bind_any(s, PORT_MDNS);
    group(s, IPV6_JOIN_GROUP, "ff02::fb", g_idx);
    CHK(setsockopt(s, IPPROTO_IPV6, IPV6_RECVPKTINFO, &on, sizeof(on)) == 0, "RECVPKTINFO");
    got = rx_prefix(s, "H:", 4000, &r);
    res(got, "recv", NULL);
    if (got) {
        struct in6_addr fb; inet_pton(AF_INET6, "ff02::fb", &fb);
        res(r.have_pi, "pktinfo-present", NULL);
        res(r.have_pi && r.pi.ipi6_ifindex == g_idx, "pktinfo-ifindex", "%u", r.pi.ipi6_ifindex);
        res(r.have_pi && IN6_ARE_ADDR_EQUAL(&r.pi.ipi6_addr, &fb), "pktinfo-dst", "%s", ntop(&r.pi.ipi6_addr));
    }
    CloseSocket(s);
}

/* link.recv-scopeid: a link-local source comes back with its zone
 * (RFC 4007 §11, RFC 3493 §3.3). */
static void c_recv_scopeid(void)
{
    struct rx r; int s = udp6(1), got;
    bind_any(s, PORT_MDNS);
    group(s, IPV6_JOIN_GROUP, "ff02::fb", g_idx);
    got = rx_prefix(s, "H:", 4000, &r);
    res(got, "recv", NULL);
    if (got)
        res(IN6_IS_ADDR_LINKLOCAL(&r.from.sin6_addr) && r.from.sin6_scope_id == g_idx,
            "source-scope-id", "%s%%%u", ntop(&r.from.sin6_addr), (unsigned)r.from.sin6_scope_id);
    CloseSocket(s);
}

/* link.mcast-loop: IPV6_MULTICAST_LOOP (default 1) delivers our own group
 * datagram to local members; 0 suppresses it (RFC 3493 §5.2). */
static void c_mcast_loop(void)
{
    struct rx r; int rcv = udp6(1), snd = udp6(1), off = 0, n;
    bind_any(rcv, PORT_MDNS); bind_any(snd, PORT_MDNS);
    group(rcv, IPV6_JOIN_GROUP, "ff02::fb", g_idx);
    setsockopt(snd, IPPROTO_IPV6, IPV6_MULTICAST_IF, &g_idx, sizeof(g_idx));
    drain(rcv);
    n = send_to(snd, "L:loop-on", "ff02::fb", 0);
    { int e = errno; res(n > 0, "sendto-loop-on", n < 0 ? "%s" : NULL, strerror(e)); }
    res(n > 0 && rx_prefix(rcv, "L:loop-on", 1500, &r), "local-copy-with-loop", NULL);
    setsockopt(snd, IPPROTO_IPV6, IPV6_MULTICAST_LOOP, &off, sizeof(off));
    n = send_to(snd, "L:loop-off", "ff02::fb", 0);
    res(n > 0 && !rx_prefix(rcv, "L:loop-off", 1500, &r), "no-local-copy-without-loop", NULL);
    host("received A-or-L:loop-on");
    CloseSocket(rcv); CloseSocket(snd);
}

/* mld.leave-explicit: IPV6_LEAVE_GROUP sends Done (RFC 2710 §4) or a v2
 * TO_IN{} record (RFC 3810 §6.1). */
static void c_mld_leave(void)
{
    int s = udp6(1);
    bind_any(s, PORT_MDNS);
    CHK(group(s, IPV6_JOIN_GROUP, "ff12::4d54:b", g_idx) == 0, "join");
    Delay(2 * 50);
    CHK(group(s, IPV6_LEAVE_GROUP, "ff12::4d54:b", g_idx) == 0, "leave");
    Delay(1 * 50);
    host("mld ff12::4d54:b report,leave");
    CloseSocket(s);
}

/* mld.close-leaves: closing a socket drops its memberships; joining again
 * is a new membership with a new Report. Mirror of IPv4 95a501ff47. */
static void c_mld_close(void)
{
    int s = udp6(1);
    bind_any(s, PORT_MDNS);
    CHK(group(s, IPV6_JOIN_GROUP, "ff12::4d54:a", g_idx) == 0, "join");
    Delay(2 * 50);
    CloseSocket(s);
    Delay(2 * 50);
    s = udp6(1);
    bind_any(s, PORT_MDNS);
    CHK(group(s, IPV6_JOIN_GROUP, "ff12::4d54:a", g_idx) == 0, "rejoin");
    Delay(2 * 50);
    CloseSocket(s);
    Delay(1 * 50);
    host("mld ff12::4d54:a report,leave,report,leave");
}

/* mld.addr-owned: an address added by hand joins its solicited-node group
 * and leaves it when removed (RFC 4861 §7.2.1, RFC 4862 §5.4.2). */
static void c_mld_addr(void)
{
    struct in6_aliasreq ifra; struct in6_ifreq ifr; int s = udp6(0), j, rc;
    memset(&ifra, 0, sizeof(ifra));
    strncpy(ifra.ifra_name, g_if, sizeof(ifra.ifra_name) - 1);
    sa6(&ifra.ifra_addr, "fd00:4d54::12:3456", 0, 0);
    ifra.ifra_prefixmask.sin6_len = sizeof(ifra.ifra_prefixmask);
    ifra.ifra_prefixmask.sin6_family = AF_INET6;
    for (j = 0; j < 8; j++) ifra.ifra_prefixmask.sin6_addr.s6_addr[j] = 0xff;
    ifra.ifra_lifetime.ia6t_vltime = ifra.ifra_lifetime.ia6t_pltime = 0xffffffffU;
    rc = IoctlSocket(s, SIOCAIFADDR_IN6, (char *)&ifra);
    { int e = errno; res(rc == 0, "add-address", rc ? "%s" : NULL, strerror(e)); }
    Delay(3 * 50);
    memset(&ifr, 0, sizeof(ifr));
    strncpy(ifr.ifr_name, g_if, sizeof(ifr.ifr_name) - 1);
    sa6(&ifr.ifr_ifru.ifru_addr, "fd00:4d54::12:3456", 0, 0);
    rc = IoctlSocket(s, SIOCDIFADDR_IN6, (char *)&ifr);
    { int e = errno; res(rc == 0, "delete-address", rc ? "%s" : NULL, strerror(e)); }
    Delay(1 * 50);
    CloseSocket(s);
    host("mld ff02::1:ff12:3456 report,leave");
}

/* A phase marker for the host: sent from a socket bound to the link-local
 * address, which works on the current stack, so the host can timestamp the
 * phases of a case. A test signal only, not a way to send multicast. */
static void marker(const char *m)
{
    struct sockaddr_in6 src; int s = udp6(0);
    if (!g_have_ll) { CloseSocket(s); return; }
    memset(&src, 0, sizeof(src)); src.sin6_len = sizeof(src); src.sin6_family = AF_INET6;
    src.sin6_addr = g_ll; src.sin6_scope_id = g_idx;
    if (bind(s, (struct sockaddr *)&src, sizeof(src)) == 0) {
        setsockopt(s, IPPROTO_IPV6, IPV6_MULTICAST_IF, &g_idx, sizeof(g_idx));
        send_to(s, m, "ff02::fb", g_idx);
    }
    CloseSocket(s);
    Delay(50);   /* the host timestamps the marker on arrival: keep a second
                  * between it and what the case does next */
}

/* link.nd-reachable: the host can resolve and ping our link-local, so
 * neighbour discovery for it works (RFC 4861 section 7.2). */
static void c_nd(void)
{
    marker("P:ping-me");
    Delay(6 * 50);
    host("nd ping-ok");
}

/* AROSTCP in-place reload through its control port (bsdsocket/netcontrol.h). */
static int net_reload(void)
{
    struct MsgPort *reply = CreateMsgPort(), *port;
    struct NetControlMsg msg; int rc = -1;
    if (!reply) return -1;
    memset(&msg, 0, sizeof(msg));
    msg.ncm_Msg.mn_ReplyPort = reply; msg.ncm_Msg.mn_Length = sizeof(msg);
    msg.ncm_Command = NCMD_RELOAD;
    Forbid();
    if ((port = FindPort((STRPTR)AROSTCP_CTRLPORT_NAME)) != NULL) PutMsg(port, &msg.ncm_Msg);
    Permit();
    if (port) { WaitPort(reply); GetMsg(reply); rc = msg.ncm_Result; }
    DeleteMsgPort(reply);
    return rc;
}

#define IFDB "SYS:System/Network/AROSTCP/db/interfaces"
static char g_db[16384];
static long g_dblen;

static int db_read(void)
{
    FILE *f = fopen(IFDB, "r"); if (!f) return 0;
    g_dblen = fread(g_db, 1, sizeof(g_db) - 1, f); fclose(f); g_db[g_dblen] = 0;
    return g_dblen > 0;
}
static int db_write(int without_if)
{
    FILE *f = fopen(IFDB, "w"); char *line, *save, *copy; size_t n = strlen(g_if);
    if (!f) return 0;
    if (!without_if) { fwrite(g_db, 1, g_dblen, f); fclose(f); return 1; }
    copy = strdup(g_db);
    for (line = strtok_r(copy, "\n", &save); line; line = strtok_r(NULL, "\n", &save))
        if (!(strncmp(line, g_if, n) == 0 && (line[n] == ' ' || line[n] == '\t')))
            fprintf(f, "%s\n", line);
    free(copy); fclose(f);
    return 1;
}

/* mld.ifdetach: a group a socket holds when its interface goes away must not
 * survive on a later interface (mirror of IPv4 4b11ae149b): after the
 * interface is removed and configured again, joining the same group is a new
 * membership with a Report; closing the socket that held the old one sends
 * nothing. */
static void c_mld_ifdetach(void)
{
    int old = udp6(1), now = -1, rc; unsigned idx2;
    bind_any(old, PORT_MDNS);
    CHK(group(old, IPV6_JOIN_GROUP, "ff12::4d54:c", g_idx) == 0, "join");
    Delay(2 * 50);
    res(db_read(), "read-interfaces-db", NULL);
    marker("P:removing");
    res(db_write(1), "drop-interface-from-db", NULL);
    rc = net_reload();
    res(rc == 0, "reload-without-interface", "rc=%d", rc);
    Delay(3 * 50);
    res(if_nametoindex((char *)g_if) == 0, "interface-gone", NULL);
    res(db_write(0), "restore-db", NULL);
    rc = net_reload();
    res(rc == 0, "reload-with-interface", "rc=%d", rc);
    Delay(8 * 50);
    idx2 = if_nametoindex((char *)g_if);
    res(idx2 > 0, "interface-back", "index %u -> %u", g_idx, idx2);
    if (!idx2) { CloseSocket(old); return; }
    g_idx = idx2; g_have_ll = find_linklocal(g_if, &g_ll);
    res(g_have_ll, "link-local-back", g_have_ll ? "%s" : NULL, ntop(&g_ll));
    marker("P:readded");
    now = udp6(1); bind_any(now, PORT_MDNS);
    CHK(group(now, IPV6_JOIN_GROUP, "ff12::4d54:c", g_idx) == 0, "join-on-new-interface");
    Delay(3 * 50);
    marker("P:rejoined");
    CloseSocket(old);
    Delay(2 * 50);
    marker("P:oldclosed");
    CloseSocket(now);
    Delay(2 * 50);
    marker("P:end");
    res(1, "no-crash", NULL);
    host("mldwin ff12::4d54:c P:readded P:rejoined report");
    host("mldwin ff12::4d54:c P:rejoined P:oldclosed none");
    host("mldwin ff12::4d54:c P:oldclosed P:end leave");
}

/* addr.delete-then-reload: delete an address with SIOCDIFADDR_IN6, then
 * remove the interface by a reload. A route left pointing at the freed address
 * crashes rt_purgeif() (ISSUE-0009). Opt-in: it takes the stack down when it fails. */
static void c_addr_delete_reload(void)
{
    struct in6_aliasreq ifra; struct in6_ifreq ifr; int s = udp6(0), j, rc;
    memset(&ifra, 0, sizeof(ifra));
    strncpy(ifra.ifra_name, g_if, sizeof(ifra.ifra_name) - 1);
    sa6(&ifra.ifra_addr, "fd00:4d54::12:3457", 0, 0);
    ifra.ifra_prefixmask.sin6_len = sizeof(ifra.ifra_prefixmask);
    ifra.ifra_prefixmask.sin6_family = AF_INET6;
    for (j = 0; j < 8; j++) ifra.ifra_prefixmask.sin6_addr.s6_addr[j] = 0xff;
    ifra.ifra_lifetime.ia6t_vltime = ifra.ifra_lifetime.ia6t_pltime = 0xffffffffU;
    CHK(IoctlSocket(s, SIOCAIFADDR_IN6, (char *)&ifra) == 0, "add-address");
    Delay(2 * 50);
    memset(&ifr, 0, sizeof(ifr));
    strncpy(ifr.ifr_name, g_if, sizeof(ifr.ifr_name) - 1);
    sa6(&ifr.ifr_ifru.ifru_addr, "fd00:4d54::12:3457", 0, 0);
    CHK(IoctlSocket(s, SIOCDIFADDR_IN6, (char *)&ifr) == 0, "delete-address");
    CloseSocket(s);
    /* the interface is then removed by a reload, as in mld.ifdetach */
    res(db_read() && db_write(1), "drop-interface-from-db", NULL);
    rc = net_reload();
    res(rc == 0, "reload-without-interface", "rc=%d", rc);
    Delay(3 * 50);
    res(db_write(0), "restore-db", NULL);
    rc = net_reload();
    res(rc == 0, "reload-with-interface", "rc=%d", rc);
    Delay(6 * 50);
    res(if_nametoindex((char *)g_if) > 0, "stack-still-up", NULL);
}

/* matter.*: Matter groupcast (Core spec 4.3; certification TC_SC_5_3). Group
 * messages are UDP to port 5540 on the per-group address
 * FF35:0040:FD<fabric>00:<group> (here fabric 1, group 0x0101) or on the IANA
 * address ff05::fa, both site-local (scope 5). */
#define PORT_MATTER 5540
#define MATTER_GROUP "ff35:40:fd00::100:101"
#define MATTER_IANA  "ff05::fa"

static int send_port(int s, const char *payload, const char *dst, int port, unsigned scope)
{
    struct sockaddr_in6 d; sa6(&d, dst, port, scope);
    return sendto(s, (char *)payload, strlen(payload), 0, (struct sockaddr *)&d, sizeof(d));
}

/* matter.group-recv: joining the group on the interface reports it from the
 * link-local (RFC 3810 section 5) and delivers the host's group datagrams;
 * closing the socket leaves the group. */
static void c_matter_group_recv(void)
{
    struct rx r; int s = udp6(1), got;
    res(bind_any(s, PORT_MATTER) == 0, "bind-5540", NULL);
    CHK(group(s, IPV6_JOIN_GROUP, MATTER_GROUP, g_idx) == 0, "join");
    got = rx_prefix(s, "G:", 4000, &r);
    res(got, "received-group-datagram", got ? "%s from %s" : NULL, r.buf, ntop(&r.from.sin6_addr));
    CloseSocket(s);
    Delay(2 * 50);
    host("mld " MATTER_GROUP " report,leave");
}

/* matter.group-send: a socket on [::]:5540 that names the interface with
 * IPV6_MULTICAST_IF sends to the per-group and to the IANA group address;
 * the host, a member of both, receives each from port 5540. */
static void c_matter_group_send(void)
{
    int s = udp6(1), n1, n2;
    res(bind_any(s, PORT_MATTER) == 0, "bind-5540", NULL);
    CHK(setsockopt(s, IPPROTO_IPV6, IPV6_MULTICAST_IF, &g_idx, sizeof(g_idx)) == 0, "MULTICAST_IF");
    n1 = send_port(s, "M:group", MATTER_GROUP, PORT_MATTER, 0);
    { int e = errno; res(n1 > 0, "sendto-group", n1 < 0 ? "%s" : NULL, strerror(e)); }
    n2 = send_port(s, "M:iana", MATTER_IANA, PORT_MATTER, 0);
    { int e = errno; res(n2 > 0, "sendto-iana", n2 < 0 ? "%s" : NULL, strerror(e)); }
    host("received M:group from-port 5540");
    host("received M:iana from-port 5540");
    Delay(50);
    CloseSocket(s);
}

/* ----------------------------------------------------------------- driver */

struct tcase { const char *name; void (*fn)(void); int link; int optin; };
static const struct tcase cases[] = {
    { "local.unicast",        c_local_unicast,   0 },
    { "local.join-semantics", c_local_join,      1 },
    { "local.reuseport-bind", c_local_reuseport, 0 },
    { "link.linklocal",       c_link_ll,         1 },
    { "link.send-mcast-if",   c_send_mcast_if,   1 },
    { "link.send-scopeid",    c_send_scopeid,    1 },
    { "link.recv-joined",     c_recv_joined,     1 },
    { "link.recv-fanout",     c_recv_fanout,     1 },
    { "link.recv-port-parity",c_recv_parity,     1 },
    { "link.pktinfo",         c_pktinfo,         1 },
    { "link.recv-scopeid",    c_recv_scopeid,    1 },
    { "link.mcast-loop",      c_mcast_loop,      1 },
    { "mld.leave-explicit",   c_mld_leave,       1 },
    { "mld.close-leaves",     c_mld_close,       1 },
    { "link.nd-reachable",    c_nd,              1 },
    { "matter.group-recv",    c_matter_group_recv, 1 },
    { "matter.group-send",    c_matter_group_send, 1 },
    { "mld.ifdetach",         c_mld_ifdetach,    1 },   /* reloads the stack */
    { "mld.addr-owned",       c_mld_addr,        1 },
    { "addr.delete-then-reload", c_addr_delete_reload, 1, 1 },  /* opt-in */
};
#define NCASES (sizeof(cases) / sizeof(cases[0]))

int main(int argc, char **argv)
{
    unsigned i; int a;
    if (argc < 2) { printf("usage: ipv6test IFNAME [CASE...]\n"); return 20; }
    g_if = argv[1];
    if (!(SocketBase = OpenLibrary((STRPTR)"bsdsocket.library", 4))) { printf("not ok setup bsdsocket\n"); return 20; }
    SocketBaseTags(SBTM_SETVAL(SBTC_ERRNOPTR(sizeof(errno))), (IPTR)&errno, TAG_END);
    if (!(MiamiBase = OpenLibrary((STRPTR)"miami.library", 0))) { printf("not ok setup miami\n"); return 20; }
    g_idx = if_nametoindex((char *)g_if);
    g_have_ll = g_idx ? find_linklocal(g_if, &g_ll) : 0;
    printf("info setup if=%s index=%u link-local=%s\n", g_if, g_idx, g_have_ll ? ntop(&g_ll) : "none");

    for (i = 0; i < NCASES; i++) {
        int run = argc == 2 && !cases[i].optin;
        for (a = 2; a < argc; a++) if (!strcmp(argv[a], cases[i].name)) run = 1;
        if (!run) continue;
        g_case = cases[i].name;
        printf("case %s\n", g_case);
        if (cases[i].link && !g_idx) { res(0, "precondition", "no interface %s", g_if); continue; }
        cases[i].fn();
    }
    printf("done %d\n", g_fail);
    CloseLibrary(MiamiBase); CloseLibrary(SocketBase);
    return g_fail ? 10 : 0;
}
