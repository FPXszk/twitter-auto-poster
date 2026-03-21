#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: bash scripts/fetch_user.sh --category <news|invest> [options]

Options:
  --category <name>      Source category to load
  --sources <path>       Path to config/sources.yaml
  --output-dir <path>    Output directory for raw JSON data
  -h, --help             Show this help message
EOF
}

main() {
  local category=""
  local output_dir="${DEFAULT_TMP_DIR}"
  local sources_config="${DEFAULT_SOURCES_CONFIG}"
  local output_path=""
  local source_dir=""
  local source_id=""
  local username=""
  local max_results=""
  local exclude_retweets=""
  local parsed=""
  local source_json=""
  local total_sources=0
  local successful_sources=0
  local failed_sources=0
  local status_file=""

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
      --output-dir)
        [[ $# -ge 2 ]] || die "--output-dir requires a value"
        output_dir="$2"
        shift 2
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
  validate_sources_config "${sources_config}"
  ensure_dependencies
  ensure_output_layout "${output_dir}"
  ensure_twitter_auth

  mapfile -t user_sources < <(sources_jsonl "${sources_config}" "${category}" "user")

  if [[ ${#user_sources[@]} -eq 0 ]]; then
    status_file="${output_dir}/runs/fetch-user-${category}.json"
    mkdir -p "$(dirname "${status_file}")"
    printf '{\n  "source_type": "user",\n  "category": "%s",\n  "total_sources": 0,\n  "successful_sources": 0,\n  "failed_sources": 0\n}\n' "${category}" > "${status_file}"
    info "no enabled user sources for category '${category}'"
    exit 0
  fi

  source_dir="${output_dir}/raw/${category}"
  mkdir -p "${source_dir}"
  status_file="${output_dir}/runs/fetch-user-${category}.json"
  total_sources="${#user_sources[@]}"

  for source_json in "${user_sources[@]}"; do
    parsed="$(python_cmd - "${source_json}" <<'PY'
import json
import sys

source = json.loads(sys.argv[1])
print(source["id"], source["username"], source["max_results"], str(source["exclude_retweets"]).lower(), sep="\t")
PY
)"

    IFS=$'\t' read -r source_id username max_results exclude_retweets <<<"${parsed}"
    output_path="${source_dir}/${source_id}.json"

    info "fetching user posts for @${username} -> ${output_path}"
    if ! retry_to_file "${output_path}" "${DEFAULT_RETRY_ATTEMPTS}" "${DEFAULT_RETRY_DELAY_SECONDS}" twitter_cmd user-posts "${username}" --max "${max_results}" --json; then
      warn "user fetch failed for '${source_id}'; continuing"
      failed_sources=$((failed_sources + 1))
      rm -f "${output_path}"
      continue
    fi

    if ! assert_structured_success "${output_path}" "user:${source_id}"; then
      warn "invalid user response for '${source_id}'; continuing"
      failed_sources=$((failed_sources + 1))
      rm -f "${output_path}"
      continue
    fi

    if [[ "${exclude_retweets}" == "true" ]]; then
      if ! filter_retweets_inplace "${output_path}"; then
        warn "failed to filter retweets for '${source_id}'; keeping original payload"
      fi
    fi
    successful_sources=$((successful_sources + 1))
  done

  python_cmd - "${status_file}" "${category}" "${total_sources}" "${successful_sources}" "${failed_sources}" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
payload = {
    "source_type": "user",
    "category": sys.argv[2],
    "total_sources": int(sys.argv[3]),
    "successful_sources": int(sys.argv[4]),
    "failed_sources": int(sys.argv[5]),
}
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

main "$@"
