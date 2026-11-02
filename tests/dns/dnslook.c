/*
 * dnslook - print what gethostbyname() gives for each name: "<name> <a.b.c.d>"
 * or "<name> none h_errno=<n>". AROS side of tests/dns/nameserver6.py.
 */
#include <proto/exec.h>
#include <proto/socket.h>
#include <netdb.h>
#include <arpa/inet.h>
#include <stdio.h>

struct Library *SocketBase;

int main(int argc, char **argv)
{
    int i;

    if (!(SocketBase = OpenLibrary("bsdsocket.library", 3))) {
        printf("no bsdsocket.library\n");
        return 20;
    }
    printf("dnslook\n");
    fflush(stdout);
    for (i = 1; i < argc; i++) {
        struct hostent *h = gethostbyname(argv[i]);

        if (h && h->h_addrtype == AF_INET && h->h_addr_list[0])
            printf("%s %s\n", argv[i], Inet_NtoA(*(ULONG *)h->h_addr_list[0]));
        else
            printf("%s none h_errno=%d\n", argv[i], h_errno);
        fflush(stdout);
    }
    CloseLibrary(SocketBase);
    return 0;
}
