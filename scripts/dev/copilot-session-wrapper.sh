#!/usr/bin/env bash

set -Eeuo pipefail

if [[ "${COPILOT_SESSION_SUMMARY_MODE:-}" == "1" ]]; then
  exec copilot "$@"
fi

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly SUMMARY_OUTPUT_DIR="${REPO_ROOT}/docs/working-memory/session-logs"

run_summary_writer() {
  python3 "${SCRIPT_DIR}/write_session_summary.py" \
    --repo-root "${REPO_ROOT}" \
    --output-dir "${SUMMARY_OUTPUT_DIR}" \
    --exit-code "${1}" >/dev/null 2>&1 || true
}

cd "${REPO_ROOT}"
set +e
copilot "$@"
exit_code=$?
set -e
run_summary_writer "${exit_code}"
exit "${exit_code}"
