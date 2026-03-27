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

resolve_source_state_file() {
  local state_file="$1"

  python_cmd - "${state_file}" <<'PY'
import pathlib
import sys

state_path = pathlib.Path(sys.argv[1])
stem = state_path.stem
suffix = state_path.suffix

if stem.endswith("-posted"):
    source_name = f"{stem[:-7]}-source-posted{suffix}"
else:
    source_name = f"{stem}-source{suffix}"

print(state_path.with_name(source_name))
PY
}

resolve_rotation_state_file() {
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
selection_mode = str(account.get("selection_mode") or "score").strip().lower()
configured = str(account.get("rotation_state_file") or "").strip()

if selection_mode != "round_robin":
    print("")
elif configured:
    state_path = pathlib.Path(configured)
    if not state_path.is_absolute():
        state_path = output_dir / state_path
    print(state_path)
else:
    print(output_dir / "state" / f"{category}-robin.txt")
PY
}

resolve_media_state_file() {
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
configured = str(account.get("media_state_file") or "").strip()

if configured:
    state_path = pathlib.Path(configured)
    if not state_path.is_absolute():
        state_path = output_dir / state_path
else:
    state_path = output_dir / "state" / f"{category}-media-selection.json"

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
  local post_error="${4:-}"

  python_cmd - "${candidate_file}" "${result_mode}" "${post_result_file}" "${post_error}" <<'PY'
import json
import pathlib
import sys

payload_path = pathlib.Path(sys.argv[1])
payload = json.loads(payload_path.read_text(encoding="utf-8"))
payload["result_mode"] = sys.argv[2]
payload["post_result_file"] = sys.argv[3] or None
payload["post_error"] = sys.argv[4] or None
payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

update_rotation_state() {
  local rotation_state_file="$1"
  local selected_source="$2"

  [[ -n "${rotation_state_file}" ]] || return 0
  python_cmd - "${rotation_state_file}" "${selected_source}" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
selected_source = sys.argv[2].strip()
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(f"{selected_source}\n", encoding="utf-8")
PY
}

update_media_state() {
  local media_state_file="$1"
  local selected_media_mode="$2"
  local selected_tweet_id="$3"

  [[ -n "${media_state_file}" ]] || return 0
  python_cmd - "${media_state_file}" "${selected_media_mode}" "${selected_tweet_id}" <<'PY'
import json
import pathlib
import sys
from datetime import datetime, timezone

path = pathlib.Path(sys.argv[1])
selected_media_mode = sys.argv[2].strip() or "text"
selected_tweet_id = sys.argv[3].strip()
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(
    json.dumps(
        {
            "last_media_mode": selected_media_mode,
            "last_tweet_id": selected_tweet_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n",
    encoding="utf-8",
)
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
  local source_state_file=""
  local candidate_file=""
  local post_text=""
  local post_result_file=""
  local rotation_state_file=""
  local selection_mode=""
  local selected_source_name=""
  local selected_media_mode=""
  local source_reference_mode="url"
  local single_post_max_length="280"
  local source_root=""
  local source_url=""
  local payload_count=""
  local selected_count=""
  local selected_tweet_id=""
  local summary_warnings=""
  local collection_status_json=""
  local source_config_json=""
  local requested_mode="live"
  local post_error=""
  local media_state_file=""

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
  source_reference_mode="$(python_cmd - "${account_json}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
print(str(payload.get("source_reference_mode") or "url").strip().lower())
PY
  )"
  single_post_max_length="$(python_cmd - "${account_json}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
print(int(payload.get("single_post_max_length") or 280))
PY
  )"

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
  source_state_file="$(resolve_source_state_file "${state_file}")"
  mkdir -p "$(dirname "${source_state_file}")"
  touch "${source_state_file}"
  media_state_file="$(resolve_media_state_file "${output_dir}" "${category}" "${account_json}")"
  mkdir -p "$(dirname "${media_state_file}")"
  touch "${media_state_file}"
  rotation_state_file="$(resolve_rotation_state_file "${output_dir}" "${category}" "${account_json}")"
  if [[ -n "${rotation_state_file}" ]]; then
    mkdir -p "$(dirname "${rotation_state_file}")"
    touch "${rotation_state_file}"
  fi
  candidate_file="$(make_run_file "${output_dir}" "candidate-${category}")"

  PYTHONPATH="${SCRIPT_DIR}/lib${PYTHONPATH:+:${PYTHONPATH}}" python_cmd - "${category}" "${source_state_file}" "${rotation_state_file}" "${media_state_file}" "${account_json}" "${source_config_json}" "${collection_status_json}" "${requested_mode}" "${payload_files[@]}" > "${candidate_file}" <<'PY'
import json
import pathlib
import re
import sys
from post_filters import candidate_rejection_reasons, merge_filters
from post_media import extract_candidate_media
from post_selection import normalize_rotation_source, preferred_media_mode_from_previous, select_candidates
from post_scoring import calculate_score, extract_candidate_metrics
from post_summary import build_source_tweet_url, build_summary, clean_post_source_text, clean_source_text

category = sys.argv[1]
source_state_file = pathlib.Path(sys.argv[2])
rotation_state_file = pathlib.Path(sys.argv[3]) if sys.argv[3] else None
media_state_file = pathlib.Path(sys.argv[4])
account = json.loads(sys.argv[5])
source_configs = json.loads(sys.argv[6])
collection = json.loads(sys.argv[7])
requested_mode = sys.argv[8]
payload_files = [pathlib.Path(item) for item in sys.argv[9:]]

posted_ids = {line.strip() for line in source_state_file.read_text(encoding="utf-8").splitlines() if line.strip()}
warnings = []
skipped_candidates = []
seen_ids = set()
seen_text = set()
candidates = []

summary_prefix = str(account.get("summary_prefix") or account.get("post_prefix") or "Xで反応上位: ")
summary_language = str(account.get("summary_language") or "ja")
summary_provider = str(account.get("summary_provider") or "legacy_google_translate")
summary_model = str(account.get("summary_model") or "gpt-5-mini")
summary_prompt_path = str(account.get("summary_prompt_path") or "")
summary_max_length = int(account.get("summary_max_length") or 280)
selection_mode = str(account.get("selection_mode") or "score")
source_reference_mode = str(account.get("source_reference_mode") or "url").strip().lower()
score_weights = account.get("score_weights") or {}
account_filters = account.get("filters") or {}
max_candidates = max(int(account.get("max_candidates") or 1), 1)
source_order = [str((source_configs.get(source_id) or {}).get("username") or source_id) for source_id in source_configs.keys()]
rotation_raw = ""
if rotation_state_file is not None:
    rotation_raw = rotation_state_file.read_text(encoding="utf-8").strip()
previous_source, _ = normalize_rotation_source(rotation_raw, source_order)
previous_media_mode = ""
if media_state_file.is_file():
    try:
        media_state = json.loads(media_state_file.read_text(encoding="utf-8"))
        previous_media_mode = str(media_state.get("last_media_mode") or "").strip().lower()
    except Exception as exc:
        warnings.append(f"{media_state_file.name}: failed to parse media state ({exc})")
target_media_mode = preferred_media_mode_from_previous(previous_media_mode)


for payload_path in payload_files:
    source_id = payload_path.stem
    source_config = source_configs.get(source_id) or {}
    source_filters = source_config.get("filters") or {}
    source_type = str(source_config.get("type") or "")
    source_score_boost = float(source_config.get("score_boost") or 0)
    source_username = str(source_config.get("username") or "")
    source_media_mode = str(source_config.get("media_mode") or "any")
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
        post_source_text = clean_post_source_text(raw_text)
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
            skipped_candidates.append({"id": tweet_id, "source_id": source_id, "text": text[:2000], "reasons": rejection_reasons})
            continue

        author = item.get("author") or {}
        metrics = extract_candidate_metrics(item)
        media = extract_candidate_media(item, fallback_mode=source_media_mode)
        score, score_breakdown = calculate_score(
            metrics,
            score_weights,
            created_at=created_at,
            max_age_hours=effective_filters.get("max_age_hours"),
            source_boost=source_score_boost,
            has_image=bool(media.get("has_image")),
        )

        candidates.append(
            {
                "id": tweet_id,
                "source_id": source_id,
                "source_type": source_type,
                "source_key": source_username or source_id,
                "source_username": source_username,
                "text": text,
                "post_source_text": post_source_text or text,
                "screen_name": str(author.get("screenName") or ""),
                "author_name": str(author.get("name") or ""),
                "likes": metrics["likes"],
                "retweets": metrics["retweets"],
                "replies": metrics["replies"],
                "views": metrics["views"],
                "has_image": bool(media.get("has_image")),
                "media_mode": str(media.get("media_mode") or "text"),
                "media_types": media.get("media_types") or [],
                "media_classification_source": str(media.get("classification_source") or "default"),
                "score": round(score, 2),
                "score_breakdown": {key: round(value, 2) for key, value in score_breakdown.items()},
                "created_at": created_at,
                "source_score_boost": round(source_score_boost, 2),
            }
        )
        seen_ids.add(tweet_id)
        seen_text.add(normalized_text)

selected_candidates, rotation = select_candidates(
    candidates,
    source_order=source_order,
    max_candidates=max_candidates,
    selection_mode=selection_mode,
    previous_source=previous_source,
    preferred_media_mode=target_media_mode,
)
selected = selected_candidates[0] if selected_candidates else None
post_text = ""
source_url = ""
summary_generation = {}
if selected:
    source_url = build_source_tweet_url(
        selected["screen_name"],
        selected["id"],
        source_username=selected["source_username"],
    )
    selected["source_url"] = source_url
    post_text = build_summary(
        selected.get("post_source_text") or selected["text"],
        prefix=summary_prefix,
        language=summary_language,
        max_length=summary_max_length,
        screen_name=selected["screen_name"],
        tweet_id=selected["id"],
        source_username=selected["source_username"],
        provider=summary_provider,
        copilot_model=summary_model,
        copilot_prompt_path=summary_prompt_path,
        working_directory=pathlib.Path.cwd(),
        diagnostics_sink=summary_generation,
    )
    selected["summary_text"] = post_text
    if summary_generation:
        selected["summary_generation"] = summary_generation

payload = {
    "category": category,
    "requested_mode": requested_mode,
    "result_mode": "candidate_ready",
    "payload_count": len(payload_files),
    "collection": collection,
    "post_text": post_text,
    "source_url": source_url,
    "selected": selected,
    "selected_candidates": selected_candidates,
    "summary_generation": summary_generation or None,
    "selection_mode": selection_mode,
    "source_reference_mode": source_reference_mode,
    "single_post_max_length": int(account.get("single_post_max_length") or 280),
    "target_media_mode": target_media_mode,
    "previous_media_mode": previous_media_mode or None,
    "rotation": rotation,
    "skipped_candidates": skipped_candidates[:20],
    "warnings": warnings,
    "post_result_file": None,
    "post_error": None,
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
  selection_mode="$(python_cmd - "${candidate_file}" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(payload.get("selection_mode", "score"))
PY
  )"
  selected_source_name="$(python_cmd - "${candidate_file}" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
rotation = payload.get("rotation") or {}
print(rotation.get("selected_source", ""))
PY
  )"
  source_url="$(python_cmd - "${candidate_file}" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(payload.get("source_url", ""))
PY
  )"
  selected_media_mode="$(python_cmd - "${candidate_file}" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
selected = payload.get("selected") or {}
print(selected.get("media_mode", ""))
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
  if ! publish_selected_post "${category}" "${post_text}" "${selected_tweet_id}" "${source_url}" "${source_reference_mode}" "${single_post_max_length}" "${state_file}" "${source_state_file}" "${post_result_file}"; then
    post_error="$(summarize_post_result_file "${post_result_file}")"
    update_candidate_result "${candidate_file}" "post_failed" "${post_result_file}" "${post_error}"
    exit 1
  fi
  if [[ "${selection_mode}" == "round_robin" && -n "${selected_source_name}" ]]; then
    update_rotation_state "${rotation_state_file}" "${selected_source_name}"
  fi
  update_media_state "${media_state_file}" "${selected_media_mode}" "${selected_tweet_id}"
  update_candidate_result "${candidate_file}" "posted" "${post_result_file}"
}

main "$@"
