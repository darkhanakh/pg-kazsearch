#!/bin/bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
HARNESS="${KAZSBL_HARNESS:-$HOME/exp/kazsbl/harness}"

changed="$(git status --porcelain --untracked-files=all | awk '{print $2}' | grep -v '^\.auto/' || true)"
if [ -n "$changed" ] && [ "$changed" != "snowball/kazakh.sbl" ]; then
  echo "only snowball/kazakh.sbl may change; also changed:"
  echo "$changed" | grep -v '^snowball/kazakh.sbl$'
  exit 1
fi

(cd "$HARNESS" && sha256sum --quiet -c "$HARNESS.sha256") || { echo "scoring harness was modified"; exit 1; }

python3 - <<'EOF'
import json, sys
v = json.load(open(".auto/gate.json"))
if not v["pass"]:
    print("gate failed:")
    for r in v["reasons"]:
        print("  " + r)
    sys.exit(1)
EOF
