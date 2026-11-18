# 站点读流量路由演练

栖原站点运维组（11人）在交接班前，用节点位点与会话时序复核读写路由，明确何时读副本、何时回主库、何时必须拒绝读取。

## 场景与模块

原先值班员在配置表和聊天记录中核对副本延迟，以“延迟很低”推断写后读安全。痛点：低延迟不等于已应用会话写位点、故障时回退策略不清、决策无逐请求证据。上游输入为人工确认的节点状态和请求轨迹，本站承接路由规则演练与证据留档，下游为站点值班与变更复核人员。

三个核心实体：复制节点 Node（主副角色/在线状态/日志谱系/位点/延迟），会话请求集 RequestSet（带时序的读写、复制应用、故障恢复事件），路由试验 Trial（冻结输入、策略参数与结果）。另有一组在线备份与定点恢复实体：写入脚本 WriteWorkload（带键值、按时刻非递减的提交序列）、备份任务 BackupJob（模糊快照 + 增量 WAL 分段 + 清单）、恢复任务 RecoveryJob（目标时刻、缺段模拟、恢复结果与失败原因）。4业务页+登录页+备份恢复页，另有管理员审计。

**这是受控复制路由模型，不连接真实主从集群。** MySQL真实保存节点、请求、任务及证据；Python真实逐事件计算策略。日志位点采用命名谱系中的单调整数，未实现完整GTID集合/真实复制协议。

## 快速启动

```sh
cp .env.example .env
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```

前端 http://localhost:18247 ，后端 http://localhost:19247/docs ，MySQL localhost:17747。

|角色|账号|密码|权限|
|---|---|---|---|
|admin|admin@qiyuan.test|Demo2026!|全部业务写入、运行与审计|
|operator|operator@qiyuan.test|Demo2026!|节点/请求编辑、运行、导出|
|viewer|viewer@qiyuan.test|Demo2026!|只读和导出，写API403|

## 一天的工作剧本

09:00 operator登录；09:05查看harbor-primary位点105、north-replica位点104/150ms、south-replica位点105/20ms；09:10打开 `QY-1117-A` 请求集；09:15确认八事件时序；09:20以100ms延迟门槛和500ms粘滞执行 `shift-20261117`；09:25检查：写入主库位点106、100ms读仍走主库、600ms南站追平106、700ms读走南站、800ms南站故障、900ms回主库、1000ms主库故障、1100ms拒绝读取；09:30导出route-1.json；09:40 viewer核验拒绝理由；10:00 admin看审计。

另有 `QY-1117-B` 高延迟副本回退主库、`QY-1117-C` 主库故障且副本未追平的拒绝案例。所有试验使用冻结快照，不会把模型故障写回节点台账。

## 真实计算规则

输入上限12节点、100事件；时间0–86400000ms，事件按at_ms非递减，时间相同按输入顺序执行。必须有且仅一个主节点，同谱系副本初始位点不能超过主库。事件字段：

```json
[
  {"at_ms":0,"kind":"write","session":"lab-A"},
  {"at_ms":100,"kind":"read","session":"lab-A"},
  {"at_ms":600,"kind":"replicate","node":"south-replica","position":106,"delay_ms":20},
  {"at_ms":700,"kind":"read","session":"lab-A"}
]
```

- write：主库在线才成功；主库位点+1，记录该会话required_position和last_write_ms。失败写入不推进会话位点。
- read：若距最近成功写入 `< sticky_ms`，必须主库在线、同谱系且位点满足；否则拒绝。到达边界即结束粘滞。
- 粘滞期外：副本必须在线、同谱系、position≥会话required_position、delay_ms≤max_delay_ms，四条件同时成立。多个候选按延迟升序、位点降序、名称字典序选择。无副本达标则回主库；主库也失效则拒绝。
- replicate：只允许在线同谱系副本；位点不能回退、不能超过主库已提交位点。node_down/node_up修改模型状态。未知节点或非法复制在入队前422。
- 每个会话独立维护位点；从未成功写入的会话required=0，允许最终一致副本读取，不承诺全局强一致。低延迟绝不覆盖落后位点。

输出每事件目标/拒绝、会话所需位点、实际位点、各副本四项资格、最终节点、会话状态、汇总和SHA256。相同输入产生相同摘要；不依赖随机数或外部网络。拒绝不安全读是正常业务结果，不算任务失败。快照与结果保存在MySQL，Redis只传递任务ID。

## 在线备份与定点恢复（PITR）演练

路由演练只能看位点，无法回答“误写前是否可恢复”。备份恢复页（导航 05）用受控模型演练在线备份与定点恢复，全程不连接真实数据库。

**模型与快照/WAL 衔接**（`backend/src/services/recovery_engine.py`，纯函数、无随机数、无网络）：

- 写入带键值（at_ms/key/value），按 at_ms 非递减编排，同刻按输入顺序分配单调提交序号 seq。
- 在线备份窗口 `[start_ms, finish_ms]` 全程**不阻塞写入**，窗口内写入就是“备份期间并发写入”。备份产物 = 模糊快照 + 增量 WAL 分段 + 清单：
  - 模糊快照只含拷贝点 `copy_point_ms`（位于窗口内）及之前已提交的写入，因此窗口内并发写入可能只进快照、只进 WAL 或两者都进，快照本身不具时间点一致性。
  - WAL 从 `start_seq`（窗口前最后一条提交的下一条）开始，覆盖窗口内全部提交，按每 4 条一个局部连续段号切分，每段独立 SHA256；快照与清单各有校验和。
