#!/usr/bin/env bash

set -Eeuo pipefail

readonly COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${COMMON_DIR}/../.." && pwd)"
readonly DEFAULT_SOURCES_CONFIG="${PROJECT_ROOT}/config/sources.yaml"
readonly DEFAULT_ACCOUNTS_CONFIG="${PROJECT_ROOT}/config/accounts.yaml"
readonly DEFAULT_TMP_DIR="${PROJECT_ROOT}/tmp"
readonly DEFAULT_TWITTER_BIN="${PROJECT_ROOT}/python/.venv/bin/twitter"

TWITTER_BIN_CACHE=""

log() {
  local level="$1"
  shift
  printf '[%s] %s\n' "${level}" "$*" >&2
}

info() {
  log info "$*"
}

warn() {
  log warn "$*"
}

die() {
  log error "$*"
  exit 1
}

require_command() {
  local command_name="$1"

  command -v "${command_name}" >/dev/null 2>&1 || die "required command not found: ${command_name}"
}

require_yaml_support() {
  python3 - <<'PY' >/dev/null 2>&1 || die "python3 package 'pyyaml' is required"
import yaml  # noqa: F401
PY
}

resolve_twitter_bin() {
  local configured_bin="${TWITTER_BIN:-}"

  if [[ -n "${configured_bin}" ]]; then
    if [[ "${configured_bin}" == */* ]]; then
      [[ -x "${configured_bin}" ]] || die "twitter-cli executable not found: ${configured_bin}"
      printf '%s\n' "${configured_bin}"
      return
    fi

    command -v "${configured_bin}" >/dev/null 2>&1 || die "required command not found: ${configured_bin}"
    command -v "${configured_bin}"
    return
  fi

  if [[ -x "${DEFAULT_TWITTER_BIN}" ]]; then
    printf '%s\n' "${DEFAULT_TWITTER_BIN}"
    return
  fi

  if command -v twitter >/dev/null 2>&1; then
    warn "falling back to twitter from PATH; expected ${DEFAULT_TWITTER_BIN}"
    command -v twitter
    return
  fi

  die "twitter-cli not found. expected ${DEFAULT_TWITTER_BIN} or a TWITTER_BIN override"
}

twitter_cmd() {
  if [[ -z "${TWITTER_BIN_CACHE}" ]]; then
    TWITTER_BIN_CACHE="$(resolve_twitter_bin)"
  fi

  "${TWITTER_BIN_CACHE}" "$@"
}

ensure_dependencies() {
  require_command python3
  require_yaml_support
  resolve_twitter_bin >/dev/null
}

ensure_config_file() {
  local config_path="$1"

  [[ -f "${config_path}" ]] || die "config file not found: ${config_path}"
}

ensure_output_layout() {
  local output_dir="$1"

  mkdir -p "${output_dir}" "${output_dir}/raw" "${output_dir}/runs" "${output_dir}/state"
}

ensure_twitter_auth() {
  twitter_cmd status --yaml >/dev/null 2>&1 || die "twitter-cli authentication required. Run 'twitter whoami' locally or set TWITTER_AUTH_TOKEN/TWITTER_CT0."
}

normalize_bool() {
  local raw_value="${1:-}"

  case "${raw_value}" in
    true|TRUE|True|1|yes|YES|on|ON)
      printf 'true\n'
      ;;
    false|FALSE|False|0|no|NO|off|OFF|'')
      printf 'false\n'
      ;;
    *)
      die "invalid boolean value: ${raw_value}"
      ;;
  esac
}

make_run_file() {
  local output_dir="$1"
  local prefix="$2"

  ensure_output_layout "${output_dir}"
  mktemp "${output_dir}/runs/${prefix}.XXXXXX"
}

assert_structured_success() {
  local payload_path="$1"
  local label="$2"

  python3 - "${payload_path}" "${label}" <<'PY'
import json
import pathlib
import sys

payload_path = pathlib.Path(sys.argv[1])
label = sys.argv[2]
payload = json.loads(payload_path.read_text(encoding="utf-8"))

if payload.get("ok") is not True:
    raise SystemExit(f"{label}: ok != true")

if "data" not in payload:
    raise SystemExit(f"{label}: missing data field")
PY
}

filter_retweets_inplace() {
  local payload_path="$1"

  python3 - "${payload_path}" <<'PY'
import json
import pathlib
import sys

payload_path = pathlib.Path(sys.argv[1])
payload = json.loads(payload_path.read_text(encoding="utf-8"))
items = payload.get("data") or []
payload["data"] = [item for item in items if not item.get("isRetweet", False)]
payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

sources_jsonl() {
  local sources_config="$1"
  local category="$2"
  local source_type="$3"

  python3 - "${sources_config}" "${category}" "${source_type}" <<'PY'
import json
import pathlib
import sys

import yaml

sources_config = pathlib.Path(sys.argv[1])
category = sys.argv[2]
source_type = sys.argv[3]

raw = yaml.safe_load(sources_config.read_text(encoding="utf-8")) or {}
defaults = raw.get("defaults") or {}
sources = raw.get("sources") or []

for item in sources:
    if not isinstance(item, dict):
        raise SystemExit("each source entry must be a mapping")

    if not item.get("enabled", True):
        continue

    if item.get("category") != category or item.get("type") != source_type:
        continue

    source_id = str(item.get("id") or "").strip()
    if not source_id:
        raise SystemExit("source entry is missing id")

    payload = {
        "id": source_id,
        "category": category,
        "type": source_type,
        "max_results": int(item.get("max_results") or defaults.get("max_results") or 5),
        "exclude_retweets": bool(item.get("exclude_retweets", defaults.get("exclude_retweets", True))),
    }

    if source_type == "user":
        username = str(item.get("username") or "").strip().lstrip("@")
        if not username:
            raise SystemExit(f"{source_id}: username is required for user source")
        payload["username"] = username
    elif source_type == "search":
        query = " ".join(str(item.get("query") or "").split())
        if not query:
            raise SystemExit(f"{source_id}: query is required for search source")
        timeline = str(item.get("timeline") or defaults.get("timeline") or "latest").strip().lower()
        if timeline not in {"top", "latest", "photos", "videos"}:
            raise SystemExit(f"{source_id}: unsupported timeline '{timeline}'")
        payload["query"] = query
        payload["timeline"] = timeline
    else:
        raise SystemExit(f"unsupported source type: {source_type}")

    print(json.dumps(payload, ensure_ascii=True))
PY
}

account_config_json() {
  local accounts_config="$1"
  local category="$2"

  python3 - "${accounts_config}" "${category}" <<'PY'
import json
import pathlib
import sys

import yaml

accounts_config = pathlib.Path(sys.argv[1])
category = sys.argv[2]

raw = yaml.safe_load(accounts_config.read_text(encoding="utf-8")) or {}
defaults = raw.get("defaults") or {}
accounts = raw.get("accounts") or {}
account = accounts.get(category) or {}

payload = {
    "dry_run": bool(account.get("dry_run", defaults.get("dry_run", True))),
    "post_prefix": str(account.get("post_prefix") or defaults.get("post_prefix") or "Update:"),
    "max_candidates": int(account.get("max_candidates") or defaults.get("max_candidates") or 1),
}

print(json.dumps(payload, ensure_ascii=True))
PY
}
