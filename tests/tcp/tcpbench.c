/*
 * tcpbench - the AROS side of the TCP-on-the-wire bench (tests/tcp/run_tcp.py).
 *
 * AROS is always the client of the Linux host over the tap, on IPv6 (as
 * Matter uses it). The host side shapes the link with tc and reads what
 * happened from a capture; this program only drives the connections.
 *
 * Usage: tcpbench IFNAME HOST-LL MODE PORT [ARG]
 *   connect PORT N     N short connections (SYN options, ports, ISNs)
 *   send PORT BYTES    send BYTES and close (loss recovery)
 *   unread PORT        the host sends; close without reading (RST or FIN)
 *   stall PORT         send 100 bytes while the host drops everything (RTO)
 *   keepalive PORT IDLE INTVL CNT [UTO]
 *                      keepalive on (seconds, probes; UTO in ms), then wait
 *                      for the connection to fail
 *   uto PORT MS        TCP_USER_TIMEOUT, then send until the connection fails
 *   zerowin PORT MS    TCP_USER_TIMEOUT, fill a peer that never reads, wait
 *                      for the connection to fail
 * The last three print "<mode> done ms=<since connect> wait=<since the
 * window closed, zerowin> errno=<e>".
 */

#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/bsdsocket.h>
#include <proto/miami.h>        /* if_nametoindex(), inet_pton() */
#include <bsdsocket/socketbasetags.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

/* the bench's toolchain headers may predate these (bsdsocket 5.24) */
#ifndef TCP_KEEPIDLE
#define TCP_KEEPINIT        128
#define TCP_KEEPIDLE        256
#define TCP_KEEPINTVL       512
#define TCP_KEEPCNT         1024
#endif
#ifndef TCP_USER_TIMEOUT
#define TCP_USER_TIMEOUT    18
#endif

struct Library *SocketBase, *MiamiBase;
static unsigned g_idx;
static struct in6_addr g_host;

/* milliseconds since some fixed time */
static long now_ms(void)
{
    struct DateStamp ds;

    DateStamp(&ds);
    return ((ds.ds_Days * 1440L + ds.ds_Minute) * 60L) * 1000L + ds.ds_Tick * (1000 / TICKS_PER_SECOND);
}

static int soerror(int s)
{
    int e = 0;
    socklen_t l = sizeof(e);

    getsockopt(s, SOL_SOCKET, SO_ERROR, &e, &l);
    return e;
}

static int tcp_connect(int port)
{
    struct sockaddr_in6 a;
    int s = socket(AF_INET6, SOCK_STREAM, 0);

    if (s < 0)
        return -1;
    memset(&a, 0, sizeof(a));
    a.sin6_len = sizeof(a);
    a.sin6_family = AF_INET6;
    a.sin6_port = htons(port);
    a.sin6_addr = g_host;
    a.sin6_scope_id = g_idx;
    if (connect(s, (struct sockaddr *)&a, sizeof(a)) != 0) {
        printf("connect %d failed: errno %d\n", port, errno);
        CloseSocket(s);
        return -1;
    }
    return s;
}

