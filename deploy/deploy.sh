#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${PROJECT_DIR}/compose.prod.yaml"
ENV_FILE="${PROJECT_DIR}/.env.production"
ACTION="${1:-deploy}"

compose() {
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}

require_environment() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "缺少 ${ENV_FILE}。请先运行：bash deploy/generate-env.sh"
    exit 1
  fi

  if grep -q 'replace-with-' "${ENV_FILE}"; then
    echo "${ENV_FILE} 中仍有 replace-with- 占位值，请先填写。"
    exit 1
  fi

  if ! docker info >/dev/null 2>&1; then
    echo "当前用户无法访问 Docker。请退出 SSH 后重新登录，或先运行 server-bootstrap.sh。"
    exit 1
  fi
}

wait_for_health() {
  local attempts=30
  local response

  for ((i = 1; i <= attempts; i++)); do
    response="$(compose exec -T backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read().decode())" 2>/dev/null || true)"
    if [[ "${response}" == *'"status":"ok"'* || "${response}" == *'"status": "ok"'* ]]; then
      echo "健康检查通过：${response}"
      return 0
    fi
    sleep 2
  done

  echo "健康检查未通过，最近的容器状态和日志如下："
  compose ps
  compose logs --tail=100 backend web
  return 1
}

require_environment
cd "${PROJECT_DIR}"

case "${ACTION}" in
  deploy|update)
    compose config --quiet
    compose pull db minio || echo "基础镜像拉取失败，将尝试使用服务器已有缓存。"
    compose build backend web
    compose up -d --remove-orphans
    wait_for_health
    compose ps
    ;;
  status)
    compose ps
    ;;
  logs)
    compose logs -f --tail=200 "${@:2}"
    ;;
  stop)
    compose stop
    ;;
  restart)
    compose restart
    wait_for_health
    ;;
  *)
    echo "用法：bash deploy/deploy.sh [deploy|update|status|logs|stop|restart]"
    exit 1
    ;;
esac
