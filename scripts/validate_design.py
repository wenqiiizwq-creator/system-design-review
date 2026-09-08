#!/usr/bin/env python3
"""v2 方案基线记录门禁；检查覆盖/证据/确认，不认证来源真伪或电气正确性。"""
from __future__ import annotations
import argparse
import hashlib
import json
from check_requirements import check as check_requirements
from check_power_tree import check as check_power
from validation_common import load, result, run_cli, strings, text

GROUPS = {'requirements': 'requirement', 'modules': 'module', 'components': 'component',
          'interfaces': 'interface', 'states': 'state', 'decisions': 'decision',
          'observations': 'observation', 'handoffs': 'handoff', 'open_issues': 'issue'}
ROLES = ('requirement', 'design', 'schematic', 'netlist', 'bom', 'datasheet',
         'platform', 'history', 'conversation', 'other', 'unclassified')


def subject_map(data):
    """Scoped approval content: editing one target invalidates approval for that target."""
    subjects = {}
    for group, prefix in GROUPS.items():
        entries = data.get(group, [])
        if isinstance(entries, list):
            for item in entries:
                if isinstance(item, dict) and text(item.get('id')):
                    subjects[f"{prefix}:{item['id']}"] = item
    power = data.get('power_tree', {})
    if isinstance(power, dict):
        for key, prefix in (('inputs', 'input'), ('rails', 'rail')):
            if isinstance(power.get(key), list):
                for item in power[key]:
                    if isinstance(item, dict) and text(item.get('id')):
                        subjects[f"{prefix}:{item['id']}"] = item
    plan = data.get('review_plan', [])
    plans = {p['id']: p for p in plan if isinstance(p, dict) and text(p.get('id'))} if isinstance(plan, list) else {}
    checks = data.get('checks', [])
    if isinstance(checks, list):
        for item in checks:
            if isinstance(item, dict) and text(item.get('plan_id')):
                subjects[f"risk:{item['plan_id']}"] = {'check': item, 'plan': plans.get(item['plan_id'])}
    subjects['baseline'] = {k: v for k, v in data.items() if k != 'approvals'}
    return subjects


