#!/usr/bin/env bash

set -Eeuo pipefail

readonly COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${COMMON_DIR}/../.." && pwd)"
readonly DEFAULT_SOURCES_CONFIG="${PROJECT_ROOT}/config/sources.yaml"
readonly DEFAULT_ACCOUNTS_CONFIG="${PROJECT_ROOT}/config/accounts.yaml"
readonly DEFAULT_TMP_DIR="${PROJECT_ROOT}/tmp"
readonly DEFAULT_TWITTER_BIN="${PROJECT_ROOT}/python/.venv/bin/twitter"
readonly DEFAULT_RETRY_ATTEMPTS="${TWITTER_RETRY_ATTEMPTS:-3}"
readonly DEFAULT_RETRY_DELAY_SECONDS="${TWITTER_RETRY_DELAY_SECONDS:-2}"

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

retry_command() {
  local attempts="${1:-${DEFAULT_RETRY_ATTEMPTS}}"
  local delay_seconds="${2:-${DEFAULT_RETRY_DELAY_SECONDS}}"
  local attempt=1
  local exit_code=0

  shift 2 || true

  (($# > 0)) || die "retry_command requires a command"

  while true; do
    if "$@"; then
      return 0
    fi

    exit_code=$?
    if (( attempt >= attempts )); then
      return "${exit_code}"
    fi

    warn "command failed (attempt ${attempt}/${attempts}); retrying in ${delay_seconds}s: $*"
    sleep "${delay_seconds}"
    attempt=$((attempt + 1))
  done
}

retry_to_file() {
  local output_path="$1"
  local attempts="${2:-${DEFAULT_RETRY_ATTEMPTS}}"
  local delay_seconds="${3:-${DEFAULT_RETRY_DELAY_SECONDS}}"
  local attempt=1
  local exit_code=0

  shift 3 || true

  (($# > 0)) || die "retry_to_file requires a command"

  while true; do
    if "$@" > "${output_path}"; then
      return 0
    fi

    exit_code=$?
    if (( attempt >= attempts )); then
      rm -f "${output_path}"
      return "${exit_code}"
    fi

    warn "command failed (attempt ${attempt}/${attempts}); retrying in ${delay_seconds}s: $*"
    sleep "${delay_seconds}"
    attempt=$((attempt + 1))
  done
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

validate_sources_config() {
  local sources_config="$1"

  python3 - "${sources_config}" <<'PY'
import pathlib
import sys

import yaml

config_path = pathlib.Path(sys.argv[1])
raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

if not isinstance(raw, dict):
    raise SystemExit("sources config must be a mapping")

defaults = raw.get("defaults") or {}
if not isinstance(defaults, dict):
    raise SystemExit("sources.defaults must be a mapping")

if "max_results" in defaults and int(defaults["max_results"]) <= 0:
    raise SystemExit("sources.defaults.max_results must be > 0")

sources = raw.get("sources") or []
if not isinstance(sources, list):
    raise SystemExit("sources.sources must be a list")

for index, item in enumerate(sources, start=1):
    if not isinstance(item, dict):
        raise SystemExit(f"sources[{index}] must be a mapping")

    source_id = str(item.get("id") or "").strip()
    if not source_id:
        raise SystemExit(f"sources[{index}] is missing id")

    category = str(item.get("category") or "").strip()
    if not category:
        raise SystemExit(f"{source_id}: category is required")

    source_type = str(item.get("type") or "").strip()
    if source_type not in {"user", "search"}:
        raise SystemExit(f"{source_id}: type must be user or search")

    if "max_results" in item and int(item["max_results"]) <= 0:
        raise SystemExit(f"{source_id}: max_results must be > 0")

    if source_type == "user":
        username = str(item.get("username") or "").strip().lstrip("@")
        if not username:
            raise SystemExit(f"{source_id}: username is required for user source")
    else:
        query = " ".join(str(item.get("query") or "").split())
        if not query:
            raise SystemExit(f"{source_id}: query is required for search source")
        timeline = str(item.get("timeline") or defaults.get("timeline") or "latest").strip().lower()
        if timeline not in {"top", "latest", "photos", "videos"}:
            raise SystemExit(f"{source_id}: unsupported timeline '{timeline}'")
PY
}

validate_accounts_config() {
  local accounts_config="$1"

  python3 - "${accounts_config}" <<'PY'
import pathlib
import sys

import yaml


def ensure_string_list(label, value):
    if value is None:
        return
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise SystemExit(f"{label} must be a list of non-empty strings")


def ensure_number_mapping(label, value):
    if value is None:
        return
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be a mapping")
    for key, item in value.items():
        try:
            float(item)
        except (TypeError, ValueError) as exc:
            raise SystemExit(f"{label}.{key} must be numeric") from exc


config_path = pathlib.Path(sys.argv[1])
raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

if not isinstance(raw, dict):
    raise SystemExit("accounts config must be a mapping")

defaults = raw.get("defaults") or {}
accounts = raw.get("accounts") or {}

if not isinstance(defaults, dict):
    raise SystemExit("accounts.defaults must be a mapping")
if not isinstance(accounts, dict):
    raise SystemExit("accounts.accounts must be a mapping")

for label, block in [("defaults", defaults), *[(f"accounts.{name}", value) for name, value in accounts.items()]]:
    if not isinstance(block, dict):
        raise SystemExit(f"{label} must be a mapping")

    if "max_candidates" in block and int(block["max_candidates"]) <= 0:
        raise SystemExit(f"{label}.max_candidates must be > 0")
    if "summary_max_length" in block and int(block["summary_max_length"]) <= 0:
        raise SystemExit(f"{label}.summary_max_length must be > 0")
    if "summary_language" in block and str(block["summary_language"]).strip() not in {"ja", "raw"}:
        raise SystemExit(f"{label}.summary_language must be 'ja' or 'raw'")

    ensure_number_mapping(f"{label}.score_weights", block.get("score_weights"))

    filters = block.get("filters")
    if filters is not None:
        if not isinstance(filters, dict):
            raise SystemExit(f"{label}.filters must be a mapping")
        if "max_age_hours" in filters and filters["max_age_hours"] is not None and float(filters["max_age_hours"]) <= 0:
            raise SystemExit(f"{label}.filters.max_age_hours must be > 0")
        ensure_string_list(f"{label}.filters.required_terms", filters.get("required_terms"))
        ensure_string_list(f"{label}.filters.exclude_keywords", filters.get("exclude_keywords"))
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

default_score_weights = defaults.get("score_weights") or {}
account_score_weights = account.get("score_weights") or {}
default_filters = defaults.get("filters") or {}
account_filters = account.get("filters") or {}

payload = {
    "dry_run": bool(account.get("dry_run", defaults.get("dry_run", True))),
    "post_prefix": str(account.get("post_prefix") or defaults.get("post_prefix") or "Update:"),
    "max_candidates": int(account.get("max_candidates") or defaults.get("max_candidates") or 1),
    "summary_prefix": str(
        account.get("summary_prefix")
        or account.get("post_prefix")
        or defaults.get("summary_prefix")
        or defaults.get("post_prefix")
        or "Xで反応上位: "
    ),
    "summary_language": str(account.get("summary_language") or defaults.get("summary_language") or "ja"),
    "summary_max_length": int(account.get("summary_max_length") or defaults.get("summary_max_length") or 140),
    "state_file": str(account.get("state_file") or defaults.get("state_file") or ""),
    "score_weights": {
        "likes": float(account_score_weights.get("likes", default_score_weights.get("likes", 1))),
        "retweets": float(account_score_weights.get("retweets", default_score_weights.get("retweets", 1))),
        "views": float(account_score_weights.get("views", default_score_weights.get("views", 1))),
    },
    "filters": {
        "max_age_hours": account_filters.get("max_age_hours", default_filters.get("max_age_hours")),
        "required_terms": account_filters.get("required_terms", default_filters.get("required_terms", [])) or [],
        "exclude_keywords": account_filters.get("exclude_keywords", default_filters.get("exclude_keywords", [])) or [],
    },
}

print(json.dumps(payload, ensure_ascii=True))
PY
}
