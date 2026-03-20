#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: bash scripts/fetch_search.sh --category <news|invest> [options]

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
  local query=""
  local timeline=""
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
  validate_sources_config "${sources_config}"
  ensure_dependencies
  ensure_output_layout "${output_dir}"
  ensure_twitter_auth

  mapfile -t search_sources < <(sources_jsonl "${sources_config}" "${category}" "search")

  if [[ ${#search_sources[@]} -eq 0 ]]; then
    info "no enabled search sources for category '${category}'"
    exit 0
  fi

  source_dir="${output_dir}/raw/${category}"
  mkdir -p "${source_dir}"

  for source_json in "${search_sources[@]}"; do
    parsed="$(python3 - "${source_json}" <<'PY'
import json
import sys

source = json.loads(sys.argv[1])
print(
    source["id"],
    source["query"],
    source["timeline"],
    source["max_results"],
    str(source["exclude_retweets"]).lower(),
    sep="\t",
)
PY
)"

    IFS=$'\t' read -r source_id query timeline max_results exclude_retweets <<<"${parsed}"
    output_path="${source_dir}/${source_id}.json"

    info "fetching search timeline '${query}' -> ${output_path}"
    if ! retry_to_file "${output_path}" "${DEFAULT_RETRY_ATTEMPTS}" "${DEFAULT_RETRY_DELAY_SECONDS}" twitter_cmd search "${query}" -t "${timeline}" -n "${max_results}" --json; then
      warn "search fetch failed for '${source_id}'; continuing"
      rm -f "${output_path}"
      continue
    fi

    if ! assert_structured_success "${output_path}" "search:${source_id}"; then
      warn "invalid search response for '${source_id}'; continuing"
      rm -f "${output_path}"
      continue
    fi

    if [[ "${exclude_retweets}" == "true" ]]; then
      if ! filter_retweets_inplace "${output_path}"; then
        warn "failed to filter retweets for '${source_id}'; keeping original payload"
      fi
    fi
  done
}

main "$@"
