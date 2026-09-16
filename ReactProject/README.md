# SWMM React 前端

这是原 Vue + Pinia 前端的 React + Zustand 迁移版本；后端 API、Mapbox 图层与结果交互保持兼容。

## 启动

```powershell
cd ReactProject
Copy-Item .env.example .env
npm install
npm run dev
```

开发服务器会将 `/api` 与 `/health` 代理至 `http://localhost:8000`。请在 `.env` 中配置 `VITE_MAPBOX_ACCESS_TOKEN`。

## 验证

```powershell
npm run build
```

状态管理位于 `src/stores/modelStore.ts`，采用 Zustand；前端 API 契约位于 `src/api/models.ts`，保持与原后端一致。
