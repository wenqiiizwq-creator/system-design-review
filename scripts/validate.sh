#!/usr/bin/env bash
# 一键重跑全部校验：语法编译 + 官方 quick_validate + 两个脚本的回归 fixture。
# 首次使用：python3 -m venv .venv && .venv/bin/pip install pyyaml
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="$SKILL_DIR/.venv/bin/python3"
VALIDATOR="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"

if [[ ! -x "$VENV_PY" ]]; then
  echo "缺少 .venv：先在项目根目录执行 python3 -m venv .venv && .venv/bin/pip install pyyaml" >&2
  exit 1
fi
if [[ ! -f "$VALIDATOR" ]]; then
  echo "找不到官方校验器: $VALIDATOR" >&2
  exit 1
fi

"$VENV_PY" -m py_compile "$SKILL_DIR"/scripts/*.py
"$VENV_PY" "$VALIDATOR" "$SKILL_DIR"

"$VENV_PY" "$SKILL_DIR/scripts/check_requirements.py" \
  "$SKILL_DIR/scripts/tests/fixtures/sample_good.json" >/dev/null
"$VENV_PY" "$SKILL_DIR/scripts/check_power_tree.py" \
  "$SKILL_DIR/scripts/tests/fixtures/sample_good.json" >/dev/null

if "$VENV_PY" "$SKILL_DIR/scripts/check_requirements.py" \
  "$SKILL_DIR/scripts/tests/fixtures/sample_bad.json" >/dev/null 2>&1; then
  echo "FAIL: 病态 fixture 应当让 check_requirements 失败" >&2
  exit 1
fi
if "$VENV_PY" "$SKILL_DIR/scripts/check_power_tree.py" \
  "$SKILL_DIR/scripts/tests/fixtures/sample_bad.json" >/dev/null 2>&1; then
  echo "FAIL: 病态 fixture 应当让 check_power_tree 失败" >&2
  exit 1
fi

echo "全部校验通过（py_compile / quick_validate / 需求覆盖 / 电源树）"
