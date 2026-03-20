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
  ensure_dependencies
  ensure_output_layout "${output_dir}"
  ensure_twitter_auth

  mapfile -t user_sources < <(sources_jsonl "${sources_config}" "${category}" "user")

  if [[ ${#user_sources[@]} -eq 0 ]]; then
    info "no enabled user sources for category '${category}'"
    exit 0
  fi

  source_dir="${output_dir}/raw/${category}"
  mkdir -p "${source_dir}"

  for source_json in "${user_sources[@]}"; do
    parsed="$(python3 - "${source_json}" <<'PY'
import json
import sys

source = json.loads(sys.argv[1])
print(source["id"], source["username"], source["max_results"], str(source["exclude_retweets"]).lower(), sep="\t")
PY
)"

    IFS=$'\t' read -r source_id username max_results exclude_retweets <<<"${parsed}"
    output_path="${source_dir}/${source_id}.json"

    info "fetching user posts for @${username} -> ${output_path}"
    twitter user-posts "${username}" --max "${max_results}" --json > "${output_path}"
    assert_structured_success "${output_path}" "user:${source_id}"

    if [[ "${exclude_retweets}" == "true" ]]; then
      filter_retweets_inplace "${output_path}"
    fi
  done
}

main "$@"
