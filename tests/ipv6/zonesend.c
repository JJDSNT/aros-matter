/*
 * zonesend - UDP datagrams to one link-local address on two links, by
 * turns (tests/ipv6/zone_probe.py): the same address is a different
 * neighbour on each link (RFC 4007 section 6), so each datagram must leave
 * by the link its zone names, to that link's neighbour.
 *
 * Usage: zonesend ADDR IF1 IF2 ROUNDS [tcp]
 * Sends "IF1 n" to ADDR%IF1, then "IF2 n" to ADDR%IF2, ROUNDS times, half
 * a second apart; prints each sendto()'s result. With tcp, each is a TCP
 * connection to port 9999 that sends the message and closes.
 */
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/bsdsocket.h>
#include <proto/miami.h>
#include <sys/socket.h>
#include <net/if.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

struct Library *SocketBase, *MiamiBase;

int main(int argc, char **argv)
{
    struct sockaddr_in6 to;
    char msg[64];
    int s, i, k, n;

    if (argc < 5 || !(SocketBase = OpenLibrary("bsdsocket.library", 4)) ||
            !(MiamiBase = OpenLibrary("miami.library", 0)))
        return 20;
    s = socket(AF_INET6, SOCK_DGRAM, 0);
    for (i = 0; i < atoi(argv[4]); i++) {
        for (k = 2; k <= 3; k++) {
            memset(&to, 0, sizeof(to));
            to.sin6_len = sizeof(to);
            to.sin6_family = AF_INET6;
            to.sin6_port = htons(9999);
            inet_pton(AF_INET6, argv[1], &to.sin6_addr);
            to.sin6_scope_id = if_nametoindex(argv[k]);
            snprintf(msg, sizeof(msg), "%s %d", argv[k], i);
            if (argc > 5 && !strcmp(argv[5], "tcp")) {
                int c = socket(AF_INET6, SOCK_STREAM, 0);

                n = connect(c, (struct sockaddr *)&to, sizeof(to));
                if (n == 0)
                    n = send(c, msg, strlen(msg), 0);
                CloseSocket(c);
            } else
                n = sendto(s, msg, strlen(msg), 0, (struct sockaddr *)&to, sizeof(to));
            printf("send %s zone %u: %d errno %d\n", msg, (unsigned)to.sin6_scope_id, n, n < 0 ? errno : 0);
            Delay(25);
        }
    }
    CloseSocket(s);
    CloseLibrary(MiamiBase);
    CloseLibrary(SocketBase);
    return 0;
}
