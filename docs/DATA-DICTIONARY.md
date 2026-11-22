# 轨迹、接头与判损字段

A、B 的 CSV 必填 `event,distance,unit,loss_db`，设计清单必填 `joint,distance,unit,limit_db`。字段可换列序，UTF-8 首行 BOM 会清理。ID 为原形字符串，按来源和 ID 分键。同键比较归一距离与损耗，完全相同保留首行，冲突整组隔离。记录保留起始物理行和原值。空白单元格、哨兵及 JSON null 分别校验。空文件、全空行、仅表头分别为 `EMPTY_FILE`、`BLANK_FILE`、`HEADER_ONLY`。每源最多 350 个正文记录、250,000 字符。

距离单位可为 mm、m 或 km，归一成整数毫米。采集损耗 dB 支持有符号值，精确到毫 dB。配置 `length_m` 为光路总长，`zero_a_m/zero_b_m` 为两向测量偏置。统一链程 A = A 原读数减 A 起偏，B = 全长减去 B 原读数扣掉 B 起偏的结果。校准有效范围是闭区间 `[0,L]`。出界测量归隔离，出界设计仍在清单中并标缺证。设计本来就在 A 端坐标系。

双端事件按链程和 ID 排序。一对一单调配对先最大化数量，再最小化距离差总和，最后依照同状态优先配对、保留较早 A 端、再保留较早 B 端的固定遍历作稳定裁决。容差 `pair_tol_m` 含等号。配对中点的分辨率为半毫米。配对双方的读数取带符号平均作为净损耗，保留单向负值和原行。通过阈值含等号，净值为负记录无效净增益。

设计点与配对中点再次按相同优化目标一对一对齐，使用 `design_tol_m`。每接头以自己的 `limit_db` 判定，损耗模块的 `reference_limit_db` 用于单独预览。单端或孤配均保留。运行清单含源 SHA-256、校准参数、时间 UTC、耗时、版本、证据。快照摘要可用排序键、紧凑 JSON 和 UTF-8 重算。

## 抢修补测字段

请求体在 `traces`/`settings` 之外可选带 `retests` 数组，元素必填 `retest_id`、`side`（`a`/`b`）、`start_distance`+`start_unit`、`end_distance`+`end_unit`、`trace`（与该端同格式的事件 CSV 文本），可选 `recorded_at`（ISO-8601，支持 `Z` 后缀）。同请求内 `retest_id` 不可重复。覆盖区间是统一链程上的闭区间，单位复用 `mm/m/km` 归一；起大于终报 `BAD_RETEST_RANGE`，端别非法报 `BAD_RETEST_SIDE`，时间非法报 `BAD_RETEST_RECORDED_AT`。

补测 CSV 走与原轨迹相同的采信、隔离与去重规则；隔离原因带 `retest_id`。区间内读数标 `epoch=RETEST, coverage=INSIDE`，区间外标 `OUTSIDE_SCOPE` 并保留为 RETEST 孤测，不取代任何基线行；仅当批次存在区间内读数时，同端同区间的基线行才转为 `SUPERSEDED`。

`/api/retest/{calibration,pairs,loss,design}` 为补测预览，不写库；`POST /api/retests` 落补测台账，`GET /api/retests` 列台账，`GET /api/retests/<id>` 取单条。台账文档由基线三源 SHA-256、校准参数、各补测批次（编号、端别、区间、采集时间、原件指纹、区间内外计数、隔离）与复算结果确定性构成；`submitted_at`、`duration_ms` 存独立列，不参与内容指纹。同编号同内容重试返回 200 且 `created=false`；同编号异内容返回 409 `RETEST_CONFLICT`，原确认记录不变；未知编号返回 404 `RETEST_NOT_FOUND`。

对账行新增 `epoch`、`retest_id`、`evidence`（每端实测的编号、物理行、代次、批次、损耗）、`retest_scope`（覆盖该接头的批次及区间）。桶位新增 `retest_passed`、`retest_over_limit`；代码新增 `RETEST_PENDING`、`RETEST_PARTIAL_PAIR`、`AWAITING_OPPOSITE_RETEST`、`SUPERSEDED_BY_RETEST`、`OUTSIDE_SCOPE`。
