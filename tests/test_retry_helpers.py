from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest import TestCase, main


class RetryHelpersTest(TestCase):
    root_dir = Path(__file__).resolve().parents[1]
    common_sh = root_dir / "scripts" / "lib" / "common.sh"

    @staticmethod
    def bash_executable() -> str:
        for candidate in (
            Path("C:/Program Files/Git/bin/bash.exe"),
            Path("C:/Program Files/Git/usr/bin/bash.exe"),
        ):
            if candidate.exists():
                return str(candidate)
        return shutil.which("bash") or "bash"

    @staticmethod
    def bash_path(path: str | Path) -> str:
        resolved = Path(path).resolve()
        if os.name != "nt":
            return str(resolved)
        bash = RetryHelpersTest.bash_executable().replace("\\", "/").lower()
        drive = resolved.drive.rstrip(":").lower()
        tail = resolved.as_posix()[3:]
        if bash.endswith("/windows/system32/bash.exe"):
            return f"/mnt/{drive}/{tail}"
        return f"/{drive}/{tail}"

    def run_bash(self, script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.bash_executable(), "-lc", script],
            cwd=self.root_dir,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_retry_command_preserves_final_failure_status(self) -> None:
        result = self.run_bash(
            f'''
            source "{self.bash_path(self.common_sh)}"
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
            output_bash = self.bash_path(output_path)
            result = self.run_bash(
                f'''
                source "{self.bash_path(self.common_sh)}"
                always_fail() {{
                  printf '%s' 'partial'
                  return 9
                }}
                set +e
                retry_to_file "{output_bash}" 2 0 always_fail
                status="$?"
                printf 'status=%s\\n' "${{status}}"
                if [[ -f "{output_bash}" ]]; then
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
