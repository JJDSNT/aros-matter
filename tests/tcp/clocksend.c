/*
 * clocksend - AROS's uptime, sent to the host over UDP, for the clock bench
 * (tests/tcp/clock_probe.py): every 250 ms for SECS seconds, a datagram
 * with GetUpTime() in milliseconds as decimal text.
 *
 * Usage: clocksend HOST-IPV4 PORT SECS
 */
#include <proto/exec.h>
#include <proto/dos.h>
#include <proto/timer.h>
#include <proto/bsdsocket.h>
#include <devices/timer.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct Library *SocketBase;
struct Device *TimerBase;

int main(int argc, char **argv)
{
    struct MsgPort *mp;
    struct timerequest *tr;
    struct sockaddr_in a;
    struct timeval tv;
    char buf[32];
    long secs, i;
    int s;

    if (argc < 4 || !(SocketBase = OpenLibrary("bsdsocket.library", 4)))
        return 20;
    mp = CreateMsgPort();
    tr = (struct timerequest *)CreateIORequest(mp, sizeof(*tr));
    if (!tr || OpenDevice("timer.device", UNIT_MICROHZ, (struct IORequest *)tr, 0) != 0)
        return 20;
    TimerBase = tr->tr_node.io_Device;
    s = socket(AF_INET, SOCK_DGRAM, 0);
    memset(&a, 0, sizeof(a));
    a.sin_len = sizeof(a);
    a.sin_family = AF_INET;
    a.sin_port = htons(atoi(argv[2]));
    a.sin_addr.s_addr = inet_addr(argv[1]);
    secs = atol(argv[3]);
    for (i = 0; i < secs * 4; i++) {
        GetUpTime(&tv);
        sprintf(buf, "%lu", (unsigned long)(tv.tv_secs * 1000 + tv.tv_micro / 1000));
        sendto(s, buf, strlen(buf), 0, (struct sockaddr *)&a, sizeof(a));
        tr->tr_node.io_Command = TR_ADDREQUEST;
        tr->tr_time.tv_secs = 0;
        tr->tr_time.tv_micro = 250000;
        DoIO((struct IORequest *)tr);
    }
    CloseSocket(s);
    CloseDevice((struct IORequest *)tr);
    CloseLibrary(SocketBase);
    printf("clocksend done %ld\n", i);
    return 0;
}
