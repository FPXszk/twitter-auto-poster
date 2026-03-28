# DOCUMENTATION_SYSTEM

## この文書の役割

- この文書は、この repo で「どの順番で文書を読むか」「どの文書が何の正本か」「どう鮮度を維持するか」を定義する入口です。
- まずはここに従って必要な文書へ進みます。

## 最初に読む順番

1. `.github/copilot-instructions.md`
2. `README.md`
3. `docs/DOCUMENTATION_SYSTEM.md`
4. 必要な個別文書

## 目的別の参照先

### 戦略を知りたい

- `docs/design-docs/STRATEGY.md`

### 設定ファイルを変えたい

- `docs/SCHEMA.md`
- 必要に応じて `config/accounts.yaml`
- 必要に応じて `config/sources.yaml`

### 運用したい / 障害対応したい

- `docs/RUNBOOK.md`

### セキュリティ方針を見たい

- `docs/SECURITY.md`

### 参考にした資料を見たい

- `docs/references/design-ref-llms.md`

### 過去の実装判断を見たい

- `docs/exec-plans/completed/`

### 今回の作業計画を見たい

- `docs/exec-plans/active/`

### セッションの working memory を見たい

- `docs/working-memory/session-logs/`

ただし session logs は working memory 用であり、仕様の正本ではありません。

## この repo における正本

- ルールの正本: `.github/copilot-instructions.md`
- プロジェクト概要の正本: `README.md`
- 設定スキーマの正本: `docs/SCHEMA.md` と `scripts/lib/common.sh`
- 運用手順の正本: `docs/RUNBOOK.md`
- 戦略の正本: `docs/design-docs/STRATEGY.md`
- 実装履歴の正本: `docs/exec-plans/completed/`

## 鮮度維持の仕組み

### 基本ルール

- コード変更と同じタイミングで、影響を受ける文書も更新する
- 「あとでまとめて直す」は原則禁止
- 実装計画には、必要な doc 更新を明示する
- 外部資料や設計参考文献を使って判断した場合は、`docs/references/design-ref-llms.md` に既存テンプレートどおり記録する

### 文書ごとの更新トリガー

- `README.md`: 起動方法、主要ディレクトリ、主要 workflow が変わったとき
- `docs/SCHEMA.md`: `config/*.yaml` のキーや意味が変わったとき
- `docs/RUNBOOK.md`: preview/live 手順、復旧手順、state 操作が変わったとき
- `docs/design-docs/STRATEGY.md`: 投稿戦略、KPI、収益化前提が変わったとき
- `docs/DOCUMENTATION_SYSTEM.md`: 文書体系や参照順が変わったとき
- `docs/references/design-ref-llms.md`: 参考にした外部資料を新しく使ったとき、または採用 / 不採用判断が増えたとき

### review 時の確認項目

- 実装したのに説明文が古いままになっていないか
- 参照リンクが実在するか
- 正本の場所が曖昧になっていないか

## session logs の扱い

- `docs/working-memory/session-logs/` は best-effort な自動要約の保存先です
- Git 追跡対象ではありません
- `/exit` や通常終了では保存できるようにし、完全強制終了は保証しません
- 内容は working memory であり、正本ではありません
