#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

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
  local state_backup_file=""
  local source_root=""
  local payload_count=""
  local selected_count=""

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
  ensure_dependencies
  ensure_output_layout "${output_dir}"
  ensure_twitter_auth

  account_json="$(account_config_json "${accounts_config}" "${category}")"
  dry_run="$(python3 - "${account_json}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
print(str(payload["dry_run"]).lower())
PY
)"

  if [[ -n "${dry_run_override}" ]]; then
    dry_run="${dry_run_override}"
  fi

  bash "${SCRIPT_DIR}/fetch_user.sh" --category "${category}" --sources "${sources_config}" --output-dir "${output_dir}"
  bash "${SCRIPT_DIR}/fetch_search.sh" --category "${category}" --sources "${sources_config}" --output-dir "${output_dir}"

  source_root="${output_dir}/raw/${category}"
  mkdir -p "${source_root}"

  mapfile -t payload_files < <(find "${source_root}" -maxdepth 1 -type f -name '*.json' | sort)

  payload_count="${#payload_files[@]}"
  [[ "${payload_count}" -gt 0 ]] || die "no payload files found for category '${category}'"

  state_file="${output_dir}/state/${category}-posted.txt"
  touch "${state_file}"
  candidate_file="$(make_run_file "${output_dir}" "candidate-${category}")"

  python3 - "${accounts_config}" "${category}" "${state_file}" "${payload_files[@]}" > "${candidate_file}" <<'PY'
import json
import pathlib
import re
import sys

import yaml

accounts_config = pathlib.Path(sys.argv[1])
category = sys.argv[2]
state_file = pathlib.Path(sys.argv[3])
payload_files = [pathlib.Path(item) for item in sys.argv[4:]]

accounts_raw = yaml.safe_load(accounts_config.read_text(encoding="utf-8")) or {}
defaults = accounts_raw.get("defaults") or {}
accounts = accounts_raw.get("accounts") or {}
account = accounts.get(category) or {}

post_prefix = str(account.get("post_prefix") or defaults.get("post_prefix") or "Update:")
max_candidates = int(account.get("max_candidates") or defaults.get("max_candidates") or 1)
posted_ids = {
    line.strip()
    for line in state_file.read_text(encoding="utf-8").splitlines()
    if line.strip()
}

seen_ids = set()
seen_text = set()
candidates = []

for payload_path in payload_files:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    if payload.get("ok") is not True:
        raise SystemExit(f"{payload_path}: ok != true")

    for item in payload.get("data") or []:
        tweet_id = str(item.get("id") or "").strip()
        text = " ".join(str(item.get("text") or "").split())
        if not tweet_id or not text:
            continue

        if tweet_id in posted_ids or tweet_id in seen_ids:
            continue

        normalized_text = re.sub(r"\s+", " ", text).strip().lower()
        if normalized_text in seen_text:
            continue

        author = item.get("author") or {}
        metrics = item.get("metrics") or {}
        likes = int(metrics.get("likes") or 0)
        retweets = int(metrics.get("retweets") or 0)

        candidates.append(
            {
                "id": tweet_id,
                "text": text,
                "screen_name": str(author.get("screenName") or ""),
                "author_name": str(author.get("name") or ""),
                "likes": likes,
                "retweets": retweets,
                "created_at": str(item.get("createdAtISO") or item.get("createdAt") or ""),
                "engagement": likes + retweets,
            }
        )
        seen_ids.add(tweet_id)
        seen_text.add(normalized_text)

candidates.sort(key=lambda item: (item["engagement"], item["created_at"]), reverse=True)
selected = candidates[:max_candidates]

segments = []
for item in selected:
    label = f"@{item['screen_name']}" if item["screen_name"] else item["author_name"]
    snippet = item["text"]
    segments.append(f"{label}: {snippet}")

post_text = ""
if segments:
    post_text = f"{post_prefix} {' | '.join(segments)}"
    if len(post_text) > 280:
        post_text = post_text[:277].rstrip() + "..."

payload = {
    "category": category,
    "post_text": post_text,
    "selected": selected,
}
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY

  selected_count="$(python3 - "${candidate_file}" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(len(payload.get("selected") or []))
PY
)"

  if [[ "${selected_count}" -eq 0 ]]; then
    info "no eligible candidates found for category '${category}'"
    exit 0
  fi

  post_text="$(python3 - "${candidate_file}" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(payload["post_text"])
PY
)"

  info "prepared post candidate for '${category}'"
  printf '%s\n' "${post_text}"

  if [[ "${dry_run}" == "true" ]]; then
    info "dry-run enabled; skipping twitter post"
    exit 0
  fi

  state_backup_file="$(make_run_file "${output_dir}" "state-${category}")"
  cp "${state_file}" "${state_backup_file}"

  python3 - "${candidate_file}" "${state_file}" <<'PY'
import json
import pathlib
import sys

candidate_file = pathlib.Path(sys.argv[1])
state_file = pathlib.Path(sys.argv[2])

payload = json.loads(candidate_file.read_text(encoding="utf-8"))
selected = payload.get("selected") or []
existing = {
    line.strip()
    for line in state_file.read_text(encoding="utf-8").splitlines()
    if line.strip()
}

with state_file.open("a", encoding="utf-8") as handle:
    for item in selected:
        tweet_id = str(item.get("id") or "").strip()
        if tweet_id and tweet_id not in existing:
            handle.write(f"{tweet_id}\n")
            existing.add(tweet_id)
PY

  post_result_file="$(make_run_file "${output_dir}" "post-${category}")"
  if ! twitter post "${post_text}" --json > "${post_result_file}"; then
    cp "${state_backup_file}" "${state_file}"
    die "twitter post failed; restored ${state_file}"
  fi

  if ! assert_structured_success "${post_result_file}" "post:${category}"; then
    cp "${state_backup_file}" "${state_file}"
    die "twitter post response validation failed; restored ${state_file}"
  fi

  info "posted category '${category}' and updated ${state_file}"
}

main "$@"
