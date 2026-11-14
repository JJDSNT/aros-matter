/*
 * mdns_reg_adapter.h - the responder fixtures' registrations, after
 * bonami.library went (realignment D8).
 *
 * The cases were written for clients of bonami.library: they fill a
 * struct MDNSIPCMsg and register, update, withdraw and are reaped through
 * its port. That port is gone from mdnsd; what the cases test is the
 * responder (probing, conflicts, answers, known answers, subtypes, proxies,
 * goodbyes), which is all still there. This adapter, in the fixture alone,
 * makes their messages canonical registrations (mdnsRegAddCanonical()), as
 * mdns_client.c did, and keeps whose each one is, so that the ownership and
 * reaping cases still mean what they did.
 */
#ifndef MDNS_REG_ADAPTER_H
#define MDNS_REG_ADAPTER_H

#include <string.h>
#include <strings.h>

/* what the cases used of <bonami/mdns.h> and mdns_ipc.h */
#define MDNS_IPC_VERSION        6
#define MDNS_OK                 0
#define MDNSERR_BADPARAM        (-1)
#define MDNSERR_NOMEM           (-2)
#define MDNSERR_DUPLICATE       (-4)
#define MDNSERR_NOTFOUND        (-5)
#define MDNS_MAX_NAME           64
#define MDNS_MAX_TYPE           32
#define MDNS_MAX_BROWSE_TYPE    127
#define MDNS_MAX_DOMAIN         16
#define MDNS_MAX_HOST           64
#define MDNS_MAX_TXT            256
#define MDNS_MAX_SUBTYPE        63
#define MDNS_MAX_SUBTYPES       8
#define MDNS_MAX_TTL            4500
#define MDNS_IPC_REGISTER       1
#define MDNS_IPC_UPDATE         2
#define MDNS_IPC_UNREGISTER     3
#define MDNS_IPC_UPDF_TXT       0x00000001UL

struct MDNSIPCMsg
{
    struct Message  mi_Msg;
    UWORD           mi_Version;
    UWORD           mi_Command;
    LONG            mi_Result;
    APTR            mi_Handle;
    ULONG           mi_Flags;
    char            mi_Name[MDNS_MAX_NAME + 1];
    char            mi_ServiceType[MDNS_MAX_BROWSE_TYPE + 1];
    UWORD           mi_SubtypeCount;
    char            mi_Subtypes[MDNS_MAX_SUBTYPES][MDNS_MAX_SUBTYPE + 1];
    char            mi_Domain[MDNS_MAX_DOMAIN + 1];
    char            mi_HostName[MDNS_MAX_HOST + 1];
    char            mi_TXT[MDNS_MAX_TXT + 1];
    UWORD           mi_Port;
    ULONG           mi_HostAddr;    /* 0xAABBCCDD == A.B.C.D */
    ULONG           mi_TTL;
    ULONG           mi_TaskID;
    struct Task    *mi_Task;
};

/* whose each registration is */
static struct { APTR ref; ULONG owner; } adapter_owners[32];

static ULONG adapter_owner(CONST_APTR ref)
{
    int i;

    for (i = 0; i < 32; i++)
        if (adapter_owners[i].ref == ref)
            return adapter_owners[i].owner;
    return 0;
}

static int adapter_known(CONST_APTR ref)
{
    int i;

    for (i = 0; i < 32; i++)
        if (adapter_owners[i].ref == ref)
            return 1;
    return 0;
}

static void adapter_forget(CONST_APTR ref)
{
    int i;

    for (i = 0; i < 32; i++)
        if (adapter_owners[i].ref == ref)
            adapter_owners[i].ref = NULL;
}

/* "key=value" items with a space between, a space or backslash inside one
 * after a backslash, as TXT data (RFC 6763 section 6). */
static UWORD adapter_txt(const char *text, UBYTE *data, size_t size)
{
    size_t at = 0;

    while (*text) {
        size_t start = at++, n = 0;

        while (*text == ' ')
            text++;
        if (!*text) {
            at = start;
            break;
        }
        while (*text && *text != ' ') {
            if (*text == '\\' && text[1])
                text++;
            if (at < size && n < 255) {
                data[at++] = (UBYTE)*text;
                n++;
            }
            text++;
        }
        data[start] = (UBYTE)n;
    }
    return (UWORD)at;
}

static int adapter_subtype_ok(const char *s)
{
    size_t n = strlen(s), i;

    if (n < 2 || n > MDNS_MAX_SUBTYPE || s[0] != '_')
        return 0;
    for (i = 1; i < n; i++) {
        char c = s[i];

        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || c == '-'))
            return 0;
    }
    return 1;
}

