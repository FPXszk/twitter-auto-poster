# XClientTransaction ベストエフォート・フォールバック修正

## 問題

`configure_client_transaction_backend()` は `ImportError` のみでフォールバックする。
CI が `XClientTransaction==1.0.2` を常時インストールするため、本番は常に XClientTransaction パスを通るが、
1.0.2 の狭い ondemand/KEY_BYTE 正規表現では実行時失敗が起こり得る。

## 変更対象ファイル

| ファイル | 操作 |
|---|---|
| `scripts/lib/post_video.py` | 修正 |
| `tests/test_post_video.py` | 修正（テスト追加） |

## スコープ外

- README.md（動作変更なし）
- twikit_compat.py（既存ロジックをそのまま利用）
- CI ワークフロー YAML

## 実装ステップ

- [ ] **RED**: `tests/test_post_video.py` に回帰テスト2件追加
  - (A) `configure_client_transaction_backend` が非ImportError例外でフォールバックすること
  - (B) `_XClientTransactionAdapter.init()` 失敗時にフォールバックし、元の client_transaction を復元すること
- [ ] テスト実行 → 失敗を確認
- [ ] **GREEN**: `scripts/lib/post_video.py` を修正
  - `configure_client_transaction_backend()`: `except ImportError` → `except Exception`、元の CT を保存
  - `_XClientTransactionAdapter`: `_client` と `_original_client_transaction` を保持
  - `_XClientTransactionAdapter.init()`: try/except で失敗時に `patch_twikit_transaction()` + CT 復元 + 再送出
- [ ] テスト実行 → 全パスを確認
- [ ] **REFACTOR**: 不要な複雑化がないか確認

## テスト戦略

- TDD: RED → GREEN → REFACTOR
- 既存テスト32件がすべてパスすることを確認
- 新規テスト2件を追加

## 検証コマンド

```bash
python/.venv/bin/python -m unittest tests.test_post_video tests.test_twikit_compat -v
```

## リスク

- `_XClientTransactionAdapter.init()` のフォールバック後、現在のリクエストは例外で失敗する可能性あり（CT は復元済みなので後続リクエストは正常動作）
- 既存テストの `configure_client_transaction_backend` テストは全パラメータ指定のため、新パラメータ未指定でも動作する必要がある
