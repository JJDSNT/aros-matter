/*
 * bindgone - AROS side of the "interface gone" bench (tests/ipv6/bindgone.py).
 *
 * Usage: bindgone IFNAME
 * Binds sockets to IFNAME - UDP/IPv4 and UDP/IPv6 with SO_BINDTODEVICE, a
 * UDP/IPv6 socket connected in its zone, a TCP/IPv6 connection to itself
 * over its link-local address, TCP listeners of both families with
 * SO_BINDTODEVICE - then takes IFNAME's line out of
 * SYS:System/Network/AROSTCP/db/interfaces and has the stack reload, which
 * removes the interface. Afterwards it prints, per socket, what a send (or
 * for TCP, a receive; -2: nothing within 2 s; for a listener, a connect()
 * to it over the loopback) gives: "<name> rc=<n> errno=<e>". Then it binds the
 * UDP/IPv6 socket to lo0 and sends again ("rebind ...").
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
#include <netinet/in.h>
#include <netinet/in_var.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

struct Library *SocketBase;

#define DB "SYS:System/Network/AROSTCP/db/interfaces"

static int find_ll(const char *ifn, struct in6_addr *ll, unsigned *idx)
{
    struct ifreq ifr; struct in6_ifreq req[16]; struct in6_ifconf ifc;
    int s = socket(AF_INET6, SOCK_DGRAM, 0), i, n, ok = 0;

    memset(&ifr, 0, sizeof(ifr)); strncpy(ifr.ifr_name, ifn, sizeof(ifr.ifr_name) - 1);
    if (IoctlSocket(s, SIOCGIFINDEX, (char *)&ifr) == 0) *idx = ifr.ifr_index;
    memset(req, 0, sizeof(req)); memset(&ifc, 0, sizeof(ifc));
    ifc.ifc6_len = sizeof(req); ifc.ifc6_req = req;
    if (IoctlSocket(s, SIOCGLIFADDR, (char *)&ifc) == 0)
        for (n = ifc.ifc6_len / sizeof(req[0]), i = 0; i < n; i++)
            if (!strcmp(req[i].ifr_name, ifn) && IN6_IS_ADDR_LINKLOCAL(&req[i].ifr_ifru.ifru_addr.sin6_addr)) {
                *ll = req[i].ifr_ifru.ifru_addr.sin6_addr; ok = 1;
            }
    CloseSocket(s);
    return ok;
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

/* Take the lines for interface ifn out of the interface database. */
static int drop_interface(const char *ifn)
{
    static char buf[16384], out[16384];
    FILE *f = fopen(DB, "r");
    size_t n, o = 0, l = strlen(ifn);
    char *p, *e;

    if (!f) return -1;
    n = fread(buf, 1, sizeof(buf) - 1, f);
    fclose(f);
    buf[n] = 0;
    for (p = buf; *p; p = e) {
        e = strchr(p, '\n');
        e = e ? e + 1 : p + strlen(p);
        if (!(strncmp(p, ifn, l) == 0 && (p[l] == ' ' || p[l] == '\t'))) {
            memcpy(out + o, p, e - p);
            o += e - p;
        }
    }
    if (!(f = fopen(DB, "w"))) return -1;
    fwrite(out, 1, o, f);
    fclose(f);
    return 0;
}

static int bindtodevice(int s, const char *ifn)
{
    return setsockopt(s, SOL_SOCKET, SO_BINDTODEVICE, (char *)ifn, strlen(ifn));
}

static void report(const char *name, int rc)
{
    printf("%s rc=%d errno=%d\n", name, rc, rc < 0 ? errno : 0);
}

