> **文档治理声明**
>
> - 本文件角色：当前共享契约项目的人类与 AI 统一交接入口。
> - 改造时间：2026-08-15（Asia/Shanghai）。
> - 原文件去向：[arctic_route_contracts_handoff_归档_20260815.md](arctic_route_contracts_handoff_归档_20260815.md)。
> - 改造原因：同步挑战杯定位、双航区最新坐标、已解决的远端状态和顶层治理仓库决策。

# Arctic Route Contracts 项目交接

## 1. 目标与边界

本包从 A 中分离，预先准备全系统共享事实与运行身份：Corridor、Scenario、VesselProfile、动态
时域、DatasetBundle v2 复核和 RunContext v2。它不下载数据、不算风险、不规划路线、不展示。

挑战杯默认使用预置本地数据稳定演示；contracts 负责保证 A/B/C/D 使用同一场景、航区、船型、
时间窗和摘要，不要求科学校准。

具体职责（源自：arctic_route_contracts_handoff_归档_20260815.md）：

- 版本化 `CorridorDefinition`、`ScenarioDefinition` 和 `VesselProfile`；
- 动态航程时域评估与冻结场景物化；
- `a.dataset-bundle.v2` 的独立语义复核；
- 创建、读取和原子写入 `run-context.v2`；
- 为 A、B、C、D 提供一致的公共 ID、版本和摘要。

## 2. 当前状态

| 维度 | 状态 |
|---|---|
| 包版本 | 0.3.0 |
| 工程基线 | Ruff 与 18 tests 通过的既有证据 |
| 双走廊/动态时域 | 已实现 |
| DatasetBundle/RunContext v2 | 已实现 |
| contracts 本地/远端同步 | 项目负责人确认问题已解决，不再列为阻塞 |
| 科学状态 | 公共船型为 `public_reference_unvalidated`；不阻塞挑战杯演示 |

已完成清单（源自：arctic_route_contracts_handoff_归档_20260815.md）：

| 能力 | 路径 |
|---|---|
| 双走廊版本化事实与动态时域 | `configs/corridors/`、`src/arctic_route_contracts/models.py` |
| retrospective/frozen 双场景语义 | `configs/scenarios/`、`src/arctic_route_contracts/config.py` |
| 公开参考船型与来源说明 | `configs/vessels/nordic_odyssey_reference_v1.toml` |
| DatasetBundle v1 历史读取与 v2 独立复核 | `schemas/dataset-bundle-v2.schema.json`、`src/arctic_route_contracts/bundle.py` |
| RunContext v2 模型、摘要与原子发布 | `schemas/run-context-v2.schema.json`、`src/arctic_route_contracts/context.py` |
| CLI 校验、场景物化与时域推荐 | `src/arctic_route_contracts/cli.py` |
| 合同回归 | `tests/` |

## 3. 航区真值

| corridor | 起终点 | allowed region | 默认/允许时域 |
|---|---|---|---|
| `offshore_murmansk_to_offshore_dikson` | 69.15°N, 33.60°E → 73.55°N, 80.40°E | 起：68.90–69.40°N, 33.00–34.50°E；终：73.30–73.80°N, 79.80–81.00°E | 168 h / 144–216 h |
| `tromso_to_isfjorden_outer` | 69.75°N, 19.00°E → 78.15°N, 13.00°E | 起：69.40–70.00°N, 18.00–20.50°E；终：77.90–78.40°N, 12.00–16.50°E | 96 h / 72–144 h |

朗伊尔城 78.22°N, 15.65°E 只用于 AIS 完整航次识别。旧 `tromso_to_svalbard` 和旧端点只
用于历史兼容，不能覆盖当前配置。

## 4. 船型真值

`nordic_odyssey_reference_v1` 是演示散货船公开参考：FSICR Ice Class 1A、225.0 m、32.31 m、
报告吃水 14.08 m、标称 15.7 kn。它不是校准性能模型，Ice Class 1A 不等于 Polar Class PC6。

未来参数按“公开典型值 → 透明拟合 → 演示默认值”新增版本，不原地修改已发布事实。

## 5. 关键不变量

1. scenario/corridor/vessel/bundle/config digest 构成共享身份。
2. `schema_version` 与 `model_version` 不互换。
3. RunContext 与 DatasetBundle ID/digest 精确绑定。
4. generation 由运行编排传播，旧代次不覆盖新结果。
5. 12 类必需环境层与 2 个可选接口保持可区分。
6. bathymetry/法规层不自动获得 hard constraint 语义。

补充关键决策（源自：arctic_route_contracts_handoff_归档_20260815.md）：

- `required` 超上限必须返回 `forecast_coverage_insufficient`，不得静默截断；
- 当前场景画像为 12 类必需环境层、2 类可选研究/信息层；
- B/C 私有摘要不进入共享摘要；
- 已发布身份不可原地修改；新事实必须产生新版本和新摘要；
- 所有正式运行必须拒绝 v1、缺类型、覆盖不足、provenance 不完整或摘要不一致的
  DatasetBundle；
- 下游必须传播同一 `run_id/scenario_id/corridor_id/vessel_profile_id/config_digest`，不得
  通过复制 TOML 或手工拼 JSON 绕过公共加载器。

架构图（源自：arctic_route_contracts_handoff_归档_20260815.md）：

```text
版本化 Corridor + Scenario + Vessel
                 │
                 ├── HorizonPolicy → 具体 simulation window
                 │
A DatasetBundle v2 ──独立复核──┐
                               ▼
                         RunContext v2
                               │
                    A / B / C / D 原样传播身份
```

## 6. 挑战杯与科学接口

工程演示允许 `formal + demo_unvalidated`。科学/真船接口保留，但不要求专家签字，不阻塞比赛。
所有输出仍禁止真实导航。

## 7. 相关入口

- [README](README.md)
- [A handoff](../work_package_a/work_package_a_handoff.md)
- [系统权威](../ARCTIC_ROUTE_SYSTEM.md)
- [十日计划](../ABC_10_DAY_SPRINT.md)

根目录的顶层治理仓库只跟踪根级文档；本子仓由项目负责人在会话结束后手动处理 Git。

## 8. 数据、配置与模型位置与验收（源自：arctic_route_contracts_handoff_归档_20260815.md）

- 走廊：`configs/corridors/`；场景：`configs/scenarios/`；船型：`configs/vessels/`；
- JSON Schema：`schemas/`；Python 公共 API：`src/arctic_route_contracts/`；测试：`tests/`；
- 本包没有运行数据、下载缓存或风险/规划模型权重。

交付验收至少确认：

- 配置能全部加载并通过 Schema/语义验证；
- 不同版本产生不同摘要，旧身份仍可读取审计；
- DatasetBundle v2 的 records、coverage、provenance 和 digest 可独立重算；
- 缺类型、future issue、错误 cadence、旧 v1 或身份串线均 fail closed；
- 相对文档链接、`git diff --check` 和仓库状态无异常。

下一步（源自：arctic_route_contracts_handoff_归档_20260815.md）：先让 A 产出主走廊真实
12 类、168 h 的 DatasetBundle v2；用共享 CLI 创建唯一 RunContext v2 并交给 B/C/orchestrator；
跨包验收后再决定第二走廊和新增船型版本；每次 A/B/C 合同升级时运行跨包兼容测试。