- 恢复规则：先还原快照中 `seq < start_seq` 的窗口前状态；快照里属于窗口区间（`seq ≥ start_seq`）的重叠条目**确定性丢弃**，窗口内以 WAL 为权威，按 seq 幂等重放到目标时刻。这样即使拷贝点晚于目标时刻，也能把键回滚到目标时刻的旧值，而不会被快照里的未来值锁死。
- 同刻边界：`at_ms <= target_ms` 的提交全部纳入，之后的不纳入；恢复结果记录同刻纳入的 seq 列表。
- 独立真值对账：用“快照∪WAL 按 seq 去重重建完整日志、再独立按目标时刻过滤”的第二条路径，与“快照还原+重放”路径逐条比对，校验和一致才标记可发布。

**可写性与恢复确定性的代价**：

|维度|收益|代价|
|---|---|---|
|可写性|备份全程可并发写入，无写阻塞|快照是模糊拷贝、不具时间点一致性，正确性完全依赖从 start_seq 起连续无缺的 WAL|
|恢复确定性|seq 幂等重放，重试不重复应用写入、结果与校验和可复现|RTO 随窗口写入量线性增长；同刻语义由序号次序确定，不支持“同刻只回滚部分提交”|
|完整性|快照/段/清单三层校验，缺段或损坏即发现|任何所需 WAL 段缺失/损坏都无法证明完整，恢复**明确失败并拒绝发布**，不允许带缺失猜测恢复|

**失败语义（有数据丢失风险就明确失败，无法证明完整时拒绝发布）**：`snapshot_corrupt` 快照校验和不符、`manifest_corrupt` 清单校验和不符、`wal_segment_missing` 所需 WAL 段缺失、`wal_segment_corrupt` 段校验和不符、`target_before_backup` 目标早于备份开始等，均以机器可读 fail_code 落库；失败任务只写失败证据，不产生任何恢复键值。发起恢复时可勾选缺段编号模拟日志缺段；备份表单可注入快照损坏或清单损坏。

**任务与隔离**：备份/恢复都走 queued→running→completed/failed，由同一个 worker 串行消费（Redis 消息为 `{kind,id}` 信封，兼容旧版纯 ID 试验消息）。重试复用原任务、按 seq 幂等，不重复应用写入，也不覆盖现有节点台账与旧试验；恢复任务名唯一、已完成结果不可变。备份/恢复 JSON 另在 ARTIFACT_DIR（默认 `/artifacts/pitr`）留一份可导出副本。种子数据 `WL-1117-PITR` 含 at_ms=400 同刻双提交，并预置一条完整备份与成功/同刻/缺段失败三条恢复演示。

## 工程说明

|服务|技术|职责|
|---|---|---|
|frontend|原生HTML/CSS/JS + Nginx|5业务页、编辑表单、共享组件、/api代理|
|backend|Python3.11/FastAPI/SQLAlchemy/PyJWT|校验、权限、审计、快照/备份恢复证据与导出|
|worker|Python3.11|会话时序路由算法、在线备份构造与定点恢复重放|
|db|MySQL8.0|真实持久化业务和JSON证据|
|redis|Redis7|持久队列|

各实体贯穿 `backend/src/{models,schemas,services,routes}` 和 `frontend/src/{api,stores,pages}`；其余强制目录含controllers/middlewares/config/constants/utils、components/common/hooks/types/router。三组件table/badge/frame共用；hooks/session/feedback和utils/forms/html共用；request_id/errors双中间件。

共享枚举角色admin/operator/viewer与任务queued/running/completed/failed位于 `backend/src/constants/enums.py` / `frontend/src/constants/enums.js`，security/trials、frame/badge消费。节点角色primary/replica和状态healthy/down由node schema及前端表单定义，事件类型由request_set schema及路由算法定义；备份损坏类型none/snapshot_corrupt/manifest_corrupt与恢复 fail_code 由 constants 枚举和 recovery_engine 定义，前端 FAIL_REASONS 消费。

环境变量见.env.example：COMPOSE_PROJECT_NAME、三端口、DB_PASSWORD、JWT_SECRET、SEED_DEMO，另支持 ARTIFACT_DIR 覆盖证据落盘目录（容器默认 /artifacts/pitr）。默认密码仅本地演示、JWT8小时；seed自然键仅补缺失，不覆盖修改。schema由metadata.create_all初始建表，无在线升级引擎。5服务均健康检查，backend/worker依赖健康db/redis，frontend依赖backend；数据库、Redis、worker产物使用命名卷。

本地开发：Python3.11安装backend/requirements.txt、配置DATABASE_URL/REDIS_URL，在backend运行 `uvicorn src.main:app --reload` 和 `python -m src.worker`，前端经Nginx同源代理。停止清空：`docker compose down -v --remove-orphans`。

限制：单worker串行、无生产任务重试/崩溃续跑；不模拟网络随机抖动、自动选主或完整GTID集合。Google Fonts离线回退，业务不依赖字体网络。

## License

MIT。源码外 `../../test-artifacts/gb-4108/` 含真实测试、截图与结果。
