/*
 * dnssdtest - dnssd.library against a running mdnsd.
 *
 *   dnssdtest NAME [MISSING]
 *
 * Checks the public layout (the same offsets on every CPU but de_UserData's
 * size), the parameter checks, an asynchronous lookup of NAME (addresses
 * with their interface, END OK), a lookup of MISSING (END TIMEOUT), a
 * lookup cancelled at once (nothing after the cancel), the synchronous
 * lookup of both, and that mdnsd keeps no session or operation afterwards.
 * Prints "PASS ..."/"FAIL ..." lines and a summary.
 */
#include <exec/types.h>
#include <dos/dos.h>
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/dnssd.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

struct Library *DNSSDBase;
static int fails, passes;
static ULONG link_index;        /* the link the host's addresses came by */

#define CHECK(cond, ...) do { \
    if (cond) { passes++; printf("PASS "); } else { fails++; printf("FAIL "); } \
    printf(__VA_ARGS__); printf("\n"); } while (0)

static void
print_address(const struct DNSSDAddress *a)
{
    char text[64];

    if (a->da_Family == DNSSD_FAMILY_IPV4) {
        snprintf(text, sizeof(text), "%u.%u.%u.%u", a->da_Bytes[0], a->da_Bytes[1],
            a->da_Bytes[2], a->da_Bytes[3]);
    } else {
        int i, n = 0;

        for (i = 0; i < 16; i += 2) {
            n += snprintf(text + n, sizeof(text) - n, "%s%x", i ? ":" : "",
                (a->da_Bytes[i] << 8) | a->da_Bytes[i + 1]);
        }
    }
    printf("  addr family=%u len=%u if=%lu %s\n", a->da_Family, a->da_Length,
        (unsigned long)a->da_Interface, text);
}

static void
layout(void)
{
    CHECK(offsetof(struct DNSSDEvent, de_Kind) == 6 &&
          offsetof(struct DNSSDEvent, de_Result) == 12 &&
          offsetof(struct DNSSDEvent, de_RRType) == 28 &&
          offsetof(struct DNSSDEvent, de_Port) == 32 &&
          offsetof(struct DNSSDEvent, de_Name) == 40 &&
          offsetof(struct DNSSDEvent, de_Instance) == 48 &&
          offsetof(struct DNSSDEvent, de_TXT) == 80 &&
          offsetof(struct DNSSDEvent, de_Addresses) == 96 &&
          offsetof(struct DNSSDEvent, de_UserData) == 104 &&
          sizeof(struct DNSSDEvent) == 104 + sizeof(IPTR),
          "layout DNSSDEvent (size %u)", (unsigned)sizeof(struct DNSSDEvent));
    CHECK(sizeof(struct DNSSDAddress) == 24 &&
          offsetof(struct DNSSDAddress, da_Interface) == 4 &&
          offsetof(struct DNSSDAddress, da_Bytes) == 8,
          "layout DNSSDAddress (size %u)", (unsigned)sizeof(struct DNSSDAddress));
}

#define PART(e, ref) ((const char *)(e) + (e)->ref.dr_Offset)

/*
 * Reads events of one operation until one of kind (or the deadline);
 * returns the event (in buf) or NULL. Prints each.
 */
static struct DNSSDEvent *
wait_kind(DNSSDSessionRef s, struct MsgPort *port, UWORD kind, int seconds,
          UBYTE *buf, ULONG max)
{
    int ticks = seconds * 10;

    while (ticks-- > 0) {
        for (;;) {
            ULONG size = max;
            struct DNSSDEvent *e = (struct DNSSDEvent *)buf;
            LONG rc = DNSSD_ReadEvent(s, e, &size);

            if (rc != DNSSD_OK) {
                break;
            }
            printf("  event %u if=%lu name=%.*s instance=%.*s type=%.*s domain=%.*s"
                   " target=%.*s port=%u txt=%lu rdata=%lu addrs=%u\n",
                e->de_Kind, (unsigned long)e->de_Interface,
                (int)e->de_Name.dr_Size, PART(e, de_Name),
                (int)e->de_Instance.dr_Size, PART(e, de_Instance),
                (int)e->de_Type.dr_Size, PART(e, de_Type),
                (int)e->de_Domain.dr_Size, PART(e, de_Domain),
                (int)e->de_Target.dr_Size, PART(e, de_Target),
                e->de_Port, (unsigned long)e->de_TXT.dr_Size,
                (unsigned long)e->de_RData.dr_Size, e->de_AddressCount);
            if (e->de_Kind == kind) {
                return e;
            }
        }
        if (GetMsg(port) == NULL) {
            Delay(5);
        }
    }
    return NULL;
}

