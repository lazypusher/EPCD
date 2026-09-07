#!/bin/sh
# Start the corrected NINECUBE Flexnet license server (port 27001).
# Created for Plan 2 Task 7: original package license has placeholder
# DAEMON path; ninecube-fixed.lic points at the real vendor daemon binary.
PKG=/package/eda9cube-d2026.06.6092-2026_06_sp1-g317a9fd-NINECUBE-2026-08-07-linux-x86-64-default
setsid "$PKG/ehouse/64bit/lmgrd" \
  -c /home/zhubo/ninecube-fixed.lic \
  -l /home/zhubo/ninecube-lmgrd.log \
  </dev/null >/dev/null 2>&1
sleep 6
tail -20 /home/zhubo/ninecube-lmgrd.log
