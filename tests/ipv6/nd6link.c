/*
 * nd6link - the IPv6 neighbour cache through an interface's life
 * (tests/ipv6/nd6_link.sh).
 *
 *   nd6link add IFNAME
 *       a static entry, fe80::5:5 at 02:00:5e:00:05:05, on IFNAME (RTM_ADD
 *       with RTF_LLINFO and RTF_STATIC, as ndp -s); IFNAME's index goes to
 *       SYS:out/nd6link.index
 *   nd6link list IFNAME LABEL
 *       "LABEL static S dynamic D": the entries GetRouteInfo(AF_INET6,
 *       RTF_LLINFO) lists on IFNAME's index - that of SYS:out/nd6link.index
 *       when IFNAME is gone - set by hand (RTF_STATIC) and learned
 */
#define __CONFIG_ROADSHOW__     /* GetRouteInfo() */
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/socket.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <net/if_dl.h>
#include <net/route.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct Library *SocketBase;

#define ROUNDUP(a) ((a) > 0 ? (1 + (((a) - 1) | (sizeof(long) - 1))) : sizeof(long))
#define INDEX_FILE "SYS:out/nd6link.index"

static unsigned index_of(const char *name)
{
    struct ifreq ifr;
    int s = socket(AF_INET6, SOCK_DGRAM, 0);
    unsigned idx = 0;

    memset(&ifr, 0, sizeof(ifr));
    strncpy(ifr.ifr_name, name, sizeof(ifr.ifr_name) - 1);
    if (s >= 0 && IoctlSocket(s, SIOCGIFINDEX, (char *)&ifr) == 0)
        idx = ifr.ifr_index;
    if (s >= 0)
        CloseSocket(s);
    return idx;
}

static int add_static(unsigned idx)
{
    static const unsigned char mac[6] = { 0x02, 0x00, 0x5e, 0x00, 0x05, 0x05 };
    long buf[256 / sizeof(long)];
    struct rt_msghdr *h = (struct rt_msghdr *)buf;
    struct sockaddr_in6 *dst = (struct sockaddr_in6 *)(h + 1);
    struct sockaddr_dl *sdl;
    int s = socket(PF_ROUTE, SOCK_RAW, 0), len;

    if (s < 0)
        return -1;
    memset(buf, 0, sizeof(buf));
    h->rtm_version = RTM_VERSION;
    h->rtm_type = RTM_ADD;
    h->rtm_flags = RTF_HOST | RTF_LLINFO | RTF_STATIC;
    h->rtm_addrs = RTA_DST | RTA_GATEWAY;
    h->rtm_seq = 1;
    h->rtm_index = idx;
    dst->sin6_len = sizeof(*dst);
    dst->sin6_family = AF_INET6;
    dst->sin6_addr.s6_addr[0] = 0xfe;
    dst->sin6_addr.s6_addr[1] = 0x80;
    dst->sin6_addr.s6_addr[13] = 0x05;
    dst->sin6_addr.s6_addr[15] = 0x05;
    len = sizeof(*h) + ROUNDUP(sizeof(*dst));
    sdl = (struct sockaddr_dl *)((char *)buf + len);
    sdl->sdl_family = AF_LINK;
    sdl->sdl_index = idx;
    sdl->sdl_alen = 6;
    memcpy(LLADDR(sdl), mac, 6);
    sdl->sdl_len = (sdl->sdl_data - (char *)sdl) + 6;
    len += ROUNDUP(sdl->sdl_len);
    h->rtm_msglen = len;
    len = send(s, (char *)buf, len, 0);
    CloseSocket(s);
    return len < 0 ? -1 : 0;
}

int main(int argc, char **argv)
{
    unsigned idx;

    if (argc < 3 || (strcmp(argv[1], "add") != 0 && strcmp(argv[1], "list") != 0) ||
        (strcmp(argv[1], "list") == 0 && argc < 4)) {
        printf("usage: nd6link add IFNAME | nd6link list IFNAME LABEL\n");
        return 5;
    }
    SocketBase = OpenLibrary("bsdsocket.library", 4);
    if (SocketBase == NULL) {
        printf("no bsdsocket.library\n");
        return 10;
    }
    idx = index_of(argv[2]);
    if (strcmp(argv[1], "add") == 0) {
        BPTR f = Open(INDEX_FILE, MODE_NEWFILE);
        char text[16];

        if (f) {
            snprintf(text, sizeof(text), "%u\n", idx);
            Write(f, text, strlen(text));
            Close(f);
        }
        printf("add on %s (index %u): %s\n", argv[2], idx, add_static(idx) == 0 ? "ok" : "failed");
    } else {
        struct rt_msghdr *buf, *h;
        int st = 0, dy = 0;
        char *p;

        if (idx == 0) {                 /* gone: the index it had */
            BPTR f = Open(INDEX_FILE, MODE_OLDFILE);
            char text[16];
            LONG n;

            if (f) {
                n = Read(f, text, sizeof(text) - 1);
                Close(f);
                if (n > 0) {
                    text[n] = 0;
                    idx = atoi(text);
                }
            }
        }
        buf = GetRouteInfo(AF_INET6, RTF_LLINFO);
        if (buf != NULL) {
            for (p = (char *)buf; (h = (struct rt_msghdr *)p)->rtm_msglen != 0; p += h->rtm_msglen) {
                if (!(h->rtm_flags & RTF_LLINFO) || h->rtm_index != idx)
                    continue;
                if (h->rtm_flags & RTF_STATIC)
                    st++;
                else
                    dy++;
            }
            FreeRouteInfo(buf);
        }
        printf("%s static %d dynamic %d (index %u%s)\n", argv[3], st, dy, idx,
               index_of(argv[2]) == 0 ? ", interface gone" : "");
    }
    CloseLibrary(SocketBase);
    return 0;
}
