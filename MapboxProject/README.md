# SWMM 地图前端

Vue 3、Vite、Pinia 与 Mapbox GL 构建的固定研究区建模界面。

## 本地开发

复制 `.env.example` 为 `.env`，填写 Mapbox 公开 Token，然后执行：

```bash
npm ci
npm run dev
```

Vite 会将 `/api` 和 `/health` 代理到本机 `http://localhost:8000`。

## 生产构建

```bash
npm run build
```

完整生产部署使用仓库根目录的 `compose.prod.yaml` 和 `deploy/README.md`。
