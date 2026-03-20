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
  local source_root=""
  local payload_count=""
  local selected_count=""
  local posted_id=""
  local summary_warnings=""

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
  if [[ "${payload_count}" -eq 0 ]]; then
    warn "no payload files found for category '${category}'"
    exit 0
  fi

  if [[ "${category}" == "invest" ]]; then
    state_file="${output_dir}/posted_ids.txt"
  else
    state_file="${output_dir}/state/${category}-posted.txt"
  fi
  mkdir -p "$(dirname "${state_file}")"
  touch "${state_file}"
  candidate_file="$(make_run_file "${output_dir}" "candidate-${category}")"

  python3 - "${category}" "${state_file}" "${payload_files[@]}" > "${candidate_file}" <<'PY'
import json
import pathlib
import re
import sys
category = sys.argv[1]
state_file = pathlib.Path(sys.argv[2])
payload_files = [pathlib.Path(item) for item in sys.argv[3:]]

posted_ids = {
    line.strip()
    for line in state_file.read_text(encoding="utf-8").splitlines()
    if line.strip()
}

warnings = []
seen_ids = set()
seen_text = set()
candidates = []


def coerce_int(value):
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        compact = value.replace(",", "").strip()
        if compact.isdigit():
            return int(compact)
        match = re.search(r"\d[\d,]*", value)
        if match:
            return int(match.group(0).replace(",", ""))
    return 0


def nested_get(mapping, *path):
    current = mapping
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def extract_metric(item, keys):
    values = []
    for path in keys:
        values.append(nested_get(item, *path))
    return max((coerce_int(value) for value in values), default=0)


def clean_source_text(text):
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#(\w+)", r"\1", text)
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \"'|")


def build_summary(text):
    cleaned = clean_source_text(text)
    replacements = [
        (r"\bearnings beat expectations\b", "決算が市場予想を上振れ"),
        (r"\brevenue outlook improves\b", "売上見通しが改善"),
        (r"\bearnings\b", "決算"),
        (r"\bexpectation(s)?\b", "期待"),
        (r"\brevenue\b", "売上"),
        (r"\boutlook\b", "見通し"),
        (r"\bguidance\b", "見通し"),
        (r"\bforecast\b", "予想"),
        (r"\bdemand\b", "需要"),
        (r"\bimprove(s|d)?\b", "改善"),
        (r"\bstrong\b", "強い"),
        (r"\bsteady\b", "安定"),
        (r"\brecent\b", "直近"),
        (r"\bpullback\b", "調整"),
        (r"\bmemory\b", "メモリ"),
        (r"\bchip(s)?\b", "半導体"),
        (r"\bsemiconductor(s)?\b", "半導体"),
        (r"\bbeat(s|ing)?\b", "上振れ"),
        (r"\bmiss(es|ing)?\b", "下振れ"),
        (r"\bsurge(s|d)?\b", "急伸"),
        (r"\bjump(s|ed|ing)?\b", "上昇"),
        (r"\brise(s|n|ing)?\b", "上昇"),
        (r"\bfall(s|ing|en)?\b", "下落"),
        (r"\bdrop(s|ped|ping)?\b", "下落"),
        (r"\bgain(s|ed|ing)?\b", "上昇"),
        (r"\bloss(es)?\b", "損失"),
        (r"\bprofit(s)?\b", "利益"),
        (r"\bbullish\b", "強気"),
        (r"\bbearish\b", "弱気"),
        (r"\bupgrade(d)?\b", "格上げ"),
        (r"\bdowngrade(d)?\b", "格下げ"),
        (r"\bAI\b", "AI"),
        (r"&", "と"),
    ]

    for pattern, replacement in replacements:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -,:;")

    if not cleaned:
        cleaned = "$MU関連の注目投稿"

    prefix = "Xで反応上位の$MU投稿: "
    if "$MU" in cleaned.upper():
        prefix = "Xで反応上位: "

    max_body_length = 140 - len(prefix)
    if len(cleaned) > max_body_length:
        cleaned = cleaned[: max_body_length - 1].rstrip(" ,.;:") + "…"

    summary = prefix + cleaned
    if len(summary) < 140 and not summary.endswith(("。", "！", "?", "？")):
        summary += "。"
    if len(summary) > 140:
        summary = summary[:139].rstrip(" ,.;:") + "…"
    return summary


for payload_path in payload_files:
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
        text = clean_source_text(str(item.get("text") or ""))
        if not tweet_id or not text:
            continue

        if tweet_id in posted_ids or tweet_id in seen_ids:
            continue

        normalized_text = re.sub(r"\s+", " ", text).strip().lower()
        if normalized_text in seen_text:
            continue

        author = item.get("author") or {}
        likes = extract_metric(item, [("metrics", "likes"), ("likes",), ("legacy", "favorite_count")])
        retweets = extract_metric(item, [("metrics", "retweets"), ("retweets",), ("legacy", "retweet_count")])
        views = extract_metric(
            item,
            [
                ("metrics", "views"),
                ("metrics", "viewCount"),
                ("views",),
                ("viewCount",),
                ("view_count",),
                ("views", "count"),
                ("legacy", "views"),
                ("legacy", "view_count"),
            ],
        )
        score = likes + retweets + views

        candidates.append(
            {
                "id": tweet_id,
                "text": text,
                "summary_text": build_summary(text),
                "screen_name": str(author.get("screenName") or ""),
                "author_name": str(author.get("name") or ""),
                "likes": likes,
                "retweets": retweets,
                "views": views,
                "score": score,
                "created_at": str(item.get("createdAtISO") or item.get("createdAt") or ""),
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

selected = candidates[0] if candidates else None
payload = {
    "category": category,
    "post_text": selected["summary_text"] if selected else "",
    "selected": selected,
    "warnings": warnings,
}
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY

  summary_warnings="$(python3 - "${candidate_file}" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
for item in payload.get("warnings") or []:
    print(item)
PY
)"

  if [[ -n "${summary_warnings}" ]]; then
    while IFS= read -r summary_warning; do
      [[ -n "${summary_warning}" ]] && warn "${summary_warning}"
    done <<<"${summary_warnings}"
  fi

  selected_count="$(python3 - "${candidate_file}" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(1 if payload.get("selected") else 0)
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
  posted_id="$(python3 - "${candidate_file}" <<'PY'
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
    info "dry-run enabled; skipping twitter post"
    exit 0
  fi

  post_result_file="$(make_run_file "${output_dir}" "post-${category}")"
  if ! twitter_cmd post "${post_text}" --json > "${post_result_file}"; then
    warn "twitter post failed for '${category}'"
    exit 0
  fi

  if ! assert_structured_success "${post_result_file}" "post:${category}"; then
    warn "twitter post response validation failed for '${category}'"
    exit 0
  fi

  if ! python3 - "${posted_id}" "${state_file}" <<'PY'
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
    exit 0
  fi

  info "posted category '${category}' and updated ${state_file}"
}

main "$@"
