/* Review fixtures for mdnsd's cache (mdns_cache.c) and dnssd.library's
 * operations (dnssd_server.c): what the bonami.library discovery and query
 * fixtures checked, retired with it (D8), on the code that does that work
 * now - and what was found missing then. Requests are built as
 * dnssd.library builds them (dnssd_ipc_build()), handed to the server as
 * mdnsd hands them, and the events read back are checked as the library's
 * caller would get them (dnssd_model_validate()). Exec, time and the
 * network are the responder fixture's mocks; packets are encoded here.
 * Exit 1: a contract failed.
 */
#define main responder_fixture_main
#include "mdns_responder_rfc.c"
#undef main

#include <stddef.h>
#include "dnssd_host_mock.h"
#include "dnssd_model.h"
#include <dnssd/dnssd.h>

#define CHECK(expr) do { if (!(expr)) { fprintf(stderr, "FAIL %s:%d: %s\n", \
    __func__, __LINE__, #expr); exit(1); } } while (0)

/* Exec and task.resource: one task, no task.resource */
void Forbid(void) {}
void Permit(void) {}
struct Task *FindTask(const char *name) { (void)name; return &owner; }
ULONG GetETaskID(struct Task *task) { return task ? live_task_id : 0; }
void Signal(struct Task *task, ULONG signals) { (void)task; (void)signals; }
APTR OpenResource(CONST_STRPTR name) { (void)name; return NULL; }
BOOL AddTaskNotifyHook(struct Hook *hook) { (void)hook; return FALSE; }
void RemTaskNotifyHook(struct Hook *hook) { (void)hook; }

static struct MDNSDaemon md;
static struct Message notify;           /* the session's, lent at OPEN */
static ULONG session, incarnation;
static UBYTE packet[MDNS_MAX_PACKET];
static size_t at;
static unsigned count;

/* ---- the daemon ---- */

static void init(void)
{
    ticks = 5000;
    live_task_id = 1;
    setup(&md, 0);
    mdnsRegFree(&md);                   /* no service of the responder's */
    md.md_DaemonID = 77;
    md.md_SendIf = -1;                  /* no packet in hand, as in mdnsd */
    CHECK(mdnsCacheInit(&md));
    CHECK(dnssdServerInit(&md, 0));
    packets = questions = 0;
    sent_hook = NULL;
}

static void finish(void)
{
    dnssdServerFree(&md);
    mdnsRegFree(&md);
    mdnsCacheFree(&md);
}

/* a turn of mdnsd's loop, as mdnsd.c runs it */
static void turn(void)
{
    mdnsCacheTick(&md);
    dnssdServerTick(&md);
}

static void later(ULONG t)
{
    ticks += t;
    turn();
}

/* ---- requests, as dnssd.library makes them ---- */

static struct DNSSDIPCMsg *request(UWORD command, const struct dnssd_ipc_parts *parts)
{
    static const struct dnssd_ipc_parts none;
    const size_t head = offsetof(struct DNSSDIPCMsg, dm_Request);
    struct DNSSDIPCMsg *msg;
    size_t need, written;

    if (!parts)
        parts = &none;
    CHECK(dnssd_ipc_measure(parts, &need) == DNSSD_IPC_OK);
    msg = calloc(1, head + need);
    CHECK(msg != NULL);
    CHECK(dnssd_ipc_build(command, parts, &msg->dm_Request, need, &written) ==
          DNSSD_IPC_OK);
    msg->dm_Msg.mn_Length = (UWORD)(head + written);
    msg->dm_Request.session = session;
    msg->dm_Request.incarnation = incarnation;
    msg->dm_Request.task = 1;
    return msg;
}

static LONG call(struct DNSSDIPCMsg *msg)
{
    msg->dm_Request.result = -99;
    dnssdServerMessage(&md, msg);
    return msg->dm_Request.result;
}

static void open_session(void)
{
    struct DNSSDIPCMsg *msg = request(DNSSD_IPC_OPEN, NULL);

    msg->dm_Notify = &notify;
    CHECK(call(msg) == DNSSD_OK);
    session = msg->dm_Request.session;
    incarnation = msg->dm_Request.incarnation;
    free(msg);
}

static void close_session(void)
{
    struct DNSSDIPCMsg *msg = request(DNSSD_IPC_CLOSE, NULL);

    CHECK(call(msg) == DNSSD_OK);
    free(msg);
}

/* a wire name, in storage of its own (four at a time) */
static const UBYTE *wire(const char *text)
{
    static UBYTE names[4][256];
    static int next;
    UBYTE *n = names[next++ & 3];

    name(n, 0, text);
    return n;
}

static uint32_t wire_length(const UBYTE *n)
{
    uint32_t length = 0;

    while (n[length])
        length += n[length] + 1u;
    return length + 1u;
}

