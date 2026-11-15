/*
 * ifconfdump [inet6] - every SIOCGIFCONF entry: interface, family, address
 * (on an AF_INET6 socket with "inet6"). For B48: ip addr showed each IPv6
 * link-local address twice.
 */
#include <proto/exec.h>
#include <proto/socket.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>

struct Library *SocketBase;
static char buf[16384];

int main(int argc, char **argv)
{
    struct ifconf ifc;
    char *cp, *lim, a[64];
    int s;

    if ((SocketBase = OpenLibrary("bsdsocket.library", 3)) == NULL)
        return 20;
    s = socket(argc > 1 ? AF_INET6 : AF_INET, SOCK_DGRAM, 0);
    ifc.ifc_len = sizeof(buf);
    ifc.ifc_buf = buf;
    if (IoctlSocket(s, SIOCGIFCONF, (char *)&ifc) != 0)
        return 10;
    for (cp = buf, lim = buf + ifc.ifc_len; cp < lim; ) {
        struct ifreq *r = (struct ifreq *)cp;
        int sz = sizeof(r->ifr_name) + r->ifr_addr.sa_len;

        a[0] = 0;
        if (r->ifr_addr.sa_family == AF_INET)
            inet_ntop(AF_INET, &((struct sockaddr_in *)&r->ifr_addr)->sin_addr, a, sizeof(a));
        else if (r->ifr_addr.sa_family == AF_INET6)
            inet_ntop(AF_INET6, &((struct sockaddr_in6 *)&r->ifr_addr)->sin6_addr, a, sizeof(a));
        printf("%-6s family %2d len %2d %s\n", r->ifr_name, r->ifr_addr.sa_family, r->ifr_addr.sa_len, a);
        cp += sz < (int)sizeof(*r) ? (int)sizeof(*r) : sz;
    }
    CloseSocket(s);
    CloseLibrary(SocketBase);
    return 0;
}