/* Does the TXT data hold this string? */
static int
txt_has(const struct DNSSDEvent *e, const char *item)
{
    const UBYTE *t = (const UBYTE *)PART(e, de_TXT);
    ULONG at = 0, n = strlen(item);

    while (at < e->de_TXT.dr_Size) {
        if (t[at] == n && memcmp(t + at + 1, item, n) == 0) {
            return 1;
        }
        at += 1 + t[at];
    }
    return 0;
}

/* Browse TYPE finds INSTANCE; Resolve gives its port, TXT and addresses;
 * the host's A record by QueryRecord. */
static void
services(const char *host, const char *type, const char *instance,
         unsigned port, const char *txt)
{
    static UBYTE buf[4096];
    struct MsgPort *mp = CreateMsgPort();
    DNSSDSessionRef s = NULL;
    DNSSDOperationRef op = NULL;
    struct DNSSDEvent *e;
    int found = 0, n;

    if (DNSSD_OpenSessionA(&s, mp, NULL) != DNSSD_OK) {
        CHECK(0, "services: open");
        DeleteMsgPort(mp);
        return;
    }
    CHECK(DNSSD_Browse(s, type, &op, TAG_DONE) == DNSSD_OK, "browse %s", type);
    for (n = 0; n < 8 && !found; n++) {
        e = wait_kind(s, mp, DNSSD_EVENT_ADD, 8, buf, sizeof(buf));
        if (e == NULL) {
            break;
        }
        found = e->de_Instance.dr_Size == strlen(instance) &&
            memcmp(PART(e, de_Instance), instance, strlen(instance)) == 0 &&
            e->de_Interface != 0 && e->de_Domain.dr_Size == 5;
    }
    CHECK(found, "browse %s: ADD %s", type, instance);
    DNSSD_Cancel(op);

    CHECK(DNSSD_Resolve(s, instance, type, &op, TAG_DONE) == DNSSD_OK,
        "resolve %s", instance);
    e = wait_kind(s, mp, DNSSD_EVENT_RESOLVED, 8, buf, sizeof(buf));
    CHECK(e != NULL && e->de_Port == port && txt_has(e, txt) &&
          e->de_AddressCount > 0 && e->de_Target.dr_Size > 0,
          "resolve %s: port %u, \"%s\", addresses", instance, port, txt);
    DNSSD_Cancel(op);

    CHECK(DNSSD_QueryRecord(s, host, 1, &op, DNSSD_Timeout, 4, TAG_DONE) == DNSSD_OK,
        "query %s A", host);
    e = wait_kind(s, mp, DNSSD_EVENT_ADD, 6, buf, sizeof(buf));
    CHECK(e != NULL && e->de_RRType == 1 && e->de_RData.dr_Size == 4,
        "query %s A: 4 bytes", host);
    DNSSD_Cancel(op);
    DNSSD_CloseSession(s);
    DeleteMsgPort(mp);
}

/* Waits for and reads the session's events until op's END (or the
 * deadline in seconds); returns how many addresses and the END result. */
