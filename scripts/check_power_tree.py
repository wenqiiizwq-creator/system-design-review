#!/usr/bin/env python3
"""电源树逐轨求和与裕量校验（机械、确定性）。

用法:
    python3 check_power_tree.py design-intent.json [--min-margin 20]
                          [--fail-on-warn] [--json out.json]

规则:
    - inputs / rails 必须非空；每轨必须有 source 与 rated_imax > 0；
    - 负载缺 current 或 status=open 不参与求和，列入“未计入”；
    - 负载合计 > rated_imax = FAIL；裕量 < min-margin% = WARN；否则 PASS；
    - sequence 若给出，rail 必须是已有轨 id，顺序编号唯一且连续。

退出码: 0 = 无 FAIL（默认不因 WARN 失败）；1 = 有 FAIL；
        2 = 文件不可读（--fail-on-warn 且存在 WARN 时为 1）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


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
    parser = argparse.ArgumentParser(description="电源树求和与裕量校验")
    parser.add_argument("path", help="design-intent.json 路径")
    parser.add_argument("--min-margin", type=float, default=20.0,
                        help="裕量下限，百分比（默认 20）")
    parser.add_argument("--fail-on-warn", action="store_true",
                        help="存在 WARN 时退出码为 1")
    parser.add_argument("--json", dest="out_json", help="结果写出到 JSON 文件")
    args = parser.parse_args()

    data = load(Path(args.path))
    pt = data.get("power_tree")
    if not isinstance(pt, dict):
        print("FAIL: power_tree 缺失或不是对象")
        return 1

    fails: list[str] = []
    warns: list[str] = []

    inputs = pt.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        fails.append("inputs 缺失或为空（没有输入源）")

    rails = pt.get("rails")
    if not isinstance(rails, list) or not rails:
        fails.append("rails 缺失或为空（没有电源轨）")
        rails = []

    rail_ids: set[str] = set()
    rail_rows = []
    for rail in rails:
        if not isinstance(rail, dict):
            fails.append("rails 中存在非对象条目")
            continue
        rid = str(rail.get("id", "")).strip()
        source = str(rail.get("source", "")).strip()
        rated = rail.get("rated_imax")
        if not rid:
            fails.append("某轨 id 为空")
            continue
        if rid in rail_ids:
            fails.append(f"{rid}: id 重复")
        rail_ids.add(rid)
        if not source:
            fails.append(f"{rid}: source 为空（谁驱动不明）")
        if not isinstance(rated, (int, float)) or rated <= 0:
            fails.append(f"{rid}: rated_imax 非法")
            rated = 0.0

        loads = rail.get("loads")
        included = 0.0
        excluded: list[str] = []
        if not isinstance(loads, list) or not loads:
            fails.append(f"{rid}: loads 缺失或为空（谁负载不明）")
            loads = []
        for ld in loads:
            if not isinstance(ld, dict):
                fails.append(f"{rid}: loads 中存在非对象条目")
                continue
            consumer = str(ld.get("consumer", "")).strip()
            cur = ld.get("current")
            status = str(ld.get("status", "confirmed")).strip()
            if not consumer:
                fails.append(f"{rid}: 负载 consumer 为空")
            if status == "open" or not isinstance(cur, (int, float)):
                excluded.append(consumer or "?")
                continue
            included += float(cur)

        margin = ((rated - included) / rated * 100.0) if rated else 0.0
        if included > rated:
            fails.append(
                f"{rid}: 负载合计 {included:.3f}A > 额定 {rated:.3f}A")
        elif margin < args.min_margin:
            warns.append(
                f"{rid}: 裕量 {margin:.1f}% < {args.min_margin:.0f}%"
                f"（合计 {included:.3f}A / 额定 {rated:.3f}A）")
        rail_rows.append((rid, source, rated, included, margin, excluded))

    seq = pt.get("sequence")
    if isinstance(seq, list) and seq:
        orders = []
        for item in seq:
            if not isinstance(item, dict):
                fails.append("sequence 中存在非对象条目")
                continue
            rail = str(item.get("rail", "")).strip()
            order = item.get("order")
            if rail not in rail_ids:
                fails.append(f"sequence 引用未知轨: {rail!r}")
            if not isinstance(order, int) or order < 1:
                fails.append(f"sequence: order 非法: {order!r}")
            else:
                orders.append(order)
        if orders and sorted(orders) != list(range(1, len(orders) + 1)):
            fails.append("sequence: 顺序编号不连续或重复")

    print("电源树检查")
    for rid, source, rated, included, margin, excluded in rail_rows:
        flag = "FAIL" if included > rated else ("WARN" if margin < args.min_margin else "PASS")
        print(f"  [{flag}] {rid}: {source} | 合计 {included:.3f}A / "
              f"额定 {rated:.3f}A | 裕量 {margin:.1f}%")
        if excluded:
            print(f"         未计入（缺电流或 open）: {', '.join(excluded)}")
    for line in fails:
        print("FAIL:", line)
    for line in warns:
        print("WARN:", line)

    result = {
        "ok": not fails,
        "fails": fails,
        "warns": warns,
    }
    if args.out_json:
        Path(args.out_json).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if fails:
        print(f"结论: 不通过（{len(fails)} 个 FAIL）")
        return 1
    if warns and args.fail_on_warn:
        print(f"结论: 不通过（--fail-on-warn，{len(warns)} 个 WARN）")
        return 1
    print("结论: 通过" + (f"（{len(warns)} 个 WARN）" if warns else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
