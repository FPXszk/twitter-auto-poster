# Documentation reference citation plan

## 問題と方針

`docs/DOCUMENTATION_SYSTEM.md` に、参考にした外部資料を `docs/references/design-ref-llms.md` へ記録する運用ルールを明記する。  
あわせて、今回のハーネスエンジニアリング関連の作業で実際に参照した外部資料を、`docs/references/design-ref-llms.md` の既存テンプレートに沿って追記する。

## 変更・削除・作成するファイル

- 変更予定: `docs/DOCUMENTATION_SYSTEM.md`
- 変更予定: `docs/references/design-ref-llms.md`
- 削除予定: なし

## 実施内容と影響範囲

- `docs/DOCUMENTATION_SYSTEM.md` に「外部資料を参考にした作業では、参照先を `docs/references/design-ref-llms.md` にテンプレートどおり追記する」という運用ルールを追加する
- 既存の `docs/references/design-ref-llms.md` のテンプレに沿って、今回参照した外部資料の URL・採用理由・活用内容を追記する
- 影響範囲はドキュメント運用ルールと参考文献集約のみで、コードや workflow の挙動は変更しない

## 今回追記する参考資料

- `Harness Engineeringとは何か`
  - URL: `https://x.com/shodaiiiiii/status/2037407745704362112?s=46`
  - 今回のハーネスエンジニアリング評価と改善方針の基準として利用した

## 実装ステップ

- [x] `docs/DOCUMENTATION_SYSTEM.md` に「参考にした外部資料は `docs/references/design-ref-llms.md` に集約する」運用ルールを追加する
- [x] `docs/references/design-ref-llms.md` に今回参照した資料をテンプレ通りに追記する
- [x] 差分と文言の整合性を確認する
