> **二次文档治理归档声明**
>
> - 本文件角色：2026-08-15 改造前的 contracts handoff 快照，仅供历史追溯。
> - 归档时间：2026-08-15（Asia/Shanghai）。
> - 现行文件：[arctic_route_contracts_handoff.md](arctic_route_contracts_handoff.md)。
> - 归档原因：同步已解决的远端状态、双航区最新坐标和顶层治理仓库决策。
>
> <!-- ORIGINAL CONTENT START -->

> **文档治理声明**
>
> - 本文件角色：当前共享契约项目的人类与 AI 统一交接入口。
> - 改造时间：2026-08-14（Asia/Shanghai）。
> - 原文归档：[README.archive-20260814-pre-governance.md](README.archive-20260814-pre-governance.md)。
> - 改造原因：补足目标边界、状态、待办、风险、验收与跨包索引，使共享包可独立交接。

# Arctic Route Contracts 项目交接

## 1. 项目目标与边界

本包是全系统公共事实和不可变运行身份的唯一来源，负责：

- 版本化 `CorridorDefinition`、`ScenarioDefinition` 和 `VesselProfile`；
- 动态航程时域评估与冻结场景物化；
- `a.dataset-bundle.v2` 的独立语义复核；
- 创建、读取和原子写入 `run-context.v2`；
- 为 A、B、C、D 提供一致的公共 ID、版本和摘要。

本包不负责数据下载、风险推理、hard mask 策略、最终船速、路线规划或展示。B/C 的模型与
规划参数不得写入共享 `config_digest`。

## 2. 当前状态

| 维度 | 状态 | 截止 2026-08-14 的准确含义 |
|---|---|---|
| 工程实现 | 已完成 | 包元数据 `0.3.0`；配置、模型、Schema、CLI 和测试存在 |
| 工程验收 | 已完成 | Ruff 通过，18 tests passed |
| 文档治理 | 已完成 | 短 README 与本 handoff 已建立，原 README 已归档 |
| 远端同步 | 待评审 | 治理前基线的本地 `main` 比 `origin/main` ahead 1；本轮文档改造尚未提交 |
| 科学校准 | 未完成/不适用 | 共享包只保存事实；船型仍为公开参考、未经校准 |

“工程正式”只表示身份和来源合同满足门禁，不表示风险规则、船模或路线已经科学有效。

## 3. 已完成清单

| 能力 | 路径 |
|---|---|
| 双走廊版本化事实与动态时域 | `configs/corridors/`、`src/arctic_route_contracts/models.py` |
| retrospective/frozen 双场景语义 | `configs/scenarios/`、`src/arctic_route_contracts/config.py` |
| 公开参考船型与来源说明 | `configs/vessels/nordic_odyssey_reference_v1.toml` |
| DatasetBundle v1 历史读取与 v2 独立复核 | `schemas/dataset-bundle-v2.schema.json`、`src/arctic_route_contracts/bundle.py` |
| RunContext v2 模型、摘要与原子发布 | `schemas/run-context-v2.schema.json`、`src/arctic_route_contracts/context.py` |
| CLI 校验、场景物化与时域推荐 | `src/arctic_route_contracts/cli.py` |
| 合同回归 | `tests/` |

当前主开发走廊为 `offshore_murmansk_to_offshore_dikson`；迁移验证走廊为
`tromso_to_isfjorden_outer`。旧 `tromso_to_svalbard` 只能作为历史兼容标识，不能覆盖
当前端点。

## 4. 未完成与待办

### P0

- 所有正式运行必须继续拒绝 v1、缺类型、覆盖不足、provenance 不完整或摘要不一致的
  DatasetBundle；依赖 A 产出真实 12 类完整 v2 制品。
- 下游必须传播同一 `run_id/scenario_id/corridor_id/vessel_profile_id/config_digest`，不得
  通过复制 TOML 或手工拼 JSON 绕过公共加载器。

### P1

