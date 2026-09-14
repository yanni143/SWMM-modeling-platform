# 腾讯云共享服务器部署手册

本方案适用于 Ubuntu 24.04，尤其是已经运行其他 Docker 容器和宿主机 Nginx 的服务器。

SWMM 使用独立的 PostgreSQL、MinIO、Docker 网络和命名卷，不复用或修改服务器现有的 `jssdc-*` 服务。前端容器使用 Nginx，并且默认只监听宿主机 `127.0.0.1:18084`；公网流量由宿主机现有 Nginx 统一接入。

```text
浏览器 → 宿主机 Nginx :80/:443 → 127.0.0.1:18084
                                      ↓
                              SWMM 前端 Nginx
                                ├─ React 静态文件
                                └─ /api → FastAPI
                                           ├─ PostgreSQL
                                           └─ MinIO
```

## 1. 部署前检查

```bash
docker ps
docker compose version
sudo ss -lntp | grep -E ':(80|443|18084)\b'
free -h
df -h
```

当前服务器若已经能正常执行 `docker ps` 和 `docker compose version`，不要运行 `server-bootstrap.sh`，也不要为了本项目重启 Docker。该脚本只用于全新服务器安装缺失工具；即使运行，新版本也不会重启 Docker 或修改 `/etc/docker/daemon.json`。

对于已有业务的共享服务器，系统升级、服务器重启和 Docker 升级都应安排维护时间。

## 2. 腾讯云安全组

公开服务通常只需要：

| 端口 | 来源 | 用途 |
|---|---|---|
| 22/TCP | 管理员公网 IP | SSH |
| 80/TCP | `0.0.0.0/0` | 宿主机 Nginx HTTP |
| 443/TCP | `0.0.0.0/0` | 宿主机 Nginx HTTPS |

不要为 SWMM 开放 5432、8000、9000、9001 或 18084。`18084` 默认只绑定 `127.0.0.1`，无法从公网直接访问。

同时检查现有 Redis、PostgreSQL 和 MinIO 的 6379、5432、9000 是否被安全组拦截，避免数据库和对象存储直接暴露公网。

## 3. 上传仓库

推荐使用 Git：

```bash
sudo mkdir -p /opt/swmm
sudo chown "$USER":"$USER" /opt/swmm
git clone 你的仓库地址 /opt/swmm/app
cd /opt/swmm/app
```

仓库已经存在时：

```bash
cd /opt/swmm/app
git pull --ff-only
```

也可以从 Windows PowerShell 上传：

```powershell
scp -r E:\SWMM ubuntu@服务器公网IP:/opt/swmm/app
```

不要上传本地 `.env`，也不要把生产密码提交到 Git。

## 4. 生成生产环境变量

```bash
cd /opt/swmm/app
bash deploy/generate-env.sh
nano .env.production
```

脚本会生成随机 PostgreSQL 和 MinIO 密码，并把文件权限设置为 `600`。必须填写：

```dotenv
VITE_MAPBOX_ACCESS_TOKEN=你的Mapbox公开Token
```

共享服务器保持以下配置：

```dotenv
WEB_BIND_ADDRESS=127.0.0.1
WEB_PORT=18084
VITE_API_BASE_URL=/
```

使用域名时可设置：

```dotenv
CORS_ORIGINS=https://swmm.example.com
```

前端和 API 实际为同源访问，宿主机 Nginx 会把请求完整转发到容器端口。

## 5. 第一次部署

```bash
cd /opt/swmm/app
bash deploy/deploy.sh deploy
```

脚本会：

1. 检查环境文件和占位值。
2. 校验 Compose 配置。
3. 拉取独立 PostgreSQL、MinIO 镜像。
4. 构建 Nginx/React 前端和 FastAPI/PySWMM 后端。
5. 启动独立容器、网络和数据卷。
6. 自动执行 `alembic upgrade head`。
7. 初始化固定研究区 V1。
8. 验证数据库和 MinIO 健康状态。

SWMM Compose 不会停止或修改任何 `jssdc-*` 容器。

## 6. 部署后验证