static int
drain(DNSSDSessionRef s, struct MsgPort *port, int seconds, LONG *endResult,
      ULONG *events, IPTR userData)
{
    union {
        struct DNSSDEvent e;
        UBYTE b[1024];
    } buf;
    int addresses = 0, ticks = seconds * 10;

    *endResult = 1;
    *events = 0;
    while (ticks-- > 0) {
        for (;;) {
            ULONG size = sizeof(buf);
            LONG rc = DNSSD_ReadEvent(s, &buf.e, &size);

            if (rc == DNSSD_ERR_EMPTY) {
                break;
            }
            if (rc != DNSSD_OK) {
                printf("  read: %ld\n", (long)rc);
                return addresses;
            }
            (*events)++;
            if (buf.e.de_Size != size || buf.e.de_Version != DNSSD_EVENT_VERSION ||
                buf.e.de_Sequence != *events || buf.e.de_UserData != userData) {
                printf("  bad event header size=%lu/%lu version=%u seq=%lu\n",
                    (unsigned long)buf.e.de_Size, (unsigned long)size,
                    buf.e.de_Version, (unsigned long)buf.e.de_Sequence);
                fails++;
            }
            if (buf.e.de_Kind == DNSSD_EVENT_ADDRESS) {
                ULONG i;

                printf("  ADDRESS %.*s ttl=%lu\n", (int)buf.e.de_Name.dr_Size,
                    (char *)buf.b + buf.e.de_Name.dr_Offset, (unsigned long)buf.e.de_TTL);
                for (i = 0; i < buf.e.de_AddressCount; i++) {
                    print_address((struct DNSSDAddress *)(buf.b +
                        buf.e.de_Addresses.dr_Offset) + i);
                    addresses++;
                }
            } else if (buf.e.de_Kind == DNSSD_EVENT_END) {
                printf("  END %ld\n", (long)buf.e.de_Result);
                *endResult = buf.e.de_Result;
                return addresses;
            } else {
                printf("  kind %u\n", buf.e.de_Kind);
            }
        }
        /* the notification, or 100 ms */
        if (GetMsg(port) == NULL) {
            Delay(5);
        }
    }
    return addresses;
}

static void
status(ULONG *inc, ULONG *sessions, ULONG *ops)
{
    LONG rc = DNSSD_GetStatus(DNSSD_Status_Incarnation, inc,
        DNSSD_Status_Sessions, sessions, DNSSD_Status_Operations, ops, TAG_DONE);

    if (rc != DNSSD_OK) {
        printf("  status: %ld\n", (long)rc);
    }
}



static void
v4(struct DNSSDAddress *a, int last)
{
    memset(a, 0, sizeof(*a));
    a->da_Family = DNSSD_FAMILY_IPV4;
    a->da_Length = 4;
    a->da_Bytes[0] = 192; a->da_Bytes[1] = 168; a->da_Bytes[2] = 166; a->da_Bytes[3] = last;
}

static void
v6(struct DNSSDAddress *a, int linklocal, ULONG zone)
{
    memset(a, 0, sizeof(*a));
    a->da_Family = DNSSD_FAMILY_IPV6;
    a->da_Length = 16;
    if (linklocal) {
        a->da_Bytes[0] = 0xfe; a->da_Bytes[1] = 0x80;
    } else {
        a->da_Bytes[0] = 0x20; a->da_Bytes[1] = 0x01; a->da_Bytes[2] = 0x0d; a->da_Bytes[3] = 0xb8;
    }
    a->da_Bytes[15] = 0x77;
    a->da_Interface = zone;
}

/* Reads events for up to seconds; counts ADD and REMOVE of rdata (len
 * bytes), or of any record if rdata is NULL. */
static void
count_records(DNSSDSessionRef s, struct MsgPort *port, int seconds,
              const UBYTE *rdata, ULONG len, int *adds, int *removes)
{
    static UBYTE buf[4096];
    int ticks = seconds * 10;

    while (ticks-- > 0) {
        for (;;) {
            ULONG size = sizeof(buf);
            struct DNSSDEvent *e = (struct DNSSDEvent *)buf;

            if (DNSSD_ReadEvent(s, e, &size) != DNSSD_OK) {
                break;
            }
            if (e->de_Kind != DNSSD_EVENT_ADD && e->de_Kind != DNSSD_EVENT_REMOVE) {
                continue;
            }
            printf("  %s type %u %lu bytes if=%lu\n",
                e->de_Kind == DNSSD_EVENT_ADD ? "ADD" : "REMOVE", e->de_RRType,
                (unsigned long)e->de_RData.dr_Size, (unsigned long)e->de_Interface);
            if (rdata == NULL || (e->de_RData.dr_Size == len &&
                    memcmp(PART(e, de_RData), rdata, len) == 0)) {
                if (e->de_Kind == DNSSD_EVENT_ADD) {
                    (*adds)++;
                } else {
                    (*removes)++;
                }
            }
        }
        if (GetMsg(port) == NULL) {
            Delay(5);
        }
    }
}

