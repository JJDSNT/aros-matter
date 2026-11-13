/*
 * onevent - tap.device's link events (S2_ONEVENT), straight to the device,
 * with no stack in between (tests/tap/onevent.sh).
 *
 * Usage: onevent UNIT
 * Two openers of tap.device UNIT; the host takes the tap down and up when
 * told (SYS:out/ready1, then SYS:out/ready2 appears; it answers with
 * SYS:out/go1, SYS:out/go2). Prints PASS/FAIL lines and "RESULT".
 */
#include <proto/exec.h>
#include <proto/dos.h>
#include <exec/memory.h>
#include <exec/errors.h>
#include <devices/sana2.h>
#include <utility/tagitem.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int passes, fails;

#define CHECK(cond, ...) do { \
    if (cond) { passes++; printf("PASS "); } else { fails++; printf("FAIL "); } \
    printf(__VA_ARGS__); printf("\n"); fflush(stdout); } while (0)

static BOOL rxcopy(APTR to, APTR from, ULONG n) { CopyMem(from, to, n); return TRUE; }
static BOOL txcopy(APTR to, APTR from, ULONG n) { CopyMem(from, to, n); return TRUE; }

static struct TagItem bm[] = {
    { S2_CopyToBuff, (IPTR)rxcopy },
    { S2_CopyFromBuff, (IPTR)txcopy },
    { TAG_DONE, 0 }
};

/* A request like base (same opener), for command, waiting for events. */
static struct IOSana2Req *clone(struct IOSana2Req *base, UWORD command, ULONG events)
{
    struct MsgPort *mp = CreateMsgPort();
    struct IOSana2Req *r = (struct IOSana2Req *)CreateIORequest(mp, sizeof(*r));

    *r = *base;
    r->ios2_Req.io_Message.mn_ReplyPort = mp;
    r->ios2_Req.io_Command = command;
    r->ios2_WireError = events;
    return r;
}

static void dispose(struct IOSana2Req *r)
{
    struct MsgPort *mp = r->ios2_Req.io_Message.mn_ReplyPort;

    DeleteIORequest((struct IORequest *)r);
    DeleteMsgPort(mp);
}

/* Done within secs? */
static int done_within(struct IOSana2Req *r, int secs)
{
    int t;

    for (t = 0; t < secs * 10; t++) {
        if (CheckIO((struct IORequest *)r)) {
            WaitIO((struct IORequest *)r);
            return 1;
        }
        Delay(5);
    }
    return 0;
}

static void signal_host(const char *ready, const char *go)
{
    BPTR f = Open(ready, MODE_NEWFILE);
    BPTR l;

    if (f)
        Close(f);
    while ((l = Lock(go, SHARED_LOCK)) == 0)
        Delay(10);
    UnLock(l);
}

static struct IOSana2Req *open_unit(LONG unit)
{
    struct MsgPort *mp = CreateMsgPort();
    struct IOSana2Req *r = (struct IOSana2Req *)CreateIORequest(mp, sizeof(*r));

    r->ios2_BufferManagement = bm;
    if (OpenDevice("networks/tap.device", unit, (struct IORequest *)r, 0) != 0) {
        dispose(r);
        return NULL;
    }
    return r;
}

