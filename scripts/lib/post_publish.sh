#!/usr/bin/env bash

publish_selected_post() {
  local category="$1"
  local post_text="$2"
  local selected_tweet_id="$3"
  local state_file="$4"
  local post_result_file="$5"

  if ! retry_to_file "${post_result_file}" "${DEFAULT_RETRY_ATTEMPTS}" "${DEFAULT_RETRY_DELAY_SECONDS}" twitter_cmd post "${post_text}" --json; then
    warn "twitter post failed for '${category}'"
    return 1
  fi

  if ! assert_structured_success "${post_result_file}" "post:${category}"; then
    warn "twitter post response validation failed for '${category}'"
    return 1
  fi

  if ! python_cmd - "${selected_tweet_id}" "${state_file}" <<'PY'
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
    return 1
  fi

  info "posted category '${category}' and updated ${state_file}"
}
