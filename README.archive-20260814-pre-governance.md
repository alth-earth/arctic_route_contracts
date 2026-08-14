> **文档治理声明**
>
> - 本文件角色：文档治理前的共享契约 README 原文归档，不再作为当前入口。
> - 改造时间：2026-08-14（Asia/Shanghai）。
> - 现行文件去向：[README.md](README.md)；详细交接见 [arctic_route_contracts_handoff.md](arctic_route_contracts_handoff.md)。
> - 改造原因：原 README 内容权威但过长；治理后由短入口和统一 handoff 分别承担导航与交接职责。

<!-- ORIGINAL CONTENT START -->

# Arctic Route Contracts

`arctic-route-contracts` 是 A/B/C/D 之外的轻量共享包。它只保存走廊、场景、船舶公共事实与一次运行的不可变身份，不保存任何工作包的算法参数，也不执行下载、风险计算、航线规划或可视化。

当前版本为 `0.3.0`。

## 当前基线

### 走廊

| 走廊 ID | 角色 | 起点 | 终点 | 默认/允许时域 |
|---|---|---|---|---|
| `offshore_murmansk_to_offshore_dikson` | 主开发航区 | 69.15°N, 33.60°E | 73.55°N, 80.40°E | 168 h / 144–216 h |
| `tromso_to_isfjorden_outer` | 迁移验证航区 | 69.75°N, 19.00°E | 78.15°N, 13.00°E | 96 h / 72–144 h |

第二条走廊在 `78.22°N, 15.65°E` 保存朗伊尔城 AIS 参考点，但它明确标记为不参与航线优化；规划终点是伊斯峡湾外部入口。端点允许区用于输入校验和有限网格对齐，不表示规划器可以随意改变业务端点。

主航区用于开发和调参。迁移验证航区应复用同一套 B 风险规则和 C 规划参数，不进行航区专用调参。导师提供的航区设计是当前配置依据；旧 A ZIP 文档只能作为数据源历史线索，不能覆盖这些新端点。

### 双场景语义

- `*_july_2026_retrospective_v1`：从 `2026-07-15T00:00:00Z` 开始的事后最佳估计。它不能表述为“严格还原 7 月当时发布的预测”。
- `*_frozen_forecast_template_v1`：冻结预报模板。模板没有隐式 `latest`；必须显式提供 UTC `simulation_start`，再生成确定性的具体场景 ID、版本和摘要。

具体场景时域为整个规划/模拟窗口。它不是固定“9 天”：初始推荐值来自航程，动态公式为：

```text
design_distance = candidate_route_distance（若已有）
                  else great_circle_distance × corridor_detour_factor
planning_speed = nominal_speed × conservative_environment_speed_factor
eta = design_distance / planning_speed
required = ceil_24h(eta + max(48h, 20% × eta))
```

`0.3.0` 将两条走廊的最小缓冲统一提高到 48 h；走廊版本分别为 `2.1.0` 和
`1.1.0`，四个场景配置版本均为 `1.1.0`。默认窗仍为 168/96 h，上限仍为
216/144 h。旧 RunContext 可继续按自身身份审计，但新旧走廊/场景版本和
`config_digest` 不得混用。

若 `required` 超出该走廊正式上限，接口报告 `forecast_coverage_insufficient`，绝不把截断后的尾段伪装为完整预报。

### 场景数据需求

场景本身固定数据需求，不能由一次运行临时把正式输入缩减成“只下载 wave 也算完整”。当前 14 类 A 环境数据分为：

- 12 类运行必需：`land_sea_mask`、海流、海冰密集度/漂移/冰缘/厚度/冰型、温度、能见度、水位、波浪、风场；
- 2 类可选研究/信息层：`bathymetry`、`long_term_restricted_area`。

“可选”只表示它们不阻止 MVP RunContext 创建，不表示可以把它们误作别的数据，也不表示 B/C 可以悄悄把它们升级为硬安全约束。水深目前保留研究接口，不作核心吃水约束；长期限制区保留原始类别语义，不把保护区、军事区和规划区统称为法律禁航 `hard_mask`。场景内容摘要会覆盖这两组清单；修改清单必须产生新的场景版本/摘要。

### 船型事实

