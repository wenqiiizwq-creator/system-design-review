# system-design-review

**资料包驱动的硬件设计意图建立、系统方案审查与优化。**

上传硬件资料包后：有需求/方案就检查需求完整性、方案合理性并比较优化；缺少时从
原理图、BOM、核心器件资料和对话提取候选方案，交工程师确认。局部缺失按模块混合处理。
输出受控设计基线，供原理图设计或已有原理图审查使用。

```text
资料盘点与版本核对
  ├─ 已有需求/方案 → 规范化与冲突检查
  ├─ 只有需求 → 候选方案与取舍
  └─ 缺失/局部缺失 → 当前实现提取与定向对话
        → 工程师确认关键意图 → 方案审查/优化/复验
        → 受控基线 → 原理图设计或 schematic-review
```

## V2 的重点

- 分开设计意图、当前实现和器件/平台约束；不把图纸缺失反写成需求不需要。
- 识别附件缺失、读取失败、参考板/旧版本/DNP 备选，已有方案本身也要审查。
- 方案优化比较收益、代价、约束和联动复算，保留工程师决策与受保护基线。
- 记录需求、模块、接口、选型、工作状态、电源预算、证据、优化和移交。
- 确认绑定版本与内容范围；资料完整、工程师确认和技术通过分别判定。
- 修复空值来源、未知/负值电流和时序依赖漏校验；缺失负载不再得到 100% 裕量 PASS。

## 工具

均使用 Python 标准库，无运行时第三方依赖。

```bash
python3 scripts/inventory_package.py /path/to/package --json /path/to/work/package-manifest.json
python3 scripts/check_requirements.py design-intent.json --json requirements-check.json
python3 scripts/check_power_tree.py design-intent.json --fail-on-warn --json power-check.json
python3 scripts/validate_design.py design-intent.json --json design-gate.json
```

盘点不解析文档、不决定需求是否存在；Agent 须用可用工具审读内容、图表与附件。
两项基础检查支持旧数据，但不签方案准出；最终门禁要求 [v2 契约](references/design-intent-schema.md)。
退出 0=所选机械策略通过，1=缺陷/缺证，2=文件错误；脚本通过不等于物理设计已正确。

示例：[完整 v2 JSON](examples/design-intent-v2.json)、[人读基线](examples/example-design-baseline.md)、
[资料包场景](examples/package-scenarios.md)。全部采用合成数据。

## 边界

本 skill 审查需求和系统方案，可读原理图提取架构，但不代替逐引脚/网表级审查。
不签 PCB、SI/PI、实测 EMC/热或生产准出。覆盖校验只约束已声明对象，不能保证零未知缺陷。
工程师确认摘要用于检测版本/内容漂移，不认证身份，也不会自动生成批准。
跨轨效率、峰值/浪涌和动态状态需专家计算证据，当前工具不做通用电路求解或文档语义证明。

## 安装与验证

```bash
git clone https://github.com/wenqiiizwq-creator/system-design-review.git ~/.agents/skills/system-design-review
python3 -m unittest discover -s scripts/tests -v
./scripts/validate.sh
```

validate.sh 总会执行本地行为回归；若本机安装了官方 quick_validate 且有 PyYAML，则另验
skill 元数据，否则明确报告跳过。可用 `python3 -m venv .venv` 后安装 PyYAML 补齐可选校验。
真实工程资料及本地分析产物不包含在公开示例中。

[MIT License](LICENSE)
