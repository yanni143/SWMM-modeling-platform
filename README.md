# SWMM Modeling Platform

面向 SWMM 模型版本管理、结构化参数调整、模拟运行、结果解析与地图可视化的一体化平台。

## 目录

- `MapboxProject/`：Vue 3、Vite、Mapbox GL 前端。
- `PythonProject/`：FastAPI、PySWMM、PostgreSQL/PostGIS、MinIO 后端。

## 后端开发

1. 复制 `PythonProject/.env.example` 为 `PythonProject/.env`。
2. 填写 PostgreSQL 与 MinIO 配置。
3. 在 `PythonProject` 下安装依赖：`pip install -e .`。
4. 执行迁移：`alembic upgrade head`。
5. 启动：`uvicorn Controller.controller:app --host 0.0.0.0 --port 8000 --reload`。

真实 `.env`、虚拟环境、IDE 配置和构建目录禁止提交。

## 持久化约定

- PostgreSQL 数据库：`fenhuModel`。
- MinIO 默认私有 bucket：`swmm-artifacts`。
- 模型版本：`models/{model_id}/versions/{version_id}/model.inp`。
- 运行输入：`runs/{run_id}/input/model.inp`。
- 运行产物：`runs/{run_id}/{raw|visual|summary}/{filename}`。

SWMM 执行期间允许使用 `.runtime/` 临时目录，运行结束后的 INP、OUT、RPT、日志和可视化文件必须进入 MinIO。

## 前端开发

在 `MapboxProject` 下执行：

```powershell
npm install
npm run dev
```

可通过 `VITE_API_BASE_URL` 配置后端地址，开发环境默认使用 `http://localhost:8000`。
