/*
 * pmtu_expiry - the same link-local destination on two links, with the
 * path MTU's real expiry (600 s, RFC 8201 section 4): a Packet Too Big by
 * eth0 puts 1400 on a host route on eth0; after its expiry the route is
 * gone, and one by eth1 puts 1300 on a host route on eth1. The helpers are
 * cunit-net-pmtu6's (AROS developer/debug/test/net/socket).
 */
#define __CONFIG_ROADSHOW__
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/socket.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <net/if_dl.h>
#include <net/route.h>
#include <netinet/in.h>
#include <netinet/in_var.h>
#include <netinet/ip6.h>
#include <netinet/icmp6.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>

struct Library *SocketBase;
#define CU_ASSERT(x) ((void)0)
static int sock_wait(int s, int w, int secs)
{
    fd_set r; struct timeval tv;
    tv.tv_sec = secs; tv.tv_usec = 0;
    (void)w; FD_ZERO(&r); FD_SET(s, &r);
    return WaitSelect(s + 1, &r, NULL, NULL, &tv, NULL);
}
static const char *ifname = "eth0";
static unsigned ifindex, ifindex2;
static struct in6_addr linklocal, linklocal2;
static int route_index;
#define GW      "fe80::4d54:a"          /* only for route()'s message */
#define LL_A    "fe80::4d54:c"          /* a link-local neighbour; nobody has it */
#define ROUNDUP(a) ((a) > 0 ? (1 + (((a) - 1) | (sizeof(long) - 1))) : sizeof(long))
static void sa6(struct sockaddr_in6 *a, const char *addr)
{
    bzero(a, sizeof(*a));
    a->sin6_len = sizeof(*a);
    a->sin6_family = AF_INET6;
    if (addr)
        inet_pton(AF_INET6, (char *)addr, &a->sin6_addr);
}
static int route(int type, const char *dst, int plen)
{
    long buf[512 / sizeof(long)];       /* aligned for the sockaddrs */
    struct rt_msghdr *h = (struct rt_msghdr *)buf;
    struct sockaddr_in6 *sa;
    char *p;
    int s, r;

    s = socket(PF_ROUTE, SOCK_RAW, 0);
    if (s < 0)
        return -1;
    bzero(buf, sizeof(buf));
    h->rtm_version = RTM_VERSION;
    h->rtm_type = type;
    h->rtm_flags = RTF_UP | RTF_GATEWAY | (plen == 128 ? RTF_HOST : RTF_STATIC);
    h->rtm_addrs = RTA_DST | RTA_GATEWAY | (plen == 128 ? 0 : RTA_NETMASK);
    h->rtm_seq = 1;
    p = (char *)(h + 1);
    sa = (struct sockaddr_in6 *)p; sa6(sa, dst); p += ROUNDUP(sizeof(*sa));
    sa = (struct sockaddr_in6 *)p; sa6(sa, GW);  p += ROUNDUP(sizeof(*sa));
    if (plen < 128) {
        int i;

        sa = (struct sockaddr_in6 *)p; sa6(sa, NULL);
        for (i = 0; i < plen / 8; i++)
            sa->sin6_addr.s6_addr[i] = 0xff;
        p += ROUNDUP(sizeof(*sa));
    }
    h->rtm_msglen = p - (char *)buf;
    r = send(s, (char *)buf, h->rtm_msglen, 0);
    CloseSocket(s);
    return r < 0 ? -1 : 0;
}
static int route_get(const char *dst, int *flags, struct rt_metrics *rmx)
{
    long buf[512 / sizeof(long)];
    struct rt_msghdr *h = (struct rt_msghdr *)buf;
    struct sockaddr_in6 *sa;
    int s, n = 0;

    s = socket(PF_ROUTE, SOCK_RAW, 0);
    if (s < 0)
        return 0;
    bzero(buf, sizeof(buf));
    h->rtm_version = RTM_VERSION;
    h->rtm_type = RTM_GET;
    h->rtm_addrs = RTA_DST | RTA_IFP;
    h->rtm_seq = 2;
    sa = (struct sockaddr_in6 *)(h + 1);
    sa6(sa, dst);
    h->rtm_msglen = sizeof(*h) + ROUNDUP(sizeof(*sa));
    if (send(s, (char *)buf, h->rtm_msglen, 0) >= 0)
        while (sock_wait(s, 0, 2) > 0) {
            n = recv(s, (char *)buf, sizeof(buf), 0);
            if (n <= 0 || (h->rtm_type == RTM_GET && h->rtm_seq == 2))
                break;
        }
    CloseSocket(s);
    if (n <= 0 || h->rtm_errno != 0)
        return 0;
    *flags = h->rtm_flags;
    *rmx = h->rtm_rmx;
    route_index = 0;
    {
        char *p = (char *)(h + 1), *end = (char *)buf + n;
        int bit;

        for (bit = 1; bit <= RTA_IFA && p < end; bit <<= 1) {
            struct sockaddr *x = (struct sockaddr *)p;

            if (!(h->rtm_addrs & bit))
                continue;
            if (bit == RTA_IFP && x->sa_family == AF_LINK)
                route_index = ((struct sockaddr_dl *)x)->sdl_index;
            p += x->sa_len ? ROUNDUP(x->sa_len) : sizeof(long);
        }
    }
    return 1;
}
static int send_ptb_to(const char *dst, unsigned mtu, int to_ll)
{
    unsigned char pkt[8 + 40 + 8];
    struct icmp6_hdr *h = (struct icmp6_hdr *)pkt;
    struct ip6_hdr *ip6 = (struct ip6_hdr *)(pkt + 8);
    struct in6_addr lo = IN6ADDR_LOOPBACK_INIT;
    struct sockaddr_in6 d;
    int s = socket(AF_INET6, SOCK_RAW, IPPROTO_ICMPV6), r;

    if (s < 0)
        return -1;
    bzero(pkt, sizeof(pkt));
    h->icmp6_type = ICMP6_PACKET_TOO_BIG;
    h->icmp6_mtu = htonl(mtu);
    ip6->ip6_vfc = IPV6_VERSION;
    ip6->ip6_plen = htons(8);
    ip6->ip6_nxt = IPPROTO_UDP;
    ip6->ip6_hlim = 64;
    ip6->ip6_src = lo;
    inet_pton(AF_INET6, (char *)dst, &ip6->ip6_dst);
    sa6(&d, NULL);
    d.sin6_addr = lo;
    if (to_ll == 1) {
        d.sin6_addr = linklocal;
        d.sin6_scope_id = ifindex;
    } else if (to_ll == 2) {
        d.sin6_addr = linklocal2;
        d.sin6_scope_id = ifindex2;
    }
    r = sendto(s, (char *)pkt, sizeof(pkt), 0, (struct sockaddr *)&d, sizeof(d));
    CloseSocket(s);
    Delay(10);                          /* let the stack take it in */
    return r;
}
static unsigned pathmtu(const char *dst, unsigned scope)
{
    struct sockaddr_in6 d;
    struct ip6_mtuinfo mi;
    socklen_t l = sizeof(mi);
    int s = socket(AF_INET6, SOCK_DGRAM, 0);
    unsigned mtu = 0;

    if (s < 0)
        return 0;
    sa6(&d, dst);
    d.sin6_port = htons(9);
    d.sin6_scope_id = scope;
    bzero(&mi, sizeof(mi));
    if (connect(s, (struct sockaddr *)&d, sizeof(d)) == 0 &&
            getsockopt(s, IPPROTO_IPV6, IPV6_PATHMTU, &mi, &l) == 0)
        mtu = mi.ip6m_mtu;
    CloseSocket(s);
    return mtu;
}
static int setup(void)
{
    struct in6_ifreq req[16];
    struct in6_ifconf ifc;
    int s = socket(AF_INET6, SOCK_DGRAM, 0), found = 0;

    if (s < 0)
        return 0;
    bzero(&ifc, sizeof(ifc));
    ifc.ifc6_len = sizeof(req);
    ifc.ifc6_req = req;
    if (IoctlSocket(s, SIOCGLIFADDR, (char *)&ifc) == 0) {
        int i, n = ifc.ifc6_len / sizeof(req[0]);

        for (i = 0; i < n; i++) {
            const char *other = strcmp(ifname, "eth1") ? "eth1" : "eth0";

            if (!IN6_IS_ADDR_LINKLOCAL(&req[i].ifr_ifru.ifru_addr.sin6_addr))
                continue;
            if (strcmp(req[i].ifr_name, ifname) == 0 && !found) {
                linklocal = req[i].ifr_ifru.ifru_addr.sin6_addr;
                found = 1;
            } else if (strcmp(req[i].ifr_name, other) == 0)
                linklocal2 = req[i].ifr_ifru.ifru_addr.sin6_addr;
        }
    }
    if (found) {
        struct ifreq ifr;

        bzero(&ifr, sizeof(ifr));
        snprintf(ifr.ifr_name, sizeof(ifr.ifr_name), "%s", ifname);
        found = IoctlSocket(s, SIOCGIFINDEX, (char *)&ifr) == 0;
        ifindex = ifr.ifr_index;
        bzero(&ifr, sizeof(ifr));
        snprintf(ifr.ifr_name, sizeof(ifr.ifr_name), "%s", strcmp(ifname, "eth1") ? "eth1" : "eth0");
        if (IoctlSocket(s, SIOCGIFINDEX, (char *)&ifr) == 0)
            ifindex2 = ifr.ifr_index;
    }
    CloseSocket(s);
    return found;
}

