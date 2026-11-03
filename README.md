# SWMM Modeling Platform

面向 SWMM 工程版本管理、结构化参数调整、模拟运行、结果解析与地图可视化的一体化平台。

## 目录

- `ReactProject/`：React、Vite、Mapbox GL 前端。
- `PythonProject/`：FastAPI、PySWMM、PostgreSQL、MinIO 后端。

## 后端开发

1. 复制 `PythonProject/.env.example` 为 `PythonProject/.env`。
2. 填写 PostgreSQL 与 MinIO 配置。
3. 在仓库根目录执行 `docker compose up -d minio`，启动本地对象存储。
4. 在 `PythonProject` 下安装依赖：`pip install -e .`。
5. 执行迁移：`alembic upgrade head`。
6. 启动：`uvicorn Controller.controller:app --host 0.0.0.0 --port 8000 --reload`。

真实 `.env`、虚拟环境、IDE 配置和构建目录禁止提交。

## 后端职责边界

- `PythonProject/app/swmm/`：SWMM 运行、INP/RPT/OUT 通用解析和可视化结果；不包含任何 LISFLOOD 规则。
- `PythonProject/app/lisflood_coupling/`：以同一模型版本的 INP、运行 RPT 和 LC/JJ 配置为输入，生成点源溢流 JSON 与虚拟降雨 TXT；不运行 SWMM、不访问数据库或 MinIO。
- `PythonProject/Service/SimulationService.py`：只编排模型运行、产物归档和对 `LisfloodExporter` 的调用。现有 LISFLOOD 下载 API 与产物名称保持不变。

## 持久化约定

- PostgreSQL 数据库：`fenhuModel`。
- MinIO 默认私有 bucket：`swmm-artifacts`。
- 工程版本：`models/{model_id}/versions/{version_id}/model.inp`（对象路径暂保持兼容）。
- 运行输入：`runs/{run_id}/input/model.inp`。
- 运行产物：`runs/{run_id}/{input|raw|visual|lisflood}/{filename}`。

SWMM 执行期间允许使用 `.runtime/` 临时目录，运行结束后的 INP、OUT、RPT、日志和可视化文件必须进入 MinIO。

## 预置研究区

系统不向用户提供 INP 上传能力。应用启动时会从后端资源目录幂等地注册两个研究区及其基线 V1：

- `PythonProject/resources/study_areas/lc/model.inp`（LC）；
- `PythonProject/resources/study_areas/jj/model.inp`（JJ）。

用户可在浏览器中选择研究区，并基于任一版本生成调参后的新版本。

前端显示研究区中文名：JJ 为金江，LC 为老城。每个研究区只有一个初始基线 V1，
降雨条件作为当前版本的可编辑参数保存，不再通过第二份完整 INP 切换版本根。

降雨设置支持芝加哥雨型、金江内置真实降雨事件、自定义固定间隔序列（粘贴 / CSV 导入）。
三种来源统一转换为分段雨量（mm）并替换目标降雨时间序列，保存后生成派生版本。
修改降雨保留父版本工程参数；仅修改工程参数或输出步长完整继承原降雨，不重新生成序列。

实测事件资料为 `PythonProject/resources/rainfall/jj/JJ_real_20260913_2d.json`，
从原始累计记录提取 576 个 5 分钟分段雨量，覆盖 48 小时，总雨量 226.2 mm。
原始 INP 留作历史核对，不再用于登记基线。事件日期用于说明，雨量按相对时间应用到当前模型。
选择事件不会修改模型开始日期、模拟时长或输出步长；用户需在原控件中设置足以覆盖序列的模拟时长。

自定义序列每行一个雨量值，也支持 `offset_seconds,rainfall_mm` 两列格式，时间从 0 按间隔连续排列。
间隔和开始偏移以整数秒填写；总雨量、覆盖时长和峰值由序列计算；允许全零降雨。
格式、接口示例、升级及验收步骤见 [降雨序列说明](PythonProject/docs/rainfall-sequences.md)。

模拟降雨的时长上限也扩展到 172800 秒（48 小时）。已有部署需将 `.env.production`
中的 `SIMULATION_DURATION_MAX_SECONDS` 更新为 `172800` 并重建/重启服务；
开发环境如有同名配置也需同步。默认输出点数上限仍为 1000，两天采用 300 秒输出步长为 576 步。

