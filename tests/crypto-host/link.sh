#!/bin/sh
# link.sh: compile the SDK sources listed in srcs.txt and link the crypto test.
C=~/aros-local/connectedhomeip; W=~/aros-local/crypto-host
# CFG: aros-cfg (as shipped), aros-cfg-b, aros-cfg-c; objects and test per config
CFG=${CFG:-aros-cfg}; LIB=${LIB:-obj}; mkdir -p $W/chip-obj-$CFG; cd $W/chip-obj-$CFG
FL="$(sed "s#-I$W/aros-cfg #-I$W/$CFG #" $W/flags) -I$C/third_party/googletest/googletest/include -O1 -DCHIP_CONFIG_TEST_GOOGLETEST=1 -Wno-deprecated-declarations"
for f in $(cat $W/srcs.txt); do
  case $f in /*) p=$f;; *) p=$C/$f;; esac
  o=$(echo $f | tr / _ | sed 's/\.cpp$/.o/')
  [ $o -nt $p ] || g++ $FL -c $p -o $o 2>$o.err || { echo "COMPILE FAIL $f"; grep error $o.err | head -3; }
done
g++ -o test-crypto *.o $W/$LIB/libmbedaros.a $W/gtest-build/libgtest.a -lpthread 2>&1 | grep -oE "undefined reference to \`[^']+'" | sed "s/undefined reference to \`//;s/'$//" | sort -u > undef.txt
echo "undefined: $(wc -l < undef.txt)"; c++filt < undef.txt | head -${1:-15}
