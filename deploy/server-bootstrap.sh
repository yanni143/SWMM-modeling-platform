#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "请使用 sudo 运行：sudo bash deploy/server-bootstrap.sh"
  exit 1
fi

DEPLOY_USER="${SUDO_USER:-ubuntu}"

apt-get update
apt-get install -y ca-certificates curl git openssl

if ! command -v docker >/dev/null 2>&1; then
  apt-get install -y docker.io docker-compose-v2
fi

if ! docker compose version >/dev/null 2>&1; then
  apt-get install -y docker-compose-v2 || apt-get install -y docker-compose-plugin
fi

if [[ ! -e /etc/docker/daemon.json ]]; then
  install -m 0755 -d /etc/docker
  printf '%s\n' \
    '{' \
    '  "registry-mirrors": ["https://mirror.ccs.tencentyun.com"]' \
    '}' \
    > /etc/docker/daemon.json
  echo "已为腾讯云内网配置 Docker Hub 镜像加速。"
else
  echo "/etc/docker/daemon.json 已存在，脚本未覆盖；如拉取 Docker Hub 超时，请手动合并 registry-mirrors 配置。"
fi

systemctl enable --now docker
systemctl restart docker
usermod -aG docker "${DEPLOY_USER}"

echo
echo "Docker 已安装并已将 ${DEPLOY_USER} 加入 docker 组。"
echo "请退出 SSH 并重新登录，然后运行：docker ps"
echo "当前会话若要立即验证，可运行：sudo docker ps"
