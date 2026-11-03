#!/usr/bin/env bash
# Every Jarvis test suite + the router eval. Exits non-zero if anything is red, so nothing red gets
# committed: the dotfiles pre-commit hook (~/.config/stark-hooks/pre-commit, core.hooksPath) runs this whenever
# .config/jarvis files are staged.
#   tools/check_all.sh            all suites, then the router eval (0 wrong actions at 0.70 required)
#   tools/check_all.sh -q         only the failures and the verdict
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
QUIET=${1:-}
fail=()

for t in tests/test_*.py; do
    out=$(timeout 300 "$PY" "$t" 2>&1)
    rc=$?
    if [ $rc -ne 0 ]; then
        fail+=("$t")
        echo "FAIL $t (exit $rc)"
        echo "$out" | grep -E "^FAIL|Error|Traceback" | head -15 | sed 's/^/    /'
    elif [ "$QUIET" != "-q" ]; then
        echo "ok   $t"
    fi
done

ev=$(timeout 300 "$PY" -I tools/eval_router.py 2>&1)
rc=$?
wrong=$(echo "$ev" | grep -A1 "threshold 0.70, gap" | grep -oP "wrong actions \K[0-9]+" | head -1)
if [ $rc -ne 0 ] || [ -z "$wrong" ]; then
    fail+=("eval_router (exit $rc, no result)")
    echo "FAIL tools/eval_router.py: no result at 0.70"
elif [ "$wrong" -ne 0 ]; then
    fail+=("eval_router ($wrong wrong actions)")
    echo "FAIL tools/eval_router.py: $wrong wrong actions at 0.70"
elif [ "$QUIET" != "-q" ]; then
    echo "ok   router eval: 0 wrong actions at 0.70"
fi

if [ ${#fail[@]} -ne 0 ]; then
    echo "RED: ${#fail[@]} failing: ${fail[*]}"
    exit 1
fi
echo "GREEN: all suites and the router eval pass"
