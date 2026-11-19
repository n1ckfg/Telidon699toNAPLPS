#!/usr/bin/env bash
# Batch-convert Telidon 699 files to NAPLPS using 699toNAPLPS.py.
#
# Usage:
#   ./batch_convert.sh [input_dir] [output_dir] [log_file]
#
# Defaults:
#   input_dir  = <repo>/samples/699
#   output_dir = <repo>/samples/naplps
#   log_file   = <repo>/logfile.txt

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONVERTER="$SCRIPT_DIR/699toNAPLPS.py"

IN_DIR="${1:-$SCRIPT_DIR/samples/699}"
OUT_DIR="${2:-$SCRIPT_DIR/samples/naplps}"
LOG_FILE="${3:-$SCRIPT_DIR/logfile.txt}"

if [[ ! -f "$CONVERTER" ]]; then
    echo "Error: converter not found at $CONVERTER" >&2
    exit 1
fi

if [[ ! -d "$IN_DIR" ]]; then
    echo "Error: input directory not found: $IN_DIR" >&2
    exit 1
fi

# Resolve absolute paths so the converter can run inside a temp working dir.
ABS_IN_DIR="$(cd "$IN_DIR" && pwd)"
mkdir -p "$OUT_DIR"
ABS_OUT_DIR="$(cd "$OUT_DIR" && pwd)"
mkdir -p "$(dirname "$LOG_FILE")"
ABS_LOG_FILE="$(cd "$(dirname "$LOG_FILE")" && pwd)/$(basename "$LOG_FILE")"

# Run 699toNAPLPS.py in an isolated temp directory because it always writes
# output to ./NAPLPS/<indir>/ and ./logfile.txt in the current directory.
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

ln -s "$ABS_IN_DIR" "$TMP_DIR/input"

(
    cd "$TMP_DIR"
    python3 "$CONVERTER" input
)

# Move converted files into the target output directory.
shopt -s nullglob
converted_files=("$TMP_DIR/NAPLPS/input/"*)
if (( ${#converted_files[@]} == 0 )); then
    echo "Warning: no files were converted from $ABS_IN_DIR" >&2
else
    mv -f "${converted_files[@]}" "$ABS_OUT_DIR/"
fi

if [[ -f "$TMP_DIR/logfile.txt" ]]; then
    mv -f "$TMP_DIR/logfile.txt" "$ABS_LOG_FILE"
fi

echo "Converted ${#converted_files[@]} file(s) from $ABS_IN_DIR to $ABS_OUT_DIR"
echo "Log written to $ABS_LOG_FILE"
