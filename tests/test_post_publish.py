from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest import TestCase, main


class PostPublishTest(TestCase):
    root_dir = Path(__file__).resolve().parents[1]
    common_sh = root_dir / "scripts" / "lib" / "common.sh"
    post_publish_sh = root_dir / "scripts" / "lib" / "post_publish.sh"

    def run_bash(self, script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-lc", script],
            cwd=self.root_dir,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_publish_selected_post_caps_single_post_limit_and_falls_back_after_186(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            result_path = temp_path / "post-result.json"
            state_path = temp_path / "posted.txt"
            source_state_path = temp_path / "source-posted.txt"
            limits_path = temp_path / "single-post-limits.txt"

            result = self.run_bash(
                f'''
                source "{self.common_sh}"
                source "{self.post_publish_sh}"

                python_cmd() {{
                  python3 "$@"
                }}

                post_calls=0
                build_plan_calls=0

                build_thread_plan_json() {{
                  local post_text="$1"
                  local source_url="$2"
                  local single_post_max_length="$3"
                  local source_reference_mode="$4"
                  local stdout_path="$5"
                  local stderr_path="$6"

                  printf '%s\n' "${{single_post_max_length}}" >> "{limits_path}"
                  build_plan_calls=$((build_plan_calls + 1))

                  if (( build_plan_calls == 1 )); then
                    printf '%s' '["quote-single-post"]' > "${{stdout_path}}"
                    : > "${{stderr_path}}"
                    return 0
                  fi
                  if (( build_plan_calls == 2 )); then
                    printf '%s' '["thread-part-1","thread-part-2"]' > "${{stdout_path}}"
                    : > "${{stderr_path}}"
                    return 0
                  fi
                  return 1
                }}

                count_thread_posts() {{
                  python3 - "$1" <<'PY'
import json
import sys

print(len(json.loads(sys.argv[1])))
PY
                }}

                estimate_thread_post_length() {{
                  printf '280\\n'
                }}

                execute_twitter_post() {{
                  local category="$1"
                  local post_text="$2"
                  local reply_to_id="${{3:-}}"
                  local quote_tweet_id="${{4:-}}"
                  local media_paths_json="${{5:-}}"
                  local output_file="$6"
                  local stderr_file="$7"

                  post_calls=$((post_calls + 1))
                  if (( post_calls == 1 )); then
                    printf '%s' '{{"ok":false}}' > "${{output_file}}"
                    printf '%s' 'Twitter API returned errors: Authorization: Tweet needs to be a bit shorter. (186)' > "${{stderr_file}}"
                    return 1
                  fi

                  if [[ -n "${{media_paths_json}}" && "${{media_paths_json}}" != "[]" ]]; then
                    printf '%s' 'quote fallback test should not pass image attachments' >&2
                    return 93
                  fi

                  if (( post_calls == 2 )) && [[ "${{quote_tweet_id}}" != "12345" ]]; then
                    printf '%s' 'first thread post should keep the quote target' >&2
                    return 91
                  fi

                  if (( post_calls == 3 )) && [[ -n "${{quote_tweet_id}}" ]]; then
                    printf '%s' 'second thread post should not include a quote target' >&2
                    return 92
                  fi

                  printf '%s' "{{\\"ok\\":true,\\"data\\":{{\\"id\\":\\"posted-${{post_calls}}\\"}}}}" > "${{output_file}}"
                  : > "${{stderr_file}}"
                  return 0
                }}

                assert_structured_success() {{
                  return 0
                }}

                set +e
                publish_selected_post \
                  "invest" \
                  "ignored post text" \
                  "12345" \
                  "https://x.com/example/status/12345" \
                  "quote" \
                  "4000" \
                  "{state_path}" \
                  "{source_state_path}" \
                  "{result_path}"
                status="$?"
                printf 'status=%s\\n' "${{status}}"
                printf 'post_calls=%s\\n' "${{post_calls}}"
                '''
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("status=0", result.stdout, msg=result.stderr)
            self.assertIn("post_calls=3", result.stdout, msg=result.stderr)
            self.assertEqual(limits_path.read_text(encoding="utf-8").splitlines(), ["280", "280"])

            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["data"]["action"], "post_thread_quote")
            self.assertEqual(payload["data"]["tweet_count"], 2)

    def test_publish_selected_post_passes_image_paths_to_execute_twitter_post(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            result_path = temp_path / "post-result.json"
            state_path = temp_path / "posted.txt"
            source_state_path = temp_path / "source-posted.txt"
            cleanup_path = temp_path / "cleanup.txt"

            result = self.run_bash(
                f'''
                source "{self.common_sh}"
                source "{self.post_publish_sh}"

                python_cmd() {{
                  python3 "$@"
                }}

                build_thread_plan_json() {{
                  local post_text="$1"
                  local source_url="$2"
                  local single_post_max_length="$3"
                  local source_reference_mode="$4"
                  local stdout_path="$5"
                  local stderr_path="$6"
                  printf '%s' '["single-post"]' > "${{stdout_path}}"
                  : > "${{stderr_path}}"
                }}

                count_thread_posts() {{
                  python3 - "$1" <<'PY'
import json
import sys

print(len(json.loads(sys.argv[1])))
PY
                }}

                prepare_image_attachments() {{
                  local image_urls_json="$1"
                  if [[ "${{image_urls_json}}" != '["https://pbs.twimg.com/media/example-1.jpg"]' ]]; then
                    printf '%s' 'unexpected image url payload' >&2
                    return 81
                  fi
                  printf '%s' '["/tmp/copied-1.jpg"]'
                }}

                cleanup_image_attachments() {{
                  printf '%s\\n' "$1" > "{cleanup_path}"
                }}

                execute_twitter_post() {{
                  local category="$1"
                  local post_text="$2"
                  local reply_to_id="${{3:-}}"
                  local quote_tweet_id="${{4:-}}"
                  local media_paths_json="$5"
                  local output_file="$6"
                  local stderr_file="$7"

                  if [[ "${{media_paths_json}}" != '["/tmp/copied-1.jpg"]' ]]; then
                    printf '%s' 'image attachments were not passed to execute_twitter_post' >&2
                    return 91
                  fi

                  printf '%s' '{{"ok":true,"data":{{"id":"posted-1"}}}}' > "${{output_file}}"
                  : > "${{stderr_file}}"
                }}

                assert_structured_success() {{
                  return 0
                }}

                set +e
                publish_selected_post \
                  "invest" \
                  "要約済みの単独ポスト" \
                  "12345" \
                  "https://x.com/example/status/12345" \
                  "url" \
                  "280" \
                  "{state_path}" \
                  "{source_state_path}" \
                  "{result_path}" \
                  '["https://pbs.twimg.com/media/example-1.jpg"]'
                status="$?"
                printf 'status=%s\\n' "${{status}}"
                '''
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("status=0", result.stdout, msg=result.stderr)
            self.assertEqual(cleanup_path.read_text(encoding="utf-8").strip(), '["/tmp/copied-1.jpg"]')

    def test_publish_selected_post_omits_source_url_in_none_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            result_path = temp_path / "post-result.json"
            state_path = temp_path / "posted.txt"
            source_state_path = temp_path / "source-posted.txt"

            result = self.run_bash(
                f'''
                source "{self.common_sh}"
                source "{self.post_publish_sh}"

                python_cmd() {{
                  python3 "$@"
                }}

                build_thread_plan_json() {{
                  local post_text="$1"
                  local source_url="$2"
                  local single_post_max_length="$3"
                  local source_reference_mode="$4"
                  local stdout_path="$5"
                  local stderr_path="$6"

                  if [[ -n "${{source_url}}" ]]; then
                    printf '%s' 'source_url should be empty in none mode' >&2
                    return 81
                  fi

                  printf '%s' '["single-post"]' > "${{stdout_path}}"
                  : > "${{stderr_path}}"
                }}

                count_thread_posts() {{
                  python3 - "$1" <<'PY'
import json
import sys

print(len(json.loads(sys.argv[1])))
PY
                }}

                execute_twitter_post() {{
                  local category="$1"
                  local post_text="$2"
                  local reply_to_id="${{3:-}}"
                  local quote_tweet_id="${{4:-}}"
                  local media_paths_json="$5"
                  local output_file="$6"
                  local stderr_file="$7"

                  if [[ -n "${{quote_tweet_id}}" ]]; then
                    printf '%s' 'quote_tweet_id should be empty in none mode' >&2
                    return 82
                  fi

                  printf '%s' '{{"ok":true,"data":{{"id":"posted-1"}}}}' > "${{output_file}}"
                  : > "${{stderr_file}}"
                }}

                assert_structured_success() {{
                  return 0
                }}

                set +e
                publish_selected_post \
                  "buz" \
                  "通常ポスト" \
                  "12345" \
                  "https://x.com/example/status/12345" \
                  "none" \
                  "280" \
                  "{state_path}" \
                  "{source_state_path}" \
                  "{result_path}"
                status="$?"
                printf 'status=%s\\n' "${{status}}"
                '''
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("status=0", result.stdout, msg=result.stderr)

    def test_publish_selected_post_survives_failed_image_prepare_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            result_path = temp_path / "post-result.json"
            state_path = temp_path / "posted.txt"
            source_state_path = temp_path / "source-posted.txt"

            result = self.run_bash(
                f'''
                source "{self.common_sh}"
                source "{self.post_publish_sh}"

                python_cmd() {{
                  python3 "$@"
                }}

                build_thread_plan_json() {{
                  local post_text="$1"
                  local source_url="$2"
                  local single_post_max_length="$3"
                  local source_reference_mode="$4"
                  local stdout_path="$5"
                  local stderr_path="$6"
                  printf '%s' '["single-post"]' > "${{stdout_path}}"
                  : > "${{stderr_path}}"
                }}

                count_thread_posts() {{
                  python3 - "$1" <<'PY'
import json
import sys
print(len(json.loads(sys.argv[1])))
PY
                }}

                prepare_image_attachments() {{
                  printf '%s' 'download failed' >&2
                  return 81
                }}

                execute_twitter_post() {{
                  local category="$1"
                  local post_text="$2"
                  local reply_to_id="${{3:-}}"
                  local quote_tweet_id="${{4:-}}"
                  local media_paths_json="$5"
                  local output_file="$6"
                  local stderr_file="$7"

                  if [[ "${{media_paths_json}}" != '[]' ]]; then
                    printf '%s' 'expected image prepare fallback to text only' >&2
                    return 91
                  fi

                  printf '%s' '{{"ok":true,"data":{{"id":"posted-1"}}}}' > "${{output_file}}"
                  : > "${{stderr_file}}"
                }}

                assert_structured_success() {{
                  return 0
                }}

                set +e
                publish_selected_post \
                  "buz" \
                  "通常ポスト" \
                  "12345" \
                  "https://x.com/example/status/12345" \
                  "none" \
                  "280" \
                  "{state_path}" \
                  "{source_state_path}" \
                  "{result_path}" \
                  '["https://pbs.twimg.com/media/example-1.jpg"]'
                status="$?"
                printf 'status=%s\\n' "${{status}}"
                '''
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("status=0", result.stdout, msg=result.stderr)


if __name__ == "__main__":
    main()
