#!/bin/bash
# Read-only runtime consistency audit. Requires an explicit --serial.
# Exit 0: sampled checks consistent; 1: differences; 2: incomplete/error.
# No exit status establishes phone authenticity, CTS compliance or device trust.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
exec python3 "$ROOT/runtime_audit.py" "$@"
