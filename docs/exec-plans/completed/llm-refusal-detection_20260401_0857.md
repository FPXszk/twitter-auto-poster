# post_buz 調査と再発防止の実装計画

## 調査結果サマリ

- 最新の `post_buz` 実行は run `23824500768` で、`schedule` 起動・`success` 終了
- この run で実際に投稿された本文は `I'm sorry, but I cannot assist with that request.` だった
- その本文は artifact `tmp/runs/candidate-buz.*` の `post_text` / `selected.summary_text` に残っており、要約プロバイダは `copilot_cli`、モデルは `gpt-5-mini`
- 対象ソースツイートは `https://x.com/pam99ham/status/2038253848922574941`、`selected.id` も `2038253848922574941`
- `config/accounts.yaml` の `buz` 設定は `source_reference_mode: "none"` なので、この run は「引用投稿しようとして失敗」ではなく、通常ポストとして拒否文をそのまま投稿している
- `.github/workflows/post_buz.yml` の cron は `0 * * * *` だが、直近 run の `created_at` は `23:37 / 22:38 / 21:43 / 20:49 / 19:07 / 17:03 / 15:06 ...` と大きく遅延・欠落しており、「毎時ちょうど」には動いていない
- `docs/exec-plans/active/` は確認時点でこの計画以外に進行中 plan がなく、競合中の実装計画は見当たらない

## 問題の整理

1. **拒否応答の投稿事故**
   - `scripts/lib/copilot_summary.py` は空でない stdout を有効要約として扱う
   - `scripts/lib/post_evaluator.py` は拒否文を弾くルールを持たない
   - そのため `scripts/fetch_and_post.sh` が拒否応答を正常候補として採用し、投稿まで進む

2. **毎時実行の信頼性不足**
   - workflow 定義は毎時だが、GitHub Actions の `schedule` はベストエフォートで遅延する
   - 現状は「遅れてもその run がそのまま投稿する」だけで、1時間に1回の投稿をアプリ側で担保する仕組みがない

## スコープ

### スコープ内

- 最新 run の事故原因に直接つながる拒否応答の検出・拒否
- 拒否検出時に `fetch_and_post.sh` の既存フォールバックで次候補へ進める状態の実現
- workflow summary / artifact から原因追跡しやすい診断表示の改善
- GitHub schedule 遅延を前提にしつつ、**実運用として 1時間に1回へ近づける**ための workflow 側対策
- 既存 `unittest` による RED→GREEN→REFACTOR

### スコープ外

- Copilot 側の拒否ポリシーそのものの変更
- 投稿候補スコアリングやアカウント選定ロジックの再設計
- `buz` 以外のアカウント設定変更
- 外部サービスへの移行や Actions 以外のスケジューラ導入

## 変更対象ファイル

| ファイル | 操作 | 概要 |
|---|---|---|
| `scripts/lib/post_evaluator.py` | 変更 | LLM拒否文を `llm_refusal` として弾く |
| `tests/test_post_evaluator.py` | 変更 | 拒否文・誤検出防止のテスト追加 |
| `scripts/lib/workflow_summary.py` | 変更 | run summary に拒否検出・provider・source tweet を明確表示 |
| `tests/test_workflow_summary.py` | 変更 | summary 表示の回帰テスト追加 |
| `.github/workflows/post_buz.yml` | 変更 | schedule の補強と hourly ガード導入 |
| `scripts/lib/hourly_post_guard.py` | 作成 | 「そのJST時間帯で既に live 投稿済みか」を判定する小さな helper |
| `tests/test_hourly_post_guard.py` | 作成 | hourly ガードの境界テスト |

`scripts/fetch_and_post.sh` は拒否応答対策では既存フォールバックをそのまま使う前提で、Phase 3 の `hourly_skip` 理由記録も workflow 側と helper / `workflow_summary.py` 側で完結させる。

## 実装方針

### Phase 1: 拒否応答を正常要約として通さない

#### RED

- [ ] `tests/test_post_evaluator.py` に、本番拒否文 `I'm sorry, but I cannot assist with that request.` を `llm_refusal` で reject するテストを追加
- [ ] 大文字小文字差分、近い英語拒否文、文中埋め込み拒否文を reject するテストを追加
- [ ] 通常の日本語要約や、単なる謝罪を含む正常文を誤検出しないテストを追加

#### GREEN

- [ ] `scripts/lib/post_evaluator.py` に拒否定型文の検出ヘルパーを追加
- [ ] `evaluate_summary()` に `llm_refusal` reason を追加
- [ ] 既存の `fetch_and_post.sh` フォールバック経路で次候補へ進める前提を崩さない

#### REFACTOR

- [ ] パターン定義を読みやすく集約し、過剰な重複を整理
- [ ] テスト名と reason 名を今後の summary 系 validation に揃える

### Phase 2: ワークフロー診断を「誰が何を返したか」まで見えるようにする

#### RED

