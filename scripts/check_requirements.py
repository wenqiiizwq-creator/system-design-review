#!/usr/bin/env python3
"""需求机械检查；退出 0=策略通过，1=缺陷/缺证，2=文件错误。不是方案准出。"""
import argparse
from validation_common import result, run_cli, text


def check(data):
    errors, failures, pending = [], [], []
    reqs = data.get("requirements")
    if not isinstance(reqs, list) or not reqs:
        return result(errors=["requirements 必须是非空数组"])
    seen = set()
    for index, req in enumerate(reqs, 1):
        label = f"requirements[{index}]"
        if not isinstance(req, dict):
            errors.append(f"{label}: 必须是对象")
            continue
        rid = req.get("id")
        for field in ("id", "text", "source"):
            if not text(req.get(field)):
                errors.append(f"{label}: {field} 必须是非空字符串")
        if text(rid):
            if rid in seen:
                errors.append(f"{rid}: id 重复")
            seen.add(rid)
        status = req.get("status")
        if status not in ("confirmed", "assumed", "open"):
            errors.append(f"{label}: status 非法")
        elif status != "confirmed":
            pending.append(f"{rid or label}: {status}，不能作为已确认需求")
        for field in ("covered_by", "verify_method"):
            value = req.get(field)
            if field in req and not isinstance(value, str):
                errors.append(f"{label}: {field} 必须是字符串")
            elif status != "open" and not text(value):
                failures.append(f"{rid or label}: {field} 缺失，覆盖或验收未闭合")
    return result(errors, failures, pending, total=len(reqs))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("--json", dest="out_json")
    parser.add_argument("--fail-on-open", action="store_true", help="兼容旧参数；现默认阻断 open/assumed")
    args = parser.parse_args()
    return run_cli(args, check)


if __name__ == "__main__":
    raise SystemExit(main())
