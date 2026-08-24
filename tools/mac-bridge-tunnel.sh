#!/bin/bash
# Persistent reverse tunnel: build-host 127.0.0.1:18080 -> Mac 127.0.0.1:8899
# Auto-reconnects if the ssh session drops (idle timeout, brief network loss).
# Does NOT survive Mac sleep by itself — keep the Mac awake during a build.
#
# Set the build-host ssh target via env (or edit the default below):
#   BUILD_HOST_SSH=user@host tools/mac-bridge-tunnel.sh
BUILD_HOST_SSH=${BUILD_HOST_SSH:-user@build-host}
while true; do
  ssh -N \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=20 \
    -o ServerAliveCountMax=3 \
    -o StrictHostKeyChecking=accept-new \
    -R 18080:127.0.0.1:8899 \
    "$BUILD_HOST_SSH"
  echo "[$(date '+%H:%M:%S')] tunnel dropped (exit $?); reconnecting in 5s..." >&2
  sleep 5
done
