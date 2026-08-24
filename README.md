---
Overall Status: ACTIVE
Content Status:
  - COMPLETED
  - PLANNED
Document Role: CANONICAL
Scope: shared contract package entrypoint
Branch: research-validation-system
Last Verified: 2026-08-21
---

> **文档治理声明**
>
> - 本文件角色：当前共享契约短入口。
> - 改造时间：2026-08-15（Asia/Shanghai）。
> - 原文件去向：[README_归档_20260815.md](README_归档_20260815.md)。
> - 改造原因：同步挑战杯演示定位和已解决的同步状态。

> **路径约定（2026-08-24）**：本文件中 `${ARCTIC_ROUTE_ROOT}` 为工作区根占位符，
> 指向包含各工作包目录（`arctic_route_contracts/`、`work_package_a/` 等）的公共根。
> 解析优先级：环境变量 > 当前所在目录 > `$HOME`。完整定义见
> `arctic_route_governance/README.md` 的"路径约定"章节。

# Arctic Route Contracts

## Research Validation 定位（2026-08-21 23:18）

本仓库继续拥有共享 corridor、scenario、vessel 和 RunContext 身份。既有 schema 作为
兼容基线；winter scenario、adaptive grid 或 route-candidate presentation 均必须通过
新版本 proposal 扩展，不得静默改变旧字段语义。

`arctic-route-contracts` 预先准备 A/B/C/D 共用的走廊、场景、船型、动态时域和 RunContext。
当前包版本为`0.3.0`；它不下载数据，不计算风险、船速或航线。

## 当前状态

- 版本 0.3.0；既有验证为 Ruff 和 18 tests 通过。
- 主走廊：摩尔曼斯克外海—迪克森外海，默认 168 h。
- 迁移走廊：特罗姆瑟外海—伊斯峡湾外部入口，默认 96 h。
- contracts 本地提交/推送问题已由项目负责人确认解决，不再列为阻塞。
- 船型为 `public_reference_unvalidated` 演示散货船参考，不阻塞挑战杯工程演示。
- 共享事实：两条版本化走廊、八个场景、一个公开参考船型；场景数以
  `configs/scenarios/` 与 `arctic-route-contracts validate` 为准。
- **`land_sea_mask` 极性（canonical，2026-08-20）**：`1 = 海 (sea)`，
  `0 = 陆/岸 (land_or_coast)`。该极性与 A 数据层、B hard-mask（land<0.5）、
  C 路线完整性、D/Viewer L2 preflight 一致，是跨包唯一权威极性。
- 正式运行：只接受 `a.dataset-bundle.v2` 并生成 `run-context.v2`（源自：
  README_归档_20260815.md）。

## 入口

1. [contracts handoff](arctic_route_contracts_handoff.md)
2. [系统权威](../ARCTIC_ROUTE_SYSTEM.md)
3. [十日计划](../ABC_10_DAY_SPRINT.md)
4. [版本记录](CHANGELOG.md)

## 快速校验

```bash
cd ${ARCTIC_ROUTE_ROOT}/arctic_route_contracts
.venv/bin/ruff check src tests
.venv/bin/pytest -q
PYTHONPATH=src .venv/bin/python -m arctic_route_contracts validate
```

已发布共享事实必须通过新版本和新摘要修改，不得原地改变。Git 操作由项目负责人在会话结束后
手动处理。
