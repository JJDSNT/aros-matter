/*
 * memsnap LABEL [SECS [STOPFILE]]  - the free memory now (AvailMem(MEMF_ANY))
 * and the largest free block, on one line: "LABEL free largest". With SECS,
 * it samples every 20 ms for that long - or until STOPFILE exists - and
 * reports the least free memory seen as well: "LABEL free largest minfree".
 */
#include <proto/exec.h>
#include <proto/dos.h>
#include <exec/memory.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    ULONG free, largest, minfree;
    int secs = argc > 2 ? atoi(argv[2]) : 0, i;
    const char *stop = argc > 3 ? argv[3] : NULL;

    if (argc < 2) {
        printf("usage: memsnap LABEL [SECS]\n");
        return 5;
    }
    minfree = AvailMem(MEMF_ANY);
    for (i = 0; i < secs * 20; i++) {
        ULONG f = AvailMem(MEMF_ANY);

        if (f < minfree)
            minfree = f;
        if (stop != NULL && (i % 25) == 0) {
            BPTR l = Lock(stop, SHARED_LOCK);

            if (l) {
                UnLock(l);
                break;
            }
        }
        Delay(1);
    }
    free = AvailMem(MEMF_ANY);
    largest = AvailMem(MEMF_ANY | MEMF_LARGEST);
    if (secs)
        printf("%s %lu %lu %lu\n", argv[1], (unsigned long)free, (unsigned long)largest,
               (unsigned long)(free < minfree ? free : minfree));
    else
        printf("%s %lu %lu\n", argv[1], (unsigned long)free, (unsigned long)largest);
    return 0;
}
