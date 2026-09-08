#!/usr/bin/env python3
"""电源预算机械检查。未知负载只报已知小计；不作完整裕量 PASS。"""
import argparse
import math
from validation_common import number, result, run_cli, text


def check(data, min_margin=20, fail_on_warn=False):
    errors, failures, pending, warns, rows = [], [], [], [], []
    if not number(min_margin) or min_margin >= 100:
        return result(errors=["min-margin 必须为 [0,100) 的有限数"])
    pt = data.get("power_tree")
    if not isinstance(pt, dict):
        return result(errors=["power_tree 必须是对象"])
    collections = {}
    all_ids = set()
    for key in ("inputs", "rails"):
        items = pt.get(key)
        if not isinstance(items, list) or not items:
            errors.append(f"{key} 必须是非空数组")
            items = []
        index = {}
        for item in items:
            if not isinstance(item, dict):
                errors.append(f"{key}: 条目必须是对象")
                continue
            ident = item.get("id")
            if not text(ident):
                errors.append(f"{key}: id 必须是非空字符串")
                continue
            if ident in all_ids:
                errors.append(f"{ident}: 电源 id 重复")
            all_ids.add(ident)
            index[ident] = item
            if not text(item.get("source")):
                errors.append(f"{ident}: source 必须是非空字符串")
            for field in ("voltage", "imax" if key == "inputs" else "rated_imax"):
                if item.get(field) is None:
                    pending.append(f"{ident}: {field} 未知，不能判定输入/输出能力")
                elif not number(item.get(field), positive=True):
                    errors.append(f"{ident}: {field} 必须是有限正数")
            if "tolerance_pct" in item and (not number(item["tolerance_pct"]) or item["tolerance_pct"] >= 100):
                errors.append(f"{ident}: tolerance_pct 必须为 [0,100)")
        collections[key] = index
    rails = collections["rails"]
    for rid, rail in rails.items():
        start_errors = len(errors)
        loads = rail.get("loads")
        if not isinstance(loads, list) or not loads:
            errors.append(f"{rid}: loads 必须是非空数组")
            loads = []
        currents, excluded, estimated = [], [], []
        for idx, load in enumerate(loads):
            label = f"{rid}.loads[{idx}]"
            if not isinstance(load, dict):
                errors.append(f"{label}: 必须是对象")
                continue
            if not text(load.get("consumer")):
                errors.append(f"{label}: consumer 必须是非空字符串")
            status = load.get("status", "confirmed")
            if status not in ("confirmed", "assumed", "open"):
                errors.append(f"{label}: status 非法")
            value = load.get("current")
            if value is not None and not number(value):
                errors.append(f"{label}: current 必须为有限非负数，不能用负负载抵消")
            if status == "open" or value is None or not number(value):
                excluded.append(load.get("consumer") if text(load.get("consumer")) else label)
            else:
                currents.append(value)
                if status == "assumed":
                    estimated.append(load.get("consumer", label))
        try:
            subtotal = math.fsum(currents)
        except OverflowError:
            subtotal = None
            errors.append(f"{rid}: 负载合计数值溢出")
        if excluded:
            pending.append(f"{rid}: 电流未知/未确认: {', '.join(excluded)}；只报告已知小计")
        if estimated:
            pending.append(f"{rid}: 估算尚未确认: {', '.join(str(x) for x in estimated)}")
        rated = rail.get("rated_imax")
        valid = (len(errors) == start_errors and number(rail.get("voltage"), positive=True)
                 and number(rated, positive=True) and text(rail.get("source")) and subtotal is not None)
        margin = None
        incomplete_rating = rail.get("rated_imax") is None or rail.get("voltage") is None
        status = ("INSUFFICIENT" if incomplete_rating and len(errors) == start_errors
                  else "ERROR" if not valid else "INSUFFICIENT" if excluded or estimated else "PASS")
        # Even a partial lower bound can prove overload; it cannot prove sufficiency.
        if valid and subtotal > rated:
            failures.append(f"{rid}: 已知负载 {subtotal:g}A 超过额定 {rated:g}A")
            status = "FAIL"
        elif valid and not excluded and not estimated:
            margin = (1 - subtotal / rated) * 100
            if margin + 1e-9 < min_margin:
                warns.append(f"{rid}: 裕量 {margin:.3f}% < {min_margin:g}%")
                status = "WARN"
        rows.append({"id": rid, "status": status, "known_load_a": subtotal,
                     "margin_pct": margin, "excluded": excluded, "estimated": estimated})
    parents = {}
    for rid, rail in rails.items():
        if "upstream_id" in rail:
            parent = rail["upstream_id"]
            if not text(parent) or parent not in all_ids or parent == rid:
                errors.append(f"{rid}: upstream_id 未知或自引用")
            else:
                parents[rid] = parent
        if "efficiency" in rail and (not number(rail["efficiency"], positive=True) or rail["efficiency"] > 1):
            errors.append(f"{rid}: efficiency 必须为 (0,1]")

    def detect_cycle(graph, name):
        for node in graph:
            seen, cursor = set(), node
            while cursor in graph:
                if cursor in seen:
                    errors.append(f"{name}: 存在依赖环，需按工况拆分: {node}")
                    break
                seen.add(cursor)
                cursor = graph[cursor]
    detect_cycle(parents, "upstream_id")
    dependencies = {}
    for rid, rail in rails.items():
        if "sequence_after" in rail:
            dep = rail["sequence_after"]
            if not text(dep) or dep not in rails or dep == rid:
                errors.append(f"{rid}: sequence_after 未知或自引用")
            else:
                dependencies[rid] = dep
    detect_cycle(dependencies, "sequence_after")
    seq = pt.get("sequence", [])
    orders, ordered = [], {}
    if not isinstance(seq, list):
        errors.append("sequence 必须是数组")
    else:
        for item in seq:
            if not isinstance(item, dict):
                errors.append("sequence 条目必须是对象")
                continue
            rid, order = item.get("rail"), item.get("order")
            if not text(rid) or rid not in rails:
                errors.append("sequence 引用未知轨")
            elif rid in ordered:
                errors.append(f"sequence 重复轨: {rid}")
            if type(order) is not int or order < 1:
                errors.append("sequence.order 必须为正整数")
            else:
                orders.append(order)
                if text(rid):
                    ordered[rid] = order
        if orders and sorted(orders) != list(range(1, len(orders) + 1)):
            errors.append("sequence 顺序编号必须连续且唯一")
        for rid, dep in dependencies.items():
            if seq and (rid not in ordered or dep not in ordered or ordered[rid] <= ordered[dep]):
                errors.append(f"{rid}: sequence 与 sequence_after 矛盾或漏列")
    return result(errors, failures, pending, warns, fail_on_warn=fail_on_warn, rails=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("--min-margin", type=float, default=20)
    parser.add_argument("--fail-on-warn", action="store_true")
    parser.add_argument("--json", dest="out_json")
    args = parser.parse_args()
    return run_cli(args, lambda data: check(data, args.min_margin, args.fail_on_warn))


if __name__ == "__main__":
    raise SystemExit(main())