/* An operation; its id. timeout 0 for the default, ~0 for no limit. */
static ULONG start(UWORD command, struct dnssd_ipc_parts *p, ULONG timeout,
                   UWORD rrtype, ULONG family)
{
    struct DNSSDIPCMsg *msg = request(command, p);
    ULONG id;

    if (timeout == ~0u) {
        msg->dm_Request.flags = DNSSD_IPC_FLAG_UNTIL_CANCELLED;
    } else {
        msg->dm_Request.timeout = timeout;
    }
    msg->dm_Request.rrtype = rrtype;
    msg->dm_Request.family = family;
    CHECK(call(msg) == DNSSD_OK);
    id = msg->dm_Request.operation;
    free(msg);
    return id;
}

static ULONG browse(const char *type, const char *subtype)
{
    struct dnssd_ipc_parts p;
    UBYTE sub[64];

    memset(&p, 0, sizeof(p));
    p.service_type = wire(type);
    p.service_type_size = wire_length(p.service_type);
    p.domain = wire("local");
    p.domain_size = wire_length(p.domain);
    if (subtype) {
        sub[0] = (UBYTE)strlen(subtype);
        memcpy(sub + 1, subtype, sub[0]);
        p.subtypes = sub;
        p.subtypes_size = 1u + sub[0];
    }
    return start(DNSSD_IPC_BROWSE, &p, 0, 0, 0);
}

static ULONG resolve(const char *instance, const char *type, ULONG timeout)
{
    struct dnssd_ipc_parts p;

    memset(&p, 0, sizeof(p));
    p.instance = (const uint8_t *)instance;
    p.instance_size = (uint32_t)strlen(instance);
    p.service_type = wire(type);
    p.service_type_size = wire_length(p.service_type);
    p.domain = wire("local");
    p.domain_size = wire_length(p.domain);
    return start(DNSSD_IPC_RESOLVE, &p, timeout, 0, 0);
}

static ULONG query(const char *owner, UWORD rrtype, ULONG timeout)
{
    struct dnssd_ipc_parts p;

    memset(&p, 0, sizeof(p));
    p.name = wire(owner);
    p.name_size = wire_length(p.name);
    return start(DNSSD_IPC_QUERY, &p, timeout, rrtype, 0);
}

static ULONG lookup(const char *host, ULONG timeout)
{
    struct dnssd_ipc_parts p;

    memset(&p, 0, sizeof(p));
    p.name = wire(host);
    p.name_size = wire_length(p.name);
    return start(DNSSD_IPC_LOOKUP, &p, timeout, 0, DNSSD_FAMILY_ANY);
}

static ULONG reg(const char *instance, const char *type, UWORD port)
{
    struct dnssd_ipc_parts p;
    struct DNSSDIPCMsg *msg;
    ULONG id;

    memset(&p, 0, sizeof(p));
    p.instance = (const uint8_t *)instance;
    p.instance_size = (uint32_t)strlen(instance);
    p.service_type = wire(type);
    p.service_type_size = wire_length(p.service_type);
    p.domain = wire("local");
    p.domain_size = wire_length(p.domain);
    msg = request(DNSSD_IPC_REGISTER, &p);
    msg->dm_Request.port = port;
    CHECK(call(msg) == DNSSD_OK);
    id = msg->dm_Request.operation;
    free(msg);
    return id;
}

/* ---- events ---- */

static union { struct DNSSDEvent e; UBYTE b[16384]; } got;

/* The next event, checked as the library's caller gets it; NULL for none. */
static const struct DNSSDEvent *next(void)
{
    struct dnssd_ipc_parts p;
    struct DNSSDIPCMsg *msg;
    LONG rc;

    memset(&p, 0, sizeof(p));
    p.reply_room = 12000;
    msg = request(DNSSD_IPC_READ, &p);
    rc = call(msg);
    if (rc == DNSSD_ERR_EMPTY) {
        free(msg);
        return NULL;
    }
    CHECK(rc == DNSSD_OK);
    CHECK(msg->dm_Request.reply.size <= sizeof(got));
    memcpy(got.b, (UBYTE *)&msg->dm_Request + msg->dm_Request.reply.offset,
           msg->dm_Request.reply.size);
    CHECK(dnssd_model_validate(got.b, msg->dm_Request.reply.size) == DNSSD_MODEL_OK);
    CHECK(got.e.de_Size == msg->dm_Request.reply.size);
    free(msg);
    if (getenv("DNSSD_FIXTURE_TRACE"))
        fprintf(stderr, "event op=%lx kind=%u port=%u addresses=%u flags=%lx\n",
                (unsigned long)got.e.de_Operation, got.e.de_Kind, got.e.de_Port,
                got.e.de_AddressCount, (unsigned long)got.e.de_Flags);
    return &got.e;
}

