#!/usr/bin/env bash
set -euo pipefail

# Keep the setup implementation in one place; this is the root-level entry.
exec bash "$(dirname "$0")/scripts/setup_phase3.sh" "$@"