int main(int argc, char **argv)
{
    struct IOSana2Req *a, *b, *a1, *a2, *a3, *a4, *a5, *b1, *b2, *x;
    LONG unit;

    if (argc < 2)
        return 20;
    unit = atol(argv[1]);
    a = open_unit(unit);
    b = open_unit(unit);
    CHECK(a != NULL && b != NULL, "two openers of tap.device unit %ld", (long)unit);
    if (a == NULL || b == NULL)
        return 20;

    x = clone(a, S2_ONEVENT, S2EVENT_ERROR);
    DoIO((struct IORequest *)x);
    CHECK(x->ios2_Req.io_Error == S2ERR_NOT_SUPPORTED && x->ios2_WireError == S2WERR_BAD_EVENT,
          "an event it does not report is refused (%d, %lu)", x->ios2_Req.io_Error,
          (unsigned long)x->ios2_WireError);
    dispose(x);

    /* both openers wait for the link to go; one more request waits for ONLINE */
    a1 = clone(a, S2_ONEVENT, S2EVENT_DISCONNECT | S2EVENT_CONNECT);
    b1 = clone(b, S2_ONEVENT, S2EVENT_DISCONNECT);
    a2 = clone(a, S2_ONEVENT, S2EVENT_ONLINE);
    SendIO((struct IORequest *)a1);
    SendIO((struct IORequest *)b1);
    SendIO((struct IORequest *)a2);
    Delay(25);
    CHECK(!CheckIO((struct IORequest *)a1) && !CheckIO((struct IORequest *)b1),
          "requests wait: an event is a change, not the state the link is in (%d %d, %d %d)",
          CheckIO((struct IORequest *)a1) != NULL, a1->ios2_Req.io_Error,
          CheckIO((struct IORequest *)b1) != NULL, b1->ios2_Req.io_Error);
    signal_host("SYS:out/ready1", "SYS:out/go1");     /* the host: link down */
    CHECK(done_within(a1, 5) && a1->ios2_Req.io_Error == 0 && a1->ios2_WireError == S2EVENT_DISCONNECT,
          "opener 1 told of the link going (%lu)", (unsigned long)a1->ios2_WireError);
    CHECK(done_within(b1, 5) && b1->ios2_Req.io_Error == 0 && b1->ios2_WireError == S2EVENT_DISCONNECT,
          "opener 2 told too (%lu)", (unsigned long)b1->ios2_WireError);

    AbortIO((struct IORequest *)a2);
    WaitIO((struct IORequest *)a2);
    CHECK(a2->ios2_Req.io_Error == IOERR_ABORTED, "a waiting request aborted (%d)", a2->ios2_Req.io_Error);

    /* an opener that closes with a request waiting gets it back */
    b2 = clone(b, S2_ONEVENT, S2EVENT_CONNECT);
    SendIO((struct IORequest *)b2);
    Delay(5);
    CloseDevice((struct IORequest *)b);
    CHECK(done_within(b2, 2) && b2->ios2_Req.io_Error == IOERR_ABORTED,
          "an opener closing with a request waiting has it back aborted (%d)", b2->ios2_Req.io_Error);

    a3 = clone(a, S2_ONEVENT, S2EVENT_CONNECT);
    SendIO((struct IORequest *)a3);
    signal_host("SYS:out/ready2", "SYS:out/go2");     /* the host: link up */
    CHECK(done_within(a3, 5) && a3->ios2_Req.io_Error == 0 && a3->ios2_WireError == S2EVENT_CONNECT,
          "the other opener told of the link coming back (%lu)", (unsigned long)a3->ios2_WireError);

    /* S2_ONLINE is S2EVENT_ONLINE */
    a4 = clone(a, S2_ONEVENT, S2EVENT_ONLINE);
    SendIO((struct IORequest *)a4);
    x = clone(a, S2_CONFIGINTERFACE, 0);
    DoIO((struct IORequest *)x);
    x->ios2_Req.io_Command = S2_ONLINE;
    DoIO((struct IORequest *)x);
    CHECK(done_within(a4, 2) && a4->ios2_Req.io_Error == 0 && a4->ios2_WireError == S2EVENT_ONLINE,
          "S2_ONLINE is S2EVENT_ONLINE (%d, %lu)", a4->ios2_Req.io_Error, (unsigned long)a4->ios2_WireError);
    dispose(x);

    /* the last opener closes with a request waiting */
    a5 = clone(a, S2_ONEVENT, S2EVENT_DISCONNECT);
    SendIO((struct IORequest *)a5);
    Delay(5);
    CloseDevice((struct IORequest *)a);
    CHECK(done_within(a5, 2) && a5->ios2_Req.io_Error == IOERR_ABORTED,
          "the unit's last opener closing: its request back aborted (%d)", a5->ios2_Req.io_Error);

    dispose(a); dispose(b);
    dispose(a1); dispose(b1); dispose(a2); dispose(b2);
    dispose(a3); dispose(a4); dispose(a5);
    printf("RESULT %d passed, %d failed\n", passes, fails);
    return fails ? 10 : 0;
}
