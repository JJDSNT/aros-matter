/*
 * ipv6probe: M0 audit of the AROSTCP IPv6 UDP features Matter relies on.
 * Runs entirely on one AROS host (loopback). Prints one PASS/FAIL line per
 * check, then a summary. See AI_context/issues/ISSUE-0001.md.
 */
#include <proto/exec.h>
#include <proto/bsdsocket.h>
#include <proto/miami.h>
#include <bsdsocket/socketbasetags.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <net/if.h>
#include <sys/ioctl.h>
#include <netinet/in.h>
#include <netinet/in_var.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>

/* AROS public headers lack struct in6_pktinfo (RFC 3542); the stack defines it
 * privately in netinet6/udp6_usrreq.c with this layout and guard. */
#ifndef IN6_PKTINFO_DEFINED
#define IN6_PKTINFO_DEFINED
struct in6_pktinfo {
    struct in6_addr ipi6_addr;
    unsigned int    ipi6_ifindex;
};
#endif

struct Library *SocketBase, *MiamiBase;
static int fails;

#define CHECK(name, expr) do { int ok_ = (expr); report(name, ok_, ok_ ? NULL : strerror(errno)); } while (0)

static void report(const char *name, int ok, const char *detail)
{
    printf("%s %s%s%s\n", ok ? "PASS" : "FAIL", name, detail ? ": " : "", detail ? detail : "");
    if (!ok) fails++;
}

static int wait_readable(int fd, int ms)
{
    fd_set r; struct timeval tv;
    tv.tv_sec = ms / 1000; tv.tv_usec = (ms % 1000) * 1000;
    FD_ZERO(&r); FD_SET(fd, &r);
    return WaitSelect(fd + 1, &r, NULL, NULL, &tv, NULL);
}

static int udp6(void)
{
    int on = 1, s = socket(AF_INET6, SOCK_DGRAM, 0);
    if (s >= 0) setsockopt(s, IPPROTO_IPV6, IPV6_V6ONLY, &on, sizeof(on));
    return s;
}

static void addr6(struct sockaddr_in6 *a, const char *txt, int port, unsigned scope)
{
    memset(a, 0, sizeof(*a));
    a->sin6_len = sizeof(*a); a->sin6_family = AF_INET6;
    a->sin6_port = htons(port); a->sin6_scope_id = scope;
    inet_pton(AF_INET6, (char *)txt, &a->sin6_addr);
}

static void t_unicast(void)
{
    char buf[64], msg[96]; struct sockaddr_in6 a, from; socklen_t fl = sizeof(from);
    int s = udp6(), n;
    report("socket(AF_INET6, SOCK_DGRAM)", s >= 0, s < 0 ? strerror(errno) : NULL);
    if (s < 0) return;
    addr6(&a, "::1", 40001, 0);
    CHECK("bind [::1]:40001", bind(s, (struct sockaddr *)&a, sizeof(a)) == 0);
    n = sendto(s, "ping6", 5, 0, (struct sockaddr *)&a, sizeof(a));
    report("sendto [::1]:40001", n == 5, n < 0 ? strerror(errno) : NULL);
    if (wait_readable(s, 2000) > 0) {
        n = recvfrom(s, buf, sizeof(buf), 0, (struct sockaddr *)&from, &fl);
        snprintf(msg, sizeof(msg), "n=%d family=%d", n, from.sin6_family);
        report("WaitSelect+recvfrom loopback", n == 5 && !memcmp(buf, "ping6", 5), msg);
    } else report("WaitSelect+recvfrom loopback", 0, "timeout");
    CloseSocket(s);
}

