/*
 * rexxhost NAME - set the host name through AROSTCP's ARexx port ("SET
 * HOSTNAME=NAME", sent as a RexxMsg: no RexxMast needed), which runs
 * rexx_sethostname() in the NETTRACE task (it polls the ARexx port,
 * kern/amiga_log.c), and report:
 *   - whether SBTC_SIG_HOSTNAME_CHANGE_MASK came, and after how long;
 *   - gethostname(), and the HOSTNAME variable with its length (B66: the
 *     ARexx path set 256 bytes, what followed the name included).
 */
#define __CONFIG_ROADSHOW__
#include <exec/types.h>
#include <exec/ports.h>
#include <rexx/storage.h>
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/socket.h>
#include <proto/rexxsyslib.h>
#include <bsdsocket/socketbasetags.h>
#include <stdio.h>
#include <string.h>

struct Library *SocketBase;
struct RxsLib *RexxSysBase;

int main(int argc, char **argv)
{
    char cmd[300], name[300], var[300];
    struct MsgPort *reply, *port;
    struct RexxMsg *rm;
    BYTE sig;
    ULONG mask;
    LONG len, rc1 = -1;
    int i;

    if (argc < 2)
        return 20;
    snprintf(cmd, sizeof(cmd), "SET HOSTNAME=%s", argv[1]);
    SocketBase = OpenLibrary("bsdsocket.library", 4);
    RexxSysBase = (struct RxsLib *)OpenLibrary("rexxsyslib.library", 0);
    if (SocketBase == NULL || RexxSysBase == NULL || (sig = AllocSignal(-1)) == -1)
        return 20;
    mask = 1UL << sig;
    if (SocketBaseTags(SBTM_SETVAL(SBTC_SIG_HOSTNAME_CHANGE_MASK), mask, TAG_END) != 0)
        printf("the stack refuses SBTC_SIG_HOSTNAME_CHANGE_MASK\n");
    SetSignal(0, mask);
    reply = CreateMsgPort();
    rm = reply ? CreateRexxMsg(reply, NULL, NULL) : NULL;
    if (rm == NULL || (rm->rm_Args[0] = (IPTR)CreateArgstring(cmd, strlen(cmd))) == 0)
        return 20;
    rm->rm_Action = RXCOMM;
    Forbid();
    port = FindPort((STRPTR)"AROSTCP");
    if (port != NULL)
        PutMsg(port, &rm->rm_Node);
    Permit();
    if (port == NULL) {
        printf("no AROSTCP port\n");
        return 20;
    }
    WaitPort(reply);
    GetMsg(reply);
    rc1 = rm->rm_Result1;
    DeleteArgstring((UBYTE *)rm->rm_Args[0]);
    DeleteRexxMsg(rm);
    DeleteMsgPort(reply);
    for (i = 0; i < 30 && !(SetSignal(0, 0) & mask); i++)
        Delay(5);                       /* 3 s at most, by 100 ms */
    printf("rexx rc %ld; signal %s", (long)rc1,
        (SetSignal(0, mask) & mask) ? "yes" : "no");
    printf(" (%d ms)\n", i * 100);
    name[0] = '\0';
    gethostname(name, sizeof(name));
    var[0] = '\0';
    len = GetVar("HOSTNAME", var, sizeof(var), GVF_GLOBAL_ONLY | GVF_BINARY_VAR);
    printf("gethostname \"%s\" (%d); HOSTNAME %ld bytes, \"%s\"\n",
        name, (int)strlen(name), (long)len, var);
    SocketBaseTags(SBTM_SETVAL(SBTC_SIG_HOSTNAME_CHANGE_MASK), 0, TAG_END);
    FreeSignal(sig);
    CloseLibrary((struct Library *)RexxSysBase);
    CloseLibrary(SocketBase);
    return 0;
}
