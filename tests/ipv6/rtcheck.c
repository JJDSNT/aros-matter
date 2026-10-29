/*
 * rtcheck - AROS side of the RFC 4191 bench (tests/ipv6/rfc4191.py).
 *
 * Usage: rtcheck IFNAME PHASES
 * Sends "P:start" to the host (from the link-local address, which works on
 * every stack version), then once per phase - every 4 s, offset by 2.5 s from
 * the host's Router Advertisements - asks the routing table (RTM_GET) for a
 * fixed set of destinations and prints, per destination, the gateway of its
 * route or "none". Phase "reload" lines are also printed when it asks the
 * stack for an in-place reload, which the host schedules by phase number.
 */
#define __CONFIG_ROADSHOW__
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/bsdsocket.h>
#include <bsdsocket/socketbasetags.h>
#include <bsdsocket/netcontrol.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <sys/time.h>
#include <net/if.h>
#include <net/route.h>
#include <netinet/in.h>
#include <netinet/in_var.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

struct Library *SocketBase;
#define ROUNDUP(a) ((a) > 0 ? (1 + (((a) - 1) | (sizeof(long) - 1))) : sizeof(long))

static const char *dsts[] = {
    "2001:db8:4d54:10::1", "2001:db8:4d54:12::1", "2001:db8:4d54:13::1",
    "2001:db8:4d54:99::1", "2001:db8:4d54:14::1", "2001:db8:4d54:15::1",
    "2001:db8:4d54:20::1", "2001:db8:4d54:21::1", "2001:db8:ffff::1",
};
#define NDST (sizeof(dsts) / sizeof(dsts[0]))

static int waitread(int s, int ms)
{
    fd_set r; struct timeval tv; tv.tv_sec = ms / 1000; tv.tv_usec = (ms % 1000) * 1000;
    FD_ZERO(&r); FD_SET(s, &r);
    return WaitSelect(s + 1, &r, NULL, NULL, &tv, NULL) > 0;
}

static void route_get(const char *dst, char *out, int outlen)
{
    static int seq;
    union { struct rt_msghdr h; char b[512]; } msg;
    struct sockaddr_in6 *sa;
    int s, n = 0, want = ++seq;

    strcpy(out, "none");
    if ((s = socket(PF_ROUTE, SOCK_RAW, 0)) < 0) { strcpy(out, "nosock"); return; }
    memset(&msg, 0, sizeof(msg));
    msg.h.rtm_version = RTM_VERSION; msg.h.rtm_type = RTM_GET;
    msg.h.rtm_addrs = RTA_DST; msg.h.rtm_seq = want;
    sa = (struct sockaddr_in6 *)(&msg.h + 1);
    sa->sin6_len = sizeof(*sa); sa->sin6_family = AF_INET6;
    inet_pton(AF_INET6, (char *)dst, &sa->sin6_addr);
    msg.h.rtm_msglen = sizeof(msg.h) + ROUNDUP(sizeof(*sa));
    if (send(s, (char *)&msg, msg.h.rtm_msglen, 0) < 0) {
        if (getenv("RTCHECK_DEBUG")) printf("dbg %s send errno=%d\n", dst, errno);
        CloseSocket(s); return;
    }
    while (waitread(s, 2000)) {
        n = recv(s, (char *)&msg, sizeof(msg), 0);
        if (n <= 0 || (msg.h.rtm_type == RTM_GET && msg.h.rtm_seq == want))
            break;
    }
    CloseSocket(s);
    if (getenv("RTCHECK_DEBUG"))
    {
        unsigned char *q = (unsigned char *)(&msg.h + 1); int k;
        printf("dbg %s n=%d type=%d errno=%d flags=0x%x addrs=0x%x hdr=%d msglen=%d\n", dst, n, msg.h.rtm_type,
               msg.h.rtm_errno, msg.h.rtm_flags, msg.h.rtm_addrs, (int)sizeof(msg.h), msg.h.rtm_msglen);
        for (k = 0; k < 3; k++) {
            printf("dbg  sa%d len=%d fam=%d\n", k, q[0], q[1]);
            q += ROUNDUP(q[0]);
        }
    }
    if (n > 0 && msg.h.rtm_errno == 0 && (msg.h.rtm_flags & RTF_GATEWAY) &&
            (msg.h.rtm_addrs & RTA_GATEWAY)) {
        char *p = (char *)(&msg.h + 1);
        p += ROUNDUP(((struct sockaddr *)p)->sa_len);
        sa = (struct sockaddr_in6 *)p;
        if (sa->sin6_family == AF_INET6)
            inet_ntop(AF_INET6, &sa->sin6_addr, out, outlen);
    }
}

