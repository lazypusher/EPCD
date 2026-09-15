# EPCD inductor 模板对比

> 本地快照，由 `backend/scripts/template_cache.py` 生成；原始 describe 载荷见 [cache.json](cache.json)。

> **图例**：opt 参数形如 `线宽 6–20` 表示最小值–最大值（单位 µm，numOfTurns 圈数无单位）；`@0.25` 表示该参数优化步进；synth 目标形如 `L=2.1 (Equal)` 表示默认值 2.1 用相等比较，`Q≥8 (Greater)` 表示下限，`maxSize≤300 (Less)` 表示上限。

| templateId | moduleName | opt 参数(um/圈) | synth 默认目标 | 内置指标 |
|---|---|---|---|---|
| `system.inductor.adv_simple_inductor` | ADV Simple Inductor | trackWidth:6.0–20.0, trackSpace:1.5–5.0, numOfTurns:0.5–8.0 @0.5, innerRadius:20.0–80.0 | inductance:2.1 (Equal), minQFactor:8 (Greater), maxSize:300 (Less) | inductance=2.1(w1), minQFactor=8(w1), maxSize=300(w1) |
| `system.inductor.bowtie_inductor` | Bowtie Inductor | trackWidth:10.0–15.0, trackSpace:2.0–5.0, numOfTurns:1–9 @1, innerRadius:60.0–200.0 | Ld:4.0 (Equal), Qd:8 (Greater), maxSize:500 (Less) | Ld=4.0(w1), Qd=8(w1), maxSize=500(w1) |
| `system.inductor.differential_inductor` | Differential Inductor | trackWidth:6.0–20.0, trackSpace:0.5–5.0, numOfTurns:2–8 @1, innerRadius:20.0–100.0 | Ld:2.1 (Equal), Qd:8 (Greater), maxSize:300 (Less) | Ld=2.1(w1), Qd=8(w1), maxSize=300(w1) |
| `system.inductor.differential_inductor_step` | Differential Inductor Step | trackWidth:6.0–20.0, trackSpace:0.5–5.0, numOfTurns:2–8 @1, innerRadius:20.0–100.0 | Ld:2.1 (Equal), Qd:8 (Greater), maxSize:300 (Less) | Ld=2.1(w1), Qd=8(w1), maxSize=300(w1) |
| `system.inductor.simple_inductor` | Simple Inductor | trackWidth:6.0–20.0, trackSpace:1.5–5.0, numOfTurns:0.25–8.0 @0.25, innerRadius:20.0–80.0 | inductance:2.1 (Equal), minQFactor:8 (Greater), maxSize:300 (Less) | inductance=2.1(w1), minQFactor=8(w1), maxSize=300(w1) |
| `system.inductor.stack_inductor` | Stack Inductor | trackSpace:0.5–5.0, numOfTurns:2–8 @1, innerRadius:20.0–100.0, layer1Width:6.0–20.0, layer2Width:6.0–20.0 | Ld:2.1 (Equal), Qd:8 (Greater), maxSize:300 (Less) | Ld=2.1(w1), Qd=8(w1), maxSize=300(w1) |
| `system.inductor.stack_inductor_overlapped` | Stack Inductor Overlapped | trackWidth:6.0–20.0, trackSpace:0.5–5.0, numOfTurns:2–8 @1, innerRadius:20.0–100.0 | Ld:2.1 (Equal), Qd:8 (Greater), maxSize:300 (Less) | Ld=2.1(w1), Qd=8(w1), maxSize=300(w1) |
| `system.tcoil.tcoil_inductor_oct` | Tcoil Inductor Oct | trackWidth:6.0–20.0, trackSpace:1.5–5.0, numOfTurns:1.0–8.0 @0.125, innerRadius:20.0–80.0 | inductance:2.1 (Equal), minQFactor:8 (Greater), maxSize:300 (Less) | inductance=2.1(w1), minQFactor=8(w1), maxSize=300(w1) |
| `system.tcoil.tcoil_inductor_rec` | Tcoil Inductor Rec | trackWidth:6.0–20.0, trackSpace:1.5–5.0, numOfTurns:1.0–8.0 @0.25, innerRadius:20.0–80.0 | inductance:2.1 (Equal), minQFactor:8 (Greater), maxSize:300 (Less) | inductance=2.1(w1), minQFactor=8(w1), maxSize=300(w1) |

> **注（stack_inductor）**：该模板是**双层同心堆叠**，两层各有独立宽度 `layer1Width`/`layer2Width`，且 `describe()` 的元数据**不含**「两层层宽须匹配」的几何合法性约束声明。优化时两层宽度失配会触发服务端 `GDS_NOT_FOUND`（"Layer1/Layer2 Width is too great"）。控制器侧已用硬约束兜底（见 `backend/src/epcd_agent/optimizer/space.py` 的 `stack_layer_width_violation`）；模板侧是否可声明该联动约束待向接口提供方确认。单层 `simple_inductor` 与双层但重叠的 `stack_inductor_overlapped`（共用同一 `trackWidth`）均无此问题。
