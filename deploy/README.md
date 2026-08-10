# 腾讯云 Docker 部署手册

本方案面向 Ubuntu 24.04。第一次部署可通过公网 IP 使用 HTTP；有域名后只需修改生产环境变量即可由 Caddy 自动启用 HTTPS。

## 1. 修复 Docker 权限并初始化服务器

错误：

```text
permission denied while trying to connect to the Docker daemon socket
```

说明 Docker 已安装，但当前登录用户不在 `docker` 用户组。把项目上传到服务器后，在仓库根目录运行：

```bash
sudo bash deploy/server-bootstrap.sh
```

脚本会安装必要工具、在需要时安装 Docker，并将当前 sudo 用户加入 `docker` 组。完成后必须退出 SSH 并重新登录：

```bash
exit
ssh ubuntu@你的服务器公网IP
docker ps
docker compose version
```

如果暂时还没上传项目，也可先手动修复已有 Docker：

```bash
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
newgrp docker
docker ps
```

`newgrp docker` 会开启一个具有新用户组的子 Shell；重新登录 SSH 是更彻底的做法。

## 2. 腾讯云安全组

入站只开放：

| 端口 | 来源 | 用途 |
|---|---|---|
| 22/TCP | 你的公网 IP，练习时可临时放宽 | SSH |
| 80/TCP | 练习时设为你的公网 IP；公开后改为 `0.0.0.0/0` | HTTP |
| 443/TCP | 练习时设为你的公网 IP；公开后改为 `0.0.0.0/0` | HTTPS |

不要开放 5432、8000、9000、9001。它们只在 `swmm-internal` Docker 网络中通信。

服务器欢迎信息里的 `10.0.0.12` 是腾讯云私网 IP。浏览器访问时应使用控制台显示的公网 IP。

你的服务器当前提示有大量系统和安全更新。第一次部署前建议执行：

```bash
sudo apt update
sudo apt upgrade -y
if [[ -f /var/run/reboot-required ]]; then sudo reboot; fi
```

重启后重新 SSH 登录，再继续下面的步骤。

## 3. 上传仓库

推荐在服务器上使用 Git：

```bash
sudo mkdir -p /opt/swmm
sudo chown "$USER":"$USER" /opt/swmm
git clone 你的仓库地址 /opt/swmm/app
cd /opt/swmm/app
```

也可从 Windows PowerShell 上传当前工作目录：

```powershell
scp -r E:\SWMM ubuntu@服务器公网IP:/opt/swmm/app
```

不要上传本地 `.env`。生产配置由下一步单独生成。

## 4. 生成生产环境变量

在服务器仓库根目录执行：

```bash
cd /opt/swmm/app
bash deploy/generate-env.sh
nano .env.production
```

脚本会生成随机的 PostgreSQL 和 MinIO 密码，并将文件权限设置为 `600`。第一次使用公网 IP 练习时保留：

```dotenv
SITE_ADDRESS=:80
VITE_API_BASE_URL=/
```

必须填写：

```dotenv
VITE_MAPBOX_ACCESS_TOKEN=你的Mapbox公开Token
```

不要把 `.env.production` 提交到 Git，也不要在聊天或截图中公开它。

## 5. 第一次部署

```bash
cd /opt/swmm/app
bash deploy/deploy.sh deploy
```

脚本依次执行：

1. 检查环境文件和占位值。
2. 校验 Compose 配置。
3. 拉取 PostGIS、MinIO 基础镜像。
4. 构建前端和后端镜像。
5. 启动容器。
6. 后端启动时自动执行 `alembic upgrade head`。
7. 等待 `/health` 同时返回数据库和 MinIO 正常。

部署成功后访问：

```text
http://服务器公网IP
http://服务器公网IP/health
```

健康接口应返回：

```json
{"status":"ok","checks":{"database":"ok","minio":"ok"}}
```

## 6. 常用运维命令

