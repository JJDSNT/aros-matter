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
 */

#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/bsdsocket.h>
#include <proto/miami.h>        /* if_nametoindex(), inet_pton() */
#include <bsdsocket/socketbasetags.h>
#include <sys/socket.h>
#include <net/if.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

struct Library *SocketBase, *MiamiBase;
static unsigned g_idx;
static struct in6_addr g_host;

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
