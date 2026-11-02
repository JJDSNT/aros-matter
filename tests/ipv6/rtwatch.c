/*
 * rtwatch - AROS side of the default router bench (tests/ipv6/defrouter.py).
 *
 * Usage: rtwatch IFNAME DST SECONDS
 * Sends "P:start" to the host, then for SECONDS sends a UDP datagram to
 * DST port 9 twice a second - traffic through the default router, which
 * keeps neighbour unreachability detection on it going - and once a second
 * prints the gateway of the route the table has for DST ("t <s> <gw>").
 */
#define __CONFIG_ROADSHOW__
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/bsdsocket.h>
#include <bsdsocket/socketbasetags.h>
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
        CloseSocket(s); return;
    }
    while (waitread(s, 2000)) {
        n = recv(s, (char *)&msg, sizeof(msg), 0);
        if (n <= 0 || (msg.h.rtm_type == RTM_GET && msg.h.rtm_seq == want))
            break;
    }
    CloseSocket(s);
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

int main(int argc, char **argv)
{
    struct in6_addr ll; unsigned idx = 0; int secs, k, s;
    struct sockaddr_in6 d;
    char gw[64];

    if (argc < 4) { printf("usage: rtwatch IFNAME DST SECONDS\n"); return 20; }
    secs = atoi(argv[3]);
    if (!(SocketBase = OpenLibrary((STRPTR)"bsdsocket.library", 4))) return 20;
    SocketBaseTags(SBTM_SETVAL(SBTC_ERRNOPTR(sizeof(errno))), (IPTR)&errno, TAG_END);
    if (!find_ll(argv[1], &ll, &idx)) { printf("no link-local on %s\n", argv[1]); return 20; }
    memset(&d, 0, sizeof(d)); d.sin6_len = sizeof(d); d.sin6_family = AF_INET6;
    d.sin6_port = htons(9);
    inet_pton(AF_INET6, argv[2], &d.sin6_addr);
    s = socket(AF_INET6, SOCK_DGRAM, 0);
    marker(&ll, idx, "P:start");
    for (k = 0; k < secs * 2; k++) {
        int r = sendto(s, (char *)"x", 1, 0, (struct sockaddr *)&d, sizeof(d));
        if (k % 2 == 0) {
            route_get(argv[2], gw, sizeof(gw));
            printf("t %d %s%s\n", k / 2, gw, r < 0 ? " (send failed)" : "");
        }
        Delay(25);
    }
    printf("done\n");
    CloseSocket(s);
    CloseLibrary(SocketBase);
    return 0;
}
