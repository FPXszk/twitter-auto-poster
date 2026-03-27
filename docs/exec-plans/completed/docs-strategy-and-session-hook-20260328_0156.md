# ドキュメント整備 + セッション要約 hook 実装計画

## 目的

他プロジェクト由来のドキュメントを、`twitter-auto-poster` の実態に合わせて整理する。

今回の主目的は次の 4 点です。

1. `docs/design-docs/STRATEGY.md` を、X 収益化を目指す現実的な戦略書へ更新する
2. `docs/SCHEMA.md` と `docs/RUNBOOK.md` の役割と現状適合性を確認し、必要なら現行仕様へ合わせて更新する
3. `docs/DOCUMENTATION_SYSTEM.md` を、`.github/copilot-instructions.md -> README.md -> docs/DOCUMENTATION_SYSTEM.md -> 必要な個別文書` の参照順に合わせて作り直す
4. `docs/working-memory/session-logs/` に Copilot セッション要約を自動保存する best-effort な仕組みを設計・実装する

## 現状整理

### 既存ドキュメントの所見

- `docs/design-docs/STRATEGY.md`
  - 収益化ラインや一般論はある
  - ただし投資/ニュース自動投稿プロジェクトとしての具体的戦略、KPI、投稿タイプ、検証ループ、リスク管理が弱い
- `docs/SCHEMA.md`
  - 役割は `config/*.yaml` のスキーマ説明で妥当
  - ただし `author_virality`、`min_author_followers`、`max_author_followers` など最新項目を反映できていない
  - 例の構造や説明粒度にも修正余地がある
- `docs/RUNBOOK.md`
  - 役割は運用手順書で妥当
  - ただし最新の候補選定ロジック・単独投稿化・画像再利用・検証フローまでは十分追随していない可能性がある
- `docs/DOCUMENTATION_SYSTEM.md`
  - 参照先に `ARCHITECTURE.md`、`COMMAND.md`、`product-specs/`、`decision-log/` など現 repo に無い/未整備の文書が残っている
  - 現在の repo に対する入口文書としては不整合

### hook 実現性の前提

- 取得できた Copilot CLI 公式情報では、終了時に任意 hook を実行する組み込み機能は確認できていない
- したがって第一候補は `devinit.sh` から起動する Copilot コマンドをラップし、終了時に別プロセスで要約保存を行う方式
- `ctrl+d` や `/exit` のような通常終了は拾える見込みが高い
- `SIGKILL` やホスト障害のような完全強制終了は 100% 捕捉できないため、best-effort 前提で設計する

## 変更対象ファイル

- `docs/design-docs/STRATEGY.md`
- `docs/SCHEMA.md`
- `docs/RUNBOOK.md`
- `docs/DOCUMENTATION_SYSTEM.md`
- `README.md`（必要なら参照順の入口だけ最小更新）
- `devinit.sh`
- `justfile`（必要ならログ/確認用コマンド追加）
- `docs/working-memory/session-logs/` 配下の初期ファイル
- 新規 hook / wrapper スクリプト
  - 例: `scripts/dev/copilot-session-wrapper.sh`
  - 例: `scripts/dev/write-session-summary.sh`

## 実装方針

### 1. STRATEGY.md の再構成

- 既存の「500万インプレ」などの原案は活かす
- ただし本プロジェクトに合わせて以下を追加する
  - 収益化前提条件と達成ライン
  - 対象アカウントのポジショニング
  - コンテンツ柱（速報、投資示唆、要約、定時サマリー）
  - 短期/中期 KPI
  - 自動投稿と手動介入の分担
  - 品質 guardrail（誤情報、過度な転載、スパム化の防止）
  - 検証サイクル（候補品質、CTR/返信率/保存率相当の proxy 指標）

### 2. SCHEMA.md / RUNBOOK.md の適合性更新

- `SCHEMA.md`
  - 「何のドキュメントか」を明示
  - `sources.yaml` / `accounts.yaml` の現行キーをコード実装準拠で反映
  - state file / media selection / summary provider / score/filter の最新項目を補完
- `RUNBOOK.md`
  - 「何のドキュメントか」を明示
  - 直近の invest 投稿フロー、preview/live、トラブルシュート、state 操作、投稿候補調査を現行仕様へ寄せる

### 3. DOCUMENTATION_SYSTEM.md の再設計

