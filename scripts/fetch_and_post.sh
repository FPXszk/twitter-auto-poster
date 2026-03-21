#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
# shellcheck source=scripts/lib/post_publish.sh
source "${SCRIPT_DIR}/lib/post_publish.sh"

usage() {
  cat <<'EOF'
Usage: bash scripts/fetch_and_post.sh --category <news|invest> [options]

Options:
  --category <name>      Category to process
  --sources <path>       Path to config/sources.yaml
  --accounts <path>      Path to config/accounts.yaml
  --output-dir <path>    Working directory for raw data, state, and previews
  --dry-run <bool>       Override dry-run mode
  --post                 Shortcut for --dry-run false
  -h, --help             Show this help message
EOF
}

resolve_state_file() {
  local output_dir="$1"
  local category="$2"
  local account_json="$3"

  python_cmd - "${output_dir}" "${category}" "${account_json}" <<'PY'
import json
import pathlib
import sys

output_dir = pathlib.Path(sys.argv[1])
category = sys.argv[2]
account = json.loads(sys.argv[3])
configured = str(account.get("state_file") or "").strip()

if configured:
    state_path = pathlib.Path(configured)
    if not state_path.is_absolute():
        state_path = output_dir / state_path
else:
    state_path = output_dir / "state" / f"{category}-posted.txt"

print(state_path)
PY
}

emit_candidate_warnings() {
  local candidate_file="$1"

  python_cmd - "${candidate_file}" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
for item in payload.get("warnings") or []:
    print(item)
PY
}

load_collection_status() {
  local output_dir="$1"
  local category="$2"

  python_cmd - "${output_dir}" "${category}" <<'PY'
import json
import pathlib
import sys

output_dir = pathlib.Path(sys.argv[1])
category = sys.argv[2]
runs_dir = output_dir / "runs"

payload = {
    "user": {"total_sources": 0, "successful_sources": 0, "failed_sources": 0},
    "search": {"total_sources": 0, "successful_sources": 0, "failed_sources": 0},
}
for source_type in ("user", "search"):
    path = runs_dir / f"fetch-{source_type}-{category}.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        payload[source_type] = {
            "total_sources": int(data.get("total_sources", 0)),
            "successful_sources": int(data.get("successful_sources", 0)),
            "failed_sources": int(data.get("failed_sources", 0)),
        }

print(json.dumps(payload, ensure_ascii=False))
PY
}

