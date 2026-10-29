#define __CONFIG_ROADSHOW__
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/bsdsocket.h>
#include <bsdsocket/socketbasetags.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
struct Library *SocketBase;
int main(void)
{
    struct sockaddr_in6 d; int s, i, n;
    SocketBase = OpenLibrary((STRPTR)"bsdsocket.library", 4);
    SocketBaseTags(SBTM_SETVAL(SBTC_ERRNOPTR(sizeof(errno))), (IPTR)&errno, TAG_END);
    Delay(8 * 50);   /* let the host's RAs install the default route */
    s = socket(AF_INET6, SOCK_DGRAM, 0);
    memset(&d, 0, sizeof(d)); d.sin6_len = sizeof(d); d.sin6_family = AF_INET6; d.sin6_port = htons(4000);
    inet_pton(AF_INET6, (char *)"2001:db8:4d54:77::1", &d.sin6_addr);
    for (i = 0; i < 5; i++) {
        n = sendto(s, (char *)"R:via-router", 12, 0, (struct sockaddr *)&d, sizeof(d));
        printf("sendto %d errno %d\n", n, n < 0 ? errno : 0);
        Delay(50);
    }
    CloseSocket(s);
    return 0;
}