/* The next event of operation op of kind kind, the others passed over. */
static const struct DNSSDEvent *next_of(ULONG op, UWORD kind)
{
    const struct DNSSDEvent *e;

    while ((e = next()) != NULL)
        if (e->de_Operation == op && e->de_Kind == kind)
            return e;
    return NULL;
}

static void drain(void) { while (next()) ; }

static const UBYTE *part(const struct DNSSDEvent *e, const struct DNSSDRef *r)
{
    return r->dr_Size ? (const UBYTE *)e + r->dr_Offset : NULL;
}

static int instance_is(const struct DNSSDEvent *e, const char *text)
{
    return e->de_Instance.dr_Size == strlen(text) &&
           memcmp(part(e, &e->de_Instance), text, strlen(text)) == 0;
}

/* Has e the IPv4 address a.b.c.d? */
static int has4(const struct DNSSDEvent *e, UBYTE a, UBYTE b, UBYTE c, UBYTE d)
{
    const struct DNSSDAddress *x = (const struct DNSSDAddress *)part(e, &e->de_Addresses);
    unsigned i;

    for (i = 0; x && i < e->de_AddressCount; i++)
        if (x[i].da_Family == DNSSD_FAMILY_IPV4 && x[i].da_Bytes[0] == a &&
            x[i].da_Bytes[1] == b && x[i].da_Bytes[2] == c && x[i].da_Bytes[3] == d)
            return 1;
    return 0;
}

/* ---- what other hosts send ---- */

static void begin(void)
{
    memset(packet, 0, sizeof(packet));
    put16(packet + 2, 0x8400);          /* a response, authoritative */
    at = 12;
    count = 0;
}

static void add(const char *owner, UWORD type, UWORD cls, ULONG ttl,
                const UBYTE *data, size_t length)
{
    at = record(packet, at, owner, type, cls, ttl, data, length);
    count++;
}

static void add_ptr(const char *owner, const char *target, ULONG ttl)
{
    UBYTE d[256];

    add(owner, DNS_TYPE_PTR, DNS_CLASS_IN, ttl, d, name(d, 0, target));
}

static void add_srv(const char *owner, UWORD port, const char *host, ULONG ttl)
{
    UBYTE d[300];
    size_t n;

    memset(d, 0, 6);
    put16(d + 4, port);
    n = name(d, 6, host);
    add(owner, DNS_TYPE_SRV, DNS_CLASS_IN_FLUSH, ttl, d, n);
}

static void add_txt(const char *owner, const char *item, ULONG ttl)
{
    UBYTE d[256];

    d[0] = (UBYTE)strlen(item);
    memcpy(d + 1, item, d[0]);
    add(owner, DNS_TYPE_TXT, DNS_CLASS_IN_FLUSH, ttl, d, 1u + d[0]);
}

static void add_a(const char *owner, UBYTE last, ULONG ttl)
{
    const UBYTE d[4] = { 203, 0, 113, last };

    add(owner, DNS_TYPE_A, DNS_CLASS_IN_FLUSH, ttl, d, 4);
}

static void send_from(UWORD port, LONG slot)
{
    put16(packet + 6, (UWORD)count);
    md.md_SendIf = slot;
    mdnsHandlePacket(&md, packet, (LONG)at, 0xcb007101, port);
    md.md_SendIf = -1;
    turn();
}

static void send_packet(void) { send_from(5353, 0); }

/* an instance, all of it, in one response */
static void instance(const char *inst, ULONG ttl, ULONG srvttl, ULONG txtttl,
                     ULONG attl, UBYTE last)
{
    char full[128];

    snprintf(full, sizeof(full), "%s._fx._tcp.local", inst);
    begin();
    add_ptr("_fx._tcp.local", full, ttl);
    add_srv(full, 7000, "peer.local", srvttl);
    add_txt(full, "v=1", txtttl);
    add_a("peer.local", last, attl);
    send_packet();
}

/* ---- questions sent ---- */

static unsigned asked;                  /* questions for watched_name */
static const UBYTE *watched_name;
static unsigned most;                   /* the most questions in a packet */

static void count_questions(LONG index, const UBYTE *pkt, LONG length)
{
    const struct MDNSHeader *h = (const struct MDNSHeader *)pkt;
    LONG offset = sizeof(*h), consumed;
    unsigned i, n = ntohs(h->qdcount);

    (void)index;
    if (ntohs(h->flags) & DNS_FLAG_QR)
        return;
    if (n > most)
        most = n;
    for (i = 0; i < n; i++) {
        struct MDNSQuestion q;

        if (mdnsParseQuestion(pkt, length, offset, &q, &consumed))
            return;
        if (watched_name && mdnsWireNameEqual(q.qwire, watched_name))
            asked++;
        offset += consumed;
    }
}

