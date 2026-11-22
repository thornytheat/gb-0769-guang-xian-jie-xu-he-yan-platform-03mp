# 光纤接续核验台

验收员从 A、B 两端 OTDR 事件原件和设计清单复算接续损耗。首页比对双端轨迹帧与设计接头，按 `J`、`K` 或使用跳检按钮定位证据。左侧七个入口分别处理采信、校准、配对、判损、对账、留档和签发。

`docker compose up --build` 后访问 `http://localhost:18468/`。本地先执行 `pip install -r requirements.txt`，再运行 `python -m flask --app app.main run --port=18468`，用 `pytest -q` 验收。`FIBER_DB` 设置 SQLite 文件，Compose 的命名卷保留运行记录。

各预览和留档 API 接收 `{"sample":"dirty"}`、`{"sample":"clean"}` 或 `{"traces":{"a":"CSV","b":"CSV","design":"CSV"},"settings":{...}}`。参数示例见 `sample_data/dirty/link.json`。从留档页提交，在签发页下载核验包。

抢修补测在请求体追加 `retests` 数组（字段见 `docs/DATA-DICTIONARY.md`），示例见 `sample_data/repair/retests.json`：`/api/retest/design` 预览分区对账，`POST /api/retests` 留补测台账。补测端的新读数不会与对端旧读数配对，覆盖区内接头在另一端补测前保持 `RETEST_PENDING`；同编号重试幂等，异内容或迟到旧记录返回 409 且不覆盖已确认留档。

- [模块与独立复算](docs/DEPTH.md)
- [字段与规则](docs/DATA-DICTIONARY.md)
