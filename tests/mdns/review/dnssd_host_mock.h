/* What dnssd_server.c uses of Exec and task.resource, for its review
 * fixtures (dnssd_server_rfc.c): one task, and no task.resource - a
 * client that goes is found by the reap, as on a system without it. No
 * scheduler, interrupt exclusion or message passing is modelled.
 */
#ifndef REVIEW_DNSSD_HOST_MOCK_H
#define REVIEW_DNSSD_HOST_MOCK_H
#include "mdns_exec_mock.h"

struct TaskNotifyMsg
{
    ULONG           tnm_Action;
    struct Task    *tnm_Task;
    struct Task    *tnm_Parent;
    struct TagItem *tnm_Tags;
};
#define TNA_ADDED   1
#define TNA_REMOVED 2
#define TNA_FAILED  3

void Forbid(void);
void Permit(void);
struct Task *FindTask(const char *name);
ULONG GetETaskID(struct Task *task);
void Signal(struct Task *task, ULONG signals);
APTR OpenResource(CONST_STRPTR name);
BOOL AddTaskNotifyHook(struct Hook *hook);
void RemTaskNotifyHook(struct Hook *hook);
#endif
