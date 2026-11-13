/* List/allocation substitutes for the pinned daemon's host protocol tests.
 * There is no scheduler, IPC, socket or ABI emulation here.
 */
#ifndef REVIEW_MDNS_EXEC_MOCK_H
#define REVIEW_MDNS_EXEC_MOCK_H
#include "aros_host.h"
void NewList(struct List *list);
void AddTail(struct List *list, struct Node *node);
void Remove(struct Node *node);
struct Node *RemHead(struct List *list);
APTR AllocMem(size_t size, ULONG flags);
void FreeMem(APTR memory, size_t size);
LONG Stricmp(const char *a, const char *b);
LONG Strnicmp(const char *a, const char *b, LONG n);
struct Task *FindTaskByPID(ULONG id);
void ReplyMsg(struct Message *message);
#define NEWLIST(list) NewList((struct List *)(list))
/* added for aros-matter: what the canonical daemon (mdns_cache.c, the
 * registration's TXT) uses besides AllocMem() */
#include <stdlib.h>
static inline APTR AllocVec(size_t size, ULONG flags) { (void)flags; return calloc(1, size ? size : 1); }
static inline void FreeVec(APTR memory) { free(memory); }
#define IsListEmpty(l) ((l)->lh_TailPred == (struct Node *)(l))
#endif