```bash
# 查看状态
bash deploy/deploy.sh status

# 查看全部日志
bash deploy/deploy.sh logs

# 只看后端日志
bash deploy/deploy.sh logs backend

# 重启
bash deploy/deploy.sh restart

# 停止容器，但保留数据库和 MinIO 数据卷
bash deploy/deploy.sh stop
```

不要执行 `docker compose down -v`，其中 `-v` 会删除 PostgreSQL、MinIO 和证书数据卷。

## 7. 后续更新部署

先备份，再拉取代码并重新发布：

```bash
cd /opt/swmm/app
bash deploy/backup.sh
git pull --ff-only
bash deploy/deploy.sh update
```

`update` 会重建有变化的镜像，并保留命名数据卷。前端的 `VITE_*` 变量在构建时写入，因此修改 Mapbox Token 后也必须执行一次 `update`。

如果采用 SCP 上传，不执行 `git pull`，覆盖代码后直接运行 `update`。

## 8. 备份

手动备份：

```bash
bash deploy/backup.sh
```

备份默认写入：

```text
backups/年月日-时分秒/postgres.dump
backups/年月日-时分秒/minio/
```

这些备份仍在同一台服务器上，必须继续复制到腾讯云 COS、本地电脑或另一块云硬盘。建议同时在腾讯云控制台启用每日云硬盘快照。

数据库恢复示例应在确认目标数据库和备份文件后执行：

```bash
cat backups/时间/postgres.dump | docker compose --env-file .env.production -f compose.prod.yaml exec -T db pg_restore -U swmm -d fenhuModel --clean --if-exists
```

恢复会覆盖数据库对象，不要在未备份时试运行。

## 9. 以后绑定域名和 HTTPS

先把域名 A 记录解析到服务器公网 IP，并确认腾讯云安全组开放 80、443。然后修改：

```dotenv
SITE_ADDRESS=swmm.example.com
CORS_ORIGINS=https://swmm.example.com
```

重新部署：

```bash
bash deploy/deploy.sh update
```

Caddy 会自动申请证书并把 HTTP 跳转到 HTTPS。证书数据保存在 `caddy-data` 命名卷中。

如果使用腾讯云中国大陆服务器，域名对外提供服务前需要完成 ICP 备案。公网 IP 练习阶段可以先验证应用和容器是否正常。

## 10. 故障排查

### Docker 仍然 permission denied

```bash
id
getent group docker
ls -l /var/run/docker.sock
```

确认用户名出现在 docker 组后退出 SSH 并重新登录。不要长期用 `chmod 666 /var/run/docker.sock`，这会让所有本机用户获得接近 root 的容器控制权限。

### 页面打不开

依次检查：

```bash
bash deploy/deploy.sh status
curl -v http://127.0.0.1/health
sudo ss -lntp | grep -E ':80|:443'
```

本机正常而外部打不开，通常是腾讯云安全组没有放行 80/443，或者访问了私网 IP `10.0.0.12`。

### 后端显示 degraded

```bash
bash deploy/deploy.sh logs backend
docker compose --env-file .env.production -f compose.prod.yaml logs --tail=100 db minio
```

常见原因是环境文件里的数据库密码出现不一致、MinIO 尚未启动完成，或者旧数据卷由另一组账号创建。

### 拉取 Docker Hub 镜像超时

初始化脚本会在 `/etc/docker/daemon.json` 不存在时配置腾讯云内网镜像加速。如果服务器已经有该文件，脚本不会覆盖，可检查：

```bash
sudo cat /etc/docker/daemon.json
docker info | sed -n '/Registry Mirrors/,+3p'
```

需要手动配置时，将下面字段合并进现有 JSON，而不是直接覆盖其他 Docker 配置：

```json
{
  "registry-mirrors": ["https://mirror.ccs.tencentyun.com"]
}
```

然后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl restart docker
```

### 前端地图不显示

检查浏览器开发者工具，以及 `.env.production` 中的 `VITE_MAPBOX_ACCESS_TOKEN`。Token 修改后需要重新构建前端：

```bash
bash deploy/deploy.sh update
```