/* ======================================================================= */

/* A record's time to live is up: what it made goes (RFC 6762 section 10).
 * which: PTR (the browse's REMOVE), SRV (the resolve's REMOVE), A (the
 * resolve's RESOLVED without it), TXT (nothing: never without the TXT). */
static void expire(int which)
{
    ULONG b, r;
    const struct DNSSDEvent *e;

    init();
    open_session();
    b = browse("_fx._tcp", NULL);
    r = resolve("One", "_fx._tcp", ~0u);
    instance("One", which == 0 ? 2 : 120, which == 1 ? 2 : 120,
             which == 3 ? 2 : 120, which == 2 ? 2 : 120, 9);
    e = next_of(b, DNSSD_EVENT_ADD);
    CHECK(e && instance_is(e, "One"));
    later(0);
    drain();
    later(99);
    CHECK(next() == NULL);              /* not yet */
    later(1);
    if (which == 0) {
        e = next_of(b, DNSSD_EVENT_REMOVE);
        CHECK(e && instance_is(e, "One"));
    } else if (which == 1) {
        CHECK(next_of(r, DNSSD_EVENT_REMOVE) != NULL);
    } else if (which == 2) {
        e = next_of(r, DNSSD_EVENT_RESOLVED);
        CHECK(e && e->de_AddressCount == 0);
    } else {
        CHECK(next() == NULL);
    }
    finish();
}

/* A goodbye (TTL 0) ends a record a second later (section 10.1); one
 * announced again within that second stays. */
static void goodbye(int rescue)
{
    ULONG b;

    init();
    open_session();
    b = browse("_fx._tcp", NULL);
    instance("One", 120, 120, 120, 120, 9);
    CHECK(next_of(b, DNSSD_EVENT_ADD) != NULL);
    drain();
    begin();
    add_ptr("_fx._tcp.local", "One._fx._tcp.local", 0);
    send_packet();
    later(49);
    CHECK(next() == NULL);
    if (rescue) {
        begin();
        add_ptr("_fx._tcp.local", "One._fx._tcp.local", 120);
        send_packet();
    }
    later(1);
    later(100);
    if (rescue)
        CHECK(next() == NULL);
    else
        CHECK(next_of(b, DNSSD_EVENT_REMOVE) != NULL);
    finish();
}

/* A cache-flush answer replaces the set a second later (section 10.2): the
 * resolve has both addresses, then the new one alone. */
static void cache_flush(void)
{
    ULONG r;
    const struct DNSSDEvent *e;

    init();
    open_session();
    r = resolve("One", "_fx._tcp", ~0u);
    instance("One", 120, 120, 120, 120, 9);
    e = next_of(r, DNSSD_EVENT_RESOLVED);
    CHECK(e && has4(e, 203, 0, 113, 9));
    later(100);
    begin();
    add_a("peer.local", 10, 120);
    send_packet();
    e = next_of(r, DNSSD_EVENT_RESOLVED);
    CHECK(e && has4(e, 203, 0, 113, 9) && has4(e, 203, 0, 113, 10));
    later(50);
    e = next_of(r, DNSSD_EVENT_RESOLVED);
    CHECK(e && !has4(e, 203, 0, 113, 9) && has4(e, 203, 0, 113, 10) &&
          e->de_AddressCount == 1);
    finish();
}

/* A watched record is asked for again at 80 % of its life and up to 2 %
 * more (section 5.2): not before. */
static void refresh(void)
{
    init();
    open_session();
    browse("_fx._tcp", NULL);
    instance("One", 60, 60, 60, 60, 9);
    drain();
    sent_hook = count_questions;
    watched_name = wire("_fx._tcp.local");
    /* the browse's own question, with its backoff, aside: look at the
     * record's refresh by the counts at 79 % and at 82 % */
    later(2000);
    asked = 0;
    later(370);                         /* 79 % */
    CHECK(asked <= 1);                  /* the backoff's, at most */
    asked = 0;
    later(92);                          /* 82 % */
    CHECK(asked >= 1);
    finish();
}

/* What is no answer is left out (sections 6, 18): another class, a
 * compression loop, a name past its record, another port than 5353; a
 * compressed name that is fine is taken. */