默认船型 `nordic_odyssey_reference_v1` 基于 Nordic Odyssey（IMO 9529451）的公开资料：75,603 DWT、Ice Class 1A、225 m × 32.31 m、公开吃水 14.08 m、公开标称航速 15.7 kn。来源保存在 TOML 中，包括 [Pangaea Logistics 船队页](https://www.pangaeals.com/fleet/)、[Pangaea 时间线](https://www.pangaeals.com/timeline/)、[Port of Hamburg 船舶资料](https://www.hafen-hamburg.de/en/vessels/nordic-odyssey-25019/) 和 [CHNL 2013 NSR 统计](https://chnl.no/wp-content/uploads/2022/12/statistics2013.pdf)。

这是 `public_reference_unvalidated` 研究参考，不是经校准的船舶数字孪生。Ice Class 1A 属于 Finnish-Swedish 冰级，绝不能写成 Polar Class PC6。公开资料未给出的转弯半径、最小安全航速、冰阻力、净空余量等不得在共享层虚构；它们仍是 C 的明确未验证算法参数。

## 统一运行顺序

```text
共享 Scenario + Corridor + Vessel
              ↓
A 按显式 simulation_start/end 获取并发布 DatasetBundle
              ↓
arctic-route-context 绑定精确 A bundle，原子生成 RunContext
              ↓
B 读取同一 RunContext，发布 RiskFrame（原样传播 run/config identity）
              ↓
C 拒绝身份不一致的 RiskFrame，规划并传播同一身份到 RoutePlan
              ↓
D 只展示同一 RunContext 下的产物
```

每次演示先用同一场景时间重新运行 A，再运行 B、C、D。A 的 `bundle_id`/`bundle_digest` 在采集完成后才写入 RunContext，避免场景配置循环引用尚不存在的数据快照。B 的模型摘要与 C 的规划器摘要属于各包自己的合同字段，不进入共享 `config_digest`。

共享 `config_digest` 只覆盖：具体 `ScenarioDefinition`（连同其 `CorridorDefinition`）、`VesselProfile`、A `DatasetBundle` 的 ID 和内容摘要。`run_id`、生成时间、B 风险权重和 C 规划权重不进入该摘要。

## CLI

开发态可直接使用：

```bash
PYTHONPATH=src python -m arctic_route_contracts list
PYTHONPATH=src python -m arctic_route_contracts validate
```

在冻结场景落盘前，可用实际候选航线距离执行时域评估；没有候选线时省略距离，使用
大圆距离乘走廊绕行系数：

```bash
arctic-route-context recommend-horizon \
  --corridor offshore_murmansk_to_offshore_dikson \
  --vessel nordic_odyssey_reference_v1 \
  --candidate-route-distance-nm 1137
```

命令输出 `required_hours/selected_hours/maximum_hours`。若超出来源与个人电脑演示上限，
返回码为 2 且状态为 `forecast_coverage_insufficient`，不会把结果钳到最大值。

事后场景创建 RunContext：

```bash
arctic-route-context create \
  --scenario murmansk_dikson_july_2026_retrospective_v1 \
  --dataset-bundle /path/from-A/dataset-bundle.json \
  --output /path/to/run-context.json
```

冻结预报模板必须显式锚定时间，且 A bundle 必须从完全相同的起点覆盖完整时域：

```bash
arctic-route-context create \
  --scenario murmansk_dikson_frozen_forecast_template_v1 \
  --simulation-start 2026-08-12T00:00:00Z \
  --candidate-route-distance-nm 1137 \
  --dataset-bundle /path/from-A/dataset-bundle.json \
  --output /path/to/run-context.json
```

提供候选距离时，物化后的场景 ID/版本会带所选时域（例如 `_h144`），避免同一开始
时刻的不同航程窗口共用摘要。未提供候选距离时使用模板的保守默认时域。

输出使用 `run-context.v2`，通过同目录临时文件和原子硬链接创建；已有目标不会被覆盖。正式运行只接受 `a.dataset-bundle.v2`。共享包不依赖 A 的 Python 包，会独立重算每个请求类型的 records/provenance 摘要、正式 cadence、起点支撑、缺口和全窗完整性；创建 RunContext 时还会从身份对象绑定的完整文档再次复算，不能靠手工构造一个 `coverage_complete=true` 摘要绕过验证。随后再核对场景的 12 类必需输入，并禁止冻结预测绑定晚于模拟起点才取得的知识。`a.dataset-bundle.v1` 仅保留读取能力，用于历史回放和迁移诊断，不能创建正式 RunContext。

## Python API

顶层 `arctic_route_contracts` 导出：

- 类型：`GeoPoint`、`GeoBoundingBox`、`ReferencePoint`、`HorizonPolicy`、`CorridorDefinition`、`ScenarioDefinition`、`VesselProfile`、`RunContext`。
- 配置：`load_corridor`、`load_scenario`、`load_vessel_profile`、`materialize_frozen_forecast`。
- 身份：`canonical_sha256`、`configuration_digest`、`create_run_context`、`load_run_context`、`write_run_context_atomic`。
- A 边界：`load_dataset_bundle`、`verify_dataset_bundle`。

配置对象均为 frozen dataclass。修改事实必须新增版本并形成新摘要，不能在运行开始后原地修改。
