#!/usr/bin/env bash
# Start, stop or check the web UI (uvicorn with --reload) in the background.
#
#   scripts/ui.sh start | stop | restart | status | logs
#
# HOST and PORT can be overridden from the environment (default 127.0.0.1:8100).
set -euo pipefail

# Config and the database are resolved relative to the working directory
cd "$(dirname "$0")/.."

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8100}"
PID_FILE=".ui.pid"
LOG_FILE="ui.log"

# The pid file holds the pid and the URL it was started on, one per line
running_url() {
    sed -n 2p "$PID_FILE"
}

running_pid() {
    [[ -f "$PID_FILE" ]] || return 1
    local pid
    pid="$(sed -n 1p "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
        echo "$pid"
    else
        rm -f "$PID_FILE"
        return 1
    fi
}

port_in_use() {
    lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

start() {
    local pid
    if pid="$(running_pid)"; then
        echo "UI already running (pid $pid) at $(running_url)"
        return 0
    fi
    if port_in_use "$PORT"; then
        echo "Port $PORT is already in use by another process; set PORT=<free port>" >&2
        return 1
    fi

    nohup uv run uvicorn gin_rummy.web.app:app --reload --host "$HOST" --port "$PORT" \
        >"$LOG_FILE" 2>&1 &
    pid=$!
    printf '%s\n%s\n' "$pid" "http://$HOST:$PORT" >"$PID_FILE"

    for _ in $(seq 1 50); do
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$PID_FILE"
            echo "UI failed to start; last lines of $LOG_FILE:" >&2
            tail -n 20 "$LOG_FILE" >&2
            return 1
        fi
        if port_in_use "$PORT"; then
            echo "UI started (pid $pid) at http://$HOST:$PORT (log: $LOG_FILE)"
            return 0
        fi
        sleep 0.2
    done
    echo "UI started (pid $pid) but is not listening on port $PORT yet; see $LOG_FILE" >&2
    return 1
}

stop() {
    local pid
    if ! pid="$(running_pid)"; then
        echo "UI is not running"
        return 0
    fi
    kill "$pid"
    for _ in $(seq 1 50); do
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$PID_FILE"
            echo "UI stopped"
            return 0
        fi
        sleep 0.2
    done
    echo "UI (pid $pid) did not stop within 10s; run 'kill -9 $pid' to force it" >&2
    return 1
}

status() {
    local pid
    if pid="$(running_pid)"; then
        echo "UI running (pid $pid) at $(running_url)"
    else
        echo "UI is not running"
        return 1
    fi
}

case "${1:-}" in
    start) start ;;
    stop) stop ;;
    restart) stop && start ;;
    status) status ;;
    logs) tail -f "$LOG_FILE" ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}" >&2
        exit 2
        ;;
esac