static void robust(int kind)
{
    ULONG b;
    UBYTE d[64];
    size_t n;

    init();
    open_session();
    b = browse("_fx._tcp", NULL);
    begin();
    if (kind == 0) {                    /* compressed target: fine */
        size_t owner = at;

        at = name(packet, at, "_fx._tcp.local");
        put16(packet + at, DNS_TYPE_PTR);
        put16(packet + at + 2, DNS_CLASS_IN);
        put32(packet + at + 4, 120);
        put16(packet + at + 8, 6);
        at += 10;
        packet[at++] = 3; memcpy(packet + at, "One", 3); at += 3;
        packet[at++] = 0xc0; packet[at++] = (UBYTE)owner;
        count = 1;
    } else if (kind == 1) {             /* class 3 */
        n = name(d, 0, "One._fx._tcp.local");
        add("_fx._tcp.local", DNS_TYPE_PTR, 3, 120, d, n);
    } else if (kind == 2) {             /* a pointer to itself */
        size_t rd;

        at = name(packet, at, "_fx._tcp.local");
        put16(packet + at, DNS_TYPE_PTR);
        put16(packet + at + 2, DNS_CLASS_IN);
        put32(packet + at + 4, 120);
        put16(packet + at + 8, 2);
        at += 10;
        rd = at;
        packet[at++] = 0xc0; packet[at++] = (UBYTE)rd;
        count = 1;
    } else if (kind == 3) {             /* the name runs past the record */
        n = name(d, 0, "One._fx._tcp.local");
        add("_fx._tcp.local", DNS_TYPE_PTR, DNS_CLASS_IN, 120, d, n);
        put16(packet + at - n - 2, (UWORD)(n - 4));
    } else {                            /* from port 1234 */
        n = name(d, 0, "One._fx._tcp.local");
        add("_fx._tcp.local", DNS_TYPE_PTR, DNS_CLASS_IN, 120, d, n);
    }
    send_from(kind == 4 ? 1234 : 5353, 0);
    if (kind == 0)
        CHECK(next_of(b, DNSSD_EVENT_ADD) != NULL);
    else
        CHECK(next() == NULL);
    finish();
}

/* The cache has a budget: when it is full, records nobody watches give way
 * first, and a watched instance stays. */
static void budget(void)
{
    ULONG r;
    unsigned i;
    UBYTE big[900];

    init();
    open_session();
    r = resolve("One", "_fx._tcp", ~0u);
    instance("One", 4500, 4500, 4500, 4500, 9);
    CHECK(next_of(r, DNSSD_EVENT_RESOLVED) != NULL);
    memset(big, 'x', sizeof(big));
    big[0] = 255;
    for (i = 0; i < 400; i++) {         /* ~370 KB, the budget 128 KB */
        char owner[64];

        snprintf(owner, sizeof(owner), "Other%u._fy._tcp.local", i);
        begin();
        add(owner, DNS_TYPE_TXT, DNS_CLASS_IN_FLUSH, 4500, big, 256);
        add(owner, DNS_TYPE_TXT, DNS_CLASS_IN_FLUSH, 4500, big + 256, 256);
        add(owner, DNS_TYPE_TXT, DNS_CLASS_IN_FLUSH, 4500, big + 512, 256);
        send_packet();
    }
    CHECK(next_of(r, DNSSD_EVENT_REMOVE) == NULL);
    finish();
}

/* A session that does not read loses events past its queue: it reads
 * DNSSD_EVENT_LOST and starts again. */
static void lost(void)
{
    unsigned i;
    int saw = 0;
    const struct DNSSDEvent *e;

    init();
    open_session();
    browse("_fx._tcp", NULL);
    for (i = 0; i < 80; i++) {
        char inst[32], full[64];

        snprintf(inst, sizeof(inst), "I%u", i);
        snprintf(full, sizeof(full), "%s._fx._tcp.local", inst);
        begin();
        add_ptr("_fx._tcp.local", full, 120);
        send_packet();
    }
    while ((e = next()) != NULL)
        if (e->de_Kind == DNSSD_EVENT_LOST)
            saw = 1;
    CHECK(saw);
    finish();
}

/* A closed session asks for nothing more, and its records are not
 * refreshed. */
static void close_quiet(void)
{
    unsigned before;

    init();
    open_session();
    browse("_fx._tcp", NULL);
    resolve("One", "_fx._tcp", ~0u);
    instance("One", 60, 60, 60, 60, 9);
    drain();
    close_session();
    before = packets;
    later(2500);
    later(50);
    CHECK(packets == before);
    finish();
}

/* The questions due on a link at once go in one query; each is asked again
 * after 1, 2, 4 s (section 5.2), not on every turn. */
static void coalesce(void)
{
    unsigned before;

    init();
    open_session();
    browse("_fx._tcp", NULL);
    browse("_fy._tcp", NULL);
    sent_hook = count_questions;
    most = 0;
    later(6);                           /* the first, within 120 ms */
    CHECK(most == 2);                   /* both in one query */
    before = packets;
    later(10);
    CHECK(packets == before);           /* not again so soon */
    later(40);
    CHECK(packets == before + 1);       /* a second later */
    later(50);
    CHECK(packets == before + 1);       /* then two seconds */
    later(50);
    CHECK(packets == before + 2);
    finish();
}

