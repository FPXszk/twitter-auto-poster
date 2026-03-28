# auto_like 低いいいね数・新しさ優先化 計画

## 概要

`auto_like` workflow の実行時間を少し短くしつつ、いいね対象の選定を「すでに大量に伸びた投稿」よりも「まだ新しく、いいね数が少ない投稿」に寄せる。具体的には、like 間隔を現状の `5〜20秒` から `2〜8秒` に短縮し、`300以上` のいいねを持つ投稿を候補から除外したうえで、候補をランダムではなく「新しさ優先・低いいいね数優先」で並べて選ぶ。

## 変更・作成・確認対象

- 変更ファイル: `python/auto_like.py`
- 変更ファイル: `tests/test_auto_like.py`
- 変更ファイル: `.github/workflows/auto_like.yml`（必要なら summary 表示だけ追随）
- 変更ファイル: `README.md`（`auto_like` の挙動説明が変わるため必要箇所を更新）
- 計画書: `docs/exec-plans/active/auto-like-low-like-recency_20260328_1533.md`

## 実装方針

- `TweetCandidate` に like 数を保持できるようにし、feed payload から `metrics.likes` / `legacy.favorite_count` / `public_metrics.like_count` など複数パスを防御的に抽出する
- しきい値 `300` 以上の投稿は eligible 候補に入れない
- feed モードでは現在の `random.shuffle()` をやめ、`created_at` が新しい順をベースにしつつ、同程度に新しい候補の中では like 数が少ないものを優先する並びへ変更する
- `target_accounts` モードは既存の意味をなるべく維持し、feed モード専用の並び替えが共通パスから波及しないよう `source_mode` ごとに選定処理を分ける
- 既存の「30分窓を優先、足りなければ60分窓へ拡張」の考え方は維持する
- like 間隔は `2〜8秒` に短縮し、テストで固定する
- summary に like 数が出せるなら selected candidate の確認情報へ含める

## 実装ステップ

- [x] 1. `tests/test_auto_like.py` に RED テストを追加する
- [x] 2. `python/auto_like.py` で like 数の抽出と candidate 型の拡張を行う
- [x] 3. `python/auto_like.py` で `source_mode` ごとに選定処理を分け、feed モードだけ `300以上除外` と `新しさ優先・低いいいね数優先` の選定へ変更する
- [x] 4. `python/auto_like.py` の sleep 範囲を `2〜8秒` に変更する
- [x] 5. workflow summary / README の表示と説明を追随する
- [x] 6. `python -m unittest tests.test_auto_like`、`python -m unittest discover -s tests`、`python -m py_compile python/auto_like.py tests/test_auto_like.py`、`.github/workflows/auto_like.yml` の YAML 検証、`git diff --check` で確認する

## 注意点

- 「短くする」は少し短くなので、`1〜5秒` のような過度な短縮は避ける
- 既存の daily like limit や state 管理は壊さない
- target account モードがあるため、feed モードの選定変更が target account モードへ不必要に波及しないようにする
- like 数が取得できない payload でも落ちないよう、未取得時は `0` 扱いなどの安全な既定値にする
- 選定ロジックは完全ランダムから変えるため、テストで並び順を固定して回帰を防ぐ
