/*
 * tcpserve - AROS as the server of one TCP connection from the host, for
 * the benches where the host opens the connection (ecn_probe.py).
 *
 * Usage: tcpserve 4|6 PORT send|recv BYTES
 *   send   accept, send BYTES, close
 *   recv   accept, read until the host closes
 * Waits up to 60 s for the connection.
 */

#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/bsdsocket.h>
#include <bsdsocket/socketbasetags.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

struct Library *SocketBase;

int main(int argc, char **argv)
{
    static char buf[16384];
    struct sockaddr_in6 a6;
    struct sockaddr_in a4;
    struct timeval tv;
    fd_set r;
    long total, done = 0;
    int l, c, on = 1, six;

    if (argc < 5) {
        printf("usage: tcpserve 4|6 PORT send|recv BYTES\n");
        return 20;
    }
    if (!(SocketBase = OpenLibrary((STRPTR)"bsdsocket.library", 4)))
        return 20;
    SocketBaseTags(SBTM_SETVAL(SBTC_ERRNOPTR(sizeof(errno))), (IPTR)&errno, TAG_END);
    six = argv[1][0] == '6';
    total = atol(argv[4]);
    memset(buf, 'x', sizeof(buf));

    l = socket(six ? AF_INET6 : AF_INET, SOCK_STREAM, 0);
    setsockopt(l, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on));
    if (six) {
        memset(&a6, 0, sizeof(a6));
        a6.sin6_len = sizeof(a6);
        a6.sin6_family = AF_INET6;
        a6.sin6_port = htons(atoi(argv[2]));
        c = bind(l, (struct sockaddr *)&a6, sizeof(a6));
    } else {
        memset(&a4, 0, sizeof(a4));
        a4.sin_len = sizeof(a4);
        a4.sin_family = AF_INET;
        a4.sin_port = htons(atoi(argv[2]));
        c = bind(l, (struct sockaddr *)&a4, sizeof(a4));
    }
    if (l < 0 || c != 0 || listen(l, 1) != 0) {
        printf("listen failed: errno %d\n", errno);
        return 10;
    }
    FD_ZERO(&r);
    FD_SET(l, &r);
    tv.tv_sec = 60;
    tv.tv_usec = 0;
    if (WaitSelect(l + 1, &r, NULL, NULL, &tv, NULL) <= 0 || (c = accept(l, NULL, NULL)) < 0) {
        printf("no connection\n");
        CloseSocket(l);
        return 10;
    }
    if (!strcmp(argv[3], "send")) {
        while (done < total) {
            int n = send(c, buf, total - done < (long)sizeof(buf) ? (int)(total - done) : (int)sizeof(buf), 0);
            if (n <= 0) {
                printf("send failed at %ld: errno %d\n", done, errno);
                break;
            }
            done += n;
        }
    } else {
        int n;

        while ((n = recv(c, buf, sizeof(buf), 0)) > 0)
            done += n;
    }
    CloseSocket(c);
    CloseSocket(l);
    printf("%s done %ld\n", argv[3], done);
    CloseLibrary(SocketBase);
    return 0;
}
