/*
 * aflagwatch - add the IPv4 alias ADDR/24 on IFNAME and print, for SECS
 * seconds, each change of its RFC 5227 state (SIOCGIFAFLAG_IN) with the
 * time since it was added (tests/ipv4/acd_reprobe_probe.py).
 *
 * Usage: aflagwatch IFNAME ADDR SECS
 * Prints "t=<s.ss> flags=<n>" at each change (1 tentative, 2 duplicated).
 */
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/bsdsocket.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <netinet/in.h>
#include <netinet/in_var.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct Library *SocketBase;

int main(int argc, char **argv)
{
    struct in_aliasreq ifra;
    struct ifreq ifr;
    struct sockaddr_in *sin = (struct sockaddr_in *)&ifr.ifr_addr;
    long t, secs;
    int s, last = -2;

    if (argc < 4 || !(SocketBase = OpenLibrary("bsdsocket.library", 4)))
        return 20;
    s = socket(AF_INET, SOCK_DGRAM, 0);
    memset(&ifra, 0, sizeof(ifra));
    snprintf(ifra.ifra_name, sizeof(ifra.ifra_name), "%s", argv[1]);
    ifra.ifra_addr.sin_len = sizeof(ifra.ifra_addr);
    ifra.ifra_addr.sin_family = AF_INET;
    ifra.ifra_addr.sin_addr.s_addr = inet_addr(argv[2]);
    ifra.ifra_mask.sin_len = sizeof(ifra.ifra_mask);
    ifra.ifra_mask.sin_family = AF_INET;
    ifra.ifra_mask.sin_addr.s_addr = htonl(0xffffff00);
    if (IoctlSocket(s, SIOCAIFADDR, (char *)&ifra) != 0) {
        printf("SIOCAIFADDR failed\n");
        return 20;
    }
    secs = atol(argv[3]);
    for (t = 0; t <= secs * 50; t += 10) {
        int f;

        memset(&ifr, 0, sizeof(ifr));
        snprintf(ifr.ifr_name, sizeof(ifr.ifr_name), "%s", argv[1]);
        sin->sin_len = sizeof(*sin);
        sin->sin_family = AF_INET;
        sin->sin_addr.s_addr = inet_addr(argv[2]);
        f = IoctlSocket(s, SIOCGIFAFLAG_IN, (char *)&ifr) == 0 ? ifr.ifr_addrflags : -1;
        if (f != last) {
            printf("t=%ld.%02ld flags=%d\n", t / 50, t % 50 * 2, f);
            fflush(stdout);
            last = f;
        }
        Delay(10);
    }
    CloseSocket(s);
    CloseLibrary(SocketBase);
    return 0;
}
