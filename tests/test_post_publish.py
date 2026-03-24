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

    def test_publish_selected_post_falls_back_to_thread_after_url_single_post_186(self) -> None:
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

                post_calls=0

                build_thread_plan_json() {{
                  local post_text="$1"
                  local source_url="$2"
                  local single_post_max_length="$3"
                  local stdout_path="$4"
                  local stderr_path="$5"

                  if [[ "${{single_post_max_length}}" == "4000" && -z "${{source_url}}" ]]; then
                    printf '%s' '["quote-single-post"]' > "${{stdout_path}}"
                    : > "${{stderr_path}}"
                    return 0
                  fi
                  if [[ "${{single_post_max_length}}" == "4000" && -n "${{source_url}}" ]]; then
                    printf '%s' '["url-single-post"]' > "${{stdout_path}}"
                    : > "${{stderr_path}}"
                    return 0
                  fi
                  if [[ "${{single_post_max_length}}" == "280" ]]; then
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
                  printf '300\\n'
                }}

                execute_twitter_post() {{
                  local category="$1"
                  local post_text="$2"
                  local reply_to_id="${{3:-}}"
                  local quote_tweet_id="${{4:-}}"
                  local output_file="$5"
                  local stderr_file="$6"

                  post_calls=$((post_calls + 1))
                  if (( post_calls == 1 )); then
                    printf '%s' '{{"ok":false}}' > "${{output_file}}"
                    printf '%s' 'Twitter API returned errors: Authorization: Tweet needs to be a bit shorter. (186)' > "${{stderr_file}}"
                    return 1
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

            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["data"]["action"], "post_thread_quote")
            self.assertEqual(payload["data"]["tweet_count"], 2)


if __name__ == "__main__":
    main()
