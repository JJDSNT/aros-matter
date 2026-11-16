/*
 * resolvtest - the system resolver's .local names (AROSTCP api/res_mdns.c),
 * AROS side of tests/mdns/resolver.sh.
 *
 * Usage: resolvtest NAME...        each NAME through the three APIs
 *        resolvtest -c NAME PORT   getaddrinfo(), then a TCP connect() to
 *                                  each address it gives
 *        resolvtest -k TASK        Ctrl-C to the task of that name (mdnsd's
 *                                  is "mdns"): "kill TASK sent|none"
 *        resolvtest -i IF...       "if IF N": the interface index of each
 *        resolvtest -r NAME N      N look-ups (getaddrinfo, gethostbyname)
 *                                  after one: "rep NAME N <bytes>" - how
 *                                  much less free memory there is after them
 *        resolvtest -s NAME...     the most of this task's stack each NAME's
 *                                  look-ups take (gethostbyname(),
 *                                  gethostbyname2(), getaddrinfo()), the
 *                                  free part painted before and read after:
 *                                  "stack NAME <size> <most used>"
 *        resolvtest -S SIZE NAME...  the same in a process of its own with a
 *                                  stack of exactly SIZE bytes, opening its
 *                                  own bsdsocket.library: "stack4 NAME
 *                                  <size> <at entry> <most used> <left>" -
 *                                  what the look-ups took is most - entry
 *        resolvtest -T ADDR NAME...  a UDP datagram "mark" to ADDR port 9,
 *                                  then gethostbyname() of each NAME, with
 *                                  the system time each started at: "M
 *                                  <secs>.<micros>", "T NAME <secs>.<micros>
 *                                  <ms> found|none" - in a capture taken
 *                                  meanwhile the datagram gives the offset
 *                                  between the two clocks
 *        resolvtest -b NAME        gethostbyname() and getaddrinfo() with
 *                                  Ctrl-C already pending: "brk NAME <ms>
 *                                  h_errno=N errno=E gai=G"
 *
 * For each NAME:
 *   hbn  NAME <ms> a.b.c.d ...         gethostbyname()
 *   hbn  NAME <ms> none h_errno=N
 *   hbn2 NAME <ms> x:y::z ...          gethostbyname2(AF_INET6) (miami.library)
 *   hbn2 NAME <ms> none h_errno=N
 *   gai  NAME <ms> 4:a.b.c.d 6:x::y%IF ...   getaddrinfo(AF_UNSPEC, SOCK_STREAM);
 *                                      %IF is sin6_scope_id when not 0
 *   gai  NAME <ms> error N
 * With -c: "conn ADDR ok" or "conn ADDR errno=N" for each address.
 */
#include <proto/exec.h>
#include <proto/dos.h>
#include <dos/dostags.h>
#include <proto/timer.h>
#include <proto/bsdsocket.h>
#include <proto/miami.h>
#include <bsdsocket/socketbasetags.h>
#include <devices/timer.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <net/if.h>
#include <exec/memory.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct Library *SocketBase = NULL, *MiamiBase = NULL;
struct Device *TimerBase = NULL;
static struct timerequest treq;
static LONG herrno, eno;

static ULONG
now_ms(void)
{
    struct timeval tv;

    GetSysTime(&tv);
    return (ULONG)tv.tv_secs * 1000 + tv.tv_micro / 1000;
}

static void
text6(const struct in6_addr *a, ULONG scope, char *out, size_t size)
{
    inet_ntop(AF_INET6, a, out, size);
    if (scope != 0)
        snprintf(out + strlen(out), size - strlen(out), "%%%lu", (unsigned long)scope);
}

