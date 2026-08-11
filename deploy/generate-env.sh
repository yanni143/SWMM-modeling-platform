#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${PROJECT_DIR}/.env.production"
TEMPLATE="${PROJECT_DIR}/.env.production.example"

if [[ -e "${TARGET}" ]]; then
  echo "${TARGET} 已存在，未覆盖。"
  exit 1
fi

POSTGRES_PASSWORD="$(openssl rand -hex 24)"
MINIO_PASSWORD="$(openssl rand -hex 24)"

sed \
  -e "s/replace-with-a-long-random-password/${POSTGRES_PASSWORD}/g" \
  -e "s/replace-with-another-long-random-password/${MINIO_PASSWORD}/g" \
  "${TEMPLATE}" > "${TARGET}"

chmod 600 "${TARGET}"
echo "已生成 ${TARGET}"
echo "请编辑 VITE_MAPBOX_ACCESS_TOKEN；使用域名时也要修改 CORS_ORIGINS。"
