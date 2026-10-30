#!/usr/bin/env bash
# Regenerates the hash-locked requirements files from the .in files.
# Usage: scripts/lock.sh YYYY-MM-DD   (the cooldown cutoff: the date 14 days ago)
set -euo pipefail

CUTOFF="${1:?Pass the cooldown cutoff date, e.g. scripts/lock.sh 2026-10-16}"

# Cooldown exceptions: packages allowed past the cutoff because the newer
# release fixes a known vulnerability. Remove an entry once CUTOFF passes its date.
EXCEPTIONS=(
  --exclude-newer-package "filelock=2026-10-17T17:00:00Z"   # 4.2.1 fixes 17 CVEs in 4.2.0
  --exclude-newer-package "certifi=2026-10-18T17:00:00Z"    # 2026.10.18 fixes PYSEC-2026-4320
)

OPTS=(--universal --python-version 3.12 --generate-hashes --exclude-newer "$CUTOFF" "${EXCEPTIONS[@]}")

uv pip compile "${OPTS[@]}" requirements.in -o requirements.txt
uv pip compile "${OPTS[@]}" requirements.in requirements-dev.in -o requirements-dev.txt
