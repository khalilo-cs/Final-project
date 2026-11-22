#!/usr/bin/env bash
# The whole system on one machine WITHOUT Docker: every service under uvicorn with
# SQLite, the built frontend behind nginx (or the Vite dev server if nginx is absent).
# Good for development, demos and the end-to-end test (e2e.py). Production uses
# docker compose (performance tests in the sandbox need Docker).
#
#   tools/local-stack/run.sh          start (http://localhost:8080)
#   tools/local-stack/run.sh stop     stop everything
#
# Environment: VENV (default .venv-local), DATA (default local-data), JWT_SECRET.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DATA="${DATA:-$ROOT/local-data}"
VENV="${VENV:-$ROOT/.venv-local}"
PORT="${PORT:-8080}"
mkdir -p "$DATA/logs" "$DATA/run"

stop() {
  for pid in "$DATA"/run/*.pid; do
    [ -e "$pid" ] || continue
    kill "$(cat "$pid")" 2>/dev/null || true
    rm -f "$pid"
  done
  [ -f "$DATA/run/nginx.conf" ] && nginx -c "$DATA/run/nginx.conf" -s stop 2>/dev/null || true
  echo "stopped"
}
if [ "${1:-}" = "stop" ]; then stop; exit 0; fi
stop >/dev/null

# -- Python environment (one venv for all services) ---------------------------------
if [ ! -x "$VENV/bin/uvicorn" ]; then
  echo "creating $VENV and installing requirements (first run only)..."
  python3 -m venv "$VENV"
  cat "$ROOT"/services/*/requirements.txt | grep -v '^\s*#' | sort -u > "$DATA/run/requirements.txt"
  "$VENV/bin/pip" install -q -r "$DATA/run/requirements.txt"
fi

# -- shared settings ---------------------------------------------------------------
SECRET_FILE="$DATA/run/jwt_secret"
[ -s "$SECRET_FILE" ] || python3 -c "import secrets;print(secrets.token_urlsafe(48))" > "$SECRET_FILE"
export JWT_SECRET="${JWT_SECRET:-$(cat "$SECRET_FILE")}"
export ADMIN_USERNAME="${ADMIN_USERNAME:-admin}" ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin-password-1}"
export PUBLIC_URL="http://localhost:$PORT"
export SPEECH_BACKEND="${SPEECH_BACKEND:-off}"   # Whisper models are large: opt in
export STORAGE_DIR="$DATA/storage"

start() {  # name port [extra env...]
  local name=$1 port=$2; shift 2
  # exec: the recorded PID is uvicorn itself (so `stop` reaches it), and no shell is
  # left holding the caller's terminal open.
  ( cd "$ROOT/services/$name" || exit 1
    exec env DATABASE_URL="sqlite:///$DATA/$name.db" "$@" \
      "$VENV/bin/uvicorn" app.main:app --host 127.0.0.1 --port "$port" \
      < /dev/null > "$DATA/logs/$name.log" 2>&1 ) &
  echo $! > "$DATA/run/$name.pid"
}
start auth-service 8001
start project-service 8002
start code-analyzer 8003
start db-analyzer 8004
start report-analyzer 8005
start viva-engine 8006
start fraud-detector 8007
start sandbox-runner 8008
start report-generator 8009
start speech-service 8010

# -- frontend ------------------------------------------------------------------------
cd "$ROOT/frontend"
[ -d node_modules ] || npm ci --no-audit --no-fund >/dev/null
if command -v nginx >/dev/null; then
  npm run -s build >/dev/null
  mkdir -p "$DATA/run/mihakk" "$DATA/run/tmp"
  cp nginx/http.inc "$DATA/run/mihakk/"
  # Same gateway as production; service names become localhost.
  sed -e "s|root /usr/share/nginx/html;|root $ROOT/frontend/dist;|" \
      -e 's|http://\([a-z-]*\):\([0-9]*\)|http://127.0.0.1:\2|g' nginx/site.inc > "$DATA/run/mihakk/site.inc"
  cat > "$DATA/run/nginx.conf" <<CONF
pid $DATA/run/nginx.pid;
error_log $DATA/logs/nginx.log;
events {}
http {
  include /etc/nginx/mime.types;
  access_log off;
  client_body_temp_path $DATA/run/tmp;
  proxy_temp_path $DATA/run/tmp;
  include $DATA/run/mihakk/http.inc;
  server { listen 127.0.0.1:$PORT; include $DATA/run/mihakk/site.inc; }
}
CONF
  nginx -c "$DATA/run/nginx.conf" < /dev/null >> "$DATA/logs/nginx.log" 2>&1
else
  echo "nginx not found: using the Vite dev server instead"
  ( exec npx vite --port "$PORT" --strictPort < /dev/null > "$DATA/logs/vite.log" 2>&1 ) &
  echo $! > "$DATA/run/vite.pid"
fi

# -- wait until everything answers -------------------------------------------------
for port in 8001 8002 8003 8004 8005 8006 8007 8008 8009 8010; do
  for _ in $(seq 60); do
    curl -fs "http://127.0.0.1:$port/health" >/dev/null && break
    sleep 0.5
  done
  curl -fs "http://127.0.0.1:$port/health" >/dev/null || { echo "service on $port did not start: see $DATA/logs"; exit 1; }
done
for _ in $(seq 60); do curl -fs "http://localhost:$PORT/" >/dev/null && break; sleep 0.5; done
echo "Mihakk is running: http://localhost:$PORT  (admin: $ADMIN_USERNAME / $ADMIN_PASSWORD)"
echo "logs: $DATA/logs    stop: tools/local-stack/run.sh stop"
