#!/usr/bin/env bash
# Usage: scripts/run.sh [sample|full]
set -euo pipefail
cd "$(dirname "$0")/.."
MODE="${1:-sample}"
case "$MODE" in
  sample) python -m src.main --config configs/sample.yaml ;;
  full)   python -m src.main --config configs/config.yaml --plot ;;
  *) echo "Usage: $0 [sample|full]"; exit 1 ;;
esac
