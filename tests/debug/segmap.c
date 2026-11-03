/*
 * segmap - print where code is loaded, to place a crash's RIP: the segments
 * of the processes named on the command line (their CLI module or seglist)
 * the code of the devices named, by debug.library's DecodeLocation() on
 * their BeginIO vector, and of the libraries named, on a library vector
 * (opened for it: bsdsocket.library's code is AROSTCP's).
 * "seg <name> <addr> <start> <end> <module>/<segment>".
 * Usage: segmap PROC=name ... DEV=name ... LIB=name ...
 */
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/debug.h>
#include <exec/execbase.h>
#include <dos/dosextens.h>
#include <libraries/debug.h>
#include <stdio.h>
#include <string.h>

struct Library *DebugBase;

static void decode(const char *what, APTR a)
{
    STRPTR mod = NULL, seg = NULL;
    APTR start = NULL, end = NULL;

    if (DecodeLocation(a, DL_ModuleName, (IPTR)&mod, DL_SegmentName, (IPTR)&seg,
                       DL_SegmentStart, (IPTR)&start, DL_SegmentEnd, (IPTR)&end, TAG_DONE))
        printf("seg %s %p %p %p %s/%s\n", what, a, start, end, mod ? (char *)mod : "?", seg ? (char *)seg : "?");
    else
        printf("seg %s %p undecoded\n", what, a);
}

int main(int argc, char **argv)
{
    int i;

    if (!(DebugBase = OpenLibrary("debug.library", 0))) { printf("no debug.library\n"); return 20; }
    for (i = 1; i < argc; i++) {
        if (strncmp(argv[i], "PROC=", 5) == 0) {
            struct Process *p;
            BPTR s;
            int n = 0;

            Forbid();
            p = (struct Process *)FindTask(argv[i] + 5);
            Permit();
            if (!p) { printf("seg %s none\n", argv[i]); continue; }
            s = p->pr_CLI ? ((struct CommandLineInterface *)BADDR(p->pr_CLI))->cli_Module : 0;
            if (!s)
                s = ((BPTR *)BADDR(p->pr_SegList))[3];
            for (; s; s = *(BPTR *)BADDR(s), n++) {
                char what[64];
                snprintf(what, sizeof(what), "%s#%d", argv[i] + 5, n);
                decode(what, (APTR)((BPTR *)BADDR(s) + 1));
            }
        } else if (strncmp(argv[i], "DEV=", 4) == 0) {
            struct Library *d;

            Forbid();
            d = (struct Library *)FindName(&SysBase->DeviceList, argv[i] + 4);
            Permit();
            if (!d) { printf("seg %s none\n", argv[i]); continue; }
            decode(argv[i] + 4, __AROS_GETVECADDR(d, 5));
        } else if (strncmp(argv[i], "RES=", 4) == 0) {
            APTR r = OpenResource(argv[i] + 4);

            if (!r) { printf("seg %s none\n", argv[i]); continue; }
            decode(argv[i] + 4, __AROS_GETVECADDR(r, 1));
        } else if (strncmp(argv[i], "LIB=", 4) == 0) {
            struct Library *l = OpenLibrary(argv[i] + 4, 0);

            if (!l) { printf("seg %s none\n", argv[i]); continue; }
            decode(argv[i] + 4, __AROS_GETVECADDR(l, 1));      /* Open */
            decode(argv[i] + 4, __AROS_GETVECADDR(l, 6));
            CloseLibrary(l);
        }
    }
    CloseLibrary(DebugBase);
    return 0;
}