int main(int argc, char **argv)
{
    struct in6_addr ll; unsigned idx = 0;
    struct sockaddr_in a4;
    struct sockaddr_in6 a6, d6;
    socklen_t len;
    int u4, u6, z6, tl, tc, ta, r, l4, l6, cs;
    struct sockaddr_in b4;
    struct sockaddr_in6 b6;
    fd_set fs; struct timeval tv;
    char c;

    if (argc < 2) { printf("usage: bindgone IFNAME\n"); return 20; }
    if (!(SocketBase = OpenLibrary((STRPTR)"bsdsocket.library", 4))) return 20;
    SocketBaseTags(SBTM_SETVAL(SBTC_ERRNOPTR(sizeof(errno))), (IPTR)&errno, TAG_END);
    if (!find_ll(argv[1], &ll, &idx)) { printf("no link-local on %s\n", argv[1]); return 20; }

    u4 = socket(AF_INET, SOCK_DGRAM, 0);
    u6 = socket(AF_INET6, SOCK_DGRAM, 0);
    z6 = socket(AF_INET6, SOCK_DGRAM, 0);
    report("bind u4", bindtodevice(u4, argv[1]));
    report("bind u6", bindtodevice(u6, argv[1]));
    memset(&d6, 0, sizeof(d6)); d6.sin6_len = sizeof(d6); d6.sin6_family = AF_INET6;
    d6.sin6_addr = ll; d6.sin6_scope_id = idx; d6.sin6_port = htons(9);
    report("connect z6", connect(z6, (struct sockaddr *)&d6, sizeof(d6)));

    /* a TCP connection to ourselves over the link-local address */
    tl = socket(AF_INET6, SOCK_STREAM, 0);
    tc = socket(AF_INET6, SOCK_STREAM, 0);
    d6.sin6_port = htons(7777);
    report("listen t", (bind(tl, (struct sockaddr *)&d6, sizeof(d6)) == 0) ? listen(tl, 1) : -1);
    report("connect t", connect(tc, (struct sockaddr *)&d6, sizeof(d6)));
    len = sizeof(a6);
    ta = accept(tl, (struct sockaddr *)&a6, &len);
    report("accept t", ta);

    /* TCP listeners on both families, bound to the interface */
    l4 = socket(AF_INET, SOCK_STREAM, 0);
    l6 = socket(AF_INET6, SOCK_STREAM, 0);
    memset(&b4, 0, sizeof(b4)); b4.sin_len = sizeof(b4); b4.sin_family = AF_INET; b4.sin_port = htons(7778);
    memset(&b6, 0, sizeof(b6)); b6.sin6_len = sizeof(b6); b6.sin6_family = AF_INET6; b6.sin6_port = htons(7779);
    report("listen l4", (bindtodevice(l4, argv[1]) == 0 && bind(l4, (struct sockaddr *)&b4, sizeof(b4)) == 0) ? listen(l4, 2) : -1);
    report("listen l6", (bindtodevice(l6, argv[1]) == 0 && bind(l6, (struct sockaddr *)&b6, sizeof(b6)) == 0) ? listen(l6, 2) : -1);

    memset(&a4, 0, sizeof(a4)); a4.sin_len = sizeof(a4); a4.sin_family = AF_INET;
    a4.sin_port = htons(9); a4.sin_addr.s_addr = inet_addr("192.168.167.1");   /* the host on IFNAME */
    memset(&a6, 0, sizeof(a6)); a6.sin6_len = sizeof(a6); a6.sin6_family = AF_INET6;
    a6.sin6_port = htons(9); a6.sin6_addr.s6_addr[15] = 1;      /* ::1 */
    report("before u4", sendto(u4, "x", 1, 0, (struct sockaddr *)&a4, sizeof(a4)));

    report("drop", drop_interface(argv[1]));
    report("reload", net_reload());
    Delay(3 * 50);
    {
        unsigned i2 = 0; struct in6_addr x;
        printf("gone %d\n", !find_ll(argv[1], &x, &i2));
    }

    report("after u4", sendto(u4, "x", 1, 0, (struct sockaddr *)&a4, sizeof(a4)));
    report("after u6", sendto(u6, "x", 1, 0, (struct sockaddr *)&a6, sizeof(a6)));
    report("after z6", send(z6, "x", 1, 0));
    FD_ZERO(&fs); FD_SET(tc, &fs); tv.tv_sec = 2; tv.tv_usec = 0;
    r = WaitSelect(tc + 1, &fs, NULL, NULL, &tv, NULL);
    report("after t", r > 0 ? recv(tc, &c, 1, 0) : -2);

    b4.sin_addr.s_addr = inet_addr("127.0.0.1");
    cs = socket(AF_INET, SOCK_STREAM, 0);
    report("after l4", connect(cs, (struct sockaddr *)&b4, sizeof(b4)));
    CloseSocket(cs);
    b6.sin6_addr.s6_addr[15] = 1;       /* ::1 */
    cs = socket(AF_INET6, SOCK_STREAM, 0);
    report("after l6", connect(cs, (struct sockaddr *)&b6, sizeof(b6)));
    CloseSocket(cs);

    report("rebind u6", bindtodevice(u6, "lo0"));
    report("again u6", sendto(u6, "x", 1, 0, (struct sockaddr *)&a6, sizeof(a6)));
    printf("done\n");
    CloseSocket(u4); CloseSocket(u6); CloseSocket(z6);
    CloseSocket(tc); CloseSocket(tl); if (ta >= 0) CloseSocket(ta);
    CloseSocket(l4); CloseSocket(l6);
    CloseLibrary(SocketBase);
    return 0;
}
