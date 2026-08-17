# Changelog

本文档记录了 Arctic Route Contracts 项目的所有重要变更。

## [Unreleased]

- 新增 RC2 迁移冒烟场景 `tromso_isfjorden_rc2_smoke_v1`（0.1.0）：Tromso
  corridor 1.1.0、72 h（2026-08-11T06:00Z → 2026-08-14T06:00Z）、12 类必需画像，
  用于第二走廊/场景迁移验证与真实 worker 冒烟；RC1 场景与 corridor 2.2.0 未改动。
  新增该场景后 `validate` 场景计数为 7。

- Murmansk 走廊版本升至 `2.2.0`：起点/终点移至 12 类数据全有限的外海区域
  （起点 69.55N/34.00E，终点 73.80N/80.00E），三个 mur 场景的 `corridor_version`
  同步为 2.2.0；用于 Demo RC1。

- 新增场景 `tromso_isfjorden_august_2026_demo_v1`：`retrospective_best_estimate`、
  144 h（2026-08-11T06:00Z → 2026-08-17T06:00Z）、12 类必需画像，用于挑战杯冻结演示
  数据交付；通过 `validate`（status=valid）。

## [0.3.0] - 2026-08-13

### Changed

- 两条走廊的 `minimum_buffer_hours` 从 24 h 提高到 48 h；默认窗口仍为
  Murmansk–Dikson 168 h、Tromsø–Isfjorden 96 h，正式上限仍为 216/144 h。
- Murmansk 走廊版本升至 `2.1.0`，Tromsø 走廊升至 `1.1.0`，四个场景配置均升至
  `1.1.0` 并更新固定的走廊版本引用。
- `DatasetBundle.v2` 与 `RunContext.v2` 结构保持不变；旧运行上下文仍可读取审计，
  但策略版本、场景摘要、走廊摘要和公共配置摘要与新配置严格隔离。

## [0.2.0] - 2026-08-13

### Added

- 提供版本化 `ScenarioDefinition`、`CorridorDefinition`、`VesselProfile` 与
  `RunContext.v2`，作为 A/B/C 共享事实来源。
- 提供 DatasetBundle v2 语义验证、动态航程时域物化、公共配置摘要以及两条航区的
  版本化配置。
- 提供 JSON Schema、Python 模型和跨包合同测试；本包是 Python 数据合同，不包含链上
  智能合约、事件或部署脚本。

### Changed

- 正式运行身份统一绑定场景、航区、船型、模拟时窗与公共 `config_digest`。
- 正式 DatasetBundle cadence 与场景必需类型画像由共享验证器 fail closed 复核。

## [0.1.0] - 2026-08-09

### Added

- 建立共享配置、数据合同与基础验证器的首个版本。
