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


static int lookup(const char *dst, int *flags)
{
    union { struct rt_msghdr h; char b[512]; } msg; struct sockaddr_in6 *sa; int s, n = 0; static int seq;
    if ((s = socket(PF_ROUTE, SOCK_RAW, 0)) < 0) return -1;
    memset(&msg, 0, sizeof(msg)); msg.h.rtm_version = RTM_VERSION; msg.h.rtm_type = RTM_GET;
    msg.h.rtm_addrs = RTA_DST; msg.h.rtm_seq = ++seq;
    sa = (struct sockaddr_in6 *)(&msg.h + 1); sa->sin6_len = sizeof(*sa); sa->sin6_family = AF_INET6;
    inet_pton(AF_INET6, (char *)dst, &sa->sin6_addr);
    msg.h.rtm_msglen = sizeof(msg.h) + ROUNDUP(sizeof(*sa));
    if (send(s, (char *)&msg, msg.h.rtm_msglen, 0) < 0) { CloseSocket(s); return 0; }
    while (waitread(s, 2000)) { n = recv(s, (char *)&msg, sizeof(msg), 0); if (n <= 0 || msg.h.rtm_seq == seq) break; }
    CloseSocket(s); *flags = msg.h.rtm_flags;
    return n > 0 && msg.h.rtm_errno == 0;
}
static int addr6(int add, const char *a)
{
    int s = socket(AF_INET6, SOCK_DGRAM, 0), r, i;
    if (add) { struct in6_aliasreq f; memset(&f, 0, sizeof(f)); strcpy(f.ifra_name, "eth0");
        f.ifra_addr.sin6_len = sizeof(f.ifra_addr); f.ifra_addr.sin6_family = AF_INET6; inet_pton(AF_INET6, (char *)a, &f.ifra_addr.sin6_addr);
        f.ifra_prefixmask.sin6_len = sizeof(f.ifra_prefixmask); f.ifra_prefixmask.sin6_family = AF_INET6;
        for (i = 0; i < 8; i++) f.ifra_prefixmask.sin6_addr.s6_addr[i] = 0xff;
        f.ifra_lifetime.ia6t_vltime = f.ifra_lifetime.ia6t_pltime = 0xffffffffU;
        r = IoctlSocket(s, SIOCAIFADDR_IN6, (char *)&f);
    } else { struct in6_ifreq q; memset(&q, 0, sizeof(q)); strcpy(q.ifr_name, "eth0");
        q.ifr_ifru.ifru_addr.sin6_len = sizeof(struct sockaddr_in6); q.ifr_ifru.ifru_addr.sin6_family = AF_INET6;
        inet_pton(AF_INET6, (char *)a, &q.ifr_ifru.ifru_addr.sin6_addr); r = IoctlSocket(s, SIOCDIFADDR_IN6, (char *)&q); }
    CloseSocket(s); return r;
}
static void show(const char *what, const char *dst)
{ int f = 0, ok = lookup(dst, &f); printf("%-38s %-22s %s flags=0x%x\n", what, dst, ok ? "FOUND" : "none", ok ? f : 0); }
int main(void)
{
    SocketBase = OpenLibrary((STRPTR)"bsdsocket.library", 4);
    SocketBaseTags(SBTM_SETVAL(SBTC_ERRNOPTR(sizeof(errno))), (IPTR)&errno, TAG_END);
    Delay(6 * 50);                                   /* host advertises a default router */
    show("default route, key ::", "::");
    show("default route, other destination", "2001:db8:ffff::1");
    printf("add fd00:4d54:77::1/64 rc=%d\n", addr6(1, "fd00:4d54:77::1"));
    Delay(50);
    show("prefix route while address exists", "fd00:4d54:77::2");
    printf("delete fd00:4d54:77::1 rc=%d\n", addr6(0, "fd00:4d54:77::1"));
    Delay(50);
    show("prefix route after address deleted", "fd00:4d54:77::2");
    CloseLibrary(SocketBase);
    return 0;
}