选择工程版本后可调用 `POST /api/model-versions/{version_id}/runs`。后端从 MinIO 下载 INP，在临时目录运行 PySWMM 一次，解析 OUT/RPT，并将输入、OUT、RPT、结果 GeoJSON、LISFLOOD 点源输入 JSON 和虚拟降雨 TXT 全部写回 MinIO。临时目录会在请求结束后删除。

每次运行都会生成独立的数据库记录和 `runs/{run_id}` MinIO 对象，不覆盖物理历史。用户侧按版本查看结果：`GET /api/model-results` 对每个版本只返回最新一次成功运行，地图和弹窗分别通过 `/api/model-versions/{version_id}/latest-result/layers` 与 `/latest-result/timeseries` 查询同一份有效结果。失败运行不会替换该版本上一次成功结果。

前端会在浏览器中按研究区保存当前版本与活动结果，以及图层顺序和显隐状态，刷新后自动恢复。旧版按降雨方案保存的选择会自动迁移。点击“恢复初始状态”返回当前研究区唯一 V1、清除当前 RUN 图层并恢复默认图层顺序，不会删除数据库版本、运行记录或 MinIO 文件。

## 安全调参流程

调参只开放白名单中的常用低风险字段：子汇水区面积/不透水率/宽度/坡度、地表曼宁系数与洼蓄量、常用下渗参数、节点与排口高程、节点最大深度、管线长度/粗糙度以及圆管管径。拓扑、控制规则和复杂断面不开放修改。

前端通过地图或对象列表选择要素，后端再次执行白名单和范围校验。保存时不会覆盖原始 INP，而是生成带父版本关系的新版本，并把逐项旧值/新值写入 `model_parameter_changes`。新版本可以直接运行并加载结果图层。

研究区入口位于 `/api/models`，版本操作位于
`/api/model-versions/{version_id}`。`POST /api/models` 不存在；用户调参时会基于当前版本生成新的派生版本，原始 V1 不会被覆盖。每次成功运行会生成 `rate_<研究区>_without_sub.json`，可通过 `/api/runs/{run_id}/lisflood-input` 获取；同时将 `.rpt` 的 `Runoff Quantity Continuity → Final Storage` 雨深按“SWMM 汇水面积 / 对应 LISFLOOD 二维域面积”缩放后、以 INP 模拟时长为历时生成 `chi_<研究区>.txt`，可通过 `/api/runs/{run_id}/lisflood-virtual-rainfall` 获取。两份数据共同构成方案三输入，点源 JSON 不含汇水区滞蓄，虚拟降雨代表该部分水量。

LISFLOOD 对接方可先调用 `GET /api/study-areas/latest-model-versions` 获取 LC、JJ 模拟降雨方案的当前 `version_id`；添加 `?rainfall_mode=real` 获取真实降雨版本，`?rainfall_mode=custom` 获取自定义降雨版本，`?rainfall_mode=all` 获取不区分降雨来源的最新版本。再分别调用 `/api/model-versions/{version_id}/latest-result/lisflood-input` 与 `/api/model-versions/{version_id}/latest-result/lisflood-virtual-rainfall` 下载点源输入和虚拟降雨。

## 前端开发

在 `ReactProject` 下执行：

```powershell
npm install
npm run dev
```

开发服务器会把 `/api` 和 `/health` 代理到 `http://localhost:8000`；生产环境由容器 Nginx 同源代理。

## 腾讯云生产部署

仓库提供了一套适用于 Ubuntu 24.04 的 Docker Compose 部署配置：

- `compose.prod.yaml`：PostgreSQL、MinIO、FastAPI 和 Nginx/React。
- `.env.production.example`：生产环境变量模板。
- `deploy/server-bootstrap.sh`：服务器初始化和 Docker 权限配置。
- `deploy/generate-env.sh`：生成随机数据库与 MinIO 密码。
- `deploy/deploy.sh`：构建、发布、更新、查看日志和状态。
- `deploy/backup.sh`：备份 PostgreSQL 和 MinIO。

完整步骤见 [`deploy/README.md`](deploy/README.md)。
