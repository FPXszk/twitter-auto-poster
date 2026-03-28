# 改善提案 issue 一本化計画

## 概要

既存の open issue には、改善提案として作られたものが複数残っている。内容が重複・分散しているため、現行プロジェクト方針に沿う項目だけを 1 本の統合 issue にまとめ、元 issue は close する。

## 対象 issue

- #27 Improve auto_like pacing and observability
- #28 Improve Copilot summary pipeline resilience
- #29 Improve account-level summary controls and posting fallback
- #30 refactor: standardize operational scripts and dry-run ergonomics
- #31 feat: tighten post collection logic for topical relevance and anti-official bias
- #32 docs: formalize config defaults and validation rules
- #33 chore: improve workflow observability and session-log operations
- #34 feat: アカウント単位のラウンドロビン選択に対応する
- #35 feat: バズ閾値を動的に調整する設定を追加する
- #36 feat: ソースアカウントを accounts.yaml から設定できるようにする
- #37 feat: auto_follow のフォロー選定条件をバズ特化に見直す
- #38 Improve post_buz script diagnostics
- #39 Improve buz collection resilience
- #40 Improve buz config validation
- #41 Improve post_buz workflow observability

## 統合方針

- 新しい統合 issue を 1 本作成する
- 統合 issue には、現行プロジェクトに沿う改善項目だけを以下のような大項目で整理する
  - 投稿/収集パイプラインの信頼性と observability
  - 設定ファイルと source 管理の改善
  - 候補品質・選定ロジック・自動エンゲージメント改善
- 既存 issue は、新 issue への統合コメントを残して close する
- すでに一部対応済みの項目（例: auto_like pacing の一部）は「一部解消済み・残りは統合 issue で管理」と明記する
- 現プロジェクトに合わない detail は統合 issue に移さず、そのまま close して破棄する

## 判断基準

- **統合**: 現在の運用方針・コード構成にまだ合っていて、今後 backlog として残す価値があるもの
- **一部解消済み**: 背景はまだ有効だが、 issue の一部はすでに実装で吸収されているもの
- **破棄**: 現在の優先度や方針から外れていて、統合 issue に残すとノイズが増えるもの

## close コメント方針

- **統合**: 「統合 issue #<new> に集約するため close」
- **一部解消済み**: 「一部は実装済み、残りは統合 issue #<new> で管理するため close」
- **破棄**: 「現行方針の統合 backlog には移さず close」

必要に応じて、1 行だけ理由を足す。コメントは短く揃える。

## 実装ステップ

- [ ] 1. issue #27-#41 を内容ごとに読み直し、統合 / 一部解消済み / 破棄 に分類する
- [ ] 2. 分類結果を反映した統合 issue 本文を作成する
- [ ] 3. `gh issue create` で統合 issue を作成する
- [ ] 4. 既存 issue #27-#41 を分類に応じたコメント付きで close する
- [ ] 5. 最終的に open issue が意図どおり 1 本化されたことを確認する

## 注意点

- 既存 issue の文面は消さず、close コメントに統合先 issue 番号を明記する
- 「不採用にした理由」が必要なものは close コメントで短く触れる
- issue 操作は `gh` CLI で行う
- 統合後に分割が必要と判明した場合は reopen を検討できるよう、close コメントは必ず残す