int main(int argc, char **argv)
{
    static char buf[16384];
    const char *mode;
    int port, s, i;

    if (argc < 5) {
        printf("usage: tcpbench IFNAME HOST-LL MODE PORT [ARG]\n");
        return 20;
    }
    if (!(SocketBase = OpenLibrary((STRPTR)"bsdsocket.library", 4)))
        return 20;
    SocketBaseTags(SBTM_SETVAL(SBTC_ERRNOPTR(sizeof(errno))), (IPTR)&errno, TAG_END);
    if (!(MiamiBase = OpenLibrary((STRPTR)"miami.library", 0)))
        return 20;
    g_idx = if_nametoindex(argv[1]);
    inet_pton(AF_INET6, argv[2], &g_host);
    mode = argv[3];
    port = atoi(argv[4]);
    memset(buf, 'x', sizeof(buf));

    if (!strcmp(mode, "connect")) {
        int n = argc > 5 ? atoi(argv[5]) : 10;
        for (i = 0; i < n; i++) {
            if ((s = tcp_connect(port)) < 0)
                break;
            send(s, "c", 1, 0);
            CloseSocket(s);
            Delay(10);
        }
        printf("connect done %d\n", i);
    } else if (!strcmp(mode, "send")) {
        long total = argc > 5 ? atol(argv[5]) : 1000000, sent = 0;
        if ((s = tcp_connect(port)) >= 0) {
            while (sent < total) {
                int n = send(s, buf, total - sent < (long)sizeof(buf) ? (int)(total - sent) : (int)sizeof(buf), 0);
                if (n <= 0) {
                    printf("send failed at %ld: errno %d\n", sent, errno);
                    break;
                }
                sent += n;
            }
            shutdown(s, 1);
            while (recv(s, buf, sizeof(buf), 0) > 0)
                ;
            CloseSocket(s);
        }
        printf("send done %ld\n", sent);
    } else if (!strcmp(mode, "unread")) {
        if ((s = tcp_connect(port)) >= 0) {
            Delay(2 * 50);          /* the host's data arrives and stays unread */
            CloseSocket(s);
        }
        printf("unread done\n");
    } else if (!strcmp(mode, "keepalive") && argc > 7) {
        long t0 = now_ms();
        int on = 1, v, e = 0;
        if ((s = tcp_connect(port)) >= 0) {
            setsockopt(s, SOL_SOCKET, SO_KEEPALIVE, &on, sizeof(on));
            v = atoi(argv[5]); setsockopt(s, IPPROTO_TCP, TCP_KEEPIDLE, &v, sizeof(v));
            v = atoi(argv[6]); setsockopt(s, IPPROTO_TCP, TCP_KEEPINTVL, &v, sizeof(v));
            v = atoi(argv[7]); setsockopt(s, IPPROTO_TCP, TCP_KEEPCNT, &v, sizeof(v));
            if (argc > 8) {
                v = atoi(argv[8]);
                setsockopt(s, IPPROTO_TCP, TCP_USER_TIMEOUT, &v, sizeof(v));
            }
            {
                int g[4] = { -1, -1, -1, -1 };
                socklen_t gl = sizeof(int);
                getsockopt(s, IPPROTO_TCP, TCP_KEEPIDLE, &g[0], &gl);
                getsockopt(s, IPPROTO_TCP, TCP_KEEPINTVL, &g[1], &gl);
                getsockopt(s, IPPROTO_TCP, TCP_KEEPCNT, &g[2], &gl);
                getsockopt(s, IPPROTO_TCP, TCP_USER_TIMEOUT, &g[3], &gl);
                printf("keepalive set idle=%d intvl=%d cnt=%d uto=%d\n", g[0], g[1], g[2], g[3]);
            }
            if (recv(s, buf, sizeof(buf), 0) < 0)
                e = errno;
            CloseSocket(s);
        }
        printf("keepalive done ms=%ld wait=0 errno=%d\n", now_ms() - t0, e);
    } else if (!strcmp(mode, "uto") && argc > 5) {
        long t0 = now_ms();
        int v = atoi(argv[5]), e = 0;
        if ((s = tcp_connect(port)) >= 0) {
            setsockopt(s, IPPROTO_TCP, TCP_USER_TIMEOUT, &v, sizeof(v));
            while (now_ms() - t0 < 600000L) {
                if (send(s, buf, 1000, 0) < 0) {
                    e = soerror(s);     /* why: EPIPE comes first on send */
                    if (!e)
                        e = errno;
                    break;
                }
                Delay(10);
            }
            CloseSocket(s);
        }
        printf("uto done ms=%ld wait=0 errno=%d\n", now_ms() - t0, e);
    } else if (!strcmp(mode, "zerowin") && argc > 5) {
        long t0 = now_ms(), t1 = 0;
        int v = atoi(argv[5]), e = 0;
        long nb = 1;
        if ((s = tcp_connect(port)) >= 0) {
            setsockopt(s, IPPROTO_TCP, TCP_USER_TIMEOUT, &v, sizeof(v));
            IoctlSocket(s, FIONBIO, (char *)&nb);
            while (!e && now_ms() - t0 < 120000L) {
                if (send(s, buf, sizeof(buf), 0) < 0) {
                    if (errno != EWOULDBLOCK)
                        e = errno;
                    else if (!t1)
                        t1 = now_ms();
                    Delay(5);
                } else
                    t1 = 0;     /* still moving */
                if (!e)
                    e = soerror(s);
            }
            CloseSocket(s);
        }
        printf("zerowin done ms=%ld wait=%ld errno=%d\n", now_ms() - t0, t1 ? now_ms() - t1 : -1, e);
    } else if (!strcmp(mode, "stall")) {
        if ((s = tcp_connect(port)) >= 0) {
            Delay(2 * 50);          /* the host starts dropping everything */
            send(s, buf, 100, 0);
            Delay(12 * 50);         /* retransmissions while dropped, then recovery */
            CloseSocket(s);
        }
        printf("stall done\n");
    }
    CloseLibrary(MiamiBase);
    CloseLibrary(SocketBase);
    return 0;
}
