#!/usr/bin/env bash

summarize_post_result_file() {
  local post_result_file="$1"

  python_cmd - "${post_result_file}" <<'PY'
import json
import pathlib
import sys


def condense(text: str) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= 2000:
        return normalized
    return normalized[:1997] + "..."


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
    if len(normalized) <= 2000:
        return normalized
    return normalized[:1997] + "..."


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

append_unique_tweet_id() {
  local tweet_id="$1"
  local state_file="$2"

  python_cmd - "${tweet_id}" "${state_file}" <<'PY'
import pathlib
import sys

tweet_id = sys.argv[1].strip()
state_file = pathlib.Path(sys.argv[2])
state_file.parent.mkdir(parents=True, exist_ok=True)
existing = set()
if state_file.exists():
    existing = {
        line.strip()
        for line in state_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

if tweet_id and tweet_id not in existing:
    with state_file.open("a", encoding="utf-8") as handle:
        handle.write(f"{tweet_id}\n")
PY
}

build_thread_plan_json() {
  local post_text="$1"
  local source_url="$2"
  local single_post_max_length="$3"
  local stdout_path="$4"
  local stderr_path="$5"

  PYTHONPATH="${PROJECT_ROOT}/scripts/lib${PYTHONPATH:+:${PYTHONPATH}}" \
    python_cmd - "${post_text}" "${source_url}" "${single_post_max_length}" > "${stdout_path}" 2> "${stderr_path}" <<'PY'
import json
import sys
from post_summary import build_thread_posts

print(
    json.dumps(
        build_thread_posts(
            sys.argv[1],
            source_url=sys.argv[2],
            single_post_max_length=int(sys.argv[3]),
        ),
        ensure_ascii=False,
    )
)
PY
}

count_thread_posts() {
  local thread_posts_json="$1"

  python_cmd - "${thread_posts_json}" <<'PY'
import json
import sys

print(len(json.loads(sys.argv[1])))
PY
}

estimate_thread_post_length() {
  local thread_posts_json="$1"
  local index="$2"

  PYTHONPATH="${PROJECT_ROOT}/scripts/lib${PYTHONPATH:+:${PYTHONPATH}}" \
    python_cmd - "${thread_posts_json}" "${index}" <<'PY'
import json
import sys
from post_summary import estimate_x_post_length

posts = json.loads(sys.argv[1])
print(estimate_x_post_length(posts[int(sys.argv[2])]))
PY
}

resolve_publish_action_name() {
  local thread_count="$1"
  local source_reference_mode="$2"
  local action_name="post"

  if (( thread_count > 1 )); then
    action_name="post_thread"
  fi
  if [[ "${source_reference_mode}" == "quote" ]]; then
    action_name="${action_name}_quote"
  fi
  printf '%s\n' "${action_name}"
}

is_quote_length_error() {
  local stdout_path="$1"
  local stderr_path="$2"

  python_cmd - "${stdout_path}" "${stderr_path}" <<'PY'
import pathlib
import sys

combined = []
for raw_path in sys.argv[1:]:
    path = pathlib.Path(raw_path)
    if path.exists():
        combined.append(path.read_text(encoding="utf-8", errors="replace"))

text = "\n".join(combined)
raise SystemExit(0 if "Tweet needs to be a bit shorter" in text and "(186)" in text else 1)
PY
}

publish_selected_post() {
  local category="$1"
  local post_text="$2"
  local source_tweet_id="$3"
  local source_url="$4"
  local source_reference_mode="${5:-url}"
  local single_post_max_length="${6:-280}"
  local state_file="$7"
  local source_state_file="$8"
  local post_result_file="$9"
  local thread_plan_stdout="${post_result_file}.plan.stdout"
  local thread_plan_stderr="${post_result_file}.plan.stderr"
  local thread_plan_source_url="${source_url}"
  local thread_posts_json=""
  local thread_count=0
  local current_post_text=""
  local reply_to_id=""
  local current_quote_tweet_id=""
  local current_output_file=""
  local current_stderr_file=""
  local response_preview=""
  local exit_code=0
  local current_post_id=""
  local action_name="post"
  local effective_source_reference_mode="${source_reference_mode}"
  local -a posted_tweet_ids=()
  local index=0
  local planning_single_post_max_length="${single_post_max_length}"
  local did_quote_length_fallback="false"
  local first_post_length=0

  if [[ "${source_reference_mode}" == "quote" && -z "${source_tweet_id}" ]]; then
    write_post_failure_file \
      "${post_result_file}" \
      "quote mode requires a source tweet id" \
      "1" \
      "/dev/null" \
      "/dev/null"
    warn "quote mode requires a source tweet id for '${category}'"
    return 1
  fi

  if [[ "${effective_source_reference_mode}" == "quote" ]]; then
    thread_plan_source_url=""
  fi

  if build_thread_plan_json "${post_text}" "${thread_plan_source_url}" "${planning_single_post_max_length}" "${thread_plan_stdout}" "${thread_plan_stderr}"; then
    exit_code=0
  else
    exit_code=$?
  fi
  if (( exit_code != 0 )); then
    write_post_failure_file \
      "${post_result_file}" \
      "failed to build thread post plan" \
      "${exit_code}" \
      "${thread_plan_stdout}" \
      "${thread_plan_stderr}"
    response_preview="$(summarize_post_result_file "${post_result_file}")"
    [[ -n "${response_preview}" ]] && warn "${response_preview}"
    rm -f "${thread_plan_stdout}" "${thread_plan_stderr}"
    return 1
  fi

  thread_posts_json="$(cat "${thread_plan_stdout}")"
  rm -f "${thread_plan_stdout}" "${thread_plan_stderr}"
  thread_count="$(count_thread_posts "${thread_posts_json}")"
  if (( thread_count <= 0 )); then
    write_post_failure_file \
      "${post_result_file}" \
      "thread plan did not produce any posts" \
      "1" \
      "/dev/null" \
      "/dev/null"
    warn "thread plan did not produce any posts for '${category}'"
    return 1
  fi
  if [[ "${effective_source_reference_mode}" == "quote" && "${thread_count}" -eq 1 ]]; then
    first_post_length="$(estimate_thread_post_length "${thread_posts_json}" 0)"
    if (( first_post_length > 280 )) && [[ -n "${source_url}" ]]; then
      if build_thread_plan_json "${post_text}" "${source_url}" "${planning_single_post_max_length}" "${thread_plan_stdout}" "${thread_plan_stderr}"; then
        exit_code=0
      else
        exit_code=$?
      fi
      if (( exit_code == 0 )); then
        local url_single_post_plan_json=""
        local url_single_post_thread_count=0
        url_single_post_plan_json="$(cat "${thread_plan_stdout}")"
        url_single_post_thread_count="$(count_thread_posts "${url_single_post_plan_json}")"
        rm -f "${thread_plan_stdout}" "${thread_plan_stderr}"
        if (( url_single_post_thread_count == 1 )); then
          thread_posts_json="${url_single_post_plan_json}"
          thread_count="${url_single_post_thread_count}"
          effective_source_reference_mode="url"
        else
          warn "quote single-post overflow for '${category}' could not stay single with source URL; keeping thread fallback path"
        fi
      else
        warn "failed to build URL single-post fallback for '${category}'; keeping quote fallback path"
        rm -f "${thread_plan_stdout}" "${thread_plan_stderr}"
      fi
    fi
  fi
  action_name="$(resolve_publish_action_name "${thread_count}" "${effective_source_reference_mode}")"

  for ((index = 0; index < thread_count; index++)); do
    current_post_text="$(python_cmd - "${thread_posts_json}" "${index}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
print(payload[int(sys.argv[2])])
PY
    )"
    current_output_file="${post_result_file}.segment-${index}.json"
    current_stderr_file="${current_output_file}.stderr"
    rm -f "${current_output_file}" "${current_stderr_file}"
    current_quote_tweet_id=""
    if [[ "${effective_source_reference_mode}" == "quote" && "${index}" -eq $((thread_count - 1)) ]]; then
      current_quote_tweet_id="${source_tweet_id}"
    fi

    execute_twitter_post "${category}" "${current_post_text}" "${reply_to_id}" "${current_quote_tweet_id}" "${current_output_file}" "${current_stderr_file}"
    exit_code=$?
    if (( exit_code != 0 )); then
      if [[ "${did_quote_length_fallback}" != "true" && "${effective_source_reference_mode}" == "quote" ]] \
        && (( thread_count == 1 )) \
        && (( index == 0 )) \
        && is_quote_length_error "${current_output_file}" "${current_stderr_file}"; then
        planning_single_post_max_length="280"
        did_quote_length_fallback="true"
        rm -f "${current_stderr_file}" "${current_output_file}"

        if build_thread_plan_json "${post_text}" "${thread_plan_source_url}" "${planning_single_post_max_length}" "${thread_plan_stdout}" "${thread_plan_stderr}"; then
          exit_code=0
        else
          exit_code=$?
        fi
        if (( exit_code != 0 )); then
          write_post_failure_file \
            "${post_result_file}" \
            "failed to build fallback thread post plan" \
            "${exit_code}" \
            "${thread_plan_stdout}" \
            "${thread_plan_stderr}"
          response_preview="$(summarize_post_result_file "${post_result_file}")"
          [[ -n "${response_preview}" ]] && warn "${response_preview}"
          rm -f "${thread_plan_stdout}" "${thread_plan_stderr}"
          return 1
        fi

        thread_posts_json="$(cat "${thread_plan_stdout}")"
        rm -f "${thread_plan_stdout}" "${thread_plan_stderr}"
        thread_count="$(count_thread_posts "${thread_posts_json}")"
        if (( thread_count <= 1 )); then
          write_post_failure_file \
            "${post_result_file}" \
            "fallback thread plan still produced a single post" \
            "1" \
            "/dev/null" \
            "/dev/null"
          warn "fallback thread plan did not split '${category}' into multiple posts"
          return 1
        fi

        action_name="$(resolve_publish_action_name "${thread_count}" "${source_reference_mode}")"
        effective_source_reference_mode="${source_reference_mode}"
        posted_tweet_ids=()
        reply_to_id=""
        index=-1
        continue
      fi

      write_post_failure_file \
        "${post_result_file}" \
        "twitter post command failed for thread segment $((index + 1))" \
        "${exit_code}" \
        "${current_output_file}" \
        "${current_stderr_file}"
      warn "twitter post failed for '${category}' at thread segment $((index + 1))"
      response_preview="$(summarize_post_result_file "${post_result_file}")"
      [[ -n "${response_preview}" ]] && warn "${response_preview}"
      rm -f "${current_stderr_file}" "${current_output_file}"
      return 1
    fi

    if [[ ! -f "${current_output_file}" ]]; then
      write_post_failure_file \
        "${post_result_file}" \
        "twitter post did not create a result file for thread segment $((index + 1))" \
        "1" \
        "${current_output_file}" \
        "${current_stderr_file}"
      warn "twitter post did not create result file for '${category}': ${current_output_file}"
      rm -f "${current_stderr_file}" "${current_output_file}"
      return 1
    fi
    if [[ ! -s "${current_output_file}" ]]; then
      write_post_failure_file \
        "${post_result_file}" \
        "twitter post created an empty result file for thread segment $((index + 1))" \
        "1" \
        "${current_output_file}" \
        "${current_stderr_file}"
      warn "twitter post created an empty result file for '${category}': ${current_output_file}"
      rm -f "${current_stderr_file}" "${current_output_file}"
      return 1
    fi
    if ! assert_structured_success "${current_output_file}" "post:${category}:segment-$((index + 1))"; then
      cp "${current_output_file}" "${post_result_file}"
      response_preview="$(summarize_post_result_file "${post_result_file}")"
      warn "twitter post response validation failed for '${category}' at thread segment $((index + 1))"
      [[ -n "${response_preview}" ]] && warn "twitter post raw response preview: ${response_preview}"
      rm -f "${current_output_file}" "${current_stderr_file}"
      return 1
    fi

    if ! current_post_id="$(python_cmd - "${current_output_file}" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
data = payload.get("data") or {}
tweet_id = str(data.get("id") or "").strip()
if not tweet_id:
    raise SystemExit("missing posted tweet id")
print(tweet_id)
PY
    )"; then
      write_post_failure_file \
        "${post_result_file}" \
        "missing posted tweet id for thread segment $((index + 1))" \
        "1" \
        "${current_output_file}" \
        "${current_stderr_file}"
      rm -f "${current_output_file}" "${current_stderr_file}"
      return 1
    fi
    posted_tweet_ids+=("${current_post_id}")
    reply_to_id="${current_post_id}"

    if (( index == 0 )); then
      if ! append_unique_tweet_id "${source_tweet_id}" "${source_state_file}"; then
        write_post_failure_file \
          "${post_result_file}" \
          "failed to update source tweet state file" \
          "1" \
          "/dev/null" \
          "/dev/null"
        warn "posted '${category}' but failed to update ${source_state_file}"
        rm -f "${current_output_file}" "${current_stderr_file}"
        return 1
      fi

      if ! append_unique_tweet_id "${current_post_id}" "${state_file}"; then
        write_post_failure_file \
          "${post_result_file}" \
          "failed to update posted tweet state file" \
          "1" \
          "/dev/null" \
          "/dev/null"
        warn "posted '${category}' but failed to update ${state_file}"
        rm -f "${current_output_file}" "${current_stderr_file}"
        return 1
      fi
    fi

    rm -f "${current_output_file}" "${current_stderr_file}"
  done

  if [[ -z "${posted_tweet_ids[0]:-}" ]]; then
    write_post_failure_file \
      "${post_result_file}" \
      "missing first posted tweet id" \
      "1" \
      "/dev/null" \
      "/dev/null"
    warn "posted '${category}' but the first posted tweet id was empty"
    return 1
  fi

  write_publish_success_file "${post_result_file}" "${action_name}" "${posted_tweet_ids[@]}"

  info "posted category '${category}' and updated ${state_file} and ${source_state_file}"
}