static void t_multicast(void)
{
    const char *ifn = "lo0";
    unsigned idx = MiamiBase ? if_nametoindex((char *)ifn) : 0;
    int s[2], i, on = 1, n, got[2] = {0, 0};
    struct sockaddr_in6 any, grp; struct ipv6_mreq mr; char msg[128], buf[64];

    snprintf(msg, sizeof(msg), "%s -> %u", ifn, idx);
    report("if_nametoindex(lo0)", idx > 0, msg);
    if (!idx) return;
    addr6(&any, "::", 5353, 0);
    addr6(&grp, "ff02::fb", 5353, idx);
    for (i = 0; i < 2; i++) {
        s[i] = udp6();
        setsockopt(s[i], SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on));
        setsockopt(s[i], SOL_SOCKET, SO_REUSEPORT, &on, sizeof(on));
        snprintf(msg, sizeof(msg), "socket %d", i);
        CHECK(i ? "bind [::]:5353 second socket (SO_REUSEPORT)" : "bind [::]:5353 first socket", bind(s[i], (struct sockaddr *)&any, sizeof(any)) == 0);
        memset(&mr, 0, sizeof(mr)); mr.ipv6mr_interface = idx;
        inet_pton(AF_INET6, "ff02::fb", &mr.ipv6mr_multiaddr);
        CHECK(i ? "IPV6_JOIN_GROUP ff02::fb (second)" : "IPV6_JOIN_GROUP ff02::fb (first)", setsockopt(s[i], IPPROTO_IPV6, IPV6_JOIN_GROUP, &mr, sizeof(mr)) == 0);
        setsockopt(s[i], IPPROTO_IPV6, IPV6_RECVPKTINFO, &on, sizeof(on));
    }
    CHECK("IPV6_MULTICAST_IF lo0", setsockopt(s[0], IPPROTO_IPV6, IPV6_MULTICAST_IF, &idx, sizeof(idx)) == 0);
    CHECK("IPV6_MULTICAST_LOOP 1", setsockopt(s[0], IPPROTO_IPV6, IPV6_MULTICAST_LOOP, &on, sizeof(on)) == 0);
    n = sendto(s[0], "mdns6", 5, 0, (struct sockaddr *)&grp, sizeof(grp));
    report("sendto ff02::fb%lo0:5353", n == 5, n < 0 ? strerror(errno) : NULL);

    for (i = 0; i < 2; i++) {
        if (wait_readable(s[i], 2000) > 0) {
            struct sockaddr_in6 from; struct iovec iov = { buf, sizeof(buf) };
            union { struct cmsghdr h; char b[CMSG_SPACE(sizeof(struct in6_pktinfo))]; } cb;
            struct msghdr mh; struct cmsghdr *c; unsigned pif = 0; char dst[INET6_ADDRSTRLEN] = "?";
            memset(&mh, 0, sizeof(mh));
            mh.msg_name = &from; mh.msg_namelen = sizeof(from);
            mh.msg_iov = &iov; mh.msg_iovlen = 1; mh.msg_control = &cb; mh.msg_controllen = sizeof(cb);
            n = recvmsg(s[i], &mh, 0);
            for (c = CMSG_FIRSTHDR(&mh); c; c = CMSG_NXTHDR(&mh, c))
                if (c->cmsg_level == IPPROTO_IPV6 && c->cmsg_type == IPV6_PKTINFO) {
                    struct in6_pktinfo *pi = (struct in6_pktinfo *)CMSG_DATA(c);
                    pif = pi->ipi6_ifindex; inet_ntop(AF_INET6, &pi->ipi6_addr, dst, sizeof(dst));
                }
            got[i] = (n == 5 && !memcmp(buf, "mdns6", 5));
            { char fs[INET6_ADDRSTRLEN]; inet_ntop(AF_INET6, &from.sin6_addr, fs, sizeof(fs));
              snprintf(msg, sizeof(msg), "socket %d n=%d from=%s ctrllen=%ld flags=0x%x pktinfo if=%u dst=%s",
                       i, n, fs, (long)mh.msg_controllen, (unsigned)mh.msg_flags, pif, dst); }
            report(i ? "recvmsg multicast (second socket)" : "recvmsg multicast (first socket)", got[i], msg);
            report(i ? "IPV6_PKTINFO ifindex (second)" : "IPV6_PKTINFO ifindex (first)", pif == idx, NULL);
        } else {
            report(i ? "recvmsg multicast (second socket)" : "recvmsg multicast (first socket)", 0, "timeout");
        }
    }
    for (i = 0; i < 2; i++) CloseSocket(s[i]);
}

/* List IPv6 addresses (SIOCGLIFADDR); returns the link-local of ifn in *ll. */
static int list_addrs6(const char *ifn, struct in6_addr *ll)
{
    struct in6_ifreq req[16]; struct in6_ifconf ifc; int s = udp6(), i, n, found = 0;
    char a[INET6_ADDRSTRLEN], msg[160];
    memset(&ifc, 0, sizeof(ifc)); ifc.ifc6_len = sizeof(req); ifc.ifc6_req = req;
    if (IoctlSocket(s, SIOCGLIFADDR, (char *)&ifc) != 0) { report("SIOCGLIFADDR", 0, strerror(errno)); CloseSocket(s); return 0; }
    n = ifc.ifc6_len / sizeof(req[0]);
    for (i = 0; i < n; i++) {
        struct sockaddr_in6 *sa = (struct sockaddr_in6 *)&req[i].ifr_ifru.ifru_addr;
        inet_ntop(AF_INET6, &sa->sin6_addr, a, sizeof(a));
        printf("INFO addr6 %s %s\n", req[i].ifr_name, a);
        if (ifn && !strcmp(req[i].ifr_name, ifn) && IN6_IS_ADDR_LINKLOCAL(&sa->sin6_addr)) { *ll = sa->sin6_addr; found = 1; }
    }
    snprintf(msg, sizeof(msg), "%d IPv6 addresses", n);
    report("SIOCGLIFADDR", n > 0, msg);
    CloseSocket(s);
    return found;
}