- 人工确认并处理本地 `main` ahead 1 的远端同步状态。
- 每次 A/B/C 合同升级时运行跨包兼容测试；结构变化必须提升 Schema/配置版本。
- 由编排器负责人确认当前只验收主走廊 168 h，还是扩展第二走廊。

### P2

- 若领域负责人取得可信船舶操纵、冰阻、净空或法律事实，只能新增版本化配置；不得补造
  当前缺失参数。
- 保留未来增加新走廊/船型的接口，但不得用扩展需求阻塞当前 MVP。

## 5. 技术架构与关键决策

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

关键决定：

1. 主走廊默认/允许时域为 168 h / 144–216 h；迁移走廊为 96 h / 72–144 h。
2. `required` 超上限必须返回 `forecast_coverage_insufficient`，不得静默截断。
3. 当前场景画像为 12 类必需环境层、2 类可选研究/信息层。
4. `bathymetry` 和法律图层不因“可选”而自动获得 hard-constraint 语义。
5. RunContext 绑定 DatasetBundle ID/digest；B/C 私有摘要不进入共享摘要。
6. 已发布身份不可原地修改；新事实必须产生新版本和新摘要。

## 6. 已知问题、坑与风险

- Ice Class 1A 属 Finnish-Swedish 体系，不能写成 Polar Class PC6。
- `public_reference_unvalidated` 不是数字孪生或船舶性能校准。
- 第二走廊优化终点是伊斯峡湾外部入口；朗伊尔城仅是 AIS 参考点。
- `formal` 与 `calibrated` 是两个维度；前者通过不能推出导航安全。
- 旧 v1 RunContext/DatasetBundle 只允许审计或迁移，不得进入正式执行。
- 若绕过公共 loader 直接读取配置，会失去版本、摘要和跨包一致性保证。

## 7. 数据、配置与模型位置

- 走廊：`configs/corridors/`
- 场景：`configs/scenarios/`
- 船型：`configs/vessels/`
- JSON Schema：`schemas/`
- Python 公共 API：`src/arctic_route_contracts/`
- 测试：`tests/`

本包没有运行数据、下载缓存或风险/规划模型权重。

## 8. 操作与验收

```bash
cd /root/my_project/arctic_route_contracts
.venv/bin/ruff check src tests
.venv/bin/pytest -q
PYTHONPATH=src .venv/bin/python -m arctic_route_contracts validate
```

交付验收至少确认：

- 配置能全部加载并通过 Schema/语义验证；
- 不同版本产生不同摘要，旧身份仍可读取审计；
- DatasetBundle v2 的 records、coverage、provenance 和 digest 可独立重算；
- 缺类型、future issue、错误 cadence、旧 v1 或身份串线均 fail closed；
- 相对文档链接、`git diff --check` 和仓库状态无异常。

## 9. 下一步计划与建议

1. 先让 A 产出主走廊真实 12 类、168 h 的 DatasetBundle v2。
2. 用共享 CLI 创建唯一 RunContext v2，并把同一文件交给 B、C 和编排器。
3. 完成跨包验收后，再决定第二走廊和新增船型版本；不要在当前配置上原地修补。
4. 由用户决定是否推送当前 ahead 1 的提交，本轮文档治理不自动提交或推送。

## 10. 顶层与相关文档索引

- 当前短入口：[README.md](README.md)
- 历史原文：[README.archive-20260814-pre-governance.md](README.archive-20260814-pre-governance.md)
- 版本记录：[CHANGELOG.md](CHANGELOG.md)
- 系统权威：[ARCTIC_ROUTE_SYSTEM.md](../ARCTIC_ROUTE_SYSTEM.md)
- 当前冲刺：[ABC_10_DAY_SPRINT.md](../ABC_10_DAY_SPRINT.md)
- 梳理报告：[项目梳理报告.md](../项目梳理报告.md)
- A 交接：[work_package_a_handoff.md](../work_package_a/work_package_a_handoff.md)
- 编排器交接：[arctic_route_orchestrator_handoff.md](../arctic_route_orchestrator/arctic_route_orchestrator_handoff.md)