- [ ] `tests/test_workflow_summary.py` に、`llm_refusal` が含まれる payload で警告行が出るテストを追加
- [ ] source tweet ID / source URL / provider / model が summary に出ることを確認するテストを追加

#### GREEN

- [ ] `scripts/lib/workflow_summary.py` に拒否検出専用の警告行を追加
- [ ] source tweet ID / source URL / provider / model の表示が、candidate artifact を開かなくても summary で追える状態にする

#### REFACTOR

- [ ] 既存の alert / diagnostics 表示と重複しない最小表示に整理

### Phase 3: 「毎時1回」を GitHub 遅延込みで担保しやすくする

#### RED

- [ ] `tests/test_hourly_post_guard.py` を追加し、同一JST時間帯では2回目を live 投稿しないことを確認
- [ ] 時間帯が切り替わったら次の投稿を許可するテストを追加
- [ ] dry-run は hourly ガード対象外として、live 投稿だけを制御するテストを追加
- [ ] state ファイルが壊れている場合は live 投稿を止めて警告を出す fail-closed 動作のテストを追加

#### GREEN

- [ ] `.github/workflows/post_buz.yml` の schedule を毎時1回より細かくする案を適用する（第一候補: 15分ごと）
- [ ] その代わり workflow / `scripts/lib/hourly_post_guard.py` で「JSTの同一時間帯に live 投稿は1回まで」のガードを追加する
- [ ] 既存 `tmp/state` キャッシュを使い、hourly state を保存・復元する
- [ ] dry-run は hourly state を消費しない仕様で固定する
- [ ] state が unreadable な live run は fail-closed でスキップし、workflow から `tmp/runs/hourly-guard-buz.json` に理由を書き出す
- [ ] `scripts/lib/workflow_summary.py` で `hourly-guard-buz.json` を読み、skip 理由を run summary に表示する

#### REFACTOR

- [ ] posting window と hourly ガードの責務を分け、複雑な inline Python を避ける
- [ ] summary / artifact に `hourly_skip` 理由を残す必要があるか確認し、必要なら最小追加

### Phase 4: 全体検証

#### RED/GREEN 最終確認

- [ ] 変更対象の個別テストを先に実行
- [ ] その後 `python -m unittest discover -s tests` を実行
- [ ] `python -m coverage run -m unittest discover -s tests` と `python -m coverage report --fail-under=80` で 80% 以上を確認する
- [ ] `python -m py_compile` と workflow YAML の妥当性確認も行う

## テスト戦略

- **ユニットテスト**
  - `tests/test_post_evaluator.py`
  - `tests/test_workflow_summary.py`
  - `tests/test_hourly_post_guard.py`
- **既存回帰**
  - `tests/test_post_summary.py`
  - `tests/test_copilot_summary.py`
- **フルスイート**
  - `python -m unittest discover -s tests`

RED→GREEN→REFACTOR の順で、まず拒否応答の再現テストを追加し、その後 summary 表示、最後に hourly ガードを入れる。

## 検証コマンド

```bash
python -m unittest tests.test_post_evaluator -v
python -m unittest tests.test_workflow_summary -v
python -m unittest tests.test_hourly_post_guard -v
python -m unittest tests.test_post_summary tests.test_copilot_summary -v
python -m unittest discover -s tests -v
python -m coverage run -m unittest discover -s tests
python -m coverage report --fail-under=80
python -m py_compile scripts/lib/post_evaluator.py scripts/lib/workflow_summary.py scripts/lib/hourly_post_guard.py
bash -n scripts/fetch_and_post.sh scripts/lib/common.sh
python - <<'PY'
from pathlib import Path
import yaml
for path in [Path('config/accounts.yaml'), Path('.github/workflows/post_buz.yml')]:
    yaml.safe_load(path.read_text(encoding='utf-8'))
    print(f"OK {path}")
PY
```

## リスクと前提

| 項目 | 内容 |
|---|---|
| 拒否文の揺れ | 英語定型文ベースで始める。今後の揺れはテスト追加で拡張する |
| 誤検出 | 日本語の通常謝罪文を reject しないテストを必ず入れる |
| schedule 遅延 | GitHub 側の遅延は消せないため、頻度を上げてアプリ側で hourly を制御する |
| state 破損/未復元 | live run は fail-closed で停止し、summary / artifact に理由を残して重複投稿を防ぐ |

## 実装時の判断ポイント

- hourly ガードは **dry-run を除外** して live 投稿だけ制御する
- refusal 検出はまず `post_evaluator.py` で行い、`fetch_and_post.sh` の既存フォールバックを活かす
- `copilot_summary.py` での早期 reject は今回の第一段では行わず、必要なら次段で検討する
- hourly guard 用 state が壊れている live run は **fail-closed** で止め、重複投稿より未投稿を優先する
- hourly guard の責務は `scripts/lib/hourly_post_guard.py` が判定、`.github/workflows/post_buz.yml` が state 保存と `hourly-guard-buz.json` 出力、`scripts/lib/workflow_summary.py` が表示を担う
