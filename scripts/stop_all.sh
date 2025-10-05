#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-5050}"
FRONTEND_PORT="${FRONTEND_PORT:-3100}"
BACKEND_CMD_PATTERN="${BACKEND_CMD_PATTERN:-[p]ython -m backend.app}"
FRONTEND_CMD_PATTERN="${FRONTEND_CMD_PATTERN:-[n]ext dev}"

collect_pids() {
  local pid_file="$1"
  local pattern="$2"
  local port="$3"

  local from_file=""
  if [[ -f "${pid_file}" ]]; then
    from_file="$(tr '\n' ' ' <"${pid_file}")"
  fi

  local from_pattern=""
  if [[ -n "${pattern}" ]]; then
    from_pattern="$(pgrep -f "${pattern}" 2>/dev/null | tr '\n' ' ' || true)"
  fi

  local from_port=""
  if [[ -n "${port}" ]]; then
    from_port="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' || true)"
  fi

  printf '%s\n%s\n%s\n' "${from_file}" "${from_pattern}" "${from_port}" \
    | tr ' ' '\n' \
    | sed '/^$/d' \
    | sort -u \
    | tr '\n' ' '
}

stop_service() {
  local name="$1"
  local pid_file="$2"
  local pattern="$3"
  local port="$4"

  local pids
  pids="$(collect_pids "${pid_file}" "${pattern}" "${port}")"

  if [[ -n "${pids}" ]]; then
    echo "Stopping ${name} (${pids})"
    # shellcheck disable=SC2086 # deliberate word splitting for kill arguments
    kill ${pids} >/dev/null 2>&1 || true
    sleep 0.5
    if [[ -n "${port}" ]]; then
      local still_listening
      still_listening="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' || true)"
      if [[ -n "${still_listening}" ]]; then
        echo "${name^} still listening on ${port}; sending SIGKILL"
        # shellcheck disable=SC2086
        kill -9 ${still_listening} >/dev/null 2>&1 || true
      fi
    fi
  else
    echo "No ${name} process found"
  fi

  rm -f "${pid_file}"
}

stop_service "backend" "logs/backend.pid" "${BACKEND_CMD_PATTERN}" "${BACKEND_PORT}"
stop_service "frontend" "logs/frontend.pid" "${FRONTEND_CMD_PATTERN}" "${FRONTEND_PORT}"
