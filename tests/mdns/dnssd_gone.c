/*
 * dnssd_gone - a client task of dnssd.library that goes without closing its
 * session (realignment step 3: the coordinator's TNA_REMOVED, D1/D7).
 *
 * A child task opens a session, registers "Gone.Test" (_gonetest._tcp) and
 * browses, then either is removed by force (RemTask(), case "removed") or
 * returns without closing anything (case "exits"). The parent watches
 * mdnsd's counts (DNSSD_GetStatus()) and says how long its session and its
 * two operations took to go: told by task.resource, at once; by the reap
 * alone, up to MDNSD_REAP_SECONDS (5 s). Before and after, the parent tries
 * the child's session from its own task: refused (DNSSD_ERR_STALE). The
 * host checks with Avahi that the service is gone (its goodbye was sent).
 *
 *     dnssd_gone removed|exits
 * Prints "PASS"/"FAIL" lines and "gone after N ms".
 */
#include <exec/types.h>
#include <exec/tasks.h>
#include <dos/dos.h>
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/dnssd.h>
#include <stdio.h>
#include <string.h>

struct Library *DNSSDBase;
static int fails, passes;

#define CHECK(cond, ...) do { \
    if (cond) { passes++; printf("PASS "); } else { fails++; printf("FAIL "); } \
    printf(__VA_ARGS__); printf("\n"); } while (0)

struct Child {
    struct Task *parent;
    int exits;                  /* return without closing, rather than wait */
    volatile int ready;
    volatile LONG rc[3];
    DNSSDSessionRef session;
};

static void child_entry(void)
{
    struct Child *c = FindTask(NULL)->tc_UserData;
    struct MsgPort *port = CreateMsgPort();
    DNSSDOperationRef reg = NULL, browse = NULL;

    c->rc[0] = port != NULL ? DNSSD_OpenSessionA(&c->session, port, NULL) : -100;
    if (c->rc[0] == DNSSD_OK) {
        c->rc[1] = DNSSD_Register(c->session, (CONST_STRPTR)"Gone.Test", (CONST_STRPTR)"_gonetest._tcp", 7,
            &reg, DNSSD_TXT, (IPTR)"\x06" "test=1", DNSSD_TXTLength, 7, TAG_DONE);
        c->rc[2] = DNSSD_Browse(c->session, (CONST_STRPTR)"_gonetest._tcp", &browse, TAG_DONE);
    }
    c->ready = 1;
    Signal(c->parent, SIGBREAKF_CTRL_F);
    if (c->exits) {
        Wait(SIGBREAKF_CTRL_E); /* the parent has seen them */
        return;                 /* nothing closed: the session, its port */
    }
    Wait(0);                    /* until removed */
}

static void status(ULONG *sessions, ULONG *ops)
{
    *sessions = *ops = 0xffffffffUL;
    DNSSD_GetStatus(DNSSD_Status_Sessions, sessions, DNSSD_Status_Operations, ops,
        TAG_DONE);
}

int main(int argc, char **argv)
{
    static struct Child c;
    struct DNSSDEvent ev;
    ULONG s0, o0, s1, o1, s, o, size;
    struct Task *t;
    LONG ms;
    int i;

    if (argc < 2 || (strcmp(argv[1], "removed") != 0 && strcmp(argv[1], "exits") != 0)) {
        printf("usage: dnssd_gone removed|exits\n");
        return RETURN_ERROR;
    }
    DNSSDBase = OpenLibrary("dnssd.library", 0);
    if (DNSSDBase == NULL) {
        printf("FAIL no dnssd.library\n");
        return RETURN_FAIL;
    }
    status(&s0, &o0);
    printf("before: %lu sessions, %lu operations\n", (unsigned long)s0, (unsigned long)o0);

    memset(&c, 0, sizeof(c));
    c.parent = FindTask(NULL);
    c.exits = strcmp(argv[1], "exits") == 0;
    SetSignal(0, SIGBREAKF_CTRL_F);
    t = NewCreateTask(TASKTAG_PC, (IPTR)child_entry, TASKTAG_NAME, (IPTR)"dnssd_gone child",
        TASKTAG_STACKSIZE, 16384, TASKTAG_USERDATA, (IPTR)&c, TAG_DONE);
    CHECK(t != NULL, "the child task starts");
    if (t == NULL)
        return RETURN_FAIL;
    Wait(SIGBREAKF_CTRL_F);
    CHECK(c.ready && c.rc[0] == DNSSD_OK && c.rc[1] == DNSSD_OK && c.rc[2] == DNSSD_OK,
        "the child has a session, a registration and a browse (%ld %ld %ld)",
        (long)c.rc[0], (long)c.rc[1], (long)c.rc[2]);
    Delay(100);                 /* the name probed and announced (2 s) */
    status(&s1, &o1);
    CHECK(s1 == s0 + 1 && o1 == o0 + 2, "mdnsd has them: %lu sessions, %lu operations",
        (unsigned long)s1, (unsigned long)o1);

    size = sizeof(ev);
    CHECK(DNSSD_ReadEvent(c.session, &ev, &size) == DNSSD_ERR_STALE,
        "another task cannot use the child's session");

    if (c.exits)
        Signal(t, SIGBREAKF_CTRL_E);    /* it returns */
    else
        RemTask(t);             /* by force: nothing of it is closed */
    /* how long until mdnsd has let them go */
    for (ms = 0; ms <= 10000; ms += 20) {
        status(&s, &o);
        if (s == s0 && o == o0)
            break;
        Delay(1);
    }
    printf("gone after %ld ms (%s)\n", (long)ms, argv[1]);
    CHECK(s == s0 && o == o0, "its session and operations are gone: %lu, %lu",
        (unsigned long)s, (unsigned long)o);
    CHECK(ms < 1000, "told at once, not by the reap (%ld ms)", (long)ms);

    size = sizeof(ev);
    CHECK(DNSSD_ReadEvent(c.session, &ev, &size) == DNSSD_ERR_STALE,
        "the child's session is no more");

    /* the slot again, for a session of this task: works */
    {
        struct MsgPort *port = CreateMsgPort();
        DNSSDSessionRef mine = NULL;

        CHECK(port != NULL && DNSSD_OpenSessionA(&mine, port, NULL) == DNSSD_OK,
            "a new session opens");
        for (i = 0; mine != NULL && i < 1; i++)
            DNSSD_CloseSession(mine);
        if (port != NULL)
            DeleteMsgPort(port);
    }
    printf("RESULT %d passed, %d failed\n", passes, fails);
    CloseLibrary(DNSSDBase);
    return fails ? RETURN_FAIL : RETURN_OK;
}
