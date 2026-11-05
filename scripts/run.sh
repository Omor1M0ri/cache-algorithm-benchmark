#!/usr/bin/env bash
# Usage: scripts/run.sh [sample|full|collect|analyze]
set -euo pipefail
cd "$(dirname "$0")/.."
MODE="${1:-sample}"
case "$MODE" in
  sample) python -m src.main --config configs/sample.yaml ;;
  full)   python -m src.main --config configs/config.yaml --plot ;;
  collect) python -m src.collect --config configs/benchmark_raw.yaml ;;
  analyze) python -m src.process_data && python -m src.visualize &&
           jupyter nbconvert --to notebook --execute --inplace notebooks/01_data_analysis.ipynb ;;
  *) echo "Usage: $0 [sample|full|collect|analyze]"; exit 1 ;;
esac
