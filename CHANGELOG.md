# Changelog

本文档记录了 Arctic Route Contracts 项目的所有重要变更。

## [Unreleased]

- 尚无未发布变更。

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
