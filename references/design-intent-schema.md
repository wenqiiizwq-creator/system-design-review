# design-intent.json · v2 数据契约

可运行完整样例：[examples/design-intent-v2.json](../examples/design-intent-v2.json)。
样例全部为合成资料和虚构确认，用于校验格式，不能替代真实工程师回复或电气证据。
本文件是脚本字段契约；未列出的扩展字段允许保留，但不会自动参与机械检查。

## 顶层

`schema_version: 2`；`project`、`baseline_version`、`product_variant` 为非空字符串。
`package_routing`: DOCUMENT / RECONSTRUCT / HYBRID / REQUIREMENTS_ONLY。

以下全部为对象数组，每项有唯一非空 `id`：
`sources/evidence/requirements/modules/components/interfaces/states/decisions/observations/`
`review_plan/power_budgets/optimizations/open_issues/handoffs`。
sources、evidence、requirements、modules、states、review_plan、power_budgets 不得为空。
`checks`、`approvals` 为数组，记录规则见下文。确实不适用的集合可空并在检查中说明；
不得删对象避开覆盖。`optimization_summary` 非空，说明优化评估范围或维持现状的理由。

草稿可缺数据，但门禁返回未完成/错误，不能准出。不是要求缺资料时停止草稿工作。

## 来源和证据

- sources：`locator/revision/role/read_status/required`。
  role 为 requirement/design/schematic/netlist/bom/datasheet/platform/history/conversation/other/
  unclassified；read_status 为 reviewed/partial/unread/error/missing；required 为布尔值。
  required=false 时有 exclusion_reason；必要来源 reviewed、角色已定、revision 不是 unknown。
  文件另记 sha256；网络文档另记 URL/获取日期；这些身份信息供 Agent 核对，脚本不打开原件。
- evidence：`source_id/locator/claim/kind/confidence/status`。
  kind=intent/implementation/constraint/estimate；confidence=A/B/C；status=verified/unverified。
  verified 只能来自 reviewed 的来源。单条证据只支撑对应主张，不扩散到整颗器件。
- 下列 `evidence_ids` 都引用 evidence.id，必须唯一。引用链未知、未读、未核或 C 不支持通过。

## 基线对象

| 集合 | 必需字段（除 id） |
|---|---|
| requirements | text/source/covered_by/verify_method/status、claim_kind=intent、critical 布尔值、evidence_ids |
| modules | title/evidence_ids |
| components | module_id/mpn/variant/identity_status/evidence_ids；身份 confirmed/open |
| interfaces | module_id/protocol/voltage_domain/resource/status/evidence_ids；ends 两项，各为 endpoint/role |
| states | name/behavior/evidence_ids；可加 critical、进入/退出、异常/控制者字段 |
| decisions | title/selected/reason/impact/status/alternatives/protected/evidence_ids |
| observations | module_id/description/status/evidence_ids |

requirements.status=confirmed/assumed/open，source 是可定位来源描述（仍需 evidence_ids）；
open 可以暂缺覆盖/验收字符串，其余状态必须非空。assumed/open 阻断确认完整性。
可加 confirmation_note 区分“文件已有明确目标，但当前候选版本未确认”和“目标本身未知”，
前者不得重复采访或当作可以任意修改的空白需求。
数值要求宜另记 target/unit/tolerance/conditions，脚本不判其自然语言含义。
interfaces.status 必须 confirmed 才完整；observations.status=fact/assumed/open，后两者待核。
decisions.status=proposed/accepted；alternatives 为非空字符串数组，protected 为布尔值。
accepted 还需真实工程师确认。无备选可写保持现状和原因，不强造选型。

## 电源树与专家预算

power_tree.inputs 非空：`id/source/voltage/imax/evidence_ids`。
power_tree.rails 非空：`id/source/voltage/rated_imax/upstream_id/evidence_ids/loads`。
已知电压/额定为有限正数；未知用 null/省略，记 INSUFFICIENT 而非编造额定；布尔值不作数字。
可选 tolerance_pct 为 [0,100)。
input 与 rail 的 id 全局唯一，upstream_id 引用 input 或 rail；环需按单向有效工况拆分。

loads 非空：`consumer/current/evidence_ids`，可加 `status=confirmed/assumed/open`（旧数据默认 confirmed）。
current 单位 A，为有限非负数；未知用 null/省略且 status=open，不以负值表达回供。
assumed 写模型与来源，仍不能当已确认预算；confirmed 也不把来源为 typ 的数冒充保证值，
需在 evidence/calculation 中说明采用的工况及保守依据。

可选 `sequence_after` 引用其他 rail；`sequence` 为 rail/order 数组，order 正整数、连续唯一，
轨不能重复，与依赖顺序一致。这里是线性次序模型，硬件允许并行组/复杂状态须另记状态表。
可选效率 `efficiency` 为 (0,1]；`min_margin_pct` 为 [0,100)，默认 20。
裕量=(1-负载/额定)×100%；缺证仅输出 known_load_a，margin_pct=null。
已知小计超额定仍能证明 FAIL。完整但低于阈值报 WARN；最终门禁按所选裕量策略阻断。