static void
by_name(const char *name)
{
    struct hostent *h;
    struct addrinfo hints, *res = NULL, *ai;
    char text[80];
    ULONG t;
    LONG rc;
    int i;

    t = now_ms();
    h = gethostbyname((STRPTR)name);
    printf("hbn %s %lu", name, (unsigned long)(now_ms() - t));
    if (h && h->h_addrtype == AF_INET)
        for (i = 0; h->h_addr_list[i]; i++)
            printf(" %s", Inet_NtoA(*(ULONG *)h->h_addr_list[i]));
    else
        printf(" none h_errno=%ld", (long)herrno);
    printf("\n");

    t = now_ms();
    h = gethostbyname2((STRPTR)name, AF_INET6);
    printf("hbn2 %s %lu", name, (unsigned long)(now_ms() - t));
    if (h && h->h_addrtype == AF_INET6)
        for (i = 0; h->h_addr_list[i]; i++) {
            inet_ntop(AF_INET6, h->h_addr_list[i], text, sizeof(text));
            printf(" %s", text);
        }
    else
        printf(" none h_errno=%ld", (long)herrno);
    printf("\n");

    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    t = now_ms();
    rc = getaddrinfo((STRPTR)name, NULL, &hints, &res);
    printf("gai %s %lu", name, (unsigned long)(now_ms() - t));
    if (rc != 0)
        printf(" error %ld", (long)rc);
    for (ai = res; rc == 0 && ai; ai = ai->ai_next) {
        if (ai->ai_family == AF_INET) {
            printf(" 4:%s", Inet_NtoA(((struct sockaddr_in *)ai->ai_addr)->sin_addr.s_addr));
        } else {
            struct sockaddr_in6 *s6 = (struct sockaddr_in6 *)ai->ai_addr;

            text6(&s6->sin6_addr, s6->sin6_scope_id, text, sizeof(text));
            printf(" 6:%s", text);
        }
    }
    if (res)
        freeaddrinfo(res);
    printf("\n");
    fflush(stdout);
}

static void
connect_all(const char *name, const char *port)
{
    struct addrinfo hints, *res = NULL, *ai;
    char text[80];
    LONG rc;

    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    rc = getaddrinfo((STRPTR)name, (STRPTR)port, &hints, &res);
    if (rc != 0) {
        printf("conn %s gai error %ld\n", name, (long)rc);
        return;
    }
    for (ai = res; ai; ai = ai->ai_next) {
        LONG s = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);

        if (ai->ai_family == AF_INET)
            snprintf(text, sizeof(text), "%s",
                Inet_NtoA(((struct sockaddr_in *)ai->ai_addr)->sin_addr.s_addr));
        else
            text6(&((struct sockaddr_in6 *)ai->ai_addr)->sin6_addr,
                ((struct sockaddr_in6 *)ai->ai_addr)->sin6_scope_id, text, sizeof(text));
        if (s < 0) {
            printf("conn %s socket errno=%ld\n", text, (long)eno);
            continue;
        }
        if (connect(s, ai->ai_addr, ai->ai_addrlen) == 0)
            printf("conn %s ok\n", text);
        else
            printf("conn %s errno=%ld\n", text, (long)eno);
        CloseSocket(s);
        fflush(stdout);
    }
    freeaddrinfo(res);
}

/*
 * The stack below the caller's frame, painted with a pattern up to a
 * margin under this function's own frame; after the look-ups, the lowest
 * byte no longer the pattern says how deep they went - with everything they
 * call (bsdsocket.library, the resolver, dnssd.library) and the task
 * switches, which use the task's stack too.
 */
#define PAINT 0xa5

static void __attribute__((noinline))
paint(UBYTE *lower)
{
    volatile UBYTE here;
    UBYTE *p;

    IPTR top = (IPTR)&here - 128;   /* this frame and what it calls stay clear */

    for (p = lower; (IPTR)p < top; p++)
        *p = PAINT;
}

static void
stack_of(const char *name)
{
    struct Task *me = FindTask(NULL);
    UBYTE *lower = (UBYTE *)me->tc_SPLower, *upper = (UBYTE *)me->tc_SPUpper, *p;
    struct addrinfo hints, *res = NULL;

    paint(lower);
    gethostbyname((STRPTR)name);
    gethostbyname2((STRPTR)name, AF_INET6);
    memset(&hints, 0, sizeof(hints));
    hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo((STRPTR)name, NULL, &hints, &res) == 0 && res)
        freeaddrinfo(res);
    for (p = lower; p < upper && *p == PAINT; p++)
        ;
    printf("stack %s %lu %lu\n", name, (unsigned long)(upper - lower),
           (unsigned long)(upper - p));
    fflush(stdout);
}