execute_twitter_post() {
  local category="$1"
  local post_text="$2"
  local reply_to_id="${3:-}"
  local quote_tweet_id="${4:-}"
  local output_file="$5"
  local stderr_file="$6"
  local attempt=1
  local exit_code=0
  local -a quote_command=()

  while true; do
    if [[ -n "${quote_tweet_id}" ]]; then
      quote_command=(
        python_cmd
        "${PROJECT_ROOT}/scripts/lib/post_quote.py"
        --text "${post_text}"
        --quote-tweet-id "${quote_tweet_id}"
      )
      if [[ -n "${reply_to_id}" ]]; then
        quote_command+=(--reply-to-id "${reply_to_id}")
      fi
      if "${quote_command[@]}" > "${output_file}" 2> "${stderr_file}"; then
        return 0
      else
        exit_code=$?
      fi
    elif [[ -n "${reply_to_id}" ]]; then
      if twitter_cmd post "${post_text}" --reply-to "${reply_to_id}" --json > "${output_file}" 2> "${stderr_file}"; then
        return 0
      else
        exit_code=$?
      fi
    else
      if twitter_cmd post "${post_text}" --json > "${output_file}" 2> "${stderr_file}"; then
        return 0
      else
        exit_code=$?
      fi
    fi

    if (( attempt >= DEFAULT_RETRY_ATTEMPTS )); then
      return "${exit_code}"
    fi

    warn "twitter post failed for '${category}' (attempt ${attempt}/${DEFAULT_RETRY_ATTEMPTS}); retrying in ${DEFAULT_RETRY_DELAY_SECONDS}s"
    sleep "${DEFAULT_RETRY_DELAY_SECONDS}"
    attempt=$((attempt + 1))
  done
}

write_publish_success_file() {
  local output_path="$1"
  local action_name="$2"
  shift 2

  python_cmd - "${output_path}" "${action_name}" "$@" <<'PY'
import json
import pathlib
import sys

output_path = pathlib.Path(sys.argv[1])
action_name = sys.argv[2]
tweet_ids = [item for item in sys.argv[3:] if item.strip()]
first_tweet_id = tweet_ids[0] if tweet_ids else ""

payload = {
    "ok": True,
    "data": {
        "success": True,
        "action": action_name,
        "id": first_tweet_id,
        "url": f"https://x.com/i/status/{first_tweet_id}" if first_tweet_id else "",
        "tweet_ids": tweet_ids,
        "tweet_count": len(tweet_ids),
    },
    "message": (
        f"posted {len(tweet_ids)} tweet(s) starting at {first_tweet_id}"
        if first_tweet_id
        else "posted thread"
    ),
}
output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}
