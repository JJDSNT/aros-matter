/*
 * nd6mem LABEL [IFNAME [del N]] - the IPv6 neighbour cache of IFNAME
 * (default eth0) and AROS's free memory, on one line:
 *   "LABEL rows R flood F lladdr L free BYTES largest BYTES"
 * R: rows GetRouteInfo(AF_INET6, RTF_LLINFO) lists on the interface; F:
 * those of the flood (fe80::a:0:0:N, which tests/ipv6/nd6_mem.py sends
 * Neighbor Solicitations from); L: rows with a link-layer address. With
 * "del N" it first deletes the flood's first N entries (RTM_DELETE with
 * RTF_LLINFO, as ndp -d) and waits a second.
 */
#define __CONFIG_ROADSHOW__     /* GetRouteInfo() */
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/socket.h>
#include <exec/memory.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <net/if_dl.h>
#include <net/route.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct Library *SocketBase;

#define ROUNDUP(a) ((a) > 0 ? (1 + (((a) - 1) | (sizeof(long) - 1))) : sizeof(long))

static void flood_addr(struct in6_addr *a, int n)
{
    memset(a, 0, sizeof(*a));
    a->s6_addr[0] = 0xfe;
    a->s6_addr[1] = 0x80;
    a->s6_addr[9] = 0x0a;
    a->s6_addr[14] = n >> 8;
    a->s6_addr[15] = n;
}

static int is_flood(const struct in6_addr *a)
{
    struct in6_addr f;

    flood_addr(&f, 0);
    return memcmp(a, &f, 14) == 0;
}

static int delete_one(int s, unsigned ifindex, int n)
{
    long buf[256 / sizeof(long)];
    struct rt_msghdr *h = (struct rt_msghdr *)buf;
    struct sockaddr_in6 *dst = (struct sockaddr_in6 *)(h + 1);

    memset(buf, 0, sizeof(buf));
    h->rtm_version = RTM_VERSION;
    h->rtm_type = RTM_DELETE;
    h->rtm_flags = RTF_HOST | RTF_LLINFO;
    h->rtm_addrs = RTA_DST;
    h->rtm_seq = n + 1;
    h->rtm_index = ifindex;
    dst->sin6_len = sizeof(*dst);
    dst->sin6_family = AF_INET6;
    flood_addr(&dst->sin6_addr, n);
    h->rtm_msglen = sizeof(*h) + ROUNDUP(sizeof(*dst));
    return send(s, (char *)buf, h->rtm_msglen, 0) < 0 ? -1 : 0;
}

int main(int argc, char **argv)
{
    const char *ifname = argc > 2 ? argv[2] : "eth0";
    int del = (argc > 4 && strcmp(argv[3], "del") == 0) ? atoi(argv[4]) : 0;
    int rows = 0, flood = 0, stale = 0, i, s;
    unsigned ifindex = 0;
    struct ifreq ifr;
    struct rt_msghdr *buf, *h;
    char *p;

    if (argc < 2) {
        printf("usage: nd6mem LABEL [IFNAME [del N]]\n");
        return 5;
    }
    SocketBase = OpenLibrary("bsdsocket.library", 4);
    if (SocketBase == NULL) {
        printf("%s no bsdsocket.library\n", argv[1]);
        return 10;
    }
    s = socket(AF_INET, SOCK_DGRAM, 0);
    memset(&ifr, 0, sizeof(ifr));
    strncpy(ifr.ifr_name, ifname, sizeof(ifr.ifr_name) - 1);
    if (s >= 0 && IoctlSocket(s, SIOCGIFINDEX, (char *)&ifr) == 0)
        ifindex = ifr.ifr_index;
    if (s >= 0)
        CloseSocket(s);

    if (del > 0) {
        s = socket(PF_ROUTE, SOCK_RAW, 0);
        for (i = 0; s >= 0 && i < del; i++)
            delete_one(s, ifindex, i);
        if (s >= 0)
            CloseSocket(s);
        Delay(50);
    }

    buf = GetRouteInfo(AF_INET6, RTF_LLINFO);
    if (buf != NULL) {
        for (p = (char *)buf; (h = (struct rt_msghdr *)p)->rtm_msglen != 0; p += h->rtm_msglen) {
            struct sockaddr_in6 *d = (struct sockaddr_in6 *)(h + 1);
            struct sockaddr_dl *g = (struct sockaddr_dl *)((char *)d + ROUNDUP(d->sin6_len));

            if (!(h->rtm_flags & RTF_LLINFO) || d->sin6_family != AF_INET6 ||
                    h->rtm_index != ifindex)
                continue;
            rows++;
            if (is_flood(&d->sin6_addr))
                flood++;
            if (g->sdl_family == AF_LINK && g->sdl_alen != 0)
                stale++;
        }
        FreeRouteInfo(buf);
    }
    printf("%s rows %d flood %d lladdr %d free %lu largest %lu\n", argv[1], rows, flood, stale,
           (unsigned long)AvailMem(MEMF_ANY), (unsigned long)AvailMem(MEMF_ANY | MEMF_LARGEST));
    CloseLibrary(SocketBase);
    return 0;
}
