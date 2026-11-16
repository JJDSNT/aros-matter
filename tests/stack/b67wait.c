/*
 * b67wait - change signals the stack task sends (B67), with the stack's
 * fault injection (tests/stack/repro/b67-busy.patch: the stack task takes
 * the base list's semaphore as busy for every new change, so each one is
 * left pending for the core's slow tick).
 *
 *   b67wait host NAME...   sets the host name to each NAME through AROSTCP's
 *                          ARexx port (rexx_sethostname(), in the NETTRACE
 *                          task - not the stack task: no host name change
 *                          comes from it, so the injection does not touch
 *                          this one), one after the other; then: when the
 *                          SBTC_SIG_HOSTNAME_CHANGE_MASK signal came, whether
 *                          another came in the 1.5 s after it, and
 *                          gethostname()
 *   b67wait addr IF ADDR   adds ADDR/32 to IF (SIOCAIFADDR); the signal of
 *                          the add comes from this task and is taken; then:
 *                          when the SBTC_SIG_ADDRESS_CHANGE_MASK signal of
 *                          its conflict detection ending came (the stack
 *                          task's, from its ARP timer), within 8 s, and the
 *                          address's IN_IFF_* flags then; the address is
 *                          deleted after
 *
 * Prints "first <ms>|none", "again yes|no", and the name or the flags.
 */
#define __CONFIG_ROADSHOW__
#include <exec/types.h>
#include <exec/ports.h>
#include <rexx/storage.h>
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/socket.h>
#include <proto/rexxsyslib.h>
#include <bsdsocket/socketbasetags.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <netinet/in.h>
#include <netinet/in_var.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>

struct Library *SocketBase;
struct RxsLib *RexxSysBase;

static int rexx(const char *cmd)
{
    struct MsgPort *reply, *port;
    struct RexxMsg *rm;
    int rc = -1;

    if ((reply = CreateMsgPort()) == NULL)
        return -1;
    rm = CreateRexxMsg(reply, NULL, NULL);
    if (rm != NULL && (rm->rm_Args[0] = (IPTR)CreateArgstring((STRPTR)cmd, strnlen(cmd, 300))) != 0) {
        rm->rm_Action = RXCOMM;
        Forbid();
        port = FindPort((STRPTR)"AROSTCP");
        if (port != NULL)
            PutMsg(port, &rm->rm_Node);
        Permit();
        if (port != NULL) {
            WaitPort(reply);
            GetMsg(reply);
            rc = (int)rm->rm_Result1;
        }
        DeleteArgstring((UBYTE *)rm->rm_Args[0]);
    }
    if (rm != NULL)
        DeleteRexxMsg(rm);
    DeleteMsgPort(reply);
    return rc;
}

/* Milliseconds until a signal in mask, by 20 ms, -1 after max ms. */
static int wait_ms(ULONG mask, int max)
{
    int t;

    for (t = 0; t <= max; t += 20) {
        if (SetSignal(0, mask) & mask)
            return t;
        Delay(1);
    }
    return -1;
}

static int alias(int add, const char *ifname, const char *addr)
{
    int s = socket(AF_INET, SOCK_DGRAM, 0), r;

    if (s < 0)
        return -1;
    if (add) {
        struct in_aliasreq ifra;

        memset(&ifra, 0, sizeof(ifra));
        snprintf(ifra.ifra_name, sizeof(ifra.ifra_name), "%s", ifname);
        ifra.ifra_addr.sin_len = ifra.ifra_mask.sin_len = sizeof(struct sockaddr_in);
        ifra.ifra_addr.sin_family = ifra.ifra_mask.sin_family = AF_INET;
        ifra.ifra_addr.sin_addr.s_addr = inet_addr(addr);
        ifra.ifra_mask.sin_addr.s_addr = inet_addr("255.255.255.255");
        r = IoctlSocket(s, SIOCAIFADDR, (char *)&ifra);
    } else {
        struct ifreq ifr;
        struct sockaddr_in *sin = (struct sockaddr_in *)&ifr.ifr_addr;

        memset(&ifr, 0, sizeof(ifr));
        snprintf(ifr.ifr_name, sizeof(ifr.ifr_name), "%s", ifname);
        sin->sin_len = sizeof(*sin);
        sin->sin_family = AF_INET;
        sin->sin_addr.s_addr = inet_addr(addr);
        r = IoctlSocket(s, SIOCDIFADDR, (char *)&ifr);
    }
    CloseSocket(s);
    return r;
}

