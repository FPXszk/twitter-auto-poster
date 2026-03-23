#!/usr/bin/env bash

summarize_post_result_file() {
  local post_result_file="$1"

  python_cmd - "${post_result_file}" <<'PY'
import json
import pathlib
import sys


def condense(text: str) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= 400:
        return normalized
    return normalized[:397] + "..."


path = pathlib.Path(sys.argv[1])
if not path.exists():
    print("twitter post did not create a result file")
    raise SystemExit(0)

raw = path.read_text(encoding="utf-8", errors="replace").strip()
if not raw:
    print("twitter post created an empty result file")
    raise SystemExit(0)

try:
    payload = json.loads(raw)
except json.JSONDecodeError:
    print(f"twitter post returned a non-JSON response: {condense(raw)}")
    raise SystemExit(0)

message = str(payload.get("message") or "").strip()
if message:
    print(message)
    raise SystemExit(0)

parts = []
error = str(payload.get("error") or "").strip()
stderr = condense(str(payload.get("stderr") or ""))
stdout = condense(str(payload.get("stdout") or ""))
exit_code = payload.get("exit_code")

if error:
    if exit_code not in (None, ""):
        parts.append(f"{error} (exit code {exit_code})")
    else:
        parts.append(error)
elif exit_code not in (None, ""):
    parts.append(f"twitter post failed with exit code {exit_code}")

if stderr:
    parts.append(f"stderr: {stderr}")
if stdout:
    parts.append(f"stdout: {stdout}")

print(" | ".join(parts) if parts else "twitter post failed")
PY
}

write_post_failure_file() {
  local output_path="$1"
  local error_label="$2"
  local exit_code="$3"
  local stdout_path="$4"
  local stderr_path="$5"

  python_cmd - "${output_path}" "${error_label}" "${exit_code}" "${stdout_path}" "${stderr_path}" <<'PY'
import json
import pathlib
import sys


def read_preview(path_str: str) -> str:
    path = pathlib.Path(path_str)
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    normalized = " ".join(text.split())
    if len(normalized) <= 400:
        return normalized
    return normalized[:397] + "..."


output_path = pathlib.Path(sys.argv[1])
error_label = sys.argv[2]
exit_code = int(sys.argv[3])
stdout_preview = read_preview(sys.argv[4])
stderr_preview = read_preview(sys.argv[5])

message = f"{error_label} with exit code {exit_code}."
if stderr_preview:
    message += f" stderr: {stderr_preview}"
if stdout_preview:
    message += f" stdout: {stdout_preview}"

payload = {
    "ok": False,
    "error": error_label,
    "exit_code": exit_code,
    "stdout": stdout_preview,
    "stderr": stderr_preview,
    "message": message,
}
output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

publish_selected_post() {
  local category="$1"
  local post_text="$2"
  local selected_tweet_id="$3"
  local state_file="$4"
  local post_result_file="$5"
  local response_preview=""
  local post_stderr_file="${post_result_file}.stderr"
  local attempt=1
  local exit_code=0

  while true; do
    if twitter_cmd post "${post_text}" --json > "${post_result_file}" 2> "${post_stderr_file}"; then
      break
    else
      exit_code=$?
    fi

    if (( attempt >= DEFAULT_RETRY_ATTEMPTS )); then
      write_post_failure_file \
        "${post_result_file}" \
        "twitter post command failed" \
        "${exit_code}" \
        "${post_result_file}" \
        "${post_stderr_file}"
      warn "twitter post failed for '${category}' after ${DEFAULT_RETRY_ATTEMPTS} attempts"
      response_preview="$(summarize_post_result_file "${post_result_file}")"
      [[ -n "${response_preview}" ]] && warn "${response_preview}"
      rm -f "${post_stderr_file}"
      return 1
    fi

    warn "twitter post failed for '${category}' (attempt ${attempt}/${DEFAULT_RETRY_ATTEMPTS}); retrying in ${DEFAULT_RETRY_DELAY_SECONDS}s"
    sleep "${DEFAULT_RETRY_DELAY_SECONDS}"
    attempt=$((attempt + 1))
  done

  rm -f "${post_stderr_file}"

  if [[ ! -f "${post_result_file}" ]]; then
    warn "twitter post did not create result file for '${category}': ${post_result_file}"
    return 1
  fi

  if [[ ! -s "${post_result_file}" ]]; then
    warn "twitter post created an empty result file for '${category}': ${post_result_file}"
    return 1
  fi

  if ! assert_structured_success "${post_result_file}" "post:${category}"; then
    response_preview="$(summarize_post_result_file "${post_result_file}")"
    warn "twitter post response validation failed for '${category}'"
    [[ -n "${response_preview}" ]] && warn "twitter post raw response preview: ${response_preview}"
    return 1
  fi

  if ! python_cmd - "${selected_tweet_id}" "${state_file}" <<'PY'
import pathlib
import sys

tweet_id = sys.argv[1].strip()
state_file = pathlib.Path(sys.argv[2])
existing = {
    line.strip()
    for line in state_file.read_text(encoding="utf-8").splitlines()
    if line.strip()
}

if tweet_id and tweet_id not in existing:
    with state_file.open("a", encoding="utf-8") as handle:
        handle.write(f"{tweet_id}\n")
PY
  then
    warn "posted '${category}' but failed to update ${state_file}"
    return 1
  fi

  info "posted category '${category}' and updated ${state_file}"
}