- 冒頭に「最初に読む順番」を明記
  1. `.github/copilot-instructions.md`
  2. `README.md`
  3. `docs/DOCUMENTATION_SYSTEM.md`
  4. 個別ドキュメント
- その上で、目的別の参照導線を定義する
  - 運用を見るとき: `RUNBOOK.md`
  - 設定を変えるとき: `SCHEMA.md`
  - 戦略を考えるとき: `design-docs/STRATEGY.md`
  - 実装履歴を見るとき: `docs/exec-plans/completed/`
- 実在しない索引へのリンクは削除し、今の repo にある文書だけを基準にする
- ドキュメント鮮度維持の仕組みもここに定義する

### 4. ドキュメント鮮度維持の仕組み

- 軽量で継続しやすい運用に寄せる
- 候補:
  - 文書に `Last reviewed` / `Source of truth` / `Update trigger` を置く
  - 実装変更時に更新対象 doc を列挙するチェックリストを exec plan に含める
  - README と DOCUMENTATION_SYSTEM に「どの変更が入ったらどの doc を更新するか」を明記する
  - 将来的には doc lint / link check / stale check の追加余地を残す

### 5. session-logs 自動要約 hook

- 第一候補:
  - `devinit.sh` から直接 `copilot` を起動せず、wrapper script を起動する
  - wrapper が Copilot 終了を検知したら、別プロセスで最新セッションを要約し `docs/working-memory/session-logs/` に保存する
- 期待する保存内容:
  - セッション日時
  - 目的
  - 変更ファイル
  - 実施内容
  - 未完了事項
  - 次回の着手点
- 制約:
  - `SIGKILL` やホストクラッシュは完全保証不可
  - まずは `/exit`、`ctrl+d`、通常終了での捕捉を優先
- 実装前に確認する技術点:
  - `copilot --continue` / `--resume` で直前会話要約を別プロセスから取得できるか
  - `tmux send-keys` 経由で起動した wrapper が Copilot 終了を trap できるか
  - session summary を repo 配下へ安全に書けるか
  - 無限ループ（要約用 copilot 起動がさらに hook される）をどう防ぐか
  - `session-logs` を Git 管理するか `.gitignore` 管理にするか

## 影響範囲

- ドキュメント入口と運用導線が変わる
- 開発セッション起動方法に wrapper が挟まる可能性がある
- `devinit.sh` / `just dev` の起動体験が少し変わる
- session logs は best-effort 自動記録になる

## 実装ステップ

- [ ] 現在の doc 構成と実装コードを突き合わせ、各文書の正本範囲を確定する
- [ ] 技術スパイク: `copilot --continue` / wrapper trap / 出力先の成立性を最小検証する
- [ ] `STRATEGY.md` の章立てを再設計し、現実的な収益化戦略へ書き換える
- [ ] `SCHEMA.md` を現行 config 実装準拠に更新する
- [ ] `RUNBOOK.md` を現行運用手順準拠に更新する
- [ ] `DOCUMENTATION_SYSTEM.md` をこの repo 用の参照順・索引・更新ルールへ全面更新する
- [ ] ドキュメント鮮度維持ルールを各入口文書へ反映する
- [ ] RED: session summary hook の想定動作をテストまたは検証手順として先に定義する
- [ ] GREEN: Copilot 起動 wrapper / session summary 保存処理を実装する
- [ ] REFACTOR: `devinit.sh` / `justfile` / working-memory 配下の整合を取る
- [ ] `session-logs` の Git 管理方針に応じて `.gitignore` か `.gitkeep` を整備する
- [ ] 検証: docs の参照導線、wrapper の通常終了、summary 出力先を確認する

## 懸念点

- 終了 hook は best-effort 止まりであり、すべての異常終了を完全に取ることはできない
- 要約を別 Copilot プロセスで行う場合、再帰起動や権限確認の設計が必要
- repo 配下に session log を自動で積むと差分が増えやすいため、コミット対象から外す運用も検討余地がある

## 期待成果物

- この repo に適合した `STRATEGY.md`
- 現行仕様に追従した `SCHEMA.md`
- 現行運用に追従した `RUNBOOK.md`
- 実在文書だけを辿る `DOCUMENTATION_SYSTEM.md`
- `docs/working-memory/session-logs/` に自動要約を出力する試作 hook
