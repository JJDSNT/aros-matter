// Host log backend for the crypto test: what src/platform/<os>/Logging.cpp does.
#include <lib/support/logging/CHIPLogging.h>
#include <cstdio>
namespace chip { namespace Logging { namespace Platform {
void LogV(const char * module, uint8_t category, const char * msg, va_list v)
{
    fprintf(stderr, "[%s] ", module);
    vfprintf(stderr, msg, v);
    fputc('\n', stderr);
}
} } }
