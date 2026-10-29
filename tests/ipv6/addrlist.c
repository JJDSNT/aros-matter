#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/bsdsocket.h>
#include <proto/miami.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <netinet/in.h>
#include <netinet/in_var.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>
struct Library *SocketBase, *MiamiBase;
int main(void)
{
    struct in6_ifreq req[64]; struct in6_ifconf ifc; int s, i, n, inpfx = 0;
    SocketBase = OpenLibrary((STRPTR)"bsdsocket.library", 4);
    MiamiBase = OpenLibrary((STRPTR)"miami.library", 0);
    Delay(25 * 50);                                  /* ~20 RAs from the host */
    s = socket(AF_INET6, SOCK_DGRAM, 0);
    memset(&ifc, 0, sizeof(ifc)); ifc.ifc6_len = sizeof(req); ifc.ifc6_req = req;
    IoctlSocket(s, SIOCGLIFADDR, (char *)&ifc);
    n = ifc.ifc6_len / sizeof(req[0]);
    for (i = 0; i < n; i++) {
        char a[64]; struct in6_addr *x = &req[i].ifr_ifru.ifru_addr.sin6_addr;
        inet_ntop(AF_INET6, x, a, sizeof(a));
        printf("addr %s %s\n", req[i].ifr_name, a);
        if (x->s6_addr[0] == 0x20 && x->s6_addr[1] == 0x01 && x->s6_addr[2] == 0x0d && x->s6_addr[3] == 0xb8 &&
                x->s6_addr[4] == 0x4d && x->s6_addr[5] == 0x54 && x->s6_addr[6] == 0 && x->s6_addr[7] == 1)
            inpfx++;
    }
    printf("in-prefix %d\n", inpfx);
    CloseSocket(s);
    return 0;
}