/* A link that goes takes what was heard on it; the questions are asked
 * again at once on the links there are. */
static void links_reset(void)
{
    ULONG b;
    unsigned before;

    init();
    configure_links(&md, TRUE, TRUE, FALSE);
    open_session();
    b = browse("_fx._tcp", NULL);
    begin();
    add_ptr("_fx._tcp.local", "Two._fx._tcp.local", 120);
    send_from(5353, 1);
    CHECK(next_of(b, DNSSD_EVENT_ADD) != NULL);
    later(300);
    configure_links(&md, FALSE, TRUE, FALSE);
    mdnsCacheLinksChanged(&md);
    before = packets;
    later(6);
    CHECK(packets > before);
    CHECK(next_of(b, DNSSD_EVENT_REMOVE) != NULL);
    finish();
}

/* A browse of a subtype sees the instances that have it, and the leaving
 * of the subtype's PTR, while the instance stays (RFC 6763 section 7.1). */
static void subtype(void)
{
    ULONG b;
    const struct DNSSDEvent *e;

    init();
    open_session();
    b = browse("_fx._tcp", "_s1");
    begin();
    add_ptr("_fx._tcp.local", "One._fx._tcp.local", 120);
    add_ptr("_fx._tcp.local", "Two._fx._tcp.local", 120);
    add_ptr("_s1._sub._fx._tcp.local", "One._fx._tcp.local", 120);
    send_packet();
    e = next_of(b, DNSSD_EVENT_ADD);
    CHECK(e && instance_is(e, "One"));
    CHECK(next_of(b, DNSSD_EVENT_ADD) == NULL);     /* not Two */
    begin();
    add_ptr("_s1._sub._fx._tcp.local", "One._fx._tcp.local", 0);
    send_packet();
    later(50);
    e = next_of(b, DNSSD_EVENT_REMOVE);
    CHECK(e && instance_is(e, "One"));
    finish();
}

/* Record questions: AAAA; PTR, its name uncompressed in RDATA. */
static void query_records(int ptr)
{
    ULONG q;
    const struct DNSSDEvent *e;
    UBYTE d[16] = { 0xfe, 0x80 };
    size_t owner;

    init();
    open_session();
    q = ptr ? query("_fx._tcp.local", DNS_TYPE_PTR, 0) :
              query("peer.local", DNS_TYPE_AAAA, 0);
    begin();
    if (!ptr) {
        d[15] = 9;
        add("peer.local", DNS_TYPE_AAAA, DNS_CLASS_IN_FLUSH, 120, d, 16);
    } else {                            /* its target compressed */
        owner = at;
        at = name(packet, at, "_fx._tcp.local");
        put16(packet + at, DNS_TYPE_PTR);
        put16(packet + at + 2, DNS_CLASS_IN);
        put32(packet + at + 4, 120);
        put16(packet + at + 8, 6);
        at += 10;
        packet[at++] = 3; memcpy(packet + at, "One", 3); at += 3;
        packet[at++] = 0xc0; packet[at++] = (UBYTE)owner;
        count = 1;
    }
    send_packet();
    e = next_of(q, DNSSD_EVENT_RECORD);
    if (!ptr) {
        CHECK(e && e->de_RRType == DNS_TYPE_AAAA && e->de_RData.dr_Size == 16 &&
              part(e, &e->de_RData)[15] == 9);
    } else {
        const UBYTE *target = wire("One._fx._tcp.local");

        CHECK(e && e->de_RData.dr_Size == wire_length(target) &&
              memcmp(part(e, &e->de_RData), target, e->de_RData.dr_Size) == 0);
    }
    finish();
}

/* A question that nothing answers ends with its time. */
static void query_timeout(void)
{
    ULONG q;
    const struct DNSSDEvent *e;

    init();
    open_session();
    q = query("nobody.local", DNS_TYPE_A, 1);
    later(48);
    CHECK(next_of(q, DNSSD_EVENT_END) == NULL);
    later(3);                           /* a second, to the tick */
    e = next_of(q, DNSSD_EVENT_END);
    CHECK(e && e->de_Result == DNSSD_ERR_TIMEOUT);
    finish();
}

/* The host's own name is answered as any other's (Bonami's query engine
 * did; D8 lost it, mdns_host.c puts its records in the cache now); when
 * another host turns out to have it, what this host said of it goes - as a
 * record question, which tells what goes, sees (a lookup tells each address
 * once, as it comes). */
static void announce_host(void);