服务器本机检查：

```bash
bash deploy/deploy.sh status
curl http://127.0.0.1:18084/health
curl -I http://127.0.0.1:18084/
```

健康接口应返回：

```json
{"status":"ok","checks":{"database":"ok","minio":"ok"}}
```

还没有域名或宿主机 Nginx 配置时，可以通过 SSH 隧道练习，不需要开放 18084：

```powershell
ssh -L 18084:127.0.0.1:18084 ubuntu@服务器公网IP
```

保持该 SSH 窗口打开，在本机浏览器访问：

```text
http://127.0.0.1:18084
http://127.0.0.1:18084/health
```

如果确实需要临时通过公网端口练习，可把 `.env.production` 改为 `WEB_BIND_ADDRESS=0.0.0.0`，并仅向自己的公网 IP 放行安全组 18084。练习完成后应恢复 `127.0.0.1` 并重新部署。

## 7. 接入宿主机 Nginx

仓库提供了 `deploy/nginx-swmm.conf.example`。先复制并修改域名：

```bash
sudo cp /opt/swmm/app/deploy/nginx-swmm.conf.example /etc/nginx/sites-available/swmm.conf
sudo nano /etc/nginx/sites-available/swmm.conf
```

把：

```nginx
server_name swmm.example.com;
```

替换成实际域名。启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/swmm.conf /etc/nginx/sites-enabled/swmm.conf
sudo nginx -t
sudo systemctl reload nginx
```

如果现有 Nginx 不使用 `sites-available/sites-enabled`，可把配置复制到它实际包含的 `conf.d` 目录。先用下面命令确认，不要覆盖现有配置：

```bash
sudo nginx -T 2>/dev/null | grep -nE 'include|server_name|listen'
```

`nginx -t` 必须成功后才能执行 `reload`。使用 `reload`，不要为了增加站点执行 `restart`。

HTTPS 证书由宿主机现有 Nginx 的证书管理方式统一配置。本项目容器不再申请或保存证书。

## 8. 常用运维命令

```bash
# 状态
bash deploy/deploy.sh status

# 全部日志
bash deploy/deploy.sh logs

# 后端日志
bash deploy/deploy.sh logs backend

# 前端 Nginx 日志
bash deploy/deploy.sh logs web

# 重启 SWMM 容器
bash deploy/deploy.sh restart

# 停止 SWMM 容器，保留数据卷
bash deploy/deploy.sh stop
```

不要执行 `docker compose down -v`，`-v` 会删除 SWMM 的 PostgreSQL 和 MinIO 数据卷。

## 9. 后续更新

```bash
cd /opt/swmm/app
bash deploy/backup.sh
git pull --ff-only
bash deploy/deploy.sh update
```

更新会保留 SWMM 命名卷，不影响服务器其他项目。`VITE_*` 变量会在前端构建时写入，因此修改 Mapbox Token 后也要运行 `update`。

## 10. 备份

```bash
bash deploy/backup.sh
```

备份目录：

```text
backups/年月日-时分秒/postgres.dump
backups/年月日-时分秒/minio/
```

同机备份不能防止整机故障，应继续复制到腾讯云 COS、另一块云硬盘或本地电脑。

## 11. 故障排查

### 18084 没有监听

```bash
bash deploy/deploy.sh status
bash deploy/deploy.sh logs web
sudo ss -lntp | grep 18084
```

### 健康状态 degraded

```bash
bash deploy/deploy.sh logs backend
docker compose --env-file .env.production -f compose.prod.yaml logs --tail=100 db minio
```

### 宿主机 Nginx 返回 502

```bash
curl -v http://127.0.0.1:18084/health
sudo nginx -t
sudo tail -n 100 /var/log/nginx/error.log
```

### Docker Hub 拉取超时

共享服务器不要未经评估直接重启 Docker。先检查现有配置：

```bash
sudo cat /etc/docker/daemon.json
docker info | sed -n '/Registry Mirrors/,+3p'
```

需要增加镜像源或升级 Docker 时，应与现有 `jssdc` 系统一起安排维护窗口。