static int find_ll(const char *ifn, struct in6_addr *ll, unsigned *idx)
{
    struct ifreq ifr; struct in6_ifreq req[16]; struct in6_ifconf ifc; int s = socket(AF_INET6, SOCK_DGRAM, 0), i, n, ok = 0;
    memset(&ifr, 0, sizeof(ifr)); strncpy(ifr.ifr_name, ifn, sizeof(ifr.ifr_name) - 1);
    if (IoctlSocket(s, SIOCGIFINDEX, (char *)&ifr) == 0) *idx = ifr.ifr_index;
    memset(&ifc, 0, sizeof(ifc)); ifc.ifc6_len = sizeof(req); ifc.ifc6_req = req;
    if (IoctlSocket(s, SIOCGLIFADDR, (char *)&ifc) == 0)
        for (n = ifc.ifc6_len / sizeof(req[0]), i = 0; i < n; i++)
            if (!strcmp(req[i].ifr_name, ifn) && IN6_IS_ADDR_LINKLOCAL(&req[i].ifr_ifru.ifru_addr.sin6_addr)) {
                *ll = req[i].ifr_ifru.ifru_addr.sin6_addr; ok = 1;
            }
    CloseSocket(s);
    return ok;
}

static void marker(const struct in6_addr *ll, unsigned idx, const char *m)
{
    struct sockaddr_in6 a; int s = socket(AF_INET6, SOCK_DGRAM, 0);
    memset(&a, 0, sizeof(a)); a.sin6_len = sizeof(a); a.sin6_family = AF_INET6;
    a.sin6_addr = *ll; a.sin6_scope_id = idx;
    if (bind(s, (struct sockaddr *)&a, sizeof(a)) == 0) {
        setsockopt(s, IPPROTO_IPV6, IPV6_MULTICAST_IF, &idx, sizeof(idx));
        inet_pton(AF_INET6, "ff02::fb", &a.sin6_addr); a.sin6_port = htons(5353);
        sendto(s, (char *)m, strlen(m), 0, (struct sockaddr *)&a, sizeof(a));
    }
    CloseSocket(s);
}

static int net_reload(void)
{
    struct MsgPort *reply = CreateMsgPort(), *port; struct NetControlMsg msg; int rc = -1;
    if (!reply) return -1;
    memset(&msg, 0, sizeof(msg)); msg.ncm_Msg.mn_ReplyPort = reply; msg.ncm_Msg.mn_Length = sizeof(msg);
    msg.ncm_Command = NCMD_RELOAD;
    Forbid(); if ((port = FindPort((STRPTR)AROSTCP_CTRLPORT_NAME))) PutMsg(port, &msg.ncm_Msg); Permit();
    if (port) { WaitPort(reply); GetMsg(reply); rc = msg.ncm_Result; }
    DeleteMsgPort(reply);
    return rc;
}

/* DOS ticks (1/50 s) since T0 */
static long ticks_since(const struct DateStamp *t0)
{
    struct DateStamp now; DateStamp(&now);
    return ((now.ds_Days - t0->ds_Days) * 1440L + (now.ds_Minute - t0->ds_Minute)) * 3000L
           + (now.ds_Tick - t0->ds_Tick);
}

static void wait_until(const struct DateStamp *t0, long tick)
{
    long d;
    while ((d = tick - ticks_since(t0)) > 0)
        Delay(d);
}

int main(int argc, char **argv)
{
    struct in6_addr ll; unsigned idx = 0; int phases, p, d, reload_at;
    struct DateStamp t0;
    char gw[64];
    if (argc < 4) { printf("usage: rtcheck IFNAME PHASES RELOADPHASE\n"); return 20; }
    phases = atoi(argv[2]); reload_at = atoi(argv[3]);
    if (!(SocketBase = OpenLibrary((STRPTR)"bsdsocket.library", 4))) return 20;
    SocketBaseTags(SBTM_SETVAL(SBTC_ERRNOPTR(sizeof(errno))), (IPTR)&errno, TAG_END);
    if (!find_ll(argv[1], &ll, &idx)) { printf("no link-local on %s\n", argv[1]); return 20; }
    DateStamp(&t0);
    marker(&ll, idx, "P:start");
    /* phase p: the host advertises during [4p, 4p+4) s; we look at 4p+2.5 s
     * (4p+3.5 s in the reload phase, which reloads at 4p+0.5 s) */
    for (p = 0; p < phases; p++) {
        if (p == reload_at) {
            wait_until(&t0, 200L * p + 25);
            printf("phase %d reload rc=%d\n", p, net_reload());
            wait_until(&t0, 200L * p + 175);
        } else
            wait_until(&t0, 200L * p + 125);
        for (d = 0; d < (int)NDST; d++) {
            route_get(dsts[d], gw, sizeof(gw));
            printf("phase %d %s %s\n", p, dsts[d], gw);
        }
    }
    printf("done\n");
    CloseLibrary(SocketBase);
    return 0;
}