/* -S: the child's job and what it found */
static const char *child_name;
static struct Task *child_parent;
static ULONG child_size, child_entry, child_most;
static BYTE child_ok;

static void
child(void)
{
    struct Library *SocketBase, *MiamiBase;
    struct Task *me = FindTask(NULL);
    UBYTE *lower = (UBYTE *)me->tc_SPLower, *upper = (UBYTE *)me->tc_SPUpper, *p;
    volatile UBYTE here;
    struct addrinfo hints, *res = NULL;

    /* painted first, from this frame down: nothing has used it yet */
    paint(lower);
    child_size = upper - lower;
    child_entry = upper - (UBYTE *)&here;
    child_ok = 0;
    if ((SocketBase = OpenLibrary((STRPTR)"bsdsocket.library", 4)) != NULL) {
        if ((MiamiBase = OpenLibrary((STRPTR)"miami.library", 0)) != NULL) {
            gethostbyname((STRPTR)child_name);
            gethostbyname2((STRPTR)child_name, AF_INET6);
            memset(&hints, 0, sizeof(hints));
            hints.ai_socktype = SOCK_STREAM;
            if (getaddrinfo((STRPTR)child_name, NULL, &hints, &res) == 0 && res)
                freeaddrinfo(res);
            CloseLibrary(MiamiBase);
            child_ok = 1;
        }
        CloseLibrary(SocketBase);
    }
    for (p = lower; p < upper && *p == PAINT; p++)
        ;
    child_most = upper - p;
    /* the parent unloads this code once told: told with the task switch
     * off, which stays off until this task is gone */
    Forbid();
    Signal(child_parent, SIGBREAKF_CTRL_F);
}

static void
stack_in_child(const char *name, ULONG size)
{
    child_name = name;
    child_parent = FindTask(NULL);
    SetSignal(0, SIGBREAKF_CTRL_F);
    if (CreateNewProcTags(NP_Entry, (IPTR)child, NP_StackSize, size,
                          NP_Name, (IPTR)"resolvtest stack", TAG_DONE) == NULL) {
        printf("stack4 %s no process\n", name);
        return;
    }
    Wait(SIGBREAKF_CTRL_F);
    printf("stack4 %s %lu %lu %lu %ld%s\n", name, (unsigned long)child_size,
           (unsigned long)child_entry, (unsigned long)child_most,
           (long)child_size - (long)child_most, child_ok ? "" : " (no library)");
    fflush(stdout);
}

