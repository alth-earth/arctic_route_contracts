> **文档治理声明**
>
> - 本文件角色：当前共享契约短入口。
> - 改造时间：2026-08-15（Asia/Shanghai）。
> - 原文件去向：[README_归档_20260815.md](README_归档_20260815.md)。
> - 改造原因：同步挑战杯演示定位和已解决的同步状态。

# Arctic Route Contracts

`arctic-route-contracts` 预先准备 A/B/C/D 共用的走廊、场景、船型、动态时域和 RunContext。
当前包版本为`0.3.0`；它不下载数据，不计算风险、船速或航线。

## 当前状态

- 版本 0.3.0；既有验证为 Ruff 和 18 tests 通过。
- 主走廊：摩尔曼斯克外海—迪克森外海，默认 168 h。
- 迁移走廊：特罗姆瑟外海—伊斯峡湾外部入口，默认 96 h。
- contracts 本地提交/推送问题已由项目负责人确认解决，不再列为阻塞。
- 船型为 `public_reference_unvalidated` 演示散货船参考，不阻塞挑战杯工程演示。
- 共享事实：两条版本化走廊、五个场景、一个公开参考船型（2026-08-15 新增
  `tromso_isfjorden_august_2026_demo_v1`，144 h 冻结演示场景）。
- 正式运行：只接受 `a.dataset-bundle.v2` 并生成 `run-context.v2`（源自：
  README_归档_20260815.md）。

## 入口

1. [contracts handoff](arctic_route_contracts_handoff.md)
2. [系统权威](../ARCTIC_ROUTE_SYSTEM.md)
3. [十日计划](../ABC_10_DAY_SPRINT.md)
4. [版本记录](CHANGELOG.md)

## 快速校验

```bash
cd /root/my_project/arctic_route_contracts
.venv/bin/ruff check src tests
.venv/bin/pytest -q
PYTHONPATH=src .venv/bin/python -m arctic_route_contracts validate
```

已发布共享事实必须通过新版本和新摘要修改，不得原地改变。Git 操作由项目负责人在会话结束后
手动处理。
