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
    status(&inc2, &sessions, &ops);
    CHECK(sessions == 0 && ops == 0, "status after sync: sessions %lu operations %lu",
        (unsigned long)sessions, (unsigned long)ops);
    if (type != NULL) {
        services(name, type, "HostTest", 9999, "vers=1");
        services(name, type, "Dot.Test", 9998, "path=/a b");
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
