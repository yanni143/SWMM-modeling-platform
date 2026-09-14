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

选择工程版本后可调用 `POST /api/model-versions/{version_id}/runs`。后端从 MinIO 下载 INP，在临时目录运行 PySWMM 一次，解析 OUT/RPT，并将输入、OUT、RPT、结果 GeoJSON、LISFLOOD 点源输入 JSON 和虚拟降雨 TXT 全部写回 MinIO。临时目录会在请求结束后删除。

每次运行都会生成独立的数据库记录和 `runs/{run_id}` MinIO 对象，不覆盖物理历史。用户侧按版本查看结果：`GET /api/model-results` 对每个版本只返回最新一次成功运行，地图和弹窗分别通过 `/api/model-versions/{version_id}/latest-result/layers` 与 `/latest-result/timeseries` 查询同一份有效结果。失败运行不会替换该版本上一次成功结果。

前端会在浏览器中保存当前版本、活动结果版本、图层顺序和显隐状态，刷新后自动恢复。点击“恢复初始状态”只会回到 V1、清除当前 RUN 图层并恢复默认图层顺序，不会删除数据库版本、运行记录或 MinIO 文件。

## 安全调参流程

调参只开放白名单中的常用低风险字段：子汇水区面积/不透水率/宽度/坡度、地表曼宁系数与洼蓄量、常用下渗参数、节点与排口高程、节点最大深度、管线长度/粗糙度以及圆管管径。拓扑、控制规则和复杂断面不开放修改。

前端通过地图或对象列表选择要素，后端再次执行白名单和范围校验。保存时不会覆盖原始 INP，而是生成带父版本关系的新版本，并把逐项旧值/新值写入 `model_parameter_changes`。新版本可以直接运行并加载结果图层。

研究区入口位于 `/api/models`，版本操作位于
`/api/model-versions/{version_id}`。`POST /api/models` 不存在；用户调参时会基于当前版本生成新的派生版本，原始 V1 不会被覆盖。每次成功运行会生成 `rate_<研究区>_without_sub.json`，可通过 `/api/runs/{run_id}/lisflood-input` 获取；同时以 `.rpt` 的 `Runoff Quantity Continuity → Final Storage` 为总雨量、以 INP 模拟时长为历时生成 `chi_<研究区>.txt`，可通过 `/api/runs/{run_id}/lisflood-virtual-rainfall` 获取。两份数据共同构成方案三输入，点源 JSON 不含汇水区滞蓄，虚拟降雨代表该部分水量。

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