/*
 * Register for another host, both families: an IPv4, a global IPv6 and a
 * link-local IPv6 with its zone. Its AAAA are found here, all the
 * addresses come with Resolve; the IPv4 replaced by an update goes
 * (REMOVE) and the new one comes; bad address sets are refused; a host
 * name another host has ends the registration with CONFLICT. Left
 * registered (*held) for the host to look at.
 */
static void
proxy(const char *type, const char *hostName, DNSSDSessionRef s, struct MsgPort *mp,
      DNSSDOperationRef *held)
{
    static UBYTE buf[4096];
    static const UBYTE old4[4] = { 192, 168, 166, 77 }, new4[4] = { 192, 168, 166, 78 };
    struct DNSSDAddress a[3], bad[9];
    DNSSDOperationRef op = NULL, q = NULL, c = NULL;
    struct DNSSDEvent *e;
    int adds = 0, removes = 0, i, v4n = 0, v6n = 0;
    ULONG k;

    v4(&a[0], 77);
    v6(&a[1], 0, 0);
    v6(&a[2], 1, link_index);
    CHECK(link_index != 0, "proxy: the link's index (%lu)", (unsigned long)link_index);

    v6(&bad[0], 1, 0);
    CHECK(DNSSD_Register(s, "Bad.Proxy", type, 7781, &op, DNSSD_Host, (IPTR)"badproxy",
        DNSSD_HostAddress, (IPTR)&bad[0], TAG_DONE) == DNSSD_ERR_BADPARAM,
        "proxy: link-local with no zone refused");
    {
        struct TagItem t[12];

        t[0].ti_Tag = DNSSD_Host;
        t[0].ti_Data = (IPTR)"badproxy";
        for (i = 0; i < 9; i++) {
            v4(&bad[i], 100 + i);
            t[1 + i].ti_Tag = DNSSD_HostAddress;
            t[1 + i].ti_Data = (IPTR)&bad[i];
        }
        t[10].ti_Tag = TAG_DONE;
        CHECK(DNSSD_RegisterA(s, "Bad.Proxy", type, 7781, &op, t) == DNSSD_ERR_BADPARAM,
            "proxy: nine addresses refused");
    }

    CHECK(DNSSD_Register(s, "Proxy.Test", type, 7780, held, DNSSD_Host, (IPTR)"proxyhost",
        DNSSD_HostAddress, (IPTR)&a[0], DNSSD_HostAddress, (IPTR)&a[1],
        DNSSD_HostAddress, (IPTR)&a[2], TAG_DONE) == DNSSD_OK, "proxy: register, 3 addresses");
    e = wait_kind(s, mp, DNSSD_EVENT_REGISTERED, 10, buf, sizeof(buf));
    CHECK(e != NULL, "proxy: registered");

    CHECK(DNSSD_Resolve(s, "Proxy.Test", type, &op, TAG_DONE) == DNSSD_OK, "proxy: resolve");
    e = wait_kind(s, mp, DNSSD_EVENT_RESOLVED, 6, buf, sizeof(buf));
    if (e != NULL) {
        const struct DNSSDAddress *got = (const struct DNSSDAddress *)PART(e, de_Addresses);

        for (k = 0; k < e->de_AddressCount; k++) {
            print_address(&got[k]);
            v4n += got[k].da_Family == DNSSD_FAMILY_IPV4;
            v6n += got[k].da_Family == DNSSD_FAMILY_IPV6;
        }
    }
    CHECK(e != NULL && e->de_Target.dr_Size == 15 &&
          memcmp(PART(e, de_Target), "proxyhost.local", 15) == 0 && v4n == 1 && v6n == 2,
          "proxy: resolve gives proxyhost.local, 1 IPv4 + 2 IPv6 (%d, %d)", v4n, v6n);
    DNSSD_Cancel(op);

    CHECK(DNSSD_QueryRecord(s, "proxyhost.local", 28, &q, TAG_DONE) == DNSSD_OK, "proxy: AAAA query");
    count_records(s, mp, 4, NULL, 0, &adds, &removes);
    CHECK(adds == 2, "proxy: 2 AAAA (%d)", adds);
    DNSSD_Cancel(q);

    CHECK(DNSSD_QueryRecord(s, "proxyhost.local", 1, &q, TAG_DONE) == DNSSD_OK, "proxy: A query");
    adds = removes = 0;
    count_records(s, mp, 3, old4, 4, &adds, &removes);
    CHECK(adds == 1, "proxy: A 192.168.166.77");
    v4(&a[0], 78);
    CHECK(DNSSD_Update(*held, DNSSD_HostAddress, (IPTR)&a[0], DNSSD_HostAddress, (IPTR)&a[1],
        DNSSD_HostAddress, (IPTR)&a[2], TAG_DONE) == DNSSD_OK, "proxy: update the addresses");
    {
        int addNew = 0, rmNew = 0, addOld = 0, rmOld = 0;
        static UBYTE ev[4096];
        int ticks = 40;

        while (ticks-- > 0) {
            for (;;) {
                ULONG size = sizeof(ev);
                struct DNSSDEvent *x = (struct DNSSDEvent *)ev;

                if (DNSSD_ReadEvent(s, x, &size) != DNSSD_OK) {
                    break;
                }
                if (x->de_RData.dr_Size != 4) {
                    continue;
                }
                if (memcmp(PART(x, de_RData), new4, 4) == 0) {
                    addNew += x->de_Kind == DNSSD_EVENT_ADD;
                    rmNew += x->de_Kind == DNSSD_EVENT_REMOVE;
                } else if (memcmp(PART(x, de_RData), old4, 4) == 0) {
                    addOld += x->de_Kind == DNSSD_EVENT_ADD;
                    rmOld += x->de_Kind == DNSSD_EVENT_REMOVE;
                }
            }
            if (GetMsg(mp) == NULL) {
                Delay(5);
            }
        }
        CHECK(addNew == 1 && rmOld == 1 && rmNew == 0,
            "proxy: after the update .78 ADD (%d), .77 REMOVE (%d)", addNew, rmOld);
    }
    DNSSD_Cancel(q);

    if (hostName != NULL) {
        struct DNSSDAddress x;

        v4(&x, 99);
        CHECK(DNSSD_Register(s, "Conflict.Test", type, 7782, &c, DNSSD_Host, (IPTR)hostName,
            DNSSD_HostAddress, (IPTR)&x, TAG_DONE) == DNSSD_OK, "proxy: register for %s", hostName);
        e = wait_kind(s, mp, DNSSD_EVENT_END, 12, buf, sizeof(buf));
        CHECK(e != NULL && e->de_Result == DNSSD_ERR_CONFLICT,
            "proxy: %s is the host's: CONFLICT (%ld)", hostName,
            e != NULL ? (long)e->de_Result : 0L);
        DNSSD_Cancel(c);
    }
}

