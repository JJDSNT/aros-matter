/*
 * modquery NAME... - for each module of the stack: whether it is started,
 * loaded from its own library, and how many users keep it
 * (NCMD_MODULE_QUERY). "admin" is the routing sockets' module.
 */
#include <exec/ports.h>
#include <proto/exec.h>
#include <bsdsocket/netcontrol.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv)
{
    int i;

    for (i = 1; i < argc; i++) {
        struct MsgPort *reply = CreateMsgPort(), *ctrl;
        struct NetControlModuleMsg mm;

        memset(&mm, 0, sizeof(mm));
        mm.ncmm_Msg.ncm_Msg.mn_Node.ln_Type = NT_MESSAGE;
        mm.ncmm_Msg.ncm_Msg.mn_ReplyPort = reply;
        mm.ncmm_Msg.ncm_Msg.mn_Length = sizeof(mm);
        mm.ncmm_Msg.ncm_Command = NCMD_MODULE_QUERY;
        strncpy(mm.ncmm_Name, argv[i], NCM_MODULE_NAMELEN - 1);
        Forbid();
        if ((ctrl = FindPort(AROSTCP_CTRLPORT_NAME)) != NULL)
            PutMsg(ctrl, &mm.ncmm_Msg.ncm_Msg);
        Permit();
        if (ctrl != NULL) {
            WaitPort(reply);
            GetMsg(reply);
        }
        printf("%s: result %ld started %d library %d users %ld\n", argv[i],
               ctrl ? (long)mm.ncmm_Msg.ncm_Result : -1L,
               (mm.ncmm_Flags & NCMMF_STARTED) != 0, (mm.ncmm_Flags & NCMMF_LIBRARY) != 0,
               (long)mm.ncmm_Users);
        DeleteMsgPort(reply);
    }
    return 0;
}