int main(void)
{
    struct rt_metrics m;
    int f = 0, ok = 1;

    if ((SocketBase = OpenLibrary("bsdsocket.library", 4)) == NULL || !setup() ||
            ifindex2 == 0 || IN6_IS_ADDR_UNSPECIFIED(&linklocal2)) {
        printf("FAIL no two interfaces with link-local addresses\n");
        return 20;
    }
    route(RTM_DELETE, LL_A, 128);
    Delay(25);
    send_ptb_to(LL_A, 1400, 1);
    ok &= route_get(LL_A, &f, &m) && (f & RTF_HOST) && m.rmx_mtu == 1400 && route_index == (int)ifindex;
    printf("A: flags 0x%x mtu %lu index %d (eth0 %u)\n", f, (unsigned long)m.rmx_mtu, route_index, ifindex);
    fflush(stdout);
    Delay(615 * 50);                    /* PMTU_EXPIRE 600 s, and the timer */
    f = 0;
    if (route_get(LL_A, &f, &m) && (f & RTF_HOST)) {
        printf("FAIL A's route still there after its expiry: mtu %lu\n", (unsigned long)m.rmx_mtu);
        ok = 0;
    } else
        printf("A's route gone after its expiry\n");
    send_ptb_to(LL_A, 1300, 2);
    ok &= route_get(LL_A, &f, &m) && (f & RTF_HOST) && m.rmx_mtu == 1300 && route_index == (int)ifindex2;
    printf("B: flags 0x%x mtu %lu index %d (eth1 %u)\n", f, (unsigned long)m.rmx_mtu, route_index, ifindex2);
    ok &= pathmtu(LL_A, ifindex2) == 1300 && pathmtu(LL_A, ifindex) > 1300;
    route(RTM_DELETE, LL_A, 128);
    printf("%s\n", ok ? "PASS" : "FAIL");
    return ok ? 0 : 10;
}