/* A TXT of 2000 bytes (RFC 6763 section 6.2 allows up to 8900): registered,
 * and resolved here whole. */
static void
big_txt(const char *type, DNSSDSessionRef s, struct MsgPort *mp, DNSSDOperationRef *held)
{
    static UBYTE txt[2000], buf[4096];
    DNSSDOperationRef op = NULL;
    struct DNSSDEvent *e;
    int i;

    for (i = 0; i < 2000; i += 200) {
        txt[i] = 199;
        memset(txt + i + 1, 'a' + i / 200, 199);
        txt[i + 1] = 'k';
        txt[i + 2] = '=';
    }
    CHECK(DNSSD_Register(s, "Big.Txt", type, 7783, held, DNSSD_TXT, (IPTR)txt,
        DNSSD_TXTLength, sizeof(txt), TAG_DONE) == DNSSD_OK, "big TXT: register 2000 bytes");
    e = wait_kind(s, mp, DNSSD_EVENT_REGISTERED, 8, buf, sizeof(buf));
    CHECK(e != NULL, "big TXT: registered");
    CHECK(DNSSD_Resolve(s, "Big.Txt", type, &op, TAG_DONE) == DNSSD_OK, "big TXT: resolve");
    e = wait_kind(s, mp, DNSSD_EVENT_RESOLVED, 6, buf, sizeof(buf));
    CHECK(e != NULL && e->de_TXT.dr_Size == sizeof(txt) &&
          memcmp(PART(e, de_TXT), txt, sizeof(txt)) == 0, "big TXT: resolved whole (%lu)",
          e != NULL ? (unsigned long)e->de_TXT.dr_Size : 0UL);
    DNSSD_Cancel(op);
}

