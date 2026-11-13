/*
 * alias_owner IFNAME ADDR SECONDS - adds ADDR/32 as an alias of IFNAME (the
 * address of another host on the link, which RFC 5227 marks duplicated),
 * writes SYS:out/alias-ready with its flags once it has been probed, and
 * holds it SECONDS before deleting it, printing its flags again then. With the host pinging this AROS
 * meanwhile (alias_owner.sh), the replies must keep coming: the duplicated
 * alias must not catch what goes to its owner.
 */
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/socket.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <netinet/in.h>
#include <netinet/in_var.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

struct Library *SocketBase;

int main(int argc, char **argv)
{
    struct in_aliasreq ifra;
    struct ifreq ifr;
    struct sockaddr_in *sin = (struct sockaddr_in *)&ifr.ifr_addr;
    int s, i, flags = -1;
    BPTR fh;

    if (argc < 4 || (SocketBase = OpenLibrary("bsdsocket.library", 4)) == NULL)
        return 20;
    s = socket(AF_INET, SOCK_DGRAM, 0);
    memset(&ifra, 0, sizeof(ifra));
    strncpy(ifra.ifra_name, argv[1], sizeof(ifra.ifra_name) - 1);
    ifra.ifra_addr.sin_len = ifra.ifra_mask.sin_len = sizeof(struct sockaddr_in);
    ifra.ifra_addr.sin_family = ifra.ifra_mask.sin_family = AF_INET;
    ifra.ifra_addr.sin_addr.s_addr = inet_addr(argv[2]);
    ifra.ifra_mask.sin_addr.s_addr = 0xffffffff;
    if (IoctlSocket(s, SIOCAIFADDR, (char *)&ifra) != 0) {
        printf("SIOCAIFADDR failed\n");
        return 10;
    }
    for (i = 0; i < 100; i++) {
        memset(&ifr, 0, sizeof(ifr));
        strncpy(ifr.ifr_name, argv[1], sizeof(ifr.ifr_name) - 1);
        sin->sin_len = sizeof(*sin);
        sin->sin_family = AF_INET;
        sin->sin_addr.s_addr = inet_addr(argv[2]);
        if (IoctlSocket(s, SIOCGIFAFLAG_IN, (char *)&ifr) == 0 &&
                !((flags = ifr.ifr_addrflags) & IN_IFF_TENTATIVE))
            break;
        Delay(5);
    }
    printf("%s flags %d (duplicated %d)\n", argv[2], flags, IN_IFF_DUPLICATED);
    fflush(stdout);
    if ((fh = Open("SYS:out/alias-ready", MODE_NEWFILE)) != BNULL)
        Close(fh);
    Delay(atoi(argv[3]) * 50);
    memset(&ifr, 0, sizeof(ifr));
    strncpy(ifr.ifr_name, argv[1], sizeof(ifr.ifr_name) - 1);
    sin->sin_len = sizeof(*sin);
    sin->sin_family = AF_INET;
    sin->sin_addr.s_addr = inet_addr(argv[2]);
    if (IoctlSocket(s, SIOCGIFAFLAG_IN, (char *)&ifr) == 0)
        printf("%s flags at the end %d\n", argv[2], ifr.ifr_addrflags);
    fflush(stdout);
    memset(&ifr, 0, sizeof(ifr));
    strncpy(ifr.ifr_name, argv[1], sizeof(ifr.ifr_name) - 1);
    sin->sin_len = sizeof(*sin);
    sin->sin_family = AF_INET;
    sin->sin_addr.s_addr = inet_addr(argv[2]);
    IoctlSocket(s, SIOCDIFADDR, (char *)&ifr);
    CloseSocket(s);
    CloseLibrary(SocketBase);
    return 0;
}
