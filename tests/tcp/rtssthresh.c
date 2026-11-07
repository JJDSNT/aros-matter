/*
 * rtssthresh - set the ssthresh metric (RTV_SSTHRESH) of the route a
 * connection to a link-local neighbour will use, for the benches: the
 * connection then starts with that ssthresh (tcp_mss()), so its first slow
 * start ends without a loss and without HyStart++ (tests/tcp/ss_probe.py
 * --ssthresh).
 *
 * Usage: rtssthresh IFNAME BYTES NEIGHBOUR [zone]
 * 1. RTM_CHANGE on the link route fe80::/64 of IFNAME;
 * 2. a UDP datagram to NEIGHBOUR, so that neighbour discovery makes its
 *    host route (cloned from the link route);
 * 3. RTM_GET of NEIGHBOUR: the route it uses, its flags and ssthresh;
 * 4. RTM_CHANGE on that host route;
 * 5. RTM_GET again.
 * Each step prints a line.
 */
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/bsdsocket.h>
#include <proto/miami.h>
#include <sys/socket.h>
#include <net/if.h>
#include <net/route.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

struct Library *SocketBase, *MiamiBase;
static unsigned ifindex;

#define ROUNDUP(a) ((a) > 0 ? (1 + (((a) - 1) | (sizeof(long) - 1))) : sizeof(long))

static void sa6(struct sockaddr_in6 *sa, const struct in6_addr *a, unsigned scope)
{
    memset(sa, 0, sizeof(*sa));
    sa->sin6_len = sizeof(*sa);
    sa->sin6_family = AF_INET6;
    sa->sin6_addr = *a;
    sa->sin6_scope_id = scope;
}

/* One routing message: type, dst (with a /64 mask if net), ssthresh (for
 * RTM_CHANGE). Prints send()'s result and the reply the socket gets back
 * (rtm_errno, flags, index, the metrics it says are set, ssthresh, the
 * address it names and its zone). 0 or errno. */
static int rtmsg(const char *what, int type, const struct in6_addr *dst, int net, u_long ssthresh,
                 int *flags, u_long *got)
{
    long buf[512 / sizeof(long)];
    struct rt_msghdr *h = (struct rt_msghdr *)buf;
    char *p;
    int s = socket(PF_ROUTE, SOCK_RAW, 0), n, rc = 0, i;

    if (s < 0)
        return errno;
    memset(buf, 0, sizeof(buf));
    h->rtm_version = RTM_VERSION;
    h->rtm_type = type;
    h->rtm_addrs = RTA_DST | (net ? RTA_NETMASK : 0);
    h->rtm_flags = net ? 0 : RTF_HOST;
    h->rtm_seq = type;
    if (type == RTM_CHANGE) {
        h->rtm_inits = RTV_SSTHRESH;
        h->rtm_rmx.rmx_ssthresh = ssthresh;
    }
    p = (char *)(h + 1);
    sa6((struct sockaddr_in6 *)p, dst, ifindex);
    p += ROUNDUP(sizeof(struct sockaddr_in6));
    if (net) {
        struct in6_addr m;

        memset(&m, 0, sizeof(m));
        for (i = 0; i < 8; i++)
            m.s6_addr[i] = 0xff;
        sa6((struct sockaddr_in6 *)p, &m, 0);
        p += ROUNDUP(sizeof(struct sockaddr_in6));
    }
    h->rtm_msglen = p - (char *)buf;
    n = send(s, (char *)buf, h->rtm_msglen, 0);
    if (n < 0)
        rc = errno;
    printf("%s: send %d errno %d\n", what, n, n < 0 ? errno : 0);
    /* the socket gets its own message back, answered */
    {
        fd_set rf;
        struct timeval tv;

        FD_ZERO(&rf);
        FD_SET(s, &rf);
        tv.tv_sec = 1;
        tv.tv_usec = 0;
        n = WaitSelect(s + 1, &rf, NULL, NULL, &tv, NULL) > 0 ? recv(s, (char *)buf, sizeof(buf), 0) : -1;
    }
    if (n > 0) {
        struct sockaddr_in6 *k = (struct sockaddr_in6 *)(h + 1);
        char a[64] = "?";

        if (k->sin6_family == AF_INET6)
            inet_ntop(AF_INET6, &k->sin6_addr, a, sizeof(a));
        printf("%s: reply type %d errno %d flags 0x%x index %d inits 0x%lx ssthresh %lu dst %s zone %u\n",
               what, h->rtm_type, h->rtm_errno, h->rtm_flags, h->rtm_index,
               (unsigned long)h->rtm_inits, (unsigned long)h->rtm_rmx.rmx_ssthresh, a,
               (unsigned)k->sin6_scope_id);
        if (h->rtm_errno)
            rc = h->rtm_errno;
        if (flags)
            *flags = h->rtm_flags;
        if (got)
            *got = h->rtm_rmx.rmx_ssthresh;
    } else
        printf("%s: no reply\n", what);
    CloseSocket(s);
    return rc;
}

int main(int argc, char **argv)
{
    struct in6_addr link, nb;
    struct sockaddr_in6 to;
    u_long want, got = 0;
    int flags = 0, u;

    if (argc < 4 || !(SocketBase = OpenLibrary("bsdsocket.library", 4)) ||
            !(MiamiBase = OpenLibrary("miami.library", 0)))
        return 20;
    /* link-local routes are keyed with zone 0 (one fe80::/64 for all
     * interfaces, see the G1 notes): the zone goes in the messages only
     * with a 4th argument */
    ifindex = argc > 4 ? if_nametoindex(argv[1]) : 0;
    want = atol(argv[2]);
    inet_pton(AF_INET6, argv[3], &nb);
    memset(&link, 0, sizeof(link));
    link.s6_addr[0] = 0xfe;
    link.s6_addr[1] = 0x80;

    rtmsg("0 get neighbour before", RTM_GET, &nb, 0, 0, &flags, &got);
    rtmsg("1 change fe80::/64", RTM_CHANGE, &link, 1, want, NULL, NULL);
    rtmsg("1 get fe80::/64", RTM_GET, &link, 1, 0, &flags, &got);

    u = socket(AF_INET6, SOCK_DGRAM, 0);
    sa6(&to, &nb, if_nametoindex(argv[1]));
    to.sin6_port = htons(9);
    sendto(u, "x", 1, 0, (struct sockaddr *)&to, sizeof(to));
    CloseSocket(u);
    Delay(50);                          /* neighbour discovery */
    printf("2 udp to %s sent\n", argv[3]);

    rtmsg("3 get neighbour", RTM_GET, &nb, 0, 0, &flags, &got);
    rtmsg("4 change neighbour", RTM_CHANGE, &nb, 0, want, NULL, NULL);
    rtmsg("5 get neighbour", RTM_GET, &nb, 0, 0, &flags, &got);

    CloseLibrary(MiamiBase);
    CloseLibrary(SocketBase);
    return 0;
}
