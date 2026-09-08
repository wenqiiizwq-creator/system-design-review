"""Shared, dependency-free validation and CLI output helpers."""
from __future__ import annotations
import json
import math
from pathlib import Path


def text(value):
    return isinstance(value, str) and bool(value.strip())


def number(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value) and (value > 0 if positive else value >= 0)
    except OverflowError:
        return False


def strings(value, *, nonempty=True):
    return (isinstance(value, list) and (bool(value) or not nonempty)
            and all(text(x) for x in value))


def load(path):
    def reject_constant(value):
        raise ValueError(f"non-finite JSON constant: {value}")
    data = json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject_constant)
    if not isinstance(data, dict):
        raise ValueError("顶层必须是对象")
    return data


def result(errors=(), violations=(), insufficient=(), warns=(), *, fail_on_warn=False, **extra):
    errors, violations = list(errors), list(violations)
    insufficient, warns = list(insufficient), list(warns)
    passed = not (errors or violations or insufficient or (fail_on_warn and warns))
    return {"validation_ok": not errors,
            "completeness": "INCOMPLETE" if errors or insufficient else "COMPLETE",
            "policy_pass": passed, "ok": passed, "freeze_allowed": False,
            "errors": errors, "fails": errors + violations,
            "insufficient": insufficient, "warns": warns, **extra}


def emit(report, output=None):
    for label, key in (("ERROR", "errors"), ("FAIL", "fails"),
                       ("INSUFFICIENT", "insufficient"), ("WARN", "warns")):
        for item in report.get(key, []):
            if label == "FAIL" and item in report.get("errors", []):
                continue
            print(f"{label}: {item}")
    print(f"数据有效: {report['validation_ok']} | 完整性: {report['completeness']}"
          f" | 策略通过: {report['policy_pass']} | 方案准出: {report['freeze_allowed']}")
    if output:
        Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                encoding="utf-8")
    return 0 if report["policy_pass"] else 1


def run_cli(args, check):
    try:
        report = check(load(args.path))
    except (OSError, ValueError, UnicodeError) as exc:
        report = result(errors=[f"输入读取失败: {exc}"])
        try:
            emit(report, args.out_json)
        except OSError as output_error:
            print(f"ERROR: 无法写结果: {output_error}")
        return 2
    try:
        return emit(report, args.out_json)
    except OSError as exc:
        print(f"ERROR: 无法写结果: {exc}")
        return 2
