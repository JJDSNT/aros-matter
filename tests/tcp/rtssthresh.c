/*
 * rtssthresh - set the ssthresh metric (RTV_SSTHRESH) of the link-local
 * route fe80::/64 on an interface, for the benches: a connection to a
 * neighbour then starts with that ssthresh (tcp_mss(), the neighbour's
 * route clones the link route's metrics), so its first slow start ends
 * without a loss and without HyStart++ (tests/tcp/ss_probe.py --pre).
 *
 * Usage: rtssthresh IFNAME BYTES
 * Prints "rtssthresh <ifname> <bytes> rc=<0|errno>".
 */
#include <proto/exec.h>
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

#define ROUNDUP(a) ((a) > 0 ? (1 + (((a) - 1) | (sizeof(long) - 1))) : sizeof(long))

int main(int argc, char **argv)
{
    long buf[512 / sizeof(long)];
    struct rt_msghdr *h = (struct rt_msghdr *)buf;
    struct sockaddr_in6 *sa;
    char *p;
    int s, rc = 0, i;

    if (argc < 3 || !(SocketBase = OpenLibrary("bsdsocket.library", 4)) ||
            !(MiamiBase = OpenLibrary("miami.library", 0)))
        return 20;
    s = socket(PF_ROUTE, SOCK_RAW, 0);
    memset(buf, 0, sizeof(buf));
    h->rtm_version = RTM_VERSION;
    h->rtm_type = RTM_CHANGE;
    h->rtm_addrs = RTA_DST | RTA_NETMASK;
    h->rtm_seq = 1;
    h->rtm_inits = RTV_SSTHRESH;
    h->rtm_rmx.rmx_ssthresh = atol(argv[2]);
    p = (char *)(h + 1);
    sa = (struct sockaddr_in6 *)p;
    sa->sin6_len = sizeof(*sa);
    sa->sin6_family = AF_INET6;
    sa->sin6_addr.s6_addr[0] = 0xfe;
    sa->sin6_addr.s6_addr[1] = 0x80;
    sa->sin6_scope_id = if_nametoindex(argv[1]);
    p += ROUNDUP(sizeof(*sa));
    sa = (struct sockaddr_in6 *)p;
    sa->sin6_len = sizeof(*sa);
    sa->sin6_family = AF_INET6;
    for (i = 0; i < 8; i++)
        sa->sin6_addr.s6_addr[i] = 0xff;
    p += ROUNDUP(sizeof(*sa));
    h->rtm_msglen = p - (char *)buf;
    if (s < 0 || send(s, (char *)buf, h->rtm_msglen, 0) < 0)
        rc = errno;
    printf("rtssthresh %s %s rc=%d\n", argv[1], argv[2], rc);
    if (s >= 0)
        CloseSocket(s);
    CloseLibrary(MiamiBase);
    CloseLibrary(SocketBase);
    return rc ? 5 : 0;
}
