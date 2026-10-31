/* Host stand-in for AROS's mbedtls_entropy_aros.c (MBEDTLS_ENTROPY_HARDWARE_ALT). */
#include <stddef.h>
#include <sys/random.h>
int mbedtls_hardware_poll(void *data, unsigned char *output, size_t len, size_t *olen)
{
    ssize_t n = getrandom(output, len, 0);
    (void)data;
    *olen = n < 0 ? 0 : (size_t)n;
    return n < 0 ? -1 : 0;
}