update_candidate_result() {
  local candidate_file="$1"
  local result_mode="$2"
  local post_result_file="${3:-}"

  python_cmd - "${candidate_file}" "${result_mode}" "${post_result_file}" <<'PY'
import json
import pathlib
import sys

payload_path = pathlib.Path(sys.argv[1])
payload = json.loads(payload_path.read_text(encoding="utf-8"))
payload["result_mode"] = sys.argv[2]
payload["post_result_file"] = sys.argv[3] or None
payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

main() {
  local category=""
  local sources_config="${DEFAULT_SOURCES_CONFIG}"
  local accounts_config="${DEFAULT_ACCOUNTS_CONFIG}"
  local output_dir="${DEFAULT_TMP_DIR}"
  local dry_run_override=""
  local account_json=""
  local dry_run=""
  local state_file=""
  local candidate_file=""
  local post_text=""
  local post_result_file=""
  local source_root=""
  local payload_count=""
  local selected_count=""
  local selected_tweet_id=""
  local summary_warnings=""
  local collection_status_json=""
  local source_config_json=""
  local requested_mode="live"

  while (($# > 0)); do
    case "$1" in
      --category)
        [[ $# -ge 2 ]] || die "--category requires a value"
        category="$2"
        shift 2
        ;;
      --sources)
        [[ $# -ge 2 ]] || die "--sources requires a value"
        sources_config="$2"
        shift 2
        ;;
      --accounts)
        [[ $# -ge 2 ]] || die "--accounts requires a value"
        accounts_config="$2"
        shift 2
        ;;
      --output-dir)
        [[ $# -ge 2 ]] || die "--output-dir requires a value"
        output_dir="$2"
        shift 2
        ;;
      --dry-run)
        [[ $# -ge 2 ]] || die "--dry-run requires a value"
        dry_run_override="$(normalize_bool "$2")"
        shift 2
        ;;
      --post)
        dry_run_override="false"
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "unknown argument: $1"
        ;;
    esac
  done

  [[ -n "${category}" ]] || die "--category is required"

  ensure_config_file "${sources_config}"
  ensure_config_file "${accounts_config}"
  validate_sources_config "${sources_config}"
  validate_accounts_config "${accounts_config}"
  ensure_dependencies
  ensure_output_layout "${output_dir}"
  ensure_twitter_auth

  account_json="$(account_config_json "${accounts_config}" "${category}")"
  source_config_json="$(category_sources_json "${sources_config}" "${category}")"
  dry_run="$(python_cmd - "${account_json}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
print(str(payload["dry_run"]).lower())
PY
  )"

  if [[ -n "${dry_run_override}" ]]; then
    dry_run="${dry_run_override}"
  fi
  if [[ "${dry_run}" == "true" ]]; then
    requested_mode="preview"
  fi

  if ! bash "${SCRIPT_DIR}/fetch_user.sh" --category "${category}" --sources "${sources_config}" --output-dir "${output_dir}"; then
    warn "user source collection failed for '${category}'; continuing"
  fi

  if ! bash "${SCRIPT_DIR}/fetch_search.sh" --category "${category}" --sources "${sources_config}" --output-dir "${output_dir}"; then
    warn "search source collection failed for '${category}'; continuing"
  fi

  source_root="${output_dir}/raw/${category}"
  mkdir -p "${source_root}"

  mapfile -t payload_files < <(find "${source_root}" -maxdepth 1 -type f -name '*.json' | sort)

  payload_count="${#payload_files[@]}"
  collection_status_json="$(load_collection_status "${output_dir}" "${category}")"
  if [[ "${payload_count}" -eq 0 ]]; then
    warn "no payload files found for category '${category}'"
    exit 0
  fi

  state_file="$(resolve_state_file "${output_dir}" "${category}" "${account_json}")"
  mkdir -p "$(dirname "${state_file}")"
  touch "${state_file}"
  candidate_file="$(make_run_file "${output_dir}" "candidate-${category}")"

  PYTHONPATH="${SCRIPT_DIR}/lib${PYTHONPATH:+:${PYTHONPATH}}" python_cmd - "${category}" "${state_file}" "${account_json}" "${source_config_json}" "${collection_status_json}" "${requested_mode}" "${payload_files[@]}" > "${candidate_file}" <<'PY'
import json
import pathlib
import re
import sys
from post_filters import candidate_rejection_reasons, merge_filters
from post_scoring import calculate_score, extract_candidate_metrics
from post_summary import build_summary, clean_source_text

category = sys.argv[1]
state_file = pathlib.Path(sys.argv[2])
account = json.loads(sys.argv[3])
source_configs = json.loads(sys.argv[4])
collection = json.loads(sys.argv[5])
requested_mode = sys.argv[6]
payload_files = [pathlib.Path(item) for item in sys.argv[7:]]

posted_ids = {line.strip() for line in state_file.read_text(encoding="utf-8").splitlines() if line.strip()}
warnings = []
skipped_candidates = []
seen_ids = set()
seen_text = set()
candidates = []

summary_prefix = str(account.get("summary_prefix") or account.get("post_prefix") or "Xで反応上位: ")
summary_language = str(account.get("summary_language") or "ja")
summary_max_length = int(account.get("summary_max_length") or 140)
score_weights = account.get("score_weights") or {}
account_filters = account.get("filters") or {}
max_candidates = max(int(account.get("max_candidates") or 1), 1)


for payload_path in payload_files:
    source_id = payload_path.stem
    source_filters = (source_configs.get(source_id) or {}).get("filters") or {}
    effective_filters = merge_filters(account_filters, source_filters)
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except Exception as exc:
        warnings.append(f"{payload_path.name}: failed to parse JSON ({exc})")
        continue

    if payload.get("ok") is not True:
        warnings.append(f"{payload_path.name}: ok != true")
        continue

    for item in payload.get("data") or []:
        tweet_id = str(item.get("id") or "").strip()
        raw_text = str(item.get("text") or "")
        text = clean_source_text(raw_text)
        if not tweet_id or not text:
            continue

        if tweet_id in posted_ids or tweet_id in seen_ids:
            continue

        normalized_text = re.sub(r"\s+", " ", text).strip().lower()
        if normalized_text in seen_text:
            continue

        created_at = str(item.get("createdAtISO") or item.get("createdAt") or "")
        rejection_reasons = candidate_rejection_reasons(text=text, created_at=created_at, raw_filters=effective_filters)
        if rejection_reasons:
            skipped_candidates.append({"id": tweet_id, "source_id": source_id, "text": text[:120], "reasons": rejection_reasons})
            continue

        author = item.get("author") or {}
        metrics = extract_candidate_metrics(item)
        score, score_breakdown = calculate_score(metrics, score_weights)

        candidates.append(
            {
                "id": tweet_id,
                "source_id": source_id,
                "text": text,
                "screen_name": str(author.get("screenName") or ""),
                "author_name": str(author.get("name") or ""),
                "likes": metrics["likes"],
                "retweets": metrics["retweets"],
                "views": metrics["views"],
                "score": round(score, 2),
                "score_breakdown": {key: round(value, 2) for key, value in score_breakdown.items()},
                "created_at": created_at,
            }
        )
        seen_ids.add(tweet_id)
        seen_text.add(normalized_text)

candidates.sort(
    key=lambda item: (
        item["score"],
        item["views"],
        item["retweets"],
        item["likes"],
        item["created_at"],
    ),
    reverse=True,
)

selected_candidates = candidates[:max_candidates]
selected = selected_candidates[0] if selected_candidates else None
post_text = ""
if selected:
    post_text = build_summary(
        selected["text"],
        prefix=summary_prefix,
        language=summary_language,
        max_length=summary_max_length,
    )
    selected["summary_text"] = post_text

payload = {
    "category": category,
    "requested_mode": requested_mode,
    "result_mode": "candidate_ready",
    "payload_count": len(payload_files),
    "collection": collection,
    "post_text": post_text,
    "selected": selected,
    "selected_candidates": selected_candidates,
    "skipped_candidates": skipped_candidates[:20],
    "warnings": warnings,
    "post_result_file": None,
}
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY

summary_warnings="$(emit_candidate_warnings "${candidate_file}")"

  if [[ -n "${summary_warnings}" ]]; then
    while IFS= read -r summary_warning; do
      [[ -n "${summary_warning}" ]] && warn "${summary_warning}"
    done <<<"${summary_warnings}"
  fi

  selected_count="$(python_cmd - "${candidate_file}" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(1 if payload.get("selected") else 0)
PY
  )"

  if [[ "${selected_count}" -eq 0 ]]; then
    update_candidate_result "${candidate_file}" "no_candidate"
    info "no eligible candidates found for category '${category}'"
    exit 0
  fi

  post_text="$(python_cmd - "${candidate_file}" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(payload["post_text"])
PY
  )"
  selected_tweet_id="$(python_cmd - "${candidate_file}" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
selected = payload.get("selected") or {}
print(selected.get("id", ""))
PY
  )"

  info "prepared post candidate for '${category}'"
  printf '%s\n' "${post_text}"

  if [[ "${dry_run}" == "true" ]]; then
    update_candidate_result "${candidate_file}" "preview"
    info "dry-run enabled; skipping twitter post"
    exit 0
  fi

  post_result_file="$(make_run_file "${output_dir}" "post-${category}")"
  if ! publish_selected_post "${category}" "${post_text}" "${selected_tweet_id}" "${state_file}" "${post_result_file}"; then
    update_candidate_result "${candidate_file}" "post_failed" "${post_result_file}"
    exit 0
  fi
  update_candidate_result "${candidate_file}" "posted" "${post_result_file}"
}

main "$@"
