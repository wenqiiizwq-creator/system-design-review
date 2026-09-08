#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_PY="${SKILL_PYTHON:-python3}"
if [[ -x "$SKILL_DIR/.venv/bin/python3" ]]; then SKILL_PY="$SKILL_DIR/.venv/bin/python3"; fi
"$SKILL_PY" -m py_compile "$SKILL_DIR"/scripts/*.py
"$SKILL_PY" -m unittest discover -s "$SKILL_DIR/scripts/tests" -v
"$SKILL_PY" "$SKILL_DIR/scripts/check_requirements.py" "$SKILL_DIR/scripts/tests/fixtures/sample_good.json"
"$SKILL_PY" "$SKILL_DIR/scripts/check_power_tree.py" "$SKILL_DIR/scripts/tests/fixtures/sample_good.json" --fail-on-warn
"$SKILL_PY" "$SKILL_DIR/scripts/validate_design.py" "$SKILL_DIR/examples/design-intent-v2.json"
VALIDATOR="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"
if [[ -f "$VALIDATOR" ]] && "$SKILL_PY" -c 'import yaml' 2>/dev/null; then
  "$SKILL_PY" "$VALIDATOR" "$SKILL_DIR"
else
  echo "SKIP: 官方 quick_validate/PyYAML 不可用；行为回归已运行，元数据校验未完成。"
fi
echo "本地行为与示例验证完成；不代表实际硬件方案通过。"
