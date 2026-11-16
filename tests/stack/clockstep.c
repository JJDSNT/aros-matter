/*
 * clockstep SECS - set the system time SECS seconds forward (back if
 * negative), as timesyncd or a user's Date does (TR_SETSYSTIME, as
 * cunit-net-clockstep), and print "step SECS ok|failed". For B72: whether
 * mdnsd's timers follow the time of day (DateStamp()) or the monotonic
 * clock (GetUpTime()).
 */
#include <exec/types.h>
#include <devices/timer.h>
#include <proto/exec.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    struct MsgPort *port;
    struct timerequest *tr;
    long secs;
    int ok = 0;

    if (argc != 2)
        return 20;
    secs = atol(argv[1]);
    if ((port = CreateMsgPort()) == NULL)
        return 20;
    tr = (struct timerequest *)CreateIORequest(port, sizeof(*tr));
    if (tr != NULL && OpenDevice("timer.device", UNIT_MICROHZ, (struct IORequest *)tr, 0) == 0) {
        tr->tr_node.io_Command = TR_GETSYSTIME;
        if (DoIO((struct IORequest *)tr) == 0) {
            tr->tr_time.tv_secs += secs;
            tr->tr_node.io_Command = TR_SETSYSTIME;
            ok = DoIO((struct IORequest *)tr) == 0;
        }
        CloseDevice((struct IORequest *)tr);
    }
    if (tr != NULL)
        DeleteIORequest((struct IORequest *)tr);
    DeleteMsgPort(port);
    printf("step %ld %s\n", secs, ok ? "ok" : "failed");
    return ok ? 0 : 10;
}
