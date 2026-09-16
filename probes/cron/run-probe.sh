#!/usr/bin/env bash
#
# Wrapper that makes probes/ldbsv_probe.py safe to run from cron on the VPS.
#
# Cron is a hostile environment: almost no PATH, no environment variables, no
# shell profile, and output vanishes unless you catch it. Everything here exists
# because of one of those.
#
#   ./run-probe.sh morning     # 12 samples, 10 min apart  (~2 hours)
#   ./run-probe.sh evening     # 12 samples, 10 min apart
#   ./run-probe.sh once        # single sample, for testing
#
# Override paths with environment variables if your layout differs:
#   TRAIN_LOADER_DIR   default ~/train-loader
#   RAIL_CROSSING_ENV  default ~/rail-crossing/backend/.env
#   PROBE_OUT          default ~/probe-runs
#   KEEP_DAYS          default 21

set -euo pipefail

TRAIN_LOADER_DIR="${TRAIN_LOADER_DIR:-$HOME/train-loader}"
RAIL_CROSSING_ENV="${RAIL_CROSSING_ENV:-$HOME/rail-crossing/backend/.env}"
PROBE_OUT="${PROBE_OUT:-$HOME/probe-runs}"
KEEP_DAYS="${KEEP_DAYS:-21}"

MODE="${1:-once}"
case "$MODE" in
  morning|evening) SAMPLES=12; INTERVAL=600 ;;
  once)            SAMPLES=1;  INTERVAL=0   ;;
  *) echo "usage: $0 [morning|evening|once]" >&2; exit 64 ;;
esac

STAMP="$(date +%Y-%m-%d_%H%M)"
LOG_DIR="$PROBE_OUT/logs"
RUN_DIR="$PROBE_OUT/$MODE-$STAMP"
mkdir -p "$LOG_DIR" "$RUN_DIR"
LOG="$LOG_DIR/$MODE-$STAMP.log"

# Everything from here lands in the log as well as on stdout.
exec > >(tee -a "$LOG") 2>&1

echo "=== $MODE run, started $(date +%Y-%m-%dT%H:%M:%S%z) ==="

finish() {
  local code=$?
  if [ $code -eq 0 ]; then
    echo "OK   $(date +%Y-%m-%dT%H:%M:%S%z)  $MODE  -> $RUN_DIR" | tee "$PROBE_OUT/last-run.txt"
  else
    # Loud, and findable without reading the whole log.
    echo "FAIL $(date +%Y-%m-%dT%H:%M:%S%z)  $MODE  exit=$code  see $LOG" | tee "$PROBE_OUT/last-run.txt"
  fi
  exit $code
}
trap finish EXIT

# 1. The key. Cron has no environment, so source it explicitly.
if [ ! -r "$RAIL_CROSSING_ENV" ]; then
  echo "Cannot read $RAIL_CROSSING_ENV — set RAIL_CROSSING_ENV to the file holding RDM_API_KEY." >&2
  exit 78
fi
set -a
# shellcheck disable=SC1090
. "$RAIL_CROSSING_ENV"
set +a

if [ -z "${RDM_API_KEY:-}" ]; then
  echo "RDM_API_KEY is empty after sourcing $RAIL_CROSSING_ENV." >&2
  exit 78
fi
echo "key loaded (${#RDM_API_KEY} chars, not printed)"

# 2. The probe itself. Absolute path: cron's PATH will not find it otherwise.
PROBE="$TRAIN_LOADER_DIR/probes/ldbsv_probe.py"
[ -r "$PROBE" ] || { echo "No probe at $PROBE — is train-loader cloned and up to date?" >&2; exit 78; }

PYTHON="$(command -v python3 || echo /usr/bin/python3)"
"$PYTHON" "$PROBE" --samples "$SAMPLES" --interval "$INTERVAL" --out "$RUN_DIR"

# 3. Disk. Each run keeps raw payloads; unattended, that grows without limit.
find "$PROBE_OUT" -maxdepth 1 -type d -name '*-20*' -mtime "+$KEEP_DAYS" -prune \
  -exec rm -rf {} + 2>/dev/null || true
find "$LOG_DIR" -type f -name '*.log' -mtime "+$KEEP_DAYS" -delete 2>/dev/null || true

echo "disk used by probe runs: $(du -sh "$PROBE_OUT" 2>/dev/null | cut -f1)"
echo "=== finished $(date +%Y-%m-%dT%H:%M:%S%z) ==="