/* The address's IN_IFF_* flags (SIOCGIFAFLAG_IN), or -1. */
static int aflags(const char *ifname, const char *addr)
{
    struct ifreq ifr;
    struct sockaddr_in *sin = (struct sockaddr_in *)&ifr.ifr_addr;
    int s = socket(AF_INET, SOCK_DGRAM, 0), r;

    if (s < 0)
        return -1;
    memset(&ifr, 0, sizeof(ifr));
    snprintf(ifr.ifr_name, sizeof(ifr.ifr_name), "%s", ifname);
    sin->sin_len = sizeof(*sin);
    sin->sin_family = AF_INET;
    sin->sin_addr.s_addr = inet_addr(addr);
    r = IoctlSocket(s, SIOCGIFAFLAG_IN, (char *)&ifr);
    CloseSocket(s);
    return r == 0 ? ifr.ifr_addrflags : -1;
}

int main(int argc, char **argv)
{
    char cmd[300], name[300];
    BYTE sig;
    ULONG mask;
    int i, first, again;

    if (argc < 3)
        return 20;
    SocketBase = OpenLibrary("bsdsocket.library", 4);
    RexxSysBase = (struct RxsLib *)OpenLibrary("rexxsyslib.library", 0);
    if (SocketBase == NULL || RexxSysBase == NULL || (sig = AllocSignal(-1)) == -1)
        return 20;
    mask = 1UL << sig;
    if (strcmp(argv[1], "host") == 0) {
        SocketBaseTags(SBTM_SETVAL(SBTC_SIG_HOSTNAME_CHANGE_MASK), mask, TAG_END);
        SetSignal(0, mask);
        for (i = 2; i < argc; i++) {
            snprintf(cmd, sizeof(cmd), "SET HOSTNAME=%s", argv[i]);
            if (rexx(cmd) != 0)
                printf("rexx %s failed\n", cmd);
        }
        first = wait_ms(mask, 3000);
        again = first >= 0 ? wait_ms(mask, 1500) : -1;
        name[0] = '\0';
        gethostname(name, sizeof(name));
        printf("host first %s%d again %s name %s\n", first < 0 ? "none " : "", first,
            again >= 0 ? "yes" : "no", name);
        SocketBaseTags(SBTM_SETVAL(SBTC_SIG_HOSTNAME_CHANGE_MASK), 0, TAG_END);
    } else if (strcmp(argv[1], "addr") == 0 && argc > 3) {
        SocketBaseTags(SBTM_SETVAL(SBTC_SIG_ADDRESS_CHANGE_MASK), mask, TAG_END);
        if (alias(1, argv[2], argv[3]) != 0)
            printf("add %s failed\n", argv[3]);
        SetSignal(0, mask);             /* the add's, sent by this task */
        printf("addr flags at once %d\n", aflags(argv[2], argv[3]));
        first = wait_ms(mask, 8000);
        printf("addr first %s%d flags then %d\n", first < 0 ? "none " : "", first,
            aflags(argv[2], argv[3]));
        alias(0, argv[2], argv[3]);
        SocketBaseTags(SBTM_SETVAL(SBTC_SIG_ADDRESS_CHANGE_MASK), 0, TAG_END);
    }
    FreeSignal(sig);
    CloseLibrary((struct Library *)RexxSysBase);
    CloseLibrary(SocketBase);
    return 0;
}
