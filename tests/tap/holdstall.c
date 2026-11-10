/*
 * holdstall - a tap.device opener that reads one frame and then stays open
 * without posting another read (tests/tap/hold_probe.py): the case where a
 * frame held for an opener's reads (tap.device receive backpressure) would
 * stall the unit's other openers - AROSTCP here - for good.
 *
 * Usage: holdstall UNIT TYPE SECS
 * Opens tap.device UNIT, reads one frame of ethertype TYPE (hex), prints
 * "got N bytes", then stays open SECS seconds and closes.
 */
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/utility.h>
#include <exec/memory.h>
#include <devices/sana2.h>
#include <utility/tagitem.h>
#include <stdio.h>
#include <stdlib.h>

static BOOL rxcopy(APTR to, APTR from, ULONG n)
{
    CopyMem(from, to, n);
    return TRUE;
}

static BOOL txcopy(APTR to, APTR from, ULONG n)
{
    CopyMem(from, to, n);
    return TRUE;
}

int main(int argc, char **argv)
{
    struct TagItem bm[] = {
        { S2_CopyToBuff, (IPTR)rxcopy },
        { S2_CopyFromBuff, (IPTR)txcopy },
        { TAG_DONE, 0 }
    };
    struct MsgPort *mp;
    struct IOSana2Req *req;
    static UBYTE buf[2048];

    if (argc < 4)
        return 20;
    mp = CreateMsgPort();
    req = (struct IOSana2Req *)CreateIORequest(mp, sizeof(*req));
    if (!req)
        return 20;
    req->ios2_BufferManagement = bm;
    if (OpenDevice("tap.device", atol(argv[1]), (struct IORequest *)req, 0) != 0) {
        printf("open failed\n");
        return 20;
    }
    req->ios2_Req.io_Command = CMD_READ;
    req->ios2_PacketType = strtoul(argv[2], NULL, 16);
    req->ios2_Data = buf;
    printf("reading one frame of type 0x%lx\n", (unsigned long)req->ios2_PacketType);
    fflush(stdout);
    if (DoIO((struct IORequest *)req) == 0)
        printf("got %lu bytes; now open without reading for %s s\n",
               (unsigned long)req->ios2_DataLength, argv[3]);
    else
        printf("read failed %d\n", req->ios2_Req.io_Error);
    fflush(stdout);
    Delay(atol(argv[3]) * 50);
    CloseDevice((struct IORequest *)req);
    DeleteIORequest((struct IORequest *)req);
    DeleteMsgPort(mp);
    printf("closed\n");
    return 0;
}