/* Workaround: a send-only socket bound to the link-local source address. */
static int send_from_linklocal(const struct in6_addr *ll, unsigned idx, const struct sockaddr_in6 *grp)
{
    struct sockaddr_in6 src; int s = udp6(), n;
    memset(&src, 0, sizeof(src)); src.sin6_len = sizeof(src); src.sin6_family = AF_INET6;
    src.sin6_addr = *ll; src.sin6_scope_id = idx;
    static int once;
    int b = bind(s, (struct sockaddr *)&src, sizeof(src));
    if (!once++) CHECK("link: bind send socket to link-local", b == 0);
    setsockopt(s, IPPROTO_IPV6, IPV6_MULTICAST_IF, &idx, sizeof(idx));
    n = sendto(s, "aros-mdns6", 10, 0, (struct sockaddr *)grp, sizeof(*grp));
    CloseSocket(s);
    return n;
}

/* Link test against a peer on a real interface (hosted: tap.device <-> host
 * aros0). Sends "aros-mdns6" to ff02::fb:5353 every second and waits for the
 * peer's "host-mdns6" on the group, for up to 15 s. */
static void t_link(const char *ifn)
{
    unsigned idx = MiamiBase ? if_nametoindex((char *)ifn) : 0;
    int s = udp6(), on = 1, n, k, got = 0, have_ll, use_ll = 0;
    struct sockaddr_in6 any, grp, from; struct ipv6_mreq mr; char msg[160], buf[64], src[INET6_ADDRSTRLEN];
    struct in6_addr ll;

    snprintf(msg, sizeof(msg), "%s -> %u", ifn, idx);
    report("link: if_nametoindex", idx > 0, msg);
    if (!idx || s < 0) return;
    have_ll = list_addrs6(ifn, &ll);
    report("link: interface has a link-local address", have_ll, NULL);
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on));
    setsockopt(s, SOL_SOCKET, SO_REUSEPORT, &on, sizeof(on));
    addr6(&any, "::", 5353, 0);
    addr6(&grp, "ff02::fb", 5353, idx);
    CHECK("link: bind [::]:5353", bind(s, (struct sockaddr *)&any, sizeof(any)) == 0);
    memset(&mr, 0, sizeof(mr)); mr.ipv6mr_interface = idx;
    inet_pton(AF_INET6, "ff02::fb", &mr.ipv6mr_multiaddr);
    CHECK("link: IPV6_JOIN_GROUP ff02::fb", setsockopt(s, IPPROTO_IPV6, IPV6_JOIN_GROUP, &mr, sizeof(mr)) == 0);
    CHECK("link: IPV6_MULTICAST_IF", setsockopt(s, IPPROTO_IPV6, IPV6_MULTICAST_IF, &idx, sizeof(idx)) == 0);
    for (k = 0; k < 15 && !got; k++) {
        n = use_ll ? -1 : sendto(s, "aros-mdns6", 10, 0, (struct sockaddr *)&grp, sizeof(grp));
        if (k == 0) report("link: sendto ff02::fb from socket bound to [::]", n == 10, n < 0 ? strerror(errno) : NULL);
        if (n < 0 && have_ll) {
            use_ll = 1;
            n = send_from_linklocal(&ll, idx, &grp);
            if (k == 0) report("link: sendto ff02::fb from link-local socket (workaround)", n == 10, n < 0 ? strerror(errno) : NULL);
        }
        while (wait_readable(s, 1000) > 0) {
            socklen_t fl = sizeof(from);
            n = recvfrom(s, buf, sizeof(buf) - 1, 0, (struct sockaddr *)&from, &fl);
            if (n == 10 && !memcmp(buf, "host-mdns6", 10)) {
                inet_ntop(AF_INET6, &from.sin6_addr, src, sizeof(src));
                snprintf(msg, sizeof(msg), "from [%s%%%u]:%u after %ds", src, (unsigned)from.sin6_scope_id, ntohs(from.sin6_port), k);
                report("link: receive peer multicast", 1, msg);
                got = 1; break;
            }
        }
    }
    if (!got) report("link: receive peer multicast", 0, "nothing from peer in 15 s");
    CloseSocket(s);
}

int main(int argc, char **argv)
{
    if (!(SocketBase = OpenLibrary("bsdsocket.library", 4))) { printf("FAIL bsdsocket.library not open\n"); return 20; }
    SocketBaseTags(SBTM_SETVAL(SBTC_ERRNOPTR(sizeof(errno))), (IPTR)&errno, TAG_END);
    MiamiBase = OpenLibrary("miami.library", 0);
    report("miami.library", MiamiBase != NULL, NULL);
    t_unicast();
    t_multicast();
    if (argc > 1) t_link(argv[1]);
    printf("SUMMARY %s (%d failed)\n", fails ? "FAIL" : "PASS", fails);
    if (MiamiBase) CloseLibrary(MiamiBase);
    CloseLibrary(SocketBase);
    return fails ? 10 : 0;
}
