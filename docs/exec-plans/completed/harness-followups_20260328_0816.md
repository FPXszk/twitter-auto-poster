# Harness follow-up improvements plan

## 問題と方針

CI 品質ゲート追加に続き、残る 3 つの改善項目である「要約 evaluator」「失敗通知改善」「フィードバックループ」を実装する。  
変更は `fetch_and_post` の候補生成・投稿・summary 出力の流れに沿ってまとめ、既存の preview/live フローを壊さずに安全装置と学習ループを足す。

## 変更・削除・作成するファイル

- 作成予定: `scripts/lib/post_evaluator.py`
- 作成予定: `scripts/lib/post_feedback.py`
- 変更予定: `scripts/fetch_and_post.sh`
- 変更予定: `scripts/lib/workflow_summary.py`
- 変更予定: `tests/test_workflow_summary.py`
- 作成予定: `tests/test_post_evaluator.py`
- 作成予定: `tests/test_post_feedback.py`
- 変更予定: `README.md`
- 変更予定: `docs/RUNBOOK.md`
- 削除予定: なし

## 実施内容と影響範囲

- 要約生成直後に evaluator を通し、空文字・長さ超過・不要リンク・重複元文近すぎなどを理由付きで reject できるようにする
- candidate payload と workflow summary に alert セクションを追加し、summary 失敗・publish 失敗・evaluator reject を目立つ形で出す
- 投稿成功時に `tmp/state/<category>-feedback-history.jsonl` へ投稿履歴を保存し、`fetch_and_post.sh` の投稿成功直後に履歴更新する
- 次回実行時には同じ履歴ファイルから最近の投稿実績を読み、source 単位の feedback boost を計算してスコアへ戻す
- 影響範囲は `fetch_and_post` 系カテゴリの選定と observability で、auto_like / auto_follow など他系統には直接手を入れない

## 実装方針

1. **要約 evaluator**
   - `post_evaluator.py` に純粋関数で評価ロジックを実装し、テストしやすくする
   - `fetch_and_post.sh` の要約生成後に評価し、reject された候補は理由を diagnostics / alerts に記録して次候補へ進める
2. **失敗通知改善**
   - `workflow_summary.py` に alerts / evaluator / feedback 状況の描画を追加する
   - candidate payload に alert 用の構造化情報を載せる
3. **フィードバックループ**
   - `post_feedback.py` で履歴読込・履歴更新・source boost 算出を実装する
   - `fetch_and_post.sh` で `publish_selected_post` 成功後に履歴更新し、候補スコア計算時に feedback boost を加算する

## 実装ステップ

- [x] 要約 evaluator とそのテストを RED -> GREEN で追加する
- [x] `fetch_and_post.sh` に evaluator 判定と diagnostics / alerts を組み込む
- [x] feedback 履歴 helper とそのテストを RED -> GREEN で追加する
- [x] `fetch_and_post.sh` に feedback boost の読込・履歴更新を組み込む
- [x] `workflow_summary.py` と関連テストを更新して alerts を見える化する
- [x] README / RUNBOOK を更新する
- [x] 既存検証コマンドと関連テストで変更後確認を行う
