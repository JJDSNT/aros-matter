/*
 * tcp4send ADDR PORT BYTES: connect to ADDR:PORT over IPv4 and send BYTES
 * bytes; prints "send done N". For the IPv4 path MTU probe (pmtud_probe.py
 * --ipv4).
 */
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/bsdsocket.h>
#include <bsdsocket/socketbasetags.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

struct Library *SocketBase;

int main(int argc, char **argv)
{
    static char buf[16384];
    struct sockaddr_in d;
    long total, sent = 0;
    int s;

    if (argc < 4 || !(SocketBase = OpenLibrary((STRPTR)"bsdsocket.library", 4)))
        return 20;
    SocketBaseTags(SBTM_SETVAL(SBTC_ERRNOPTR(sizeof(errno))), (IPTR)&errno, TAG_END);
    total = atol(argv[3]);
    memset(&d, 0, sizeof(d));
    d.sin_len = sizeof(d);
    d.sin_family = AF_INET;
    d.sin_port = htons(atoi(argv[2]));
    d.sin_addr.s_addr = inet_addr(argv[1]);
    memset(buf, 'x', sizeof(buf));
    s = socket(AF_INET, SOCK_STREAM, 0);
    if (s < 0 || connect(s, (struct sockaddr *)&d, sizeof(d)) != 0) {
        printf("connect failed: errno %d\n", errno);
    } else {
        while (sent < total) {
            long n = send(s, buf, total - sent < (long)sizeof(buf) ? total - sent : (long)sizeof(buf), 0);
            if (n <= 0)
                break;
            sent += n;
        }
    }
    printf("send done %ld\n", sent);
    if (s >= 0)
        CloseSocket(s);
    CloseLibrary(SocketBase);
    return 0;
}
