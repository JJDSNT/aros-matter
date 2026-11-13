/*
 * nd6vars - the IPv6 neighbour cache's limits as the stack sized them:
 *   "limits maxnbrs N maxheld N maxqlen N"
 * (net.inet6.icmp6.nd6_maxnbrs, nd6_maxheld, nd6_maxqlen, read with
 * miami.library's MiamiSysCtl()); -1 for one that cannot be read.
 */
#include <proto/exec.h>
#include <proto/miami.h>
#include <sys/socket.h>
#include <sys/sysctl.h>
#include <netinet/in.h>
#include <netinet/icmp6.h>
#include <stdio.h>

struct Library *MiamiBase;

static long icmp6var(int leaf)
{
    LONG mib[4] = { CTL_NET, PF_INET6, IPPROTO_ICMPV6, 0 }, v = -1, len = sizeof(v);

    mib[3] = leaf;
    if (MiamiSysCtl(mib, 4, &v, &len, NULL, 0, 0) != 0)
        return -1;
    return v;
}

int main(void)
{
    MiamiBase = OpenLibrary("miami.library", 0);
    if (MiamiBase == NULL) {
        printf("limits: no miami.library\n");
        return 10;
    }
    printf("limits maxnbrs %ld maxheld %ld maxqlen %ld\n", icmp6var(ICMPV6CTL_ND6_MAXNBRS),
           icmp6var(ICMPV6CTL_ND6_MAXHELD), icmp6var(ICMPV6CTL_ND6_MAXQLEN));
    CloseLibrary(MiamiBase);
    return 0;
}
