/*
 * dnsgone - AROS side of tests/dns/dnsgone.py: an interface going away while
 * an application holds the dynamic database.
 *
 * Usage: dnsgone IFNAME SERVER KEPT
 * SERVER is the IPv4 DNS= server of IFNAME's line in db/interfaces, KEPT
 * that of an interface that stays. Prints "before <0|1>" (SERVER in
 * ObtainDomainNameServerList()), then holds the
 * database with miami.library's ClearDynDomain(), takes IFNAME's line out of
 * db/interfaces and asks the stack to reload, waiting at most 5 s:
 * "reload done" or "reload stalled". Then EndDynDomain(), and after 2 s
 * "reload replied" once it has, "after <0|1>" for SERVER and "kept <0|1>"
 * for KEPT.
 */
#define __CONFIG_ROADSHOW__
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/timer.h>
#include <proto/bsdsocket.h>
#include <defines/miami.h>
#include <bsdsocket/netcontrol.h>
#include <libraries/bsdsocket.h>
#include <devices/timer.h>
#include <stdio.h>
#include <string.h>

struct Library *SocketBase, *MiamiBase;

#define DB "SYS:System/Network/AROSTCP/db/interfaces"

static int listed(const char *server)
{
    struct List *l = ObtainDomainNameServerList();
    struct Node *n;
    int found = 0;

    if (!l)
        return -1;
    for (n = l->lh_Head; n->ln_Succ; n = n->ln_Succ)
        if (strcmp((char *)((struct DomainNameServerNode *)n)->dnsn_Address, server) == 0)
            found = 1;
    ReleaseDomainNameServerList(l);
    return found;
}

static int drop_interface(const char *ifn)
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
        if (!(strncmp(p, ifn, l) == 0 && (p[l] == ' ' || p[l] == '\t'))) {
            memcpy(out + o, p, e - p);
            o += e - p;
        }
    }
    if (!(f = fopen(DB, "w"))) return -1;
    fwrite(out, 1, o, f);
    fclose(f);
    return 0;
}

int main(int argc, char **argv)
{
    struct MsgPort *reply, *port;
    struct NetControlMsg msg;
    int replied;

    if (argc < 4) { printf("usage: dnsgone IFNAME SERVER KEPT\n"); return 20; }
    if (!(SocketBase = OpenLibrary("bsdsocket.library", 4))) { printf("no bsdsocket.library\n"); return 20; }
    if (!(MiamiBase = OpenLibrary("miami.library", 0))) { printf("no miami.library\n"); return 20; }
    printf("before %d\n", listed(argv[2]));
    fflush(stdout);

    ClearDynDomain();                   /* holds the database */
    drop_interface(argv[1]);
    reply = CreateMsgPort();
    memset(&msg, 0, sizeof(msg));
    msg.ncm_Msg.mn_ReplyPort = reply;
    msg.ncm_Msg.mn_Length = sizeof(msg);
    msg.ncm_Command = NCMD_RELOAD;
    Forbid();
    if ((port = FindPort((STRPTR)AROSTCP_CTRLPORT_NAME)))
        PutMsg(port, &msg.ncm_Msg);
    Permit();
    if (!port) { printf("no control port\n"); return 20; }
    {
        int i;

        for (replied = 0, i = 0; i < 100 && !replied; i++) {
            if (GetMsg(reply))
                replied = 1;
            else
                Delay(2);
        }
    }
    printf("reload %s\n", replied ? "done" : "stalled");
    fflush(stdout);
    EndDynDomain();
    if (!replied) {
        WaitPort(reply);
        GetMsg(reply);
    }
    printf("reload replied\n");
    Delay(2 * 50);
    printf("after %d\n", listed(argv[2]));
    printf("kept %d\n", listed(argv[3]));
    DeleteMsgPort(reply);
    CloseLibrary(MiamiBase);
    CloseLibrary(SocketBase);
    return 0;
}