power_budgets 每项：`scenario/calculation/assumptions/state_ids/input_ids/rail_ids/evidence_ids/result`。
引用当前 states、inputs、rails；result=PASS/FAIL/INSUFFICIENT。全部状态、输入和轨都须有预算
记录，组内写共同最坏条件/互斥原因。calculation 包含跨轨效率、输入能力、并发/瞬态、
保护选择性、启动/复位/故障/回供等适用验算。脚本只查引用/覆盖/结果，不验证公式或物理模型。

## 逐项检查

review_plan 每项：id、layer 整数 0..9、subject_ids、critical 布尔值、
applicability=APPLICABLE/NA。十层都须有记录，不适用层明确 NA 并给依据。
subject_ids 为 `<类别>:<id>`，类别为 requirement/module/component/interface/state/decision/
observation/input/rail，必要时 handoff/issue。上述已知方案对象必须全部进入计划。
关联 critical=true 对象的检查不能设 critical=false；已列需求不能以 NA 代替覆盖审查，
不适用的技术检查请关联相应模块并说明依据。不要用 NA 绕过适用对象。

checks 每项：`plan_id/result/confidence/evidence_ids/rationale`。
每个计划恰好一条，result=PASS/FAIL/INSUFFICIENT/NA；NA 与计划适用性一致。
PASS/FAIL/NA 须 A/B 和已核证据，A 不能由 B 证据升级；INSUFFICIENT 可留空 evidence_ids。
critical FAIL、任何检查缺证/漏答均阻断。非关键 FAIL 仅在明确 risk 接受后可保持 FAIL 移交。
语义适用性和“有没有尚未纳入计划的未知对象”仍需 Agent 人工核查，校验不提供零漏检保证。

## 优化、未决与移交

optimizations：objective/baseline/recommendation/decision_id/candidates。
至少两个候选（可含原方案），各有 description/benefits/costs/risks/unknowns/verification。
通过 decision_id 关联取舍，避免把推荐自动记为采纳；没有适用优化可空数组并填 summary。

open_issues：description/critical/status=OPEN/CLOSED/ACCEPTED。
CLOSED 需 resolution_evidence_ids；ACCEPTED 仅限非关键且有显式 issue 确认。

handoffs：required 布尔值、state=OPEN/ACCEPTED/VERIFIED、receivers 非空字符串数组、
constraint/verification。必需项有显式接收确认；VERIFIED 还需 evidence_ids。
接收动作应由接收方或有权负责其资源的人员作出，Agent 不能代填。

## 版本和确认

approvals 每条：`actor/source_id/locator/baseline_version/scope/content_digest/decision`。
source_id 指 reviewed 的 conversation/history；decision=accepted/rejected。
scope 为唯一字符串数组，可含 requirement:R1、decision:D1、risk:C1、issue:O1、handoff:H1，
或 baseline。普通 baseline 确认仅可满足意图/决策确认，不能自动接受风险/接收移交。

先向工程师展示具体版本与范围；真实回复后保存确认记录。摘要计算：

```bash
python3 scripts/validate_design.py design-intent.json --digest-scope requirement:R1 decision:D1
```

该命令只显示当前内容摘要，不创建确认，不代表授权。摘要包含 project/version/variant
和 scope 对象的规范 JSON；内容修改或升版后旧确认不能通过。scope=baseline 包含除 approvals
外全部内容；逐对象确认便于无关检查更新后继续使用。摘要不是签名，脚本不能认证回复真伪。
历史确认/拒绝保留在旧版产物，当前 approvals 不得混入不适用旧版记录。

## CLI 语义及旧数据迁移

三项独立输出：validation_ok（结构合法）、completeness（COMPLETE/INCOMPLETE）、
policy_pass（所选机械策略）；`ok` 是 policy_pass 的兼容别名，不再表示仅无 fails。
`freeze_allowed` 在两个基础检查中始终 false，只有 validate_design 根据全部记录计算。
最终 true 也仅表示申报记录满足方案门禁，不证明来源、技术语义或实物性能真实正确。

退出 0=策略通过，1=缺陷/缺证/策略不满足，2=读写失败。--fail-on-open 保留兼容，
需求现默认阻断 open/assumed；电源未知/assumed 默认未完成，--fail-on-warn 另阻断低裕量。

旧 requirements/power_tree 可继续用于两项基础检查，但需补合法字段和明确未知；迁移 v2
时增加资料、意图/现状区分、对象/状态/证据、专家预算、计划和真实确认。不能自动补 confirmed
或生成接受记录让旧数据通过。sample_incomplete.json 保留了旧“好样例”的未决状态。
