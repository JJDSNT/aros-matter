/* udp6once IFNAME ADDR PORT [SIZE]: send one UDP datagram of SIZE bytes (1) to ADDR%IFNAME:PORT, wait 3 s. */
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
int main(int argc, char **argv)
{
    struct sockaddr_in6 d;
    int s, r;
    if (argc < 4 || !(SocketBase = OpenLibrary((STRPTR)"bsdsocket.library", 4)) ||
            !(MiamiBase = OpenLibrary((STRPTR)"miami.library", 0)))
        return 20;
    memset(&d, 0, sizeof(d));
    d.sin6_len = sizeof(d);
    d.sin6_family = AF_INET6;
    d.sin6_port = htons(atoi(argv[3]));
    inet_pton(AF_INET6, argv[2], &d.sin6_addr);
    d.sin6_scope_id = if_nametoindex(argv[1]);
    s = socket(AF_INET6, SOCK_DGRAM, 0);
    {
        static char big[9000];
        int n = argc > 4 ? atoi(argv[4]) : 1;

        memset(big, 'x', sizeof(big));
        r = sendto(s, big, n, 0, (struct sockaddr *)&d, sizeof(d));
    }
    printf("sent %d\n", r);
    Delay(3 * 50);
    printf("still alive\n");
    CloseSocket(s);
    CloseLibrary(MiamiBase);
    CloseLibrary(SocketBase);
    return 0;
}
