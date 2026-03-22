from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest import TestCase, main


class RetryHelpersTest(TestCase):
    root_dir = Path(__file__).resolve().parents[1]
    common_sh = root_dir / "scripts" / "lib" / "common.sh"

    def run_bash(self, script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-lc", script],
            cwd=self.root_dir,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_retry_command_preserves_final_failure_status(self) -> None:
        result = self.run_bash(
            f'''
            source "{self.common_sh}"
            always_fail() {{
              return 7
            }}
            set +e
            retry_command 2 0 always_fail
            status="$?"
            printf '%s\\n' "${{status}}"
            '''
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip().splitlines()[-1], "7")

    def test_retry_to_file_preserves_failure_status_and_removes_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "post.json"
            result = self.run_bash(
                f'''
                source "{self.common_sh}"
                always_fail() {{
                  printf '%s' 'partial'
                  return 9
                }}
                set +e
                retry_to_file "{output_path}" 2 0 always_fail
                status="$?"
                printf 'status=%s\\n' "${{status}}"
                if [[ -f "{output_path}" ]]; then
                  printf 'exists=yes\\n'
                else
                  printf 'exists=no\\n'
                fi
                '''
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("status=9", result.stdout)
        self.assertIn("exists=no", result.stdout)


if __name__ == "__main__":
    main()