def approval_digest(data, scope):
    subjects = subject_map(data)
    if not strings(scope) or len(set(scope)) != len(scope) or any(s not in subjects for s in scope):
        raise ValueError('确认 scope 必须唯一且引用现有对象或 baseline')
    payload = {'project': data.get('project'), 'baseline_version': data.get('baseline_version'),
               'product_variant': data.get('product_variant'),
               'subjects': {s: subjects[s] for s in sorted(scope)}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def check(data):
    errors, failures, pending, warns = [], [], [], []
    if type(data.get('schema_version')) is not int or data['schema_version'] != 2:
        return result(errors=['需要 schema_version=2；旧输入仅支持两个机械检查，不能准出'])
    for field in ('project', 'baseline_version', 'product_variant', 'optimization_summary'):
        if not text(data.get(field)):
            errors.append(f'{field}: 必须为非空字符串')
    for field in ('package_routing',):
        if data.get(field) not in ('DOCUMENT', 'RECONSTRUCT', 'HYBRID', 'REQUIREMENTS_ONLY'):
            errors.append(f'{field}: 需内容审读后的有效路由')

    def indexed(key, *, nonempty=False):
        values = data.get(key)
        if not isinstance(values, list) or (nonempty and not values):
            errors.append(f'{key}: 必须是' + ('非空' if nonempty else '') + '数组')
            return {}
        index = {}
        for item in values:
            if not isinstance(item, dict) or not text(item.get('id')):
                errors.append(f'{key}: 每项必须为带非空 id 的对象')
                continue
            if item['id'] in index:
                errors.append(f"{key}: 重复 id {item['id']}")
            index[item['id']] = item
        return index

    groups = {key: indexed(key, nonempty=key in ('requirements', 'modules', 'states')) for key in GROUPS}
    sources = indexed('sources', nonempty=True)
    evidence = indexed('evidence', nonempty=True)
    plans = indexed('review_plan', nonempty=True)
    optimizations = indexed('optimizations')
    for sid, source in sources.items():
        for field in ('locator', 'revision'):
            if not text(source.get(field)):
                errors.append(f'{sid}: {field} 缺失')
        if source.get('role') not in ROLES:
            errors.append(f'{sid}: role 非法')
        if source.get('read_status') not in ('reviewed', 'partial', 'unread', 'error', 'missing'):
            errors.append(f'{sid}: read_status 非法')
        if type(source.get('required')) is not bool:
            errors.append(f'{sid}: required 必须为布尔值')
        if source.get('required') is not False and (source.get('read_status') != 'reviewed' or source.get('role') == 'unclassified'):
            pending.append(f'{sid}: 必要资料未完成内容审读/角色识别')
        if source.get('revision') == 'unknown' and source.get('required') is not False:
            pending.append(f'{sid}: 必要资料版本未确定')
        if source.get('required') is False and not text(source.get('exclusion_reason')):
            errors.append(f'{sid}: 排除资料须写 exclusion_reason')

    def refs(item, field, index, label, *, nonempty=True):
        value = item.get(field)
        if not strings(value, nonempty=nonempty) or len(set(value)) != len(value):
            errors.append(f'{label}: {field} 必须为唯一字符串数组')
            return []
        for ident in value:
            if ident not in index:
                errors.append(f'{label}: {field} 引用未知 {ident}')
        return [ident for ident in value if ident in index]

    for eid, ev in evidence.items():
        sid = ev.get('source_id')
        if not text(sid) or sid not in sources:
            errors.append(f'{eid}: 未知 source_id')
        for field in ('locator', 'claim'):
            if not text(ev.get(field)):
                errors.append(f'{eid}: {field} 缺失')
        if ev.get('kind') not in ('intent', 'implementation', 'constraint', 'estimate'):
            errors.append(f'{eid}: kind 非法')
        if ev.get('confidence') not in ('A', 'B', 'C') or ev.get('status') not in ('verified', 'unverified'):
            errors.append(f'{eid}: evidence 状态/置信度非法')
        if ev.get('status') == 'verified' and (not text(sid) or sources.get(sid, {}).get('read_status') != 'reviewed'):
            errors.append(f'{eid}: 未审读来源不能产生 verified 证据')

    def usable(ids, label, confidence='B'):
        for eid in ids:
            ev = evidence[eid]
            if ev.get('status') != 'verified' or ev.get('confidence') == 'C':
                pending.append(f'{label}: 证据 {eid} 未核实或为 C')
            if confidence == 'A' and ev.get('confidence') != 'A':
                errors.append(f'{label}: 低置信度证据不能提升为 A')

    # Baseline fields checked here; semantic accuracy is answered by review_plan/checks.
    fields = {'modules': ('title',), 'components': ('module_id', 'mpn', 'variant', 'identity_status'),
              'interfaces': ('module_id', 'protocol', 'voltage_domain', 'resource', 'status'),
              'states': ('name', 'behavior'), 'decisions': ('title', 'selected', 'reason', 'impact', 'status'),
              'observations': ('module_id', 'description', 'status')}
    for key, required_fields in fields.items():
        for ident, item in groups[key].items():
            for field in required_fields:
                if not text(item.get(field)):
                    errors.append(f'{key}.{ident}: {field} 缺失')
            eids = refs(item, 'evidence_ids', evidence, ident)
            usable(eids, ident)
            if 'module_id' in required_fields and (not text(item.get('module_id')) or item['module_id'] not in groups['modules']):
                errors.append(f'{ident}: 未知 module_id')
    for ident, comp in groups['components'].items():
        if comp.get('identity_status') not in ('confirmed', 'open'):
            errors.append(f'{ident}: identity_status 非法')
        elif comp['identity_status'] == 'open':
            pending.append(f'{ident}: 型号/封装身份未确定')
    for ident, interface in groups['interfaces'].items():
        ends = interface.get('ends')
        if not isinstance(ends, list) or len(ends) != 2 or any(not isinstance(e, dict) or not text(e.get('endpoint')) or not text(e.get('role')) for e in ends):
            errors.append(f'{ident}: ends 必须明确两个端点及各自角色')
        if interface.get('status') != 'confirmed':
            pending.append(f'{ident}: 接口角色/资源未确认')
    for ident, observation in groups['observations'].items():
        if observation.get('status') not in ('fact', 'assumed', 'open'):
            errors.append(f'{ident}: observation.status 非法')
        elif observation['status'] != 'fact':
            pending.append(f'{ident}: 候选实现/用途尚待核实')
    for ident, req in groups['requirements'].items():
        if req.get('claim_kind') != 'intent' or type(req.get('critical')) is not bool:
            errors.append(f'{ident}: 需求须声明 claim_kind=intent 和 critical')
        usable(refs(req, 'evidence_ids', evidence, ident), ident)
    for ident, decision in groups['decisions'].items():
        if decision.get('status') not in ('proposed', 'accepted'):
            errors.append(f'{ident}: decision.status 非法')
        elif decision['status'] != 'accepted':
            pending.append(f'{ident}: 决策尚未接受')
        if not strings(decision.get('alternatives')) or type(decision.get('protected')) is not bool:
            errors.append(f'{ident}: 需 alternatives 和 protected 布尔值')

    power_config = data.get('power_tree', {})
    margin_policy = power_config.get('min_margin_pct', 20) if isinstance(power_config, dict) else 20
    for report in (check_requirements(data), check_power(data, min_margin=margin_policy, fail_on_warn=True)):
        errors.extend(report['errors'])
        failures.extend(x for x in report['fails'] if x not in report['errors'])
        pending.extend(report['insufficient'])
        # Low margin remains an explicit blocker under the selected budget policy.
        failures.extend(report['warns'])
    pt = data.get('power_tree', {})
    if isinstance(pt, dict):
        for key in ('inputs', 'rails'):
            items = pt.get(key, [])
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                ident = item.get('id', key)
                usable(refs(item, 'evidence_ids', evidence, str(ident)), str(ident))
                if key == 'rails':
                    if not text(item.get('upstream_id')):
                        pending.append(f'{ident}: 未追到上游供电对象')
                    for load_item in item.get('loads', []) if isinstance(item.get('loads'), list) else []:
                        if isinstance(load_item, dict):
                            usable(refs(load_item, 'evidence_ids', evidence, f'{ident}.load'), f'{ident}.load')

    budgets = indexed('power_budgets', nonempty=True)
    budget_states, budget_inputs, budget_rails = set(), set(), set()
    power_items = subject_map(data)
    input_index = {k[6:]: v for k, v in power_items.items() if k.startswith('input:')}
    rail_index = {k[5:]: v for k, v in power_items.items() if k.startswith('rail:')}
    for bid, budget in budgets.items():
        for field in ('scenario', 'calculation', 'assumptions'):
            if not text(budget.get(field)):
                errors.append(f'{bid}: 预算须说明 {field}')
        budget_states.update(refs(budget, 'state_ids', groups['states'], bid))
        budget_inputs.update(refs(budget, 'input_ids', input_index, bid))
        budget_rails.update(refs(budget, 'rail_ids', rail_index, bid))
        usable(refs(budget, 'evidence_ids', evidence, bid), bid)
        if budget.get('result') not in ('PASS', 'FAIL', 'INSUFFICIENT'):
            errors.append(f'{bid}: 预算 result 非法')
        elif budget['result'] != 'PASS':
            pending.append(f'{bid}: 跨轨/输入/动态预算未通过')
    for label, known, covered in (('state', groups['states'], budget_states),
                                  ('input', input_index, budget_inputs), ('rail', rail_index, budget_rails)):
        if set(known) - covered:
            pending.append(f'电源工况预算未覆盖 {label}: {sorted(set(known) - covered)}')

    subjects = subject_map(data)
    # Explicit plan coverage over known scheme objects, not an assertion of zero unknown defects.
    required_subjects = {key for key in subjects if key != 'baseline' and not key.startswith(('risk:', 'handoff:', 'issue:'))}
    coverage, layers = set(), set()
    for pid, plan in plans.items():
        if type(plan.get('layer')) is not int or not 0 <= plan['layer'] <= 9:
            errors.append(f'{pid}: layer 必须为 0..9')
        else:
            layers.add(plan['layer'])
        if type(plan.get('critical')) is not bool or plan.get('applicability') not in ('APPLICABLE', 'NA'):
            errors.append(f'{pid}: critical/applicability 非法')
        targets = refs(plan, 'subject_ids', subjects, pid)
        if plan.get('applicability') == 'NA' and any(t.startswith('requirement:') for t in targets):
            errors.append(f'{pid}: 已列需求不能用 NA 代替覆盖审查')
        coverage.update(targets)
        if plan.get('critical') is False and any(subjects[t].get('critical') is True for t in targets):
            errors.append(f'{pid}: 不能把关键对象降为非关键检查')
    if layers != set(range(10)):
        pending.append(f'检查层未覆盖: {sorted(set(range(10)) - layers)}')
    for target in sorted(required_subjects - coverage):
        pending.append(f'未纳入方案检查计划: {target}')

    # Validate acceptance provenance and scoped snapshot. Digest is not an electronic signature.
    approved = set()
    approvals = data.get('approvals')
    if not isinstance(approvals, list):
        errors.append('approvals 必须为数组')
        approvals = []
    for approval in approvals:
        if not isinstance(approval, dict):
            errors.append('approval 必须为对象')
            continue
        sid, scope = approval.get('source_id'), approval.get('scope')
        if (not text(approval.get('actor')) or not text(approval.get('locator')) or not text(sid)
                or sid not in sources or sources[sid].get('read_status') != 'reviewed'
                or sources[sid].get('role') not in ('conversation', 'history')):
            errors.append('approval 需具名工程师、定位和已审读对话/评审来源')
            continue
        if approval.get('decision') not in ('accepted', 'rejected'):
            errors.append('approval.decision 非法')
            continue
        try:
            expected = approval_digest(data, scope)
        except (ValueError, TypeError):
            errors.append('approval scope/digest 无效')
            continue
        if approval.get('baseline_version') != data.get('baseline_version') or approval.get('content_digest') != expected:
            pending.append('确认记录已过期或内容发生变化，需核对本次确认范围')
        elif approval['decision'] == 'accepted':
            approved.update(scope)
        else:
            pending.append('当前版本存在明确拒绝的确认记录，需完成修订闭环')

    def accepted(target):
        # General baseline confirmation does not silently accept risks or receive handoffs.
        return target in approved or ('baseline' in approved and target.startswith(('requirement:', 'decision:')))

    for key in ('requirements', 'decisions'):
        for ident in groups[key]:
            target = f'{GROUPS[key]}:{ident}'
            if not accepted(target):
                pending.append(f'{target}: 缺当前内容的工程师确认')

    checks = data.get('checks')
    seen_checks = set()
    if not isinstance(checks, list):
        errors.append('checks 必须为数组')
        checks = []
    for item in checks:
        if not isinstance(item, dict) or not text(item.get('plan_id')):
            errors.append('check 必须为带 plan_id 的对象')
            continue
        pid = item['plan_id']
        if pid not in plans or pid in seen_checks:
            errors.append(f'{pid}: 未知或重复 check')
            continue
        seen_checks.add(pid)
        plan = plans[pid]
        status, confidence = item.get('result'), item.get('confidence')
        if status not in ('PASS', 'FAIL', 'INSUFFICIENT', 'NA') or confidence not in ('A', 'B', 'C'):
            errors.append(f'{pid}: 结果/置信度非法')
        if not text(item.get('rationale')):
            errors.append(f'{pid}: rationale 缺失')
        eids = refs(item, 'evidence_ids', evidence, pid, nonempty=status != 'INSUFFICIENT')
        if status != 'INSUFFICIENT':
            usable(eids, pid, confidence)
            if confidence == 'C':
                errors.append(f'{pid}: C 证据只能支持 INSUFFICIENT')
        if (status == 'NA') != (plan.get('applicability') == 'NA'):
            errors.append(f'{pid}: NA 与适用性计划矛盾')
        if status == 'INSUFFICIENT':
            pending.append(f'{pid}: 方案条款缺证')
        if status == 'FAIL':
            if plan.get('critical') is not False or not accepted(f'risk:{pid}'):
                failures.append(f'{pid}: 关键不符合或非关键风险未获接受')
            else:
                warns.append(f'{pid}: 非关键不符合保留 FAIL，工程师接受记录已关联')
    for pid in plans.keys() - seen_checks:
        pending.append(f'{pid}: 检查未作答')
    for ident, issue in groups['open_issues'].items():
        if type(issue.get('critical')) is not bool or issue.get('status') not in ('OPEN', 'CLOSED', 'ACCEPTED') or not text(issue.get('description')):
            errors.append(f'{ident}: issue 字段非法')
        if issue.get('status') == 'CLOSED':
            usable(refs(issue, 'resolution_evidence_ids', evidence, ident), ident)
        elif issue.get('status') == 'ACCEPTED' and issue.get('critical') is False and accepted(f'issue:{ident}'):
            warns.append(f'{ident}: 非关键未决项已具名接受')
        else:
            pending.append(f'{ident}: 未决项未闭环')
    for ident, handoff in groups['handoffs'].items():
        if type(handoff.get('required')) is not bool or handoff.get('state') not in ('OPEN', 'ACCEPTED', 'VERIFIED'):
            errors.append(f'{ident}: handoff 状态非法')
        if not strings(handoff.get('receivers')) or not text(handoff.get('constraint')) or not text(handoff.get('verification')):
            errors.append(f'{ident}: 移交须有接收方、约束和验收方法')
        if handoff.get('required') is True and (handoff.get('state') == 'OPEN' or not accepted(f'handoff:{ident}')):
            pending.append(f'{ident}: 必需移交未被接收')
        if handoff.get('state') == 'VERIFIED':
            usable(refs(handoff, 'evidence_ids', evidence, ident), ident)
    for ident, opt in optimizations.items():
        for field in ('objective', 'baseline', 'recommendation'):
            if not text(opt.get(field)):
                errors.append(f'{ident}: optimization.{field} 缺失')
        options = opt.get('candidates')
        if not isinstance(options, list) or len(options) < 2:
            errors.append(f'{ident}: 优化须比较至少两个候选（可含保留现状）')
        else:
            for option in options:
                if not isinstance(option, dict) or any(not text(option.get(f)) for f in ('description', 'benefits', 'costs', 'risks', 'unknowns', 'verification')):
                    errors.append(f'{ident}: 候选缺收益/代价/风险/未知或验证')
        decision_id = opt.get('decision_id')
        if not text(decision_id) or decision_id not in groups['decisions']:
            errors.append(f'{ident}: 优化需关联决策，不能自动采纳')
    report = result(errors, failures, pending, warns)
    report['freeze_allowed'] = report['policy_pass']
    report['scope'] = '系统方案基线；不签原理图、PCB或实物性能'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path')
    parser.add_argument('--json', dest='out_json')
    parser.add_argument('--digest-scope', nargs='+', help='显示待确认内容摘要；不会创建确认记录')
    args = parser.parse_args()
    if args.digest_scope:
        try:
            print(approval_digest(load(args.path), args.digest_scope))
            return 0
        except (OSError, ValueError, TypeError) as exc:
            print(f'ERROR: {exc}')
            return 2
    return run_cli(args, check)


if __name__ == '__main__':
    raise SystemExit(main())
