# 深度登记 光纤接续核验台

- 规模：中型
- 核心规则：校准双向链程后做单调一对一最优配对，按带符号均值验设计接头。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 轨迹文件采信 | 检查原行与隔离原因 | POST /api/trace | `app/modules/trace/service.py` | `tests/test_trace.py` |
| M2 距离与方向校准 | 核对双端坐标与起偏 | POST /api/calibration | `app/modules/calibration/service.py` | `tests/test_calibration.py` `tests/test_settings.py` |
| M3 双端事件最优配对 | 核查相邻冲突及孤测 | POST /api/pairs | `app/modules/pairs/optimal.py` | `tests/test_pairs.py` `tests/test_pair_oracle.py` |
| M4 接续净损耗判定 | 对照带符号读数和均值 | POST /api/loss | `app/modules/loss/service.py` | `tests/test_loss.py` |
| M5 设计与实测对账 | 核对逐接头是否缺证 | POST /api/design | `app/modules/design/service.py` | `tests/test_design.py` |
| M8 抢修补测对账 | 分区复核、跨代禁配与补测台账 | POST /api/retest/design · POST /api/retests | `app/modules/retest/` | `tests/test_retest.py` `tests/test_retest_edges.py` `tests/test_retest_trap.py` |
| M6 批次留档复跑 | 留档和重跑同一轨迹组 | POST /api/inspections | `app/modules/archive/storage.py` | `tests/test_archive.py` |
| M7 光纤证据签发 | 复核签发条件并下载 | GET /api/certificate/<id> | `app/modules/certificate/service.py` | `tests/test_certificate.py` |

## 陷阱登记

| TRAP | 现象 | 朴素错误 | 处理 | 位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-02 | A 端首列 BOM | 事件列读不到 | 清理首 BOM | `app/modules/trace/reader.py` | `tests/test_trace.py::test_bom_and_repeated_header` |
| TRAP-04 | A 端续行表头 | 当配对记录 | 按分段另计 | `app/modules/trace/reader.py` | `tests/test_trace.py::test_bom_and_repeated_header` |
| TRAP-05 | A-Y 列尾多字段 | 错配字段值 | 原行隔离 | `app/modules/trace/reader.py` | `tests/test_trace.py::test_extra_fields_keep_raw_location` |
| TRAP-07 | A-N 哨兵、B-G 空值 | 当成零损耗 | 两种原因分别留档 | `app/reasons.py` | `tests/test_trace.py::test_missing_sentinel_and_blank_are_isolated` |
| TRAP-10 | 0.2005 dB 半毫精度 | 先舍入误过限 | 用两倍毫 dB 判界 | `app/modules/loss/verdict.py` | `tests/test_loss.py::test_double_mdb_preserves_half_increment` |
| TRAP-14 | A-C 同键异距 | 后写覆盖 | 整组隔离 | `app/modules/trace/service.py` | `tests/test_trace.py::test_conflicting_records_both_withdrawn` |
| TRAP-15 | A-02 米和千米并存 | 两条虚假轨迹 | 归一毫米后比对 | `app/modules/trace/units.py` | `tests/test_trace.py::test_equivalent_units_dedupe` |
| TRAP-19 | A100 可匹配 B97 或 B101 | 最近优先导致 A105 无法配对 | 先最大配对数再最小间差 | `app/modules/pairs/optimal.py` | `tests/test_pairs.py::test_global_pairing_beats_greedy_and_keeps_competition` |
| TRAP-21 | A700 和 B820 均无对侧 | 只报一端孤测 | 分别记录缺 A 或缺 B | `app/modules/pairs/service.py` | `tests/test_pairs.py::test_opposite_ends_missing_in_both_directions` |
| TRAP-31 | 抢修只补 A 端，对端 B 仍是旧读数 | 新旧凑双端，接头误判合格 | 按 BASELINE/RETEST 分代，跨代禁配，覆盖区接头挂 `RETEST_PENDING` | `app/modules/retest/pairs.py` `app/modules/retest/design.py` | `tests/test_retest_trap.py::test_old_opposite_reading_cannot_make_repair_pass` |
| TRAP-32 | 补测读数落在申报覆盖区间外 | 误取代基线或凭空配对 | 标 `OUTSIDE_SCOPE`，仅作 RETEST 孤测；无区间内读数则不取代基线 | `app/modules/retest/service.py` | `tests/test_retest_edges.py::test_superseded_baseline_returns_when_retest_has_no_in_scope_reading` |
| TRAP-33 | 同编号补测重试 / 迟到旧记录 | 重复留档或覆盖已确认补测 | 台账按编号去重；同内容幂等、异内容 409 `RETEST_CONFLICT`，提交时间与耗时不进内容指纹 | `app/modules/retest/storage.py` | `tests/test_retest.py::test_retest_ledger_is_idempotent` `tests/test_retest.py::test_late_old_measurement_does_not_replace_confirmed` |

## 抢修补测规则

- 补测批次自带 `retest_id`、端别、起点/终点（与轨迹同单位，归一成链程毫米闭区间）与采集时间；区间是补测自己的覆盖范围，不沿用原轨迹边界。
- 校准到同一链程后，读数分三代：`BASELINE`（原轨迹）、`SUPERSEDED`（被区间内补测取代的原读数）、`RETEST`（补测）。配对只在同代之间做，RETEST 与 BASELINE 永不配对。
- 设计点落在任一补测区间内即进入补测分区：只有同代 RETEST 双端配对才能判 `PASS`/`OVER_LIMIT`；单端覆盖为 `RETEST_PENDING`，双端覆盖但未配成为 `RETEST_PARTIAL_PAIR`。区间外设计点仍由原轨迹出对账结果。
- 每个接头的 `evidence` 记录端别、原件编号、物理行、代次、补测批次号与损耗；台账 `batches` 另存每批次原件 SHA-256、覆盖区间、区间内/外读数与隔离数。
- 补测台账独立于整链路 `inspections` 表。同编号同内容重试返回 `created=false` 不新增行；同编号异内容（含更早采集时间的迟到记录）返回 409，已确认记录不可变。

## 对账规则

- 6 个设计接头 = 3 通过 + 1 超限 + 2 缺证。
- 12 条窗内端点 = 2×(4 已挂接 + 1 孤配) + 2 单端。窗外测量另计 1 条。
- F-01 双向均值 (−0.100+0.300)/2=0.1000 dB，F-03 为 (0.33+0.31)/2=0.3200 dB，超出 0.200 dB。

输入为设备导出的事件表。二进制曲线解码、坡度自校与电子签章未纳入该工作台。
