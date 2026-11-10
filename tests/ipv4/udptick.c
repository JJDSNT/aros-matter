/*
 * udptick - a UDP datagram to HOST:PORT every 200 ms for SECS seconds, its
 * text the tick number (tests/ipv4/arp_stale_probe.py).
 *
 * Usage: udptick HOST-IPV4 PORT SECS
 */
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/bsdsocket.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct Library *SocketBase;

int main(int argc, char **argv)
{
    struct sockaddr_in a;
    char buf[32];
    long i, n;
    int s;

    if (argc < 4 || !(SocketBase = OpenLibrary("bsdsocket.library", 4)))
        return 20;
    s = socket(AF_INET, SOCK_DGRAM, 0);
    memset(&a, 0, sizeof(a));
    a.sin_len = sizeof(a);
    a.sin_family = AF_INET;
    a.sin_port = htons(atoi(argv[2]));
    a.sin_addr.s_addr = inet_addr(argv[1]);
    n = atol(argv[3]) * 5;
    for (i = 0; i < n; i++) {
        snprintf(buf, sizeof(buf), "%ld", i);
        sendto(s, buf, strlen(buf), 0, (struct sockaddr *)&a, sizeof(a));
        Delay(10);
    }
    CloseSocket(s);
    CloseLibrary(SocketBase);
    printf("udptick done %ld\n", i);
    return 0;
}