static const char *hostName;    /* the host on the link's name, its first label */

/*
 * Register: an instance with a dot, binary TXT and a subtype; it is found
 * here (Browse, Resolve), updated, refused twice, renamed on a conflict
 * with the host's, and held for HOLD seconds with SYS:out/registered
 * written, for the host to look at it.
 */
static void
registration(const char *type, const char *hostType, int hold)
{
    static UBYTE buf[4096];
    static const UBYTE txt1[] = { 6, 'v','e','r','s','=','2', 6, 'b','i','n','=',0x00,0xff };
    static const UBYTE txt2[] = { 6, 'v','e','r','s','=','3' };
    struct MsgPort *mp = CreateMsgPort();
    DNSSDSessionRef s = NULL;
    DNSSDOperationRef reg = NULL, dup = NULL, conflict = NULL, op = NULL, proxyOp = NULL;
    DNSSDOperationRef bigOp = NULL;
    struct DNSSDEvent *e;
    BPTR fh;
    int n, found = 0;

    if (DNSSD_OpenSessionA(&s, mp, NULL) != DNSSD_OK) {
        CHECK(0, "register: open");
        return;
    }
    CHECK(DNSSD_Register(s, "Reg.Test", type, 7777, &reg, DNSSD_TXT, (IPTR)txt1,
        DNSSD_TXTLength, sizeof(txt1), DNSSD_Subtype, (IPTR)"_sub1", TAG_DONE) == DNSSD_OK,
        "register Reg.Test %s", type);
    e = wait_kind(s, mp, DNSSD_EVENT_REGISTERED, 8, buf, sizeof(buf));
    CHECK(e != NULL && e->de_Instance.dr_Size == 8 &&
          memcmp(PART(e, de_Instance), "Reg.Test", 8) == 0 && e->de_Port == 7777,
          "registered as Reg.Test");
    CHECK(DNSSD_Register(s, "Reg.Test", type, 7778, &dup, TAG_DONE) == DNSSD_ERR_EXISTS,
        "the same again: EXISTS");

    CHECK(DNSSD_Browse(s, type, &op, DNSSD_Subtype, (IPTR)"_sub1", TAG_DONE) == DNSSD_OK,
        "browse own subtype");
    for (n = 0; n < 4 && !found; n++) {
        e = wait_kind(s, mp, DNSSD_EVENT_ADD, 4, buf, sizeof(buf));
        found = e != NULL && e->de_Instance.dr_Size == 8 &&
            memcmp(PART(e, de_Instance), "Reg.Test", 8) == 0;
    }
    CHECK(found, "browse finds own Reg.Test by subtype");
    DNSSD_Cancel(op);
    CHECK(DNSSD_Resolve(s, "Reg.Test", type, &op, TAG_DONE) == DNSSD_OK, "resolve own");
    e = wait_kind(s, mp, DNSSD_EVENT_RESOLVED, 6, buf, sizeof(buf));
    CHECK(e != NULL && e->de_Port == 7777 && e->de_TXT.dr_Size == sizeof(txt1) &&
          memcmp(PART(e, de_TXT), txt1, sizeof(txt1)) == 0,
          "resolve own: port 7777, binary TXT whole");
    CHECK(DNSSD_Update(reg, DNSSD_TXT, (IPTR)txt2, DNSSD_TXTLength, sizeof(txt2),
        TAG_DONE) == DNSSD_OK, "update TXT");
    e = wait_kind(s, mp, DNSSD_EVENT_RESOLVED, 6, buf, sizeof(buf));
    CHECK(e != NULL && txt_has(e, "vers=3"), "resolve own after the update: vers=3");
    DNSSD_Cancel(op);

    if (hostType != NULL) {
        CHECK(DNSSD_Register(s, "HostTest", hostType, 7779, &conflict, TAG_DONE) == DNSSD_OK,
            "register HostTest, which the host has");
        e = wait_kind(s, mp, DNSSD_EVENT_REGISTERED, 12, buf, sizeof(buf));
        CHECK(e != NULL && e->de_Instance.dr_Size == 12 &&
              memcmp(PART(e, de_Instance), "HostTest (2)", 12) == 0,
              "renamed HostTest (2)");
    }
    proxy(type, hostType != NULL ? hostName : NULL, s, mp, &proxyOp);
    big_txt(type, s, mp, &bigOp);
    fh = Open("SYS:out/registered", MODE_NEWFILE);
    if (fh != BNULL) {
        Close(fh);
    }
    Delay(hold * 50);
    DNSSD_Cancel(reg);
    if (proxyOp != NULL) {
        DNSSD_Cancel(proxyOp);
    }
    if (bigOp != NULL) {
        DNSSD_Cancel(bigOp);
    }
    if (conflict != NULL) {
        DNSSD_Cancel(conflict);
    }
    DNSSD_CloseSession(s);
    DeleteMsgPort(mp);
}

