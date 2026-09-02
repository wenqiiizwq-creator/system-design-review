#!/usr/bin/env python3
"""需求覆盖闭合检查（机械、确定性）。

用法:
    python3 check_requirements.py design-intent.json [--json out.json]

规则:
    - 每条需求必须有 id/text/source，status 取值 confirmed|assumed|open；
    - covered_by 非空才算被方案覆盖，verify_method 非空才算可验收
      （仅对 confirmed/assumed 强制；open 项本就没有结论，不算 FAIL）；
    - id 重复或缺失 = FAIL；open 项列入“未确认”，可用 --fail-on-open 阻断。

退出码: 0 = 无 FAIL；1 = 存在 FAIL 或文件不可读。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

VALID_STATUS = {"confirmed", "assumed", "open"}


def load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"FAIL: 文件不存在: {path}")
    except json.JSONDecodeError as exc:
        sys.exit(f"FAIL: JSON 解析失败: {path}: {exc}")
    if not isinstance(data, dict):
        sys.exit(f"FAIL: 顶层必须是对象: {path}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="需求覆盖闭合检查")
    parser.add_argument("path", help="design-intent.json 路径")
    parser.add_argument("--fail-on-open", action="store_true",
                        help="存在 open 需求时退出码为 1")
    parser.add_argument("--json", dest="out_json", help="结果写出到 JSON 文件")
    args = parser.parse_args()

    data = load(Path(args.path))
    reqs = data.get("requirements")
    if not isinstance(reqs, list) or not reqs:
        print("FAIL: requirements 缺失或为空，无法闭合")
        return 1

    fails: list[str] = []
    opens: list[str] = []
    seen: set[str] = set()

    print(f"需求总数: {len(reqs)}")
    for idx, req in enumerate(reqs, start=1):
        if not isinstance(req, dict):
            fails.append(f"#{idx}: 条目不是对象")
            continue
        rid = str(req.get("id", "")).strip()
        text = str(req.get("text", "")).strip()
        status = str(req.get("status", "")).strip()
        covered_by = str(req.get("covered_by", "")).strip()
        verify = str(req.get("verify_method", "")).strip()

        if not rid:
            fails.append(f"#{idx}: id 为空")
        elif rid in seen:
            fails.append(f"{rid}: id 重复")
        seen.add(rid)

        if not text:
            fails.append(f"{rid or idx}: text 为空")
        if status not in VALID_STATUS:
            fails.append(f"{rid or idx}: status 非法（{status!r}）")
        if status == "open":
            opens.append(rid or f"#{idx}")
        else:
            if not covered_by:
                fails.append(f"{rid or idx}: covered_by 为空（需求未落到方案章节）")
            if not verify:
                fails.append(f"{rid or idx}: verify_method 为空（不可验收）")

    for line in fails:
        print("FAIL:", line)
    print(f"未确认（open）: {len(opens)} 条" + (f" -> {', '.join(opens)}" if opens else ""))

    result = {
        "ok": not fails,
        "total": len(reqs),
        "fails": fails,
        "open": opens,
    }
    if args.out_json:
        Path(args.out_json).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if fails:
        print(f"结论: 不通过（{len(fails)} 个问题）")
        return 1
    if opens and args.fail_on_open:
        print(f"结论: 不通过（--fail-on-open，{len(opens)} 条未确认需求）")
        return 1
    if opens:
        print("结论: 覆盖闭合通过，但存在未确认需求，冻结前须关闭或书面接受")
        return 0
    print("结论: 通过（覆盖与可验收闭合）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
