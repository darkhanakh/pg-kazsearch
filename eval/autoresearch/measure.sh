#!/bin/bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
HARNESS="${KAZSBL_HARNESS:-$HOME/exp/kazsbl/harness}"
base="$(mktemp --suffix=.sbl)"
trap 'rm -f "$base"' EXIT
git show HEAD:snowball/kazakh.sbl > "$base"
cd "$HARNESS"
uv run --quiet --no-project --with numpy --with scipy python eval/sbl_autoresearch.py score \
  "$OLDPWD/snowball/kazakh.sbl" "$base" --gate-out "$OLDPWD/.auto/gate.json"