static LONG adapter_add(struct MDNSDaemon *md, struct MDNSIPCMsg *msg)
{
    struct dnssd_reg reg;
    struct dnssd_reg_parts p;
    struct dnssd_model_wire_address address;
    UBYTE type[256], domain[256], subtypes[MDNS_MAX_SUBTYPES * 64];
    UBYTE txt[MDNS_MAX_TXT + 1];
    LONG used, at = 0, i, j, rc;
    ULONG sublen = 0;
    APTR ref;

    if (!msg->mi_Name[0] || !msg->mi_ServiceType[0] || !msg->mi_Port ||
        msg->mi_TTL > MDNS_MAX_TTL ||
        strlen(msg->mi_ServiceType) > MDNS_MAX_TYPE ||
        ((msg->mi_HostName[0] != 0) != (msg->mi_HostAddr != 0)) ||
        mdnsNameToWire(msg->mi_ServiceType, type, sizeof(type), &used) != 0)
        return MDNSERR_BADPARAM;
    memset(&p, 0, sizeof(p));
    p.instance = (const UBYTE *)msg->mi_Name;
    p.instance_len = (ULONG)strlen(msg->mi_Name);
    p.type = type;
    p.type_len = (ULONG)used;
    if (mdnsNameToWire(msg->mi_Domain[0] ? msg->mi_Domain : "local", domain,
                       sizeof(domain), &used) != 0)
        return MDNSERR_BADPARAM;
    p.domain = domain;
    p.domain_len = (ULONG)used;
    for (i = 0; i < msg->mi_SubtypeCount && i < MDNS_MAX_SUBTYPES; i++) {
        size_t n = strlen(msg->mi_Subtypes[i]);

        if (!adapter_subtype_ok(msg->mi_Subtypes[i]))
            return MDNSERR_BADPARAM;
        for (j = 0; j < i; j++)
            if (strcasecmp(msg->mi_Subtypes[i], msg->mi_Subtypes[j]) == 0)
                return MDNSERR_BADPARAM;
        subtypes[sublen++] = (UBYTE)n;
        memcpy(subtypes + sublen, msg->mi_Subtypes[i], n);
        sublen += (ULONG)n;
    }
    p.subtypes = subtypes;
    p.subtypes_len = sublen;
    if (msg->mi_HostName[0]) {
        while (at < MDNS_MAX_HOST && msg->mi_HostName[at] &&
               msg->mi_HostName[at] != '.')
            at++;
        if (msg->mi_HostName[at] &&
            strcasecmp(msg->mi_HostName + at, ".local") != 0 &&
            strcasecmp(msg->mi_HostName + at, ".local.") != 0)
            return MDNSERR_BADPARAM;
        memset(&address, 0, sizeof(address));
        address.family = DNSSD_MODEL_ADDR_IPV4;
        address.length = 4;
        mdnsAddrData(msg->mi_HostAddr, address.bytes);
        p.host = (const UBYTE *)msg->mi_HostName;
        p.host_len = (ULONG)at;
        p.addresses = &address;
        p.address_count = 1;
    }
    p.port = msg->mi_Port;
    if (dnssd_reg_init(&reg, &p) != DNSSD_REG_OK)
        return MDNSERR_BADPARAM;
    rc = mdnsRegAddCanonical(md, &reg, txt,
                             adapter_txt(msg->mi_TXT, txt, sizeof(txt)),
                             msg->mi_TTL, NULL, NULL, &ref);
    if (rc == MDNSD_OK) {
        msg->mi_Handle = ref;
        for (i = 0; i < 32; i++)
            if (!adapter_owners[i].ref) {
                adapter_owners[i].ref = ref;
                adapter_owners[i].owner = msg->mi_TaskID;
                break;
            }
    }
    return rc;
}

static LONG adapter_update(struct MDNSDaemon *md, const struct MDNSIPCMsg *msg)
{
    UBYTE txt[MDNS_MAX_TXT + 1];
    UWORD length = 0;

    if (!msg->mi_Handle || !adapter_known(msg->mi_Handle))
        return MDNSERR_NOTFOUND;
    if (adapter_owner(msg->mi_Handle) != msg->mi_TaskID ||
        msg->mi_TTL > MDNS_MAX_TTL)
        return MDNSERR_BADPARAM;
    if (msg->mi_Flags & MDNS_IPC_UPDF_TXT)
        length = adapter_txt(msg->mi_TXT, txt, sizeof(txt));
    return mdnsRegUpdateRef(md, msg->mi_Handle,
                            (msg->mi_Flags & MDNS_IPC_UPDF_TXT) ? txt : NULL,
                            length, msg->mi_Port, NULL, -1, msg->mi_TTL);
}

static void adapter_remove(struct MDNSDaemon *md, const struct MDNSIPCMsg *msg)
{
    if (msg->mi_Handle && adapter_known(msg->mi_Handle) &&
        adapter_owner(msg->mi_Handle) == msg->mi_TaskID) {
        mdnsRegRemoveRef(md, msg->mi_Handle);
        adapter_forget(msg->mi_Handle);
    }
}

/* the registrations of tasks that ended go (FindTaskByPID() is mocked) */
static void adapter_reap(struct MDNSDaemon *md)
{
    int i;

    for (i = 0; i < 32; i++)
        if (adapter_owners[i].ref && adapter_owners[i].owner &&
            FindTaskByPID(adapter_owners[i].owner) == NULL) {
            mdnsRegRemoveRef(md, adapter_owners[i].ref);
            adapter_owners[i].ref = NULL;
        }
}

#endif
