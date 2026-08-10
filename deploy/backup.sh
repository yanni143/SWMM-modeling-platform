#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PROJECT_DIR}/.env.production"
COMPOSE_FILE="${PROJECT_DIR}/compose.prod.yaml"
BACKUP_ROOT="${BACKUP_DIR:-${PROJECT_DIR}/backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DESTINATION="${BACKUP_ROOT}/${STAMP}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "缺少 ${ENV_FILE}"
  exit 1
fi

env_value() {
  local key="$1"
  sed -n "s/^${key}=//p" "${ENV_FILE}" | tail -n 1
}

POSTGRES_USER="$(env_value POSTGRES_USER)"
POSTGRES_DB="$(env_value POSTGRES_DB)"
MINIO_ROOT_USER="$(env_value MINIO_ROOT_USER)"
MINIO_ROOT_PASSWORD="$(env_value MINIO_ROOT_PASSWORD)"
MINIO_BUCKET="$(env_value MINIO_BUCKET)"
MINIO_MC_IMAGE="$(env_value MINIO_MC_IMAGE)"
MINIO_MC_IMAGE="${MINIO_MC_IMAGE:-quay.io/minio/mc:latest}"

if [[ -z "${POSTGRES_USER}" || -z "${POSTGRES_DB}" || -z "${MINIO_ROOT_USER}" || -z "${MINIO_ROOT_PASSWORD}" || -z "${MINIO_BUCKET}" ]]; then
  echo "${ENV_FILE} 缺少备份所需的数据库或 MinIO 配置。"
  exit 1
fi

mkdir -p "${DESTINATION}/minio"
chmod 700 "${BACKUP_ROOT}" "${DESTINATION}"

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T db \
  pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc \
  > "${DESTINATION}/postgres.dump"

docker run --rm \
  --network swmm-internal \
  -v "${DESTINATION}/minio:/backup" \
  --entrypoint /bin/sh \
  "${MINIO_MC_IMAGE}" \
  -c "mc alias set local http://minio:9000 '${MINIO_ROOT_USER}' '${MINIO_ROOT_PASSWORD}' >/dev/null && mc mirror --overwrite local/'${MINIO_BUCKET}' /backup"

echo "备份完成：${DESTINATION}"
echo "请再把该目录复制到 COS、另一块磁盘或本地；同机备份不能防止整机故障。"