int
main(int argc, char **argv)
{
    int i;

    if (!(SocketBase = OpenLibrary((STRPTR)"bsdsocket.library", 4)) ||
        !(MiamiBase = OpenLibrary((STRPTR)"miami.library", 0))) {
        printf("no bsdsocket.library / miami.library\n");
        return 20;
    }
    SocketBaseTags(SBTM_SETVAL(SBTC_HERRNOLONGPTR), (IPTR)&herrno,
                   SBTM_SETVAL(SBTC_ERRNOLONGPTR), (IPTR)&eno, TAG_DONE);
    if (OpenDevice((STRPTR)TIMERNAME, UNIT_MICROHZ, (struct IORequest *)&treq, 0) != 0) {
        printf("no timer.device\n");
        return 20;
    }
    TimerBase = treq.tr_node.io_Device;
    if (argc == 4 && strcmp(argv[1], "-c") == 0)
        connect_all(argv[2], argv[3]);
    else if (argc >= 4 && strcmp(argv[1], "-S") == 0) {
        for (i = 3; i < argc; i++)
            stack_in_child(argv[i], (ULONG)atol(argv[2]));
    } else if (argc >= 3 && strcmp(argv[1], "-s") == 0) {
        for (i = 2; i < argc; i++)
            stack_of(argv[i]);
    } else if (argc == 3 && strcmp(argv[1], "-k") == 0) {
        struct Task *t;

        Forbid();
        if ((t = FindTask((STRPTR)argv[2])) != NULL)
            Signal(t, SIGBREAKF_CTRL_C);
        Permit();
        printf("kill %s %s\n", argv[2], t ? "sent" : "none");
    } else if (argc >= 3 && strcmp(argv[1], "-i") == 0) {
        for (i = 2; i < argc; i++)
            printf("if %s %lu\n", argv[i], (unsigned long)if_nametoindex((STRPTR)argv[i]));
    } else if (argc == 4 && strcmp(argv[1], "-r") == 0) {
        struct addrinfo hints, *res;
        int n = atoi(argv[3]), k;
        IPTR before = 0;

        memset(&hints, 0, sizeof(hints));
        hints.ai_socktype = SOCK_STREAM;
        for (k = 0; k <= n; k++) {
            if (k == 1)
                before = AvailMem(MEMF_ANY);
            res = NULL;
            if (getaddrinfo((STRPTR)argv[2], NULL, &hints, &res) == 0 && res)
                freeaddrinfo(res);
            gethostbyname((STRPTR)argv[2]);
        }
        printf("rep %s %d %ld\n", argv[2], n, (long)(before - AvailMem(MEMF_ANY)));
    } else if (argc >= 4 && strcmp(argv[1], "-T") == 0) {
        struct sockaddr_in to;
        struct timeval m;
        int s = socket(AF_INET, SOCK_DGRAM, 0);

        memset(&to, 0, sizeof(to));
        to.sin_len = sizeof(to);
        to.sin_family = AF_INET;
        to.sin_port = htons(9);
        to.sin_addr.s_addr = inet_addr((STRPTR)argv[2]);
        GetSysTime(&m);
        sendto(s, (APTR)"mark", 4, 0, (struct sockaddr *)&to, sizeof(to));
        CloseSocket(s);
        printf("M %lu.%06lu\n", (unsigned long)m.tv_secs, (unsigned long)m.tv_micro);
        for (i = 3; i < argc; i++) {
            struct timeval a, b;
            struct hostent *h;

            GetSysTime(&a);
            h = gethostbyname((STRPTR)argv[i]);
            GetSysTime(&b);
            printf("T %s %lu.%06lu %lu %s\n", argv[i], (unsigned long)a.tv_secs,
                   (unsigned long)a.tv_micro,
                   (unsigned long)((b.tv_secs - a.tv_secs) * 1000 +
                                   ((LONG)b.tv_micro - (LONG)a.tv_micro) / 1000),
                   h ? "found" : "none");
        }
    } else if (argc == 3 && strcmp(argv[1], "-b") == 0) {
        struct addrinfo hints, *res = NULL;
        struct hostent *h;
        LONG rc, e1, h1;
        ULONG t = now_ms();

        SetSignal(SIGBREAKF_CTRL_C, SIGBREAKF_CTRL_C);
        h = gethostbyname((STRPTR)argv[2]);
        h1 = herrno;
        e1 = eno;
        memset(&hints, 0, sizeof(hints));
        hints.ai_socktype = SOCK_STREAM;
        SetSignal(SIGBREAKF_CTRL_C, SIGBREAKF_CTRL_C);
        rc = getaddrinfo((STRPTR)argv[2], NULL, &hints, &res);
        if (res)
            freeaddrinfo(res);
        SetSignal(0, SIGBREAKF_CTRL_C);
        printf("brk %s %lu %s h_errno=%ld errno=%ld gai=%ld\n", argv[2],
               (unsigned long)(now_ms() - t), h ? "found" : "none",
               (long)h1, (long)e1, (long)rc);
    }
    else
        for (i = 1; i < argc; i++)
            by_name(argv[i]);
    CloseDevice((struct IORequest *)&treq);
    CloseLibrary(MiamiBase);
    CloseLibrary(SocketBase);
    return 0;
}
