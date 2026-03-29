from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class PostVideoEntrypointTest(unittest.TestCase):
    def test_default_client_factory_loads_twikit_compat_without_scripts_lib_on_syspath(self) -> None:
        entrypoint_path = Path(__file__).resolve().parents[1] / "python" / "post_video.py"
        scripts_lib_path = str((Path(__file__).resolve().parents[1] / "scripts" / "lib").resolve())

        transaction_module = types.ModuleType("twikit.x_client_transaction.transaction")

        class FakeClientTransaction:
            async def get_indices(self, home_page_response, session, headers):
                raise NotImplementedError

        transaction_module.ClientTransaction = FakeClientTransaction

        client_package = types.ModuleType("twikit.x_client_transaction")
        client_package.transaction = transaction_module

        twikit_module = types.ModuleType("twikit")

        class FakeClient:
            def __init__(self, language: str) -> None:
                self.language = language

        twikit_module.Client = FakeClient
        twikit_module.x_client_transaction = client_package

        fake_modules = {
            "twikit": twikit_module,
            "twikit.x_client_transaction": client_package,
            "twikit.x_client_transaction.transaction": transaction_module,
        }

        original_sys_path = list(sys.path)
        filtered_sys_path = [
            path
            for path in original_sys_path
            if str(Path(path).resolve()) != scripts_lib_path
        ]

        spec = importlib.util.spec_from_file_location("repo_post_video_entrypoint_test", entrypoint_path)
        if spec is None or spec.loader is None:
            self.fail(f"failed to load spec for {entrypoint_path}")
        module = importlib.util.module_from_spec(spec)

        with patch.dict(sys.modules, fake_modules, clear=False):
            with patch.object(sys, "path", filtered_sys_path):
                spec.loader.exec_module(module)
                client = module.helper_module._default_client_factory()

        self.assertIsInstance(client, FakeClient)
        self.assertEqual(client.language, "en-US")


if __name__ == "__main__":
    unittest.main()