static void own_host(void)
{
    ULONG l, q;
    const struct DNSSDEvent *e;

    init();
    open_session();
    md.md_HostState = MDNS_NAME_PROBING;
    mdnsHostRestart(&md);
    announce_host();
    l = lookup("arosbox.local", 3);
    e = next_of(l, DNSSD_EVENT_ADDRESS);
    CHECK(e && has4(e, 192, 0, 2, 2));
    drain();
    q = query("arosbox.local", DNS_TYPE_A, 0);
    e = next_of(q, DNSSD_EVENT_RECORD);
    CHECK(e && e->de_RData.dr_Size == 4 && part(e, &e->de_RData)[3] == 2);
    drain();
    /* another host's address for the name: the name is lost */
    begin();
    add_a("arosbox.local", 50, 120);
    send_packet();
    while ((e = next_of(q, DNSSD_EVENT_RECORD)) != NULL)
        if ((e->de_Flags & DNSSD_EVENTF_REMOVED) && e->de_RData.dr_Size == 4 &&
            part(e, &e->de_RData)[0] == 192 && part(e, &e->de_RData)[3] == 2)
            break;
    CHECK(e != NULL);                   /* ours, withdrawn from the cache */
    finish();
}

/* The host's name probed and announced, as mdnsd's loop does it. */
static void announce_host(void)
{
    int step;

    for (step = 0; step < 8; step++) {  /* three probes, then announced */
        mdnsHostTick(&md);
        later(13);
    }
    CHECK(md.md_HostState == MDNS_NAME_ANNOUNCED);
}

/* Is e a record of the IPv4 address a.b.c.d, removed (gone) or not? */
static int a_record(const struct DNSSDEvent *e, int gone, UBYTE a, UBYTE b,
                    UBYTE c, UBYTE d)
{
    const UBYTE *x = part(e, &e->de_RData);

    return e->de_Kind == DNSSD_EVENT_RECORD && e->de_RRType == DNS_TYPE_A &&
           !(e->de_Flags & DNSSD_EVENTF_REMOVED) == !gone &&
           e->de_RData.dr_Size == 4 && x[0] == a && x[1] == b && x[2] == c &&
           x[3] == d;
}

/* The next event of q that is the A record a.b.c.d (gone or not). */
static int saw_a(ULONG q, int gone, UBYTE a, UBYTE b, UBYTE c, UBYTE d)
{
    const struct DNSSDEvent *e;

    while ((e = next_of(q, DNSSD_EVENT_RECORD)) != NULL)
        if (a_record(e, gone, a, b, c, d))
            return 1;
    return 0;
}

/* Each way the host's own records stop being true takes them out of its
 * cache (mdns_host.c: host_forget(), from mdnsHostSetName() and
 * mdnsHostRestart(); a link that goes, in the cache's turn; the goodbye):
 *   restart  the links or their addresses changed: out, and back with the
 *            announcement under what there is now
 *   link     one of two links goes: its address goes, the other's stays
 *   rename   the system names itself otherwise: the old name's go, the new
 *            name has them once announced
 *   goodbye  mdnsd stops: gone a second later (RFC 6762 section 10.1) */
static void own_host_paths(int path)
{
    ULONG q, q2;

    init();
    if (path == 1)
        configure_links(&md, TRUE, TRUE, FALSE);
    open_session();
    md.md_HostState = MDNS_NAME_PROBING;
    mdnsHostRestart(&md);
    announce_host();
    q = query("arosbox.local", DNS_TYPE_A, 0);
    later(0);
    CHECK(saw_a(q, 0, 192, 0, 2, 2));
    if (path == 1)
        CHECK(saw_a(q, 0, 198, 51, 100, 2));
    drain();
    if (path == 0) {
        mdnsHostRestart(&md);
        later(0);
        CHECK(saw_a(q, 1, 192, 0, 2, 2));
        announce_host();
        CHECK(saw_a(q, 0, 192, 0, 2, 2));
    } else if (path == 1) {
        configure_links(&md, FALSE, TRUE, FALSE);
        later(1);
        CHECK(saw_a(q, 1, 198, 51, 100, 2));
        later(100);
        CHECK(!saw_a(q, 1, 192, 0, 2, 2));
    } else if (path == 2) {
        q2 = query("newname.local", DNS_TYPE_A, 0);
        mdnsHostSetName(&md, "newname", 0);
        later(0);
        CHECK(saw_a(q, 1, 192, 0, 2, 2));
        mdnsHostRestart(&md);           /* as a rescan that renamed does */
        announce_host();
        CHECK(saw_a(q2, 0, 192, 0, 2, 2));
    } else {
        mdnsHostGoodbye(&md);
        later(49);
        CHECK(!saw_a(q, 1, 192, 0, 2, 2));
        later(1);
        CHECK(saw_a(q, 1, 192, 0, 2, 2));
    }
    finish();
}

/* A service renamed after a conflict says nothing more under the name it
 * lost: its own records under it leave the cache (they get no goodbye), and
 * a resolve of that name sees the other host's alone. */
