/*
 * udpdiag - open a socket of each kind and print the errno of those that
 * fail: UDP and TCP over IPv4 and IPv6. On m68k, UDP failed with ENOBUFS
 * while udp_recvspace was above what sbreserve() allows there (B31).
 */
#include <proto/exec.h>
#include <proto/bsdsocket.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <stdio.h>

struct Library *SocketBase = NULL;

static void try(const char *what, int fam, int type)
{
    int s = socket(fam, type, 0);

    if (s < 0)
        printf("%-5s FAIL errno %ld\n", what, (long)Errno());
    else {
        printf("%-5s ok\n", what);
        CloseSocket(s);
    }
}

int main(void)
{
    if (!(SocketBase = OpenLibrary("bsdsocket.library", 4))) {
        printf("no bsdsocket.library\n");
        return 5;
    }
    try("udp4", AF_INET, SOCK_DGRAM);
    try("udp6", AF_INET6, SOCK_DGRAM);
    try("tcp4", AF_INET, SOCK_STREAM);
    try("tcp6", AF_INET6, SOCK_STREAM);
    CloseLibrary(SocketBase);
    return 0;
}
