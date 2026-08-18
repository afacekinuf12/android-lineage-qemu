#!/bin/bash
# Persistent reverse tunnel: build-host 127.0.0.1:18080 -> Mac 127.0.0.1:8899
# Auto-reconnects if the ssh session drops (idle timeout, brief network loss).
# Does NOT survive Mac sleep by itself — keep the Mac awake during a build.
while true; do
  ssh -N \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=20 \
    -o ServerAliveCountMax=3 \
    -o StrictHostKeyChecking=accept-new \
    -R 18080:127.0.0.1:8899 \
    liuming.001@10.37.7.50
  echo "[$(date '+%H:%M:%S')] tunnel dropped (exit $?); reconnecting in 5s..." >&2
  sleep 5
done
