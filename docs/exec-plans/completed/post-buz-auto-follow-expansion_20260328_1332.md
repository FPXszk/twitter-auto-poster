# post_buz アカウント追加 / auto_follow 拡張 計画

## 概要

`post_buz` に指定された 6 アカウントを追加し、`auto_follow` を「新規フォロー + フォローバック」の合計で 10〜15 件程度動くように拡張する。既存の `auto_unfollow` ロジックは維持し、state 管理と summary を壊さない範囲で追随させる。

## 変更・作成・確認対象

- 変更ファイル: `config/sources.yaml`
  - `buz` ソースへ以下 6 アカウントを追加する
  - `sakenmilove`
  - `bovccgdlap95845`
  - `fuwaraidou_2525`
  - `yeskiri`
  - `romi_hoshino`
  - `aigare01`
- 変更ファイル: `python/auto_follow.py`
  - 1 回の follow 件数を `10〜15` に引き上げる
  - 自分のフォロワーを優先的に followback 候補として取り込み、新規フォロー候補と合算する
  - follow state / summary に follow 種別が追える形を必要最小限で追加する
- 変更ファイル: `tests/test_auto_follow.py`
  - followback 候補の扱い、合計件数、state 記録の RED/GREEN テストを追加する
- 変更ファイル: `README.md`
  - `post_buz` の対象アカウント数と `auto_follow` の挙動説明を現実に合わせて更新する
- 変更ファイル: `docs/design-docs/STRATEGY.md`
  - `post_buz` のローテーション説明と `auto_follow` の件数説明を最新仕様へ合わせる
- 変更候補: `.github/workflows/auto_follow.yml`
  - summary 表示の追随が必要な場合のみ最小変更で更新する
- 確認対象: `python/auto_unfollow.py`, `tests/test_auto_unfollow.py`
  - 既存の解除条件を壊していないか確認する（基本は無変更）
- 新規作成なし / 削除なし

## 実装方針

- `post_buz` 側は既存の `big / small` 2 ソース構成を踏襲し、各アカウントに対して同じ閾値・`score_boost` を追加する
- `auto_follow` はテストしやすいように、候補収集と follow 実行の責務を少し整理する
- 合計 follow 件数は毎回 `10〜15` 件のランダムに変更する
- followback は「自分をフォローしているが、まだこちらがフォローしていない相手」を優先候補にし、先に取り込み、残枠を新規フォローで埋める
- 新規フォローはこれまでどおり `@tkzwgrs` のフォロワーから既存の日本語 / 株関連 / 認証済み条件で選ぶ
- followback 候補はユーザー要望を優先し、`missing_username` / `already_following` / `already_recorded` のみを除外条件として扱い、既存の認証済み・日本語・株関連フィルタは適用しない前提で進める
- `auto_unfollow` は現状のまま維持し、フォローバック済み相手を解除しない既存仕様に依存する
- summary は followback 件数と新規 follow 件数の内訳が分かる形を検討する
- 既存の `state/buz-robin.txt` が旧ローテーション状態を持っていても、追加後のアカウント群で round-robin が継続できることを確認する

## 影響範囲

- `post_buz` の候補母数と round-robin 対象アカウント数が増える
- `auto_follow` は 1 日あたりの follow 件数が増え、follow 元の母集団が 2 系統（followback / 新規）になる
- `config/follow_state.json` の entry に補助フィールドを足す場合、既存 state を壊さない後方互換が必要
- README の説明が古くなるため、関連記述を合わせて更新する
- `docs/design-docs/STRATEGY.md` の固定値記述も古くなるため更新する

## 実装ステップ

- [ ] 1. `tests/test_auto_follow.py` に followback 優先・合計 10〜15 件・state 記録の RED テストを追加する
- [ ] 2. `python/auto_follow.py` に followback 候補収集ロジックを追加し、新規フォロー候補と合算して 10〜15 件を目標に follow できるようにする
- [ ] 3. 必要最小限の state / summary 拡張を行い、followback / 新規 follow の内訳が追えるようにする
- [ ] 4. `config/sources.yaml` に 6 アカウント分の `buz` ソース（big / small）を追加する
- [ ] 5. `README.md`・`docs/design-docs/STRATEGY.md` と必要なら `.github/workflows/auto_follow.yml` の表示を更新する
- [ ] 6. `python -m unittest tests.test_auto_follow tests.test_auto_unfollow`、`python -m unittest discover -s tests`、`python -m py_compile python/auto_follow.py python/auto_unfollow.py`、`.github/workflows/auto_follow.yml` と `config/sources.yaml` の YAML 検証、`git diff --check`、既存 `buz-robin` state を前提にした round-robin の継続確認で検証する

## 注意点

- followback を完全無条件にしすぎるとスパムを拾いやすいので、少なくとも `missing_username` / `already_following` / `already_recorded` は必ず弾く
- 既存 `auto_unfollow` は「7 日経過かつ未フォローバック」を解除する前提なので、state の `followed_at` / `unfollowed` を壊さない
- `post_buz` の README 記述は現在「6 ソース」となっているため、追加後の実態に合わせて修正する
- follow 件数が最大 `15` へ増えるため、過度に連続実行されないよう sleep / summary / rate limit への影響を意識して実装する
- 実装は RED → GREEN → REFACTOR の順で進める
