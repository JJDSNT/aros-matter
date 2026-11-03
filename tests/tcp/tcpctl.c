/*
 * tcpctl - set a net.inet.tcp sysctl on AROS, for the benches.
 *
 * Usage: tcpctl LEAF [VALUE]   (LEAF as TCPCTL_*: 13 is prr)
 * Prints "tcpctl <leaf> = <value>" after setting it.
 */
#include <proto/exec.h>
#include <aros/libcall.h>
#include <stdio.h>
#include <stdlib.h>

struct Library *MiamiBase;

/* the bench's toolchain headers may predate MiamiSysCtl()'s arguments */
#define TCPCTL_SYSCTL(a1, a2, a3, a4, a5, a6, a7) \
        AROS_LC7(int, MiamiSysCtl, \
                  AROS_LCA(LONG *, (a1), A0), \
                  AROS_LCA(ULONG, (a2), D0), \
                  AROS_LCA(void *, (a3), A1), \
                  AROS_LCA(LONG *, (a4), A2), \
                  AROS_LCA(void *, (a5), A3), \
                  AROS_LCA(LONG, (a6), D1), \
                  AROS_LCA(int, (a7), D2), \
        struct Library *, MiamiBase, 5, Miami)
#define CTL_NET     4
#define PF_INET     2
#define IPPROTO_TCP 6

int main(int argc, char **argv)
{
    LONG name[4] = { CTL_NET, PF_INET, IPPROTO_TCP, 0 };
    LONG v = -1, n, len = sizeof(v);
    int rc;

    if (argc < 2 || !(MiamiBase = OpenLibrary((STRPTR)"miami.library", 0)))
        return 20;
    name[3] = atoi(argv[1]);
    if (argc > 2) {
        n = atol(argv[2]);
        rc = TCPCTL_SYSCTL(name, 4, &v, &len, &n, sizeof(n), 0);
    } else
        rc = 0;
    if (rc == 0)
        rc = TCPCTL_SYSCTL(name, 4, &v, &len, NULL, 0, 0);
    printf("tcpctl %ld = %ld (rc %d)\n", (long)name[3], (long)v, rc);
    CloseLibrary(MiamiBase);
    return rc ? 10 : 0;
}
