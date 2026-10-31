#!/bin/sh
# build-mbedtls.sh CFGDIR OUT: build mbedTLS 3.6.7 for the host as AROS does
# (library/*.c except net_sockets.c, MBEDTLS_CONFIG_FILE=mbedtls_aros_config.h).
M=~/aros-local/mbedtls-3.6.7; C=$1; O=$2; rm -rf $O; mkdir -p $O
for f in $M/library/*.c $C/mbedtls_platform_aros.c $C/hardware_poll_host.c; do
  case $f in */net_sockets.c) continue;; esac
  gcc -O1 -I$C -I$M/include -I$M/library -DMBEDTLS_CONFIG_FILE='"mbedtls_aros_config.h"' -c $f -o $O/$(basename $f .c).o || echo "FAILED $f"
done
ar rcs $O/libmbedaros.a $O/*.o