static void renamed(void)
{
    ULONG r;
    const struct DNSSDEvent *e;
    int step;

    init();
    open_session();
    reg("Svc", "_fx._tcp", 4000);
    for (step = 0; step < 12; step++) { /* probed, announced */
        mdnsRegTick(&md);
        later(13);
    }
    drain();
    r = resolve("Svc", "_fx._tcp", ~0u);
    later(0);                           /* what the cache has: in the turn */
    e = next_of(r, DNSSD_EVENT_RESOLVED);
    CHECK(e && e->de_Port == 4000);     /* ours, from the cache */
    drain();
    /* another host's SRV under that name: ours becomes "Svc (2)" */
    begin();
    add_srv("Svc._fx._tcp.local", 5000, "peer.local", 120);
    add_txt("Svc._fx._tcp.local", "theirs=1", 120);
    add_a("peer.local", 9, 120);
    send_packet();
    later(50);
    e = next_of(r, DNSSD_EVENT_RESOLVED);
    while (e && e->de_Port != 5000)
        e = next_of(r, DNSSD_EVENT_RESOLVED);
    CHECK(e && e->de_Port == 5000);
    later(100);
    while ((e = next()) != NULL)        /* never ours again */
        CHECK(!(e->de_Operation == r && e->de_Kind == DNSSD_EVENT_RESOLVED &&
                e->de_Port == 4000));
    /* and whoever asks afterwards finds the other host's SRV alone: ours,
     * which no goodbye ended, is not left in the cache */
    {
        ULONG q = query("Svc._fx._tcp.local", DNS_TYPE_SRV, 0);
        int theirs = 0, ours = 0;

        later(0);
        while ((e = next_of(q, DNSSD_EVENT_RECORD)) != NULL) {
            const UBYTE *d = part(e, &e->de_RData);
            UWORD port = d ? (UWORD)((d[4] << 8) | d[5]) : 0;

            if (e->de_Flags & DNSSD_EVENTF_REMOVED)
                continue;
            theirs += port == 5000;
            ours += port == 4000;
        }
        CHECK(theirs == 1 && ours == 0);
    }
    finish();
}

/* The cache's clock wraps: a record still ends when its time is up. */
static void wrap(void)
{
    ULONG b;

    init();
    ticks = 0xffffffd0u;
    open_session();
    b = browse("_fx._tcp", NULL);
    begin();
    add_ptr("_fx._tcp.local", "One._fx._tcp.local", 2);
    send_packet();
    CHECK(next_of(b, DNSSD_EVENT_ADD) != NULL);
    later(100);
    CHECK(next_of(b, DNSSD_EVENT_REMOVE) != NULL);
    finish();
}

int main(int argc, char **argv)
{
    static const struct { const char *name; void (*run)(void); } cases[] = {
        { "cache-flush", cache_flush }, { "refresh", refresh },
        { "budget", budget }, { "lost", lost }, { "close-quiet", close_quiet },
        { "coalesce", coalesce }, { "links-reset", links_reset },
        { "subtype", subtype },
        { "query-timeout", query_timeout }, { "own-host", own_host },
        { "renamed", renamed }, { "clock-wrap", wrap },
    };
    static const char *const expires[] = {
        "expire-ptr", "expire-srv", "expire-a", "expire-txt"
    };
    static const char *const robusts[] = {
        "compressed", "wrong-class", "pointer-cycle", "name-past-rdata",
        "wrong-port"
    };
    size_t i;

    if (argc != 2)
        return 2;
    for (i = 0; i < 4; i++)
        if (!strcmp(argv[1], expires[i])) { expire((int)i); return 0; }
    for (i = 0; i < 5; i++)
        if (!strcmp(argv[1], robusts[i])) { robust((int)i); return 0; }
    if (!strcmp(argv[1], "own-host-restart")) { own_host_paths(0); return 0; }
    if (!strcmp(argv[1], "own-host-link-gone")) { own_host_paths(1); return 0; }
    if (!strcmp(argv[1], "own-host-renamed")) { own_host_paths(2); return 0; }
    if (!strcmp(argv[1], "own-host-goodbye")) { own_host_paths(3); return 0; }
    if (!strcmp(argv[1], "query-aaaa")) { query_records(0); return 0; }
    if (!strcmp(argv[1], "query-ptr")) { query_records(1); return 0; }
    if (!strcmp(argv[1], "goodbye")) { goodbye(0); return 0; }
    if (!strcmp(argv[1], "goodbye-rescued")) { goodbye(1); return 0; }
    for (i = 0; i < sizeof(cases) / sizeof(cases[0]); i++)
        if (!strcmp(argv[1], cases[i].name)) { cases[i].run(); return 0; }
    return 2;
}
