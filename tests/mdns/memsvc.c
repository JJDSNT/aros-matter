/*
 * memsvc - what N registered services cost in memory, mdnsd and
 * dnssd.library together, as the system sees it (AvailMem).
 *
 *   memsvc N [HOLD]
 *
 * Prints the free memory (all, and the largest block) before; registers N
 * services "Mem 1".."Mem N" of _memsvc._tcp, in as many sessions as needed
 * (DNSSD_SESSION_OPERATIONS each), and waits until every one is
 * REGISTERED (60 s at most); prints the free memory then and after HOLD
 * seconds (default 5: the announcements done); cancels all, closes the
 * sessions, and prints it once more, a second later. Lines:
 *   mem before <free> <largest>
 *   mem registered <n> of <N> <free> <largest> <seconds>
 *   mem held <free> <largest>
 *   mem after <free> <largest>
 * The cost of the services is before - held; what is not given back,
 * before - after.
 */
#include <exec/types.h>
#include <exec/memory.h>
#include <dos/dos.h>
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/dnssd.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef DNSSD_SESSION_OPERATIONS
#define DNSSD_SESSION_OPERATIONS 24
#endif
#define PER_SESSION     (DNSSD_SESSION_OPERATIONS - 2)
#define MAX_SERVICES    200
#define MAX_SESSIONS    ((MAX_SERVICES + PER_SESSION - 1) / PER_SESSION)

struct Library *DNSSDBase;

static void
mem(const char *what)
{
    printf("mem %s %lu %lu\n", what, (unsigned long)AvailMem(MEMF_ANY),
        (unsigned long)AvailMem(MEMF_ANY | MEMF_LARGEST));
}

/* Reads every event waiting in the sessions; returns how many were
 * REGISTERED. */
static int
drain(DNSSDSessionRef *s, int sessions)
{
    union {
        struct DNSSDEvent e;
        UBYTE b[2048];
    } buf;
    int i, registered = 0;

    for (i = 0; i < sessions; i++) {
        for (;;) {
            ULONG size = sizeof(buf);

            if (DNSSD_ReadEvent(s[i], &buf.e, &size) != DNSSD_OK) {
                break;
            }
            if (buf.e.de_Kind == DNSSD_EVENT_REGISTERED) {
                registered++;
            } else if (buf.e.de_Kind == DNSSD_EVENT_END) {
                printf("end event, result %ld\n", (long)buf.e.de_Result);
            }
        }
    }
    return registered;
}

int
main(int argc, char **argv)
{
    static DNSSDSessionRef s[MAX_SESSIONS];
    static DNSSDOperationRef op[MAX_SERVICES];
    struct MsgPort *mp;
    int n = argc > 1 ? atoi(argv[1]) : 1;
    int hold = argc > 2 ? atoi(argv[2]) : 5;
    int sessions, i, registered = 0, ticks = 0;
    char name[32];

    if (n < 0 || n > MAX_SERVICES) {
        printf("memsvc N [HOLD]: N from 0 to %d\n", MAX_SERVICES);
        return 20;
    }
    DNSSDBase = OpenLibrary("dnssd.library", 0);
    mp = CreateMsgPort();
    if (DNSSDBase == NULL || mp == NULL) {
        printf("no dnssd.library\n");
        return 20;
    }
    sessions = (n + PER_SESSION - 1) / PER_SESSION;
    Delay(50);
    mem("before");
    for (i = 0; i < sessions; i++) {
        if (DNSSD_OpenSessionA(&s[i], mp, NULL) != DNSSD_OK) {
            printf("session %d: no\n", i + 1);
            sessions = i;
            break;
        }
    }
    for (i = 0; i < n && i / PER_SESSION < sessions; i++) {
        LONG rc;

        snprintf(name, sizeof(name), "Mem %d", i + 1);
        rc = DNSSD_Register(s[i / PER_SESSION], name, "_memsvc._tcp",
            (UWORD)(9000 + i), &op[i], TAG_DONE);
        if (rc != DNSSD_OK) {
            printf("register %d: %ld\n", i + 1, (long)rc);
            op[i] = NULL;
        }
    }
    while (registered < n && ticks < 60 * 50) {
        registered += drain(s, sessions);
        if (registered < n) {
            Delay(10);
            ticks += 10;
        }
    }
    printf("mem registered %d of %d %lu %lu %d\n", registered, n,
        (unsigned long)AvailMem(MEMF_ANY),
        (unsigned long)AvailMem(MEMF_ANY | MEMF_LARGEST), ticks / 50);
    Delay(hold * 50);
    drain(s, sessions);
    mem("held");
    for (i = 0; i < n; i++) {
        if (op[i] != NULL) {
            DNSSD_Cancel(op[i]);
        }
    }
    for (i = 0; i < sessions; i++) {
        drain(&s[i], 1);
        DNSSD_CloseSession(s[i]);
    }
    Delay(50);
    mem("after");
    DeleteMsgPort(mp);
    CloseLibrary(DNSSDBase);
    return 0;
}
