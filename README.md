# system-design-review

**一套“原理图之前”的硬件系统级方案设计审查方法论，打包成 AI Agent 可直接调用的 skill。**

双模式：

- **模式 A：设计采集与成稿** —— 工程师用自然语言描述板卡，AI 分层采访（每轮批量
  3–5 问）、翻译成专业设计语言、增量成稿 `Design_Baseline_<项目>.md` +
  `design-intent.json`。
- **模式 B：系统级方案审查** —— 0–9 共 10 层检查表（需求覆盖矩阵、整体架构、
  电源树、外设分配、关键选型、功能链路、环境/EMC 前置、可测性），签
  “系统方案可冻结并进入原理图设计”。

## 核心思想

方案阶段的可靠性问题主要是两类：**需求没被覆盖/自相矛盾**，以及**估算值被当成
事实**。所以本 skill 把两条纪律做进流程：

- 每个参数三分：**事实**（有出处）/ **假设**（有推导依据）/ **待确认**（`[XXX]`），
  未确认值绝不写成最终规格；
- 每条结论带证据链（文件:页码 / datasheet:表号 / 对话轮次），机械可穷举的检查
  交给确定性脚本，工程判断留给分层审查。

确定性校验脚本：

| 脚本 | 检查什么 |
|---|---|
| `scripts/check_requirements.py` | 需求覆盖闭合：每条需求必须有方案落点 + 验证方式 |
| `scripts/check_power_tree.py` | 电源树逐轨求和与裕量：谁驱动/谁负载/超额定/裕量<20% |

脚本 0 错误 ≠ 方案通过——架构判断、功能链路走查、datasheet 条款符合性仍是模式 B
的专家工作。

## 与 schematic-review 的分工

```
需求/对话 → 本 skill（模式A成稿 → 模式B审查）→ 原理图绘制
          → schematic-review（网表级审查）→ PCB Layout
```

本 skill 签的是“方案可冻结进入原理图设计”；`schematic-review` 签的是“原理图可冻结
进入 PCB”。不审查已绘制原理图的网表/ERC，也不做 PCB 布局、SI/PI、EMC、热、DFM。

## 结构

```
SKILL.md                 双模式入口 + 通用纪律
references/              采集协议、10层检查表、边界矩阵、报告模板、数据契约
scripts/                 两个确定性校验脚本 + validate.sh + 回归 fixture
examples/                合成示例基线文档
```

## 安装

```bash
git clone https://github.com/wenqiiizwq-creator/system-design-review.git \
  ~/.agents/skills/system-design-review
```

## 校验

项目根目录执行：

```bash
./scripts/validate.sh
```

首次使用先准备校验环境（`PyYAML` 只用于官方 quick_validate 解析 frontmatter）：

```bash
python3 -m venv .venv
.venv/bin/pip install pyyaml
```

## License

[MIT](LICENSE)
