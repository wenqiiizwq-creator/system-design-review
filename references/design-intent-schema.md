# design-intent.json 数据契约

两个校验脚本的输入。键用英文，值可中文。

```json
{
  "project": "<项目名>",
  "requirements": [
    {
      "id": "REQ-1",
      "text": "……",
      "source": "对话轮1 | 文件:页码",
      "covered_by": "基线§3",
      "verify_method": "样机测 X",
      "status": "confirmed"
    }
  ],
  "power_tree": {
    "inputs": [
      {"id": "VIN", "name": "VIN_24", "voltage": 24, "tolerance_pct": 5,
       "source": "外部适配器", "imax": 5.0}
    ],
    "rails": [
      {
        "id": "V3V3",
        "voltage": 3.3,
        "rated_imax": 3.0,
        "source": "U1 buck",
        "loads": [
          {"consumer": "MCU", "current": 0.8, "note": "datasheet typ"},
          {"consumer": "预留", "current": 0.5, "status": "assumed"}
        ],
        "sequence_after": "V5V0",
        "notes": ""
      }
    ],
    "sequence": [
      {"rail": "V5V0", "order": 1},
      {"rail": "V3V3", "order": 2}
    ]
  }
}
```

约束：

- `requirements[].status`：`confirmed` / `assumed` / `open`（open = `[XXX]`）。
- `covered_by` 非空才算被覆盖；`verify_method` 非空才算可验收。
- `rails[].loads[].current` 单位 A；缺电流或 `status` 为 `open` 的负载不参与
  求和，但列入“未计入”输出。
- 裕量 =（rated_imax − 负载合计）/ rated_imax；≥20% PASS，0–20% WARN，<0 FAIL。
- `sequence` 若给出，其 `rail` 必须是 `rails[].id` 之一，且顺序编号连续无重。
- 脚本只做求和与裕量；转换效率折算、动态峰值、浪涌由模式 B 专家判断。