int
main(int argc, char **argv)
{
    const char *name = argc > 1 ? argv[1] : "arosbox.local";
    const char *missing = argc > 2 ? argv[2] : "nobody-here.local";
    const char *type = argc > 3 ? argv[3] : NULL;
    struct MsgPort *port;
    DNSSDSessionRef s = NULL;
    DNSSDOperationRef op = NULL;
    struct DNSSDAddress addrs[8];
    ULONG count, inc = 0, inc2 = 0, sessions = 99, ops = 99, events;
    LONG rc, end;
    int n;

    layout();
    DNSSDBase = OpenLibrary("dnssd.library", 1);
    if (DNSSDBase == NULL) {
        printf("FAIL no dnssd.library\n");
        return 20;
    }
    port = CreateMsgPort();

    status(&inc, &sessions, &ops);
    CHECK(inc != 0, "status before: incarnation %lu sessions %lu operations %lu",
        (unsigned long)inc, (unsigned long)sessions, (unsigned long)ops);

    CHECK(DNSSD_OpenSessionA(NULL, port, NULL) == DNSSD_ERR_BADPARAM, "open without session");
    rc = DNSSD_OpenSessionA(&s, port, NULL);
    CHECK(rc == DNSSD_OK && s != NULL, "open (%ld)", (long)rc);
    if (s == NULL) {
        goto out;
    }
    CHECK(DNSSD_LookupAddress(s, "", &op, TAG_DONE) == DNSSD_ERR_BADNAME, "lookup empty name");
    CHECK(DNSSD_LookupAddress(s, "a..b", &op, TAG_DONE) == DNSSD_ERR_BADNAME, "lookup empty label");
    CHECK(DNSSD_LookupAddress(s, name, &op, DNSSD_Timeout, 0, TAG_DONE) == DNSSD_ERR_BADPARAM,
        "lookup timeout 0");

    rc = DNSSD_LookupAddress(s, name, &op, DNSSD_Timeout, 3, DNSSD_UserData, 0x1234, TAG_DONE);
    CHECK(rc == DNSSD_OK, "lookup %s (%ld)", name, (long)rc);
    n = drain(s, port, 6, &end, &events, 0x1234);
    CHECK(n > 0 && end == DNSSD_OK, "lookup %s: %d addresses, end %ld", name, n, (long)end);
    DNSSD_Cancel(op);

    rc = DNSSD_LookupAddress(s, name, &op, DNSSD_Family, DNSSD_FAMILY_IPV6, TAG_DONE);
    n = drain(s, port, 6, &end, &events, 0);
    CHECK(rc == DNSSD_OK && n > 0 && end == DNSSD_OK, "lookup %s IPv6 only: %d", name, n);
    DNSSD_Cancel(op);

    rc = DNSSD_LookupAddress(s, missing, &op, DNSSD_Timeout, 2, TAG_DONE);
    n = drain(s, port, 5, &end, &events, 0);
    CHECK(rc == DNSSD_OK && n == 0 && end == DNSSD_ERR_TIMEOUT, "lookup %s: end %ld", missing,
        (long)end);
    DNSSD_Cancel(op);

    rc = DNSSD_LookupAddress(s, missing, &op, DNSSD_Timeout, 1, TAG_DONE);
    CHECK(DNSSD_Cancel(op) == DNSSD_OK, "cancel at once");
    n = drain(s, port, 3, &end, &events, 0);
    CHECK(events == 0, "nothing after the cancel (%lu events)", (unsigned long)events);

    status(&inc2, &sessions, &ops);
    CHECK(inc2 == inc && sessions >= 1 && ops == 0, "status open: sessions %lu operations %lu",
        (unsigned long)sessions, (unsigned long)ops);

    /* an operation left running is ended by the close */
    DNSSD_LookupAddress(s, missing, &op, DNSSD_Timeout, 10, TAG_DONE);
    DNSSD_CloseSession(s);
    s = NULL;
    CHECK(GetMsg(port) == NULL, "port empty after close");
    status(&inc2, &sessions, &ops);
    CHECK(sessions == 0 && ops == 0, "status closed: sessions %lu operations %lu",
        (unsigned long)sessions, (unsigned long)ops);

    count = 8;
    rc = DNSSD_LookupAddressSync(name, addrs, &count, NULL);
    for (n = 0; n < (int)count; n++) {
        print_address(&addrs[n]);
    }
    CHECK(rc == DNSSD_OK && count > 0, "sync %s (%ld): %lu", name, (long)rc, (unsigned long)count);
    count = 8;
    rc = DNSSD_LookupAddressSync(missing, addrs, &count, DNSSD_Timeout, 1, TAG_DONE);
    CHECK(rc == DNSSD_ERR_NOTFOUND && count == 0, "sync %s (%ld)", missing, (long)rc);
    count = 1;
    rc = DNSSD_LookupAddressSync(name, addrs, &count, DNSSD_Family, DNSSD_FAMILY_IPV4, TAG_DONE);
    CHECK(rc == DNSSD_OK && count == 1 && addrs[0].da_Family == DNSSD_FAMILY_IPV4,
        "sync %s IPv4, one slot (%ld)", name, (long)rc);
    if (rc == DNSSD_OK && count == 1) {
        link_index = addrs[0].da_Interface;
    }
    status(&inc2, &sessions, &ops);
    CHECK(sessions == 0 && ops == 0, "status after sync: sessions %lu operations %lu",
        (unsigned long)sessions, (unsigned long)ops);
    {
        /* "palerma.local": "palerma" */
        static char label[64];
        int k;

        for (k = 0; k < 63 && name[k] != '\0' && name[k] != '.'; k++) {
            label[k] = name[k];
        }
        label[k] = '\0';
        hostName = label;
    }
    if (type != NULL) {
        services(name, type, "HostTest", 9999, "vers=1");
        services(name, type, "Dot.Test", 9998, "path=/a b");
        registration("_arostest._tcp", type, 20);
    }
out:
    if (s != NULL) {
        DNSSD_CloseSession(s);
    }
    DeleteMsgPort(port);
    CloseLibrary(DNSSDBase);
    printf("dnssdtest: %d passed, %d failed\n", passes, fails);
    return fails ? 10 : 0;
}
