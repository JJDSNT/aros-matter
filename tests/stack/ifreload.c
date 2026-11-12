/* ifreload [drop NAME] - "drop NAME": the AROSTCP interfaces file without NAME's lines (saved in T:if.saved); with no argument: the saved file back. Then the stack reloads in place (NCMD_RELOAD), as the Network preferences do. */
#include <exec/ports.h>
#include <proto/exec.h>
#include <proto/dos.h>
#include <bsdsocket/netcontrol.h>
#include <stdio.h>
#include <string.h>
#define CFG "SYS:System/Network/AROSTCP/db/interfaces"
static char buf[65536], out[65536];
static long reload(void)
{
    struct MsgPort *reply = CreateMsgPort(), *ctrl;
    struct NetControlMsg msg;
    memset(&msg, 0, sizeof(msg));
    msg.ncm_Msg.mn_Node.ln_Type = NT_MESSAGE; msg.ncm_Msg.mn_ReplyPort = reply;
    msg.ncm_Msg.mn_Length = sizeof(msg); msg.ncm_Command = NCMD_RELOAD;
    Forbid(); ctrl = FindPort(AROSTCP_CTRLPORT_NAME); if (ctrl) PutMsg(ctrl, &msg.ncm_Msg); Permit();
    if (ctrl) { WaitPort(reply); GetMsg(reply); }
    DeleteMsgPort(reply);
    return ctrl ? msg.ncm_Result : -1;
}
int main(int argc, char **argv)
{
    /* reload2 drop NAME | reload2 restore */
    BPTR fh; long n, i = 0, o = 0;
    if (argc > 2) {
        fh = Open(CFG, MODE_OLDFILE); n = Read(fh, buf, sizeof(buf)); Close(fh);
        fh = Open("T:if.saved", MODE_NEWFILE); Write(fh, buf, n); Close(fh);
        while (i < n) { long e = i; while (e < n && buf[e] != '\n') e++; if (e < n) e++;
            if (strncmp(buf + i, argv[2], strlen(argv[2])) != 0) { memcpy(out + o, buf + i, e - i); o += e - i; }
            i = e; }
        fh = Open(CFG, MODE_NEWFILE); Write(fh, out, o); Close(fh);
    } else {
        fh = Open("T:if.saved", MODE_OLDFILE); n = Read(fh, buf, sizeof(buf)); Close(fh);
        fh = Open(CFG, MODE_NEWFILE); Write(fh, buf, n); Close(fh);
    }
    printf("reload: %ld\n", reload());
    return 0;
}
