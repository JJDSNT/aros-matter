/*
 * ifbrd IFNAME ADDR - SIOCGIFNETMASK and SIOCGIFBRDADDR for one of IFNAME's
 * IPv4 addresses (the stack answers for the address named in ifr_addr).
 * Prints "ADDR netmask M broadcast B".
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

static struct in_addr ask(int s, const char *name, struct in_addr a, int cmd)
{
    struct ifreq ifr;
    struct sockaddr_in *sin = (struct sockaddr_in *)&ifr.ifr_addr;

    memset(&ifr, 0, sizeof(ifr));
    strncpy(ifr.ifr_name, name, sizeof(ifr.ifr_name) - 1);
    sin->sin_len = sizeof(*sin);
    sin->sin_family = AF_INET;
    sin->sin_addr = a;
    if (IoctlSocket(s, cmd, (char *)&ifr) != 0)
        sin->sin_addr.s_addr = 0;
    return sin->sin_addr;
}

int main(int argc, char **argv)
{
    struct in_addr a, m, b;
    int s;

    if (argc < 3 || (SocketBase = OpenLibrary("bsdsocket.library", 3)) == NULL)
        return 20;
    s = socket(AF_INET, SOCK_DGRAM, 0);
    a.s_addr = inet_addr(argv[2]);
    m = ask(s, argv[1], a, SIOCGIFNETMASK);
    b = ask(s, argv[1], a, SIOCGIFBRDADDR);
    printf("%s netmask ", argv[2]);
    printf("%s broadcast ", inet_ntoa(m));
    printf("%s\n", inet_ntoa(b));
    CloseSocket(s);
    CloseLibrary(SocketBase);
    return 0;
}
