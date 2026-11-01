/*
 * udpecho - large UDP datagrams to the host and back (udpbig_probe.py).
 *
 * Usage: udpecho 4|6 IFNAME HOST PORT SIZE...
 * For each SIZE: send a datagram of SIZE patterned bytes, wait up to 3 s
 * for the host's echo, compare. Prints "size=<n> <ok|bad|lost|senderr=<e>>".
 */

#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/bsdsocket.h>
#include <proto/miami.h>        /* if_nametoindex(), inet_pton() */
#include <bsdsocket/socketbasetags.h>
#include <sys/socket.h>
#include <net/if.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

struct Library *SocketBase, *MiamiBase;

int main(int argc, char **argv)
{
    static unsigned char out[9216], in[9216];
    struct sockaddr_storage ss;
    struct timeval tv;
    fd_set r;
    socklen_t len;
    int six, s, i, k, big = 16384;

    if (argc < 6)
        return 20;
    if (!(SocketBase = OpenLibrary((STRPTR)"bsdsocket.library", 4)) ||
            !(MiamiBase = OpenLibrary((STRPTR)"miami.library", 0)))
        return 20;
    SocketBaseTags(SBTM_SETVAL(SBTC_ERRNOPTR(sizeof(errno))), (IPTR)&errno, TAG_END);
    six = argv[1][0] == '6';
    memset(&ss, 0, sizeof(ss));
    if (six) {
        struct sockaddr_in6 *d = (struct sockaddr_in6 *)&ss;

        d->sin6_len = sizeof(*d);
        d->sin6_family = AF_INET6;
        d->sin6_port = htons(atoi(argv[4]));
        inet_pton(AF_INET6, argv[3], &d->sin6_addr);
        d->sin6_scope_id = if_nametoindex(argv[2]);
        len = sizeof(*d);
    } else {
        struct sockaddr_in *d = (struct sockaddr_in *)&ss;

        d->sin_len = sizeof(*d);
        d->sin_family = AF_INET;
        d->sin_port = htons(atoi(argv[4]));
        inet_pton(AF_INET, argv[3], &d->sin_addr);
        len = sizeof(*d);
    }
    s = socket(six ? AF_INET6 : AF_INET, SOCK_DGRAM, 0);
    setsockopt(s, SOL_SOCKET, SO_SNDBUF, &big, sizeof(big));
    setsockopt(s, SOL_SOCKET, SO_RCVBUF, &big, sizeof(big));
    for (k = 5; k < argc; k++) {
        int n = atoi(argv[k]), got;

        for (i = 0; i < n; i++)
            out[i] = (unsigned char)(i * 13 + n);
        if (sendto(s, out, n, 0, (struct sockaddr *)&ss, len) != n) {
            printf("size=%d senderr=%d\n", n, errno);
            continue;
        }
        FD_ZERO(&r);
        FD_SET(s, &r);
        tv.tv_sec = 3;
        tv.tv_usec = 0;
        if (WaitSelect(s + 1, &r, NULL, NULL, &tv, NULL) <= 0) {
            printf("size=%d lost\n", n);
            continue;
        }
        got = recv(s, in, sizeof(in), 0);
        printf("size=%d %s\n", n, got == n && memcmp(in, out, n) == 0 ? "ok" : "bad");
    }
    CloseSocket(s);
    CloseLibrary(MiamiBase);
    CloseLibrary(SocketBase);
    return 0;
}
