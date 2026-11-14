/*
 * srcprobe ADDR DST - is ADDR, one of this host's IPv4 addresses, in use?
 * (tests/ipv4/acd_linkup.sh, CONFLICT=1). Binds a UDP socket to ADDR and
 * says what bind() gave; then sends one datagram, "srcprobe", to DST port 9
 * from an unbound socket - the host captures it and checks its source.
 * Prints "bind ADDR: ok" or "bind ADDR: refused (errno N)", then
 * "sent to DST: ok" or "sent to DST: failed (errno N)".
 */
#include <proto/socket.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>

struct Library *SocketBase;

int main(int argc, char **argv)
{
    struct sockaddr_in a;
    int s;

    if (argc < 3 || (SocketBase = OpenLibrary("bsdsocket.library", 3)) == NULL)
        return 20;
    memset(&a, 0, sizeof(a));
    a.sin_len = sizeof(a);
    a.sin_family = AF_INET;
    a.sin_addr.s_addr = inet_addr(argv[1]);
    s = socket(AF_INET, SOCK_DGRAM, 0);
    if (bind(s, (struct sockaddr *)&a, sizeof(a)) == 0)
        printf("bind %s: ok\n", argv[1]);
    else
        printf("bind %s: refused (errno %ld)\n", argv[1], (long)Errno());
    CloseSocket(s);

    a.sin_addr.s_addr = inet_addr(argv[2]);
    a.sin_port = htons(9);
    s = socket(AF_INET, SOCK_DGRAM, 0);
    if (sendto(s, "srcprobe", 8, 0, (struct sockaddr *)&a, sizeof(a)) == 8)
        printf("sent to %s: ok\n", argv[2]);
    else
        printf("sent to %s: failed (errno %ld)\n", argv[2], (long)Errno());
    CloseSocket(s);
    CloseLibrary(SocketBase);
    return 0;
}
