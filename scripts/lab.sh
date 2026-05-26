#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -z "${CONFIG:-}" ]; then
  if [ -f config/lab.yaml ]; then CONFIG=config/lab.yaml
  elif [ -f config/lab.json ]; then CONFIG=config/lab.json
  else CONFIG=config/lab.yaml.example
  fi
fi
CMD="${1:-up}"

python3() {
  command python3 "$@" 2>/dev/null || command python "$@"
}

generate() {
  python3 scripts/generate_compose.py -c "$CONFIG"
}

case "$CMD" in
  generate)
    generate
    ;;
  up)
    generate
    docker compose build
    docker compose up -d
    ;;
  down)
    docker compose down
    ;;
  restart)
    generate
    docker compose down
    docker compose build
    docker compose up -d
    ;;
  status)
    docker compose ps
    ;;
  logs)
    docker compose logs -f "${2:-}"
    ;;
  detect-gateway)
    python3 scripts/host_network.py -j
    ;;
  *)
    echo "Usage: $0 {up|down|restart|generate|status|logs|detect-gateway}" >&2
    exit 1
    ;;
esac
