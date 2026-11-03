/*
 * remloop - remove interface IFNAME by an in-place reload and add it back,
 * N times: its line is taken out of SYS:System/Network/AROSTCP/db/interfaces
 * and put back. Prints "iter <i> removed" / "iter <i> added" as it goes, so
 * a crash shows in which step. Usage: remloop IFNAME N
 */
#define __CONFIG_ROADSHOW__
#include <proto/exec.h>
#include <proto/dos.h>
#include <bsdsocket/netcontrol.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DB "SYS:System/Network/AROSTCP/db/interfaces"

static char line[512];

static int net_reload(void)
{
    struct MsgPort *reply = CreateMsgPort(), *port; struct NetControlMsg msg; int rc = -1;
    if (!reply) return -1;
    memset(&msg, 0, sizeof(msg)); msg.ncm_Msg.mn_ReplyPort = reply; msg.ncm_Msg.mn_Length = sizeof(msg);
    msg.ncm_Command = NCMD_RELOAD;
    Forbid(); if ((port = FindPort((STRPTR)AROSTCP_CTRLPORT_NAME))) PutMsg(port, &msg.ncm_Msg); Permit();
    if (port) { WaitPort(reply); GetMsg(reply); rc = msg.ncm_Result; }
    DeleteMsgPort(reply);
    return rc;
}

/* Take ifn's line out (keeping it in line[]), or put line[] back. */
static int edit(const char *ifn, int add)
{
    static char buf[16384], out[16384];
    FILE *f = fopen(DB, "r");
    size_t n, o = 0, l = strlen(ifn);
    char *p, *e;

    if (!f) return -1;
    n = fread(buf, 1, sizeof(buf) - 1, f);
    fclose(f);
    buf[n] = 0;
    for (p = buf; *p; p = e) {
        e = strchr(p, '\n');
        e = e ? e + 1 : p + strlen(p);
        if (strncmp(p, ifn, l) == 0 && (p[l] == ' ' || p[l] == '\t')) {
            if (!add && (size_t)(e - p) < sizeof(line)) {
                memcpy(line, p, e - p);
                line[e - p] = 0;
            }
            continue;
        }
        memcpy(out + o, p, e - p);
        o += e - p;
    }
    if (add) {
        size_t k = strlen(line);
        memcpy(out + o, line, k);
        o += k;
    }
    if (!(f = fopen(DB, "w"))) return -1;
    fwrite(out, 1, o, f);
    fclose(f);
    return 0;
}

int main(int argc, char **argv)
{
    int i, n;

    if (argc < 3) { printf("usage: remloop IFNAME N\n"); return 20; }
    n = atoi(argv[2]);
    for (i = 0; i < n; i++) {
        edit(argv[1], 0);
        printf("iter %d removed rc=%d\n", i, net_reload());
        fflush(stdout);
        Delay(50);
        edit(argv[1], 1);
        printf("iter %d added rc=%d\n", i, net_reload());
        fflush(stdout);
        Delay(100);
    }
    printf("done\n");
    return 0;
}
