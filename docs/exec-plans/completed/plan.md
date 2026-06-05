# TikTok動画取得・匿名化・自動投稿 実装計画

## 現在地メモ 2026-06-05

- `Phase 0` は実施済み。`tmp/tiktok-debug/environment.txt`、`tmp/tiktok-debug/baseline-test.txt`、`tmp/tiktok-debug/current-flow.md` が作成され、既存のTikTok処理フローと依存状況の確認までは完了している。
- `Phase 1` は実質完了に近い。`scripts/tiktok/download_video.py` による `dry-run` と実ダウンロードの確認が済み、`source.mp4`、`metadata.json`、`ffprobe.json`、`result.json` などの取得成果物も確認できている。
- ただし `Phase 1` の中で見つかった「取得できても再生互換性が十分でない」という課題があり、これを解消する追加計画として `TikTok_H264自動変換_実装計画.md` が派生している。
- `Phase 2` は部分着手。`ffprobe` による形式確認までは進んだが、元プランで想定していた「後続処理が常に互換性の高い動画を使える状態」にはまだ到達していない。
- `Phase 3` 以降の顔検出、顔スタンプ、投稿文生成、TikTok投稿API、状態管理は未着手。

## 0. この計画の目的

本計画は、`FPXszk/twitter-auto-poster` に以下の処理を段階的に追加し、最終的にTikTok動画の自動投稿が実現可能かを検証するためのものとする。

1. 許可済みTikTok動画URLを受け取る
2. TikTokから取得可能な最高品質の動画をダウンロードする
3. 動画内の顔を検出する
4. 顔の位置へ追従するスタンプを合成する
5. 動画内容から投稿文を生成する
6. dry-runで成果物を確認する
7. TikTok公式Content Posting APIで投稿する
8. 投稿結果と処理履歴を保存する

最初から全工程を実装してはいけない。

**最優先は「TikTok動画を安定して取得できるか」の確認である。**

動画取得が安定するまで、顔加工・文章生成・TikTok投稿機能へ進まないこと。

---

## 1. CLIへの最重要指示

### 1.1 作業方針

- ユーザーとは日本語でコミュニケーションを取ること
- 既存コードを先に読み、現在の設計を壊さないこと
- 変更は小さく段階的に行うこと
- 一度に複数フェーズを実装しないこと
- 各フェーズでテストと手動確認を完了してから次へ進むこと
- 原因が分からないまま回避コードを追加しないこと
- 失敗時は、標準出力・標準エラー・実行コマンド・環境情報を保存すること
- 最初は必ずdry-runとローカル実行を使用すること
- GitHub Actionsや自動スケジュール実行は最後に追加すること
- TikTokの非公式な投稿自動化やブラウザ操作を第一候補にしないこと
- 投稿にはTikTok公式Content Posting APIを優先すること
- 第三者動画の無断転載を前提とした実装にしないこと
- 対象は自分・自社・転載許可済み・利用許諾済み動画に限定すること
- 秘密情報、Cookie、トークンをログやGitへ出力しないこと

### 1.2 作業開始前に必ず読むファイル

以下を最初に確認すること。

```text
README.md
AGENTS.md
CLAUDE.md
.github/copilot-instructions.md
.agents/skills/repo-planning-discipline/SKILL.md
.agents/skills/github-actions-failure-debugging/SKILL.md
docs/RUNBOOK.md
scripts/lib/tiktok_pipeline.py
scripts/lib/tiktok_downloader.py
scripts/lib/tiktok_client.py
scripts/lib/tiktok_allowlist.py
scripts/lib/post_video.py
config/tiktok_allowlist.yaml
config/accounts.yaml
```

存在しないファイルは、その事実を作業記録へ残すこと。

### 1.3 実装前に確認すること

以下を調査し、結果を簡潔に報告してから変更を始めること。

- 現在のTikTok関連ファイル一覧
- 既存のTikTok処理フロー
- `tiktok_pipeline.py`が現在何を入力としているか
- `tiktok_downloader.py`が現在どの形式を想定しているか
- `yt-dlp`の呼び出し方法
- MP4以外が返った場合の挙動
- Cookie対応の有無
- リダイレクトURL対応の有無
- 画質選択指定の有無
- ffmpeg依存の有無
- 単体テストの有無
- TikTok公式APIを使用している処理の有無
- X投稿処理とTikTok投稿処理が混在していないか

---

# 2. 対象範囲

## 2.1 今回実装する範囲

- TikTok動画URLの入力
- URLの正規化
- 許可済み投稿者・URLの確認
- `yt-dlp`による動画取得
- 取得フォーマットの検査
- 動画品質情報の保存
- 顔検出
- 顔スタンプ合成
- 投稿文候補生成
- TikTok公式API投稿
- dry-run
- 状態保存
- 再実行時の重複防止
- エラーログ
- 手動実行用CLI
- 最終段階でのGitHub Actions対応

## 2.2 今回実装しない範囲

- 第三者アカウントからの大量収集
- 無許可動画の自動転載
- TikTokの画面を自動操作する非公式投稿
- CAPTCHA回避
- アクセス制限回避
- デバイス偽装
- 透かし除去を目的とした加工
- 顔検出漏れがある状態での完全自動公開
- 最初から複数アカウント対応
- 最初から複数動画の一括処理
- 最初から定期スケジュール投稿
- 音源権利の自動判定
- 投稿前確認を省略した完全無人運用

---

# 3. 現在の実装に対する認識

現状では以下の構成が存在する。

```text
scripts/lib/tiktok_pipeline.py
scripts/lib/tiktok_downloader.py
scripts/lib/tiktok_client.py
scripts/lib/tiktok_allowlist.py
scripts/lib/tiktok_filters.py
scripts/lib/tiktok_scoring.py
scripts/lib/tiktok_state.py
scripts/lib/post_video.py
config/tiktok_allowlist.yaml
```

現在の`download_tiktok_video()`は、概ね次の処理を行っている。

```text
TikTok URL検証
↓
yt-dlp存在確認
↓
一時ディレクトリ作成
↓
yt-dlp実行
↓
*.mp4を探索
↓
動画ファイル検証
↓
取得したPathを返却
```

ただし、現在の実装には少なくとも以下の確認が必要である。

- `-f`または`--format`による最高品質指定がない
- `--merge-output-format mp4`がない
- TikTok短縮URLのリダイレクト後URLを記録していない
- `webm`や`mkv`になった場合に失敗する可能性がある
- Cookieを使用する経路がない
- `yt-dlp`のバージョンを記録していない
- 実行コマンド、取得フォーマット、動画メタデータを保存していない
- 再試行方針がない
- 原因別エラー分類がない
- 最高品質で取得できたかを検証する仕組みがない
- 同一URLの再ダウンロード防止がない
- ダウンロード工程だけを単独実行するCLIが弱い、または存在しない可能性がある
- X投稿パイプラインと取得検証が密結合している

このため、最初に動画取得処理を独立させる。

---

# 4. 全体フェーズ

```text
Phase 0  現状調査・テスト基盤
Phase 1  TikTok動画取得だけを独立して安定化
Phase 2  動画検査・品質記録・再現性確保
Phase 3  顔検出のみ実装
Phase 4  顔スタンプ追従と動画書き出し
Phase 5  投稿文候補生成
Phase 6  dry-run統合
Phase 7  TikTok公式API投稿
Phase 8  状態管理・重複防止・再試行
Phase 9  GitHub Actions／セルフホステッドランナー
Phase 10 限定運用・安定性評価
```

各Phaseには完了条件を設ける。

完了条件を満たしていない状態で次のPhaseへ進まないこと。

---

# 5. Phase 0：現状調査とテスト基盤

## 5.1 目的

既存実装を壊さず、TikTok動画取得だけを安全に検証できる状態にする。

## 5.2 実施内容

1. Gitの作業状態を確認する

```bash
git status --short
git branch --show-current
git log -5 --oneline
```

2. TikTok関連ファイルを列挙する

```bash
find . -maxdepth 4 -type f | sort | grep -i tiktok
```

3. 依存コマンドを確認する

```bash
python3 --version
which python3
yt-dlp --version
which yt-dlp
ffmpeg -version
ffprobe -version
```

4. Python依存関係を確認する

```bash
python3 -m pip show yt-dlp
python3 -m pip show opencv-python
python3 -m pip show mediapipe
python3 -m pip show pyyaml
```

5. 既存テストを確認する

```bash
find . -maxdepth 4 -type f | sort | grep -E 'test_|_test\.py|tests/'
```

6. 既存TikTokテストを実行する

```bash
python3 -m pytest -q
```

テスト全体が重い場合はTikTok関連だけに絞る。

```bash
python3 -m pytest -q -k tiktok
```

7. 現行コードの動作を変更前に記録する

```bash
python3 scripts/lib/tiktok_pipeline.py --help
```

8. 現行のdry-runコマンドを確認する

READMEと実装が一致しているか確認すること。

## 5.3 作成する記録

```text
tmp/tiktok-debug/environment.txt
tmp/tiktok-debug/baseline-test.txt
tmp/tiktok-debug/current-flow.md
```

`environment.txt`には次を含める。

- OS
- Pythonバージョン
- yt-dlpバージョン
- ffmpegバージョン
- 実行日時
- GitコミットSHA
- 実行場所
- WSLかGitHub Actionsか
- Cookie利用有無

秘密情報は含めない。

## 5.4 完了条件

- 現在のTikTok処理フローを説明できる
- 現在のテスト結果を保存した
- `yt-dlp`と`ffmpeg`の存在を確認した
- 変更前の基準状態を記録した
- 既存テストの失敗が今回の変更前から存在するか区別できる

---

# 6. Phase 1：TikTok動画取得だけを独立して安定化

## 6.1 目的

URLを1件入力し、投稿・顔加工・文章生成を行わず、動画取得だけを検証できるCLIを作る。

## 6.2 最初に作るCLI

以下のようなコマンドを用意する。

```bash
python3 scripts/tiktok/download_video.py \
  --url "https://www.tiktok.com/@example/video/1234567890" \
  --output-dir tmp/tiktok-debug/downloads \
  --dry-run
```

実ダウンロード時:

```bash
python3 scripts/tiktok/download_video.py \
  --url "https://www.tiktok.com/@example/video/1234567890" \
  --output-dir tmp/tiktok-debug/downloads
```

Cookieを使用する場合:

```bash
python3 scripts/tiktok/download_video.py \
  --url "https://www.tiktok.com/@example/video/1234567890" \
  --output-dir tmp/tiktok-debug/downloads \
  --cookies-from-browser chrome
```

Cookieファイルを使用する場合:

```bash
python3 scripts/tiktok/download_video.py \
  --url "https://www.tiktok.com/@example/video/1234567890" \
  --output-dir tmp/tiktok-debug/downloads \
  --cookies-file /secure/path/cookies.txt
```

Cookie値そのものをログへ出してはいけない。

## 6.3 CLIの出力

成功時は、人間向けログとJSON結果の両方を残す。

例:

```json
{
  "ok": true,
  "input_url": "https://...",
  "resolved_url": "https://...",
  "video_id": "1234567890",
  "uploader": "example",
  "title": "...",
  "output_path": "tmp/tiktok-debug/downloads/1234567890/source.mp4",
  "container": "mp4",
  "video_codec": "h264",
  "audio_codec": "aac",
  "width": 1080,
  "height": 1920,
  "fps": 30,
  "duration_seconds": 15.3,
  "size_bytes": 12345678,
  "yt_dlp_version": "...",
  "download_strategy": "anonymous",
  "metadata_path": ".../metadata.json",
  "command_log_path": ".../download.log"
}
```

失敗時:

```json
{
  "ok": false,
  "stage": "download",
  "error_code": "TIKTOK_LOGIN_REQUIRED",
  "message": "...",
  "retryable": true,
  "input_url": "https://...",
  "log_path": ".../download.log"
}
```

## 6.4 URL検証

以下を区別する。

- 通常URL
- `www.tiktok.com`
- `m.tiktok.com`
- `vm.tiktok.com`
- 短縮URL
- クエリ文字列付きURL
- 共有URL
- 不正なドメイン
- HTTP
- 空文字
- 複数動画を含むURL
- TikTok以外のURL

短縮URLはリダイレクト後の最終URLも記録する。

不正URLは`yt-dlp`実行前に拒否する。

## 6.5 画質指定

第一候補は以下とする。

```bash
yt-dlp \
  --no-playlist \
  --no-progress \
  --force-overwrites \
  --write-info-json \
  --print-json \
  --format "bestvideo*+bestaudio/best" \
  --merge-output-format mp4 \
  --output "video.%(ext)s" \
  "<URL>"
```

ただし、TikTok側の配信形式によっては単一MP4ストリームのほうが高品質・安定する場合がある。

そのため、実装では次の順に試す。

### Strategy A

```text
bestvideo*+bestaudio/best
merge_output_format=mp4
```

### Strategy B

```text
best[ext=mp4]/best
```

### Strategy C

```text
best
```

各Strategyは同じ実行内で無制限に試さず、原因をログに残す。

再試行回数は最大3回程度とし、指数バックオフを使う。

例:

```text
1回目: 即時
2回目: 3秒後
3回目: 10秒後
```

HTTP 4xxのうち、認証・利用不可・削除済みは無駄に再試行しない。

## 6.6 出力ファイル構成

```text
tmp/tiktok-debug/downloads/
└── <video_id-or-url-hash>/
    ├── source.mp4
    ├── source.info.json
    ├── metadata.json
    ├── download.log
    ├── ffprobe.json
    └── result.json
```

動画IDが取得できない場合はURLのSHA-256先頭16文字を使用する。

## 6.7 元ファイルを上書きしない

以下を厳守する。

- ダウンロード元は`source.*`
- 加工後は`edited.*`
- 元ファイルを加工処理で上書きしない
- 同じ動画IDが存在する場合は、既存ファイルを検査して再利用できるようにする
- `--force`指定時のみ再取得する
- 途中ファイルは`.part`または一時ディレクトリへ保存する
- 成功後に原子的に確定ファイル名へ移動する

## 6.8 Phase 1の単体テスト

最低限、以下を追加する。

```text
tests/test_tiktok_downloader.py
tests/test_tiktok_download_cli.py
```

テスト項目:

- 空URLを拒否
- 非TikTok URLを拒否
- HTTP URLを拒否
- 許可ホストを受け入れる
- 短縮URLを受け入れる
- `yt-dlp`未インストール時のエラー
- subprocess成功時
- subprocess失敗時
- MP4生成時
- WebM生成時にMP4へ統合される
- 出力ファイルなし
- ファイルサイズ超過
- ffprobe失敗
- JSON出力形式
- Cookie引数がログでマスクされる
- 同一動画の再利用
- `--force`で再取得

ネットワークを使うテストと、モックによる単体テストを分ける。

通常のCIではモックテストを実行し、実TikTok URLを使うテストは手動実行にする。

## 6.9 Phase 1の完了条件

以下をすべて満たすこと。

- 単独CLIでURLを1件指定できる
- 投稿処理を呼ばない
- 最高品質候補を明示して取得できる
- 成功時にMP4が生成される
- ffprobe結果が保存される
- yt-dlpのJSONメタデータが保存される
- 失敗理由を分類して表示できる
- Cookieなし・Cookieありを切り替えられる
- 秘密情報をログへ出さない
- 既存TikTokパイプラインのテストを壊していない
- 最低3種類の許可済みテスト動画で手動確認した
- 同じURLを3回連続実行して再現性を確認した

---

# 7. TikTok動画取得のデバッグ手順

この章は、動画取得に失敗した際に上から順に実施する。

順番を飛ばしてはいけない。

## 7.1 Step 1：入力URLの確認

確認項目:

```text
URLは空でないか
HTTPSか
TikTokドメインか
動画ページURLか
短縮URLか
ブラウザで開けるか
動画が削除されていないか
非公開動画ではないか
年齢・地域制限がないか
ログイン必須ではないか
```

実行:

```bash
python3 scripts/tiktok/download_video.py \
  --url "<URL>" \
  --output-dir tmp/tiktok-debug/downloads \
  --dry-run \
  --verbose
```

期待結果:

- URLの種類
- 正規化後URL
- リダイレクト後URL
- 対象ホスト
- 動画ID
- 実行予定Strategy

## 7.2 Step 2：yt-dlp単体で情報取得

コード経由ではなく、まずCLI単体で確認する。

```bash
yt-dlp --version
yt-dlp --verbose --dump-single-json --skip-download "<URL>" \
  > tmp/tiktok-debug/ytdlp-metadata.json \
  2> tmp/tiktok-debug/ytdlp-metadata.log
```

ここで失敗する場合、Pythonコードではなく、TikTok・URL・yt-dlp・認証環境の問題である可能性が高い。

確認するエラー:

```text
Unsupported URL
Video unavailable
Login required
Requested format is not available
HTTP Error 403
HTTP Error 429
Sign in to confirm
Unable to extract
No video formats found
```

## 7.3 Step 3：利用可能フォーマット確認

```bash
yt-dlp -F "<URL>" \
  > tmp/tiktok-debug/formats.txt \
  2> tmp/tiktok-debug/formats-error.log
```

確認項目:

- 利用可能な解像度
- ビットレート
- コンテナ
- 動画コーデック
- 音声有無
- 透かし有無に関するメタデータ
- 最高品質候補
- 1080x1920が存在するか
- 単一MP4か映像・音声分離か

「オリジナル画質」という表現は使用せず、次のように記録する。

```text
TikTokが現在配信している取得可能フォーマット中の最高品質
```

TikTok投稿前の原本ファイルと同一とは保証しない。

## 7.4 Step 4：最小コマンドでダウンロード

```bash
mkdir -p tmp/tiktok-debug/manual
yt-dlp \
  --verbose \
  --no-playlist \
  -o "tmp/tiktok-debug/manual/video.%(ext)s" \
  "<URL>" \
  > tmp/tiktok-debug/manual/stdout.log \
  2> tmp/tiktok-debug/manual/stderr.log
```

これで成功するか確認する。

成功する場合は、Pythonラッパー側の問題を疑う。

失敗する場合は、yt-dlp・URL・TikTok側制限を疑う。

## 7.5 Step 5：最高品質指定を追加

```bash
yt-dlp \
  --verbose \
  --no-playlist \
  --format "bestvideo*+bestaudio/best" \
  --merge-output-format mp4 \
  -o "tmp/tiktok-debug/manual/best.%(ext)s" \
  "<URL>"
```

失敗時は次を試す。

```bash
yt-dlp \
  --verbose \
  --no-playlist \
  --format "best[ext=mp4]/best" \
  -o "tmp/tiktok-debug/manual/best-mp4.%(ext)s" \
  "<URL>"
```

## 7.6 Step 6：ffmpeg確認

```bash
which ffmpeg
which ffprobe
ffmpeg -version
ffprobe -version
```

映像・音声分離形式を選んだ場合、ffmpegがないとマージできない。

生成物確認:

```bash
ffprobe \
  -v error \
  -show_format \
  -show_streams \
  -of json \
  tmp/tiktok-debug/manual/best.mp4
```

確認項目:

- 動画ストリームが1つ以上ある
- 音声ストリームが必要に応じて存在する
- durationが0より大きい
- widthとheightが0より大きい
- ファイルサイズが0より大きい
- MP4コンテナとして読み取れる
- デコードエラーがない

簡易デコード確認:

```bash
ffmpeg \
  -v error \
  -i tmp/tiktok-debug/manual/best.mp4 \
  -f null -
```

## 7.7 Step 7：Cookieなしで失敗する場合

ブラウザCookieを利用して確認する。

```bash
yt-dlp \
  --verbose \
  --cookies-from-browser chrome \
  --dump-single-json \
  --skip-download \
  "<URL>"
```

WSLからWindows ChromeのCookie取得が失敗する場合がある。

その場合は次を切り分ける。

- Windows側でyt-dlpを実行
- WSL側でCookieファイルを安全に受け渡す
- Chromeのプロファイル名を明示
- Edgeを試す
- Cookie DBのロックを確認
- DPAPIや暗号化の制約を確認

CookieファイルはGit管理しない。

`.gitignore`へ以下相当を追加する。

```gitignore
cookies*.txt
*.cookies.txt
tmp/tiktok-debug/
tmp/tiktok-download/
```

## 7.8 Step 8：yt-dlp更新

TikTok側変更で抽出に失敗する場合は、バージョンを確認する。

```bash
yt-dlp --version
python3 -m pip install --upgrade yt-dlp
yt-dlp --version
```

`uv tool`で導入している場合は、その管理方法に合わせる。

更新前後のバージョンを記録する。

安易にnightly版へ固定しない。

通常版で失敗し、nightly版で修正済みと確認できる場合のみ検討する。

## 7.9 Step 9：HTTP 403

確認すること:

- Cookieの有無
- User-Agent
- IP制限
- 地域制限
- URL期限切れ
- TikTok側レート制限
- 同一IPからの短時間大量アクセス
- GitHub Actions共有IPからのアクセス
- WSLとWindowsで結果が異なるか

試験順:

```text
1. ローカルWindows
2. WSL
3. CookieありWSL
4. セルフホステッドランナー
5. GitHubホステッドランナー
```

GitHubホステッドランナーだけ失敗する場合、共有IPや環境差の可能性が高い。

## 7.10 Step 10：HTTP 429

- 自動再試行を連打しない
- 実行頻度を下げる
- Retry-Afterがあれば尊重する
- 取得間隔へランダムな待機を入れる
- 同一URLの再取得を避ける
- 同一ジョブの多重起動を防ぐ
- 無限リトライを禁止する

## 7.11 Step 11：MP4が生成されない

現行実装は`*.mp4`のみ探すため、WebMやMKV出力時に失敗する可能性がある。

確認:

```bash
find tmp/tiktok-debug -type f -maxdepth 4 -printf '%p %s bytes\n'
```

対応方針:

- `--merge-output-format mp4`
- yt-dlpのJSONから実ファイルパスを取得
- 拡張子を決め打ちしない
- 必要に応じてffmpegでMP4へ正規化
- 正規化後に元ダウンロードファイルと変換ファイルを区別する

## 7.12 Step 12：ダウンロードは成功するが画質が低い

比較する。

```bash
yt-dlp -F "<URL>"
ffprobe -v error -show_streams -show_format -of json "<FILE>"
```

記録する。

- format_id
- width
- height
- fps
- vcodec
- acodec
- tbr
- filesize
- protocol

単にファイルサイズが大きいものを最高画質と判定しない。

優先順位例:

```text
解像度
動画ビットレート
fps
コーデック互換性
音声有無
コンテナ互換性
```

## 7.13 Step 13：Python経由のみ失敗

比較する。

- 実際に生成したコマンド
- カレントディレクトリ
- PATH
- yt-dlpの実体
- Python実行ユーザー
- 環境変数
- stdout
- stderr
- timeout
- 文字コード
- subprocess引数

Python側に`--verbose`相当のデバッグモードを追加し、実行コマンドは秘密情報をマスクして記録する。

## 7.14 Step 14：同じURLで結果が不安定

最低5回試験する。

```text
成功回数
失敗回数
平均取得時間
取得解像度
取得ファイルサイズ
format_id
エラー分類
```

不安定要因を分類する。

```text
ネットワーク
TikTok応答
Cookie
yt-dlp抽出
ffmpegマージ
ファイル検証
一時ファイル
タイムアウト
```

## 7.15 デバッグ結果の判定

### Go

- 許可済みの複数URLで安定取得できる
- 失敗原因を分類できる
- Cookie有無を選択できる
- MP4へ正規化できる
- ffprobeで正常判定できる
- 同一URL再実行が安全
- ログに秘密情報がない

### Conditional Go

- Cookieありでのみ取得可能
- ローカル・セルフホステッドランナーでは成功
- GitHubホステッドランナーでは失敗

この場合はセルフホステッドランナー前提で次へ進む。

### No-Go

- 許可済み公開動画でも安定取得できない
- TikTok仕様変更ごとに大規模修正が必要
- Cookie保存が安全に運用できない
- 取得結果の品質が要求を満たさない
- 利用規約・権利条件を満たせない

No-Goの場合は、URLダウンロード方式を中止し、投稿者が元MP4を所定フォルダへ配置する方式へ切り替える。

---

# 8. Phase 2：動画検査・品質記録

## 8.1 目的

取得成功だけではなく、後続処理に使用できる動画かを判定する。

## 8.2 検査項目

- MP4として開ける
- 動画ストリームが存在する
- duration > 0
- width > 0
- height > 0
- fps > 0
- サイズ上限以内
- TikTok投稿APIの仕様範囲内
- 音声ストリームの有無
- 回転メタデータ
- ピクセルフォーマット
- 可変フレームレート
- 破損フレーム
- 先頭・末尾がデコード可能
- 極端に短い・長い動画ではない

## 8.3 正規化

後続処理のため、必要に応じて次の形式へ正規化する。

```text
container: MP4
video codec: H.264
audio codec: AAC
pixel format: yuv420p
faststart: enabled
```

ただし、取得直後に無条件で再エンコードしない。

元動画が互換形式ならコピーまたはそのまま使用する。

## 8.4 完了条件

- `source.mp4`と検査JSONが保存される
- 正規化が必要か判定できる
- 破損ファイルを拒否できる
- 後続処理が使う入力形式が固定される

---

# 9. Phase 3：顔検出だけを実装

## 9.1 目的

動画を書き換えず、顔の位置情報だけを取得する。

## 9.2 第一候補

最初はCPUで扱いやすい方式を選ぶ。

候補:

```text
MediaPipe Face Detection
OpenCV DNN Face Detector
YOLO face model
```

CLIは次の形式とする。

```bash
python3 scripts/tiktok/detect_faces.py \
  --input tmp/tiktok-debug/downloads/<id>/source.mp4 \
  --output-dir tmp/tiktok-debug/downloads/<id>/faces
```

## 9.3 出力

```text
faces/
├── detections.json
├── summary.json
├── preview/
│   ├── frame_000001.jpg
│   └── ...
└── detect.log
```

`detections.json`例:

```json
{
  "frame_index": 120,
  "timestamp_ms": 4000,
  "faces": [
    {
      "track_id": null,
      "x": 0.25,
      "y": 0.10,
      "width": 0.20,
      "height": 0.25,
      "confidence": 0.92
    }
  ]
}
```

座標は0〜1の正規化座標を基本とする。

## 9.4 検証動画

最低限、次を含む許可済み動画で確認する。

- 1人・正面
- 1人・横顔
- 複数人
- 顔が小さい
- 顔が一時的に隠れる
- 激しい動き
- 暗い場面
- 画面内写真
- 顔が映らない動画

## 9.5 完了条件

- 元動画を変更しない
- フレーム単位の顔座標をJSONへ保存できる
- 顔なし動画を正常扱いできる
- 検出件数のサマリーを出せる
- 検出漏れを人間が確認できるプレビューがある

---

# 10. Phase 4：顔スタンプ追従と動画書き出し

## 10.1 目的

検出した顔へPNGスタンプを合成し、匿名化済み動画を生成する。

## 10.2 必須仕様

- 元動画を上書きしない
- 透過PNG対応
- 顔より広い範囲を覆う
- スタンプ位置を平滑化
- 一時的に検出が切れても数フレーム維持
- 複数人対応
- 音声保持
- 回転情報保持または正規化
- 出力MP4を再検査
- 加工前後のduration差を検査

## 10.3 スタンプサイズ

初期値:

```text
横幅: 検出顔幅の1.4倍
縦幅: 検出顔高の1.4倍
中心: 顔中心
```

設定化する。

## 10.4 トラッキング

第一段階:

- IoU
- 中心点距離
- 前フレーム座標
- 移動平均

必要になった場合のみByteTrack等を導入する。

最初から過剰なモデルを追加しない。

## 10.5 安全判定

以下の場合は自動公開不可とする。

- 検出信頼度が閾値未満
- フレーム間で顔数が急変
- 長時間検出が途切れる
- 顔が画面端で切れる
- 追跡IDが頻繁に切り替わる
- 処理中に例外が発生
- 出力動画の検査に失敗
- 人間のレビューが未完了

## 10.6 出力

```text
edited/
├── edited.mp4
├── overlay-summary.json
├── face-coverage-report.json
├── processing.log
└── preview.mp4
```

## 10.7 完了条件

- スタンプが顔へ追従する
- チラつきが許容範囲
- 複数人を隠せる
- 音声が残る
- 元動画と長さが一致する
- 失敗時に公開工程へ進まない
- 人間がプレビュー確認できる

---

# 11. Phase 5：投稿文候補生成

## 11.1 目的

動画内容から投稿文を生成するが、最初は候補生成だけとする。

## 11.2 入力

- 元投稿の説明文
- 投稿者名
- 許諾・出典情報
- 動画メタデータ
- 音声文字起こし
- 代表フレーム
- OCR結果
- 動画カテゴリ
- 使用言語

## 11.3 出力

```json
{
  "caption": "...",
  "hashtags": ["#..."],
  "source_credit": "...",
  "safety_notes": [],
  "generation_model": "...",
  "generation_prompt_version": "v1",
  "requires_review": true
}
```

## 11.4 必須制約

- 内容を捏造しない
- 動画にない事実を断定しない
- 元投稿者の表現を丸写ししない
- 出典・許諾表記を落とさない
- 誇大表現を避ける
- 差別・誹謗中傷・個人情報を出さない
- 顔を隠した人物を推測しない
- 最初は必ず人間確認を要求する

## 11.5 完了条件

- 投稿文候補を生成できる
- 出典情報を含められる
- promptとmodelを記録できる
- 人間が編集できるテキストファイルを保存する
- 生成失敗時に投稿工程へ進まない

---

# 12. Phase 6：dry-run統合

## 12.1 目的

URL入力から投稿直前までを一つのジョブとして実行する。

## 12.2 CLI

```bash
python3 scripts/tiktok/pipeline.py \
  --url "<許可済みURL>" \
  --output-dir tmp/tiktok-jobs \
  --dry-run
```

## 12.3 処理順

```text
URL入力
↓
URL検証
↓
allowlist確認
↓
動画取得
↓
動画検査
↓
顔検出
↓
顔スタンプ合成
↓
加工済み動画検査
↓
投稿文候補生成
↓
レビュー用成果物生成
↓
終了
```

## 12.4 成果物

```text
tmp/tiktok-jobs/<job_id>/
├── input.json
├── source/
│   ├── source.mp4
│   ├── metadata.json
│   └── ffprobe.json
├── faces/
│   ├── detections.json
│   └── summary.json
├── edited/
│   ├── edited.mp4
│   ├── preview.mp4
│   └── coverage-report.json
├── caption/
│   ├── transcript.txt
│   ├── caption.txt
│   └── caption.json
├── logs/
│   ├── download.log
│   ├── detect.log
│   ├── edit.log
│   └── pipeline.log
└── result.json
```

## 12.5 完了条件

- 一つのコマンドでdry-runが完了する
- 途中失敗時に後続工程を実行しない
- 再実行可能
- 元動画を保持
- 投稿されない
- レビュー用成果物が揃う
- result.jsonだけで成否を判断できる

---

# 13. Phase 7：TikTok公式Content Posting API

## 13.1 目的

編集済み動画をTikTok公式APIで投稿する。

## 13.2 事前調査

実装前に最新の公式仕様を確認する。

- TikTok Developerアプリ
- Content Posting API
- OAuth
- `video.publish`スコープ
- Direct Post
- Upload API
- 投稿可能動画仕様
- アプリ監査
- 未監査クライアントの公開範囲
- レート制限
- 投稿ステータス確認
- エラーコード
- トークン有効期限
- リフレッシュトークン
- commercial content disclosure
- privacy_level
- duet・stitch設定

公式ドキュメント以外を仕様の根拠にしない。

## 13.3 投稿方式

第一候補:

```text
ローカルMP4
↓
投稿初期化
↓
upload_urlへアップロード
↓
publish_id保存
↓
ステータス確認
↓
完了記録
```

## 13.4 投稿前チェック

- `--dry-run false`が明示されている
- ユーザー承認済み
- allowlist一致
- 動画検査合格
- 顔カバレッジ検査合格
- 投稿文確認済み
- 出典情報あり
- 重複投稿でない
- アクセストークン有効
- API投稿先アカウント一致
- 公開範囲を明示
- テスト時は非公開または限定公開

## 13.5 live投稿CLI

```bash
python3 scripts/tiktok/pipeline.py \
  --job-id "<job_id>" \
  --publish \
  --privacy-level SELF_ONLY
```

最初から`PUBLIC_TO_EVERYONE`を既定値にしない。

既定値は最も安全な公開範囲とする。

## 13.6 完了条件

- 公式APIを使用
- 投稿初期化とアップロードを分離
- publish_idを保存
- 投稿ステータスを確認
- APIエラーを分類
- 二重投稿を防止
- 最初は非公開投稿で検証
- 人間承認なしに公開しない

---

# 14. Phase 8：状態管理・重複防止・再試行

## 14.1 状態

ジョブ状態例:

```text
CREATED
URL_VALIDATED
DOWNLOADING
DOWNLOADED
SOURCE_VALIDATED
FACE_DETECTED
EDITED
EDIT_VALIDATED
CAPTION_GENERATED
REVIEW_REQUIRED
APPROVED
PUBLISHING
PUBLISHED
FAILED
REJECTED
```

## 14.2 stateに保存する情報

- job_id
- input_url
- resolved_url
- video_id
- source_creator
- source_hash
- edited_hash
- caption_hash
- current_stage
- retry_count
- last_error
- created_at
- updated_at
- approved_at
- published_at
- publish_id
- TikTok投稿URL
- 投稿先アカウント
- Git commit SHA
- pipeline version

## 14.3 冪等性

- 同じvideo_idは原則1ジョブ
- 同じsource hashは重複扱い
- 投稿成功後は再投稿不可
- 投稿状態不明時はステータス照会してから再試行
- uploadだけ成功した場合も再初期化しない
- `--force`でも公開済み動画の再投稿は別の明示オプションを必要とする

## 14.4 完了条件

- 中断後に安全に再開できる
- 二重投稿を防げる
- 状態不明時に確認できる
- エラー履歴を残せる
- retryableとnon-retryableを区別できる

---

# 15. Phase 9：GitHub Actions／セルフホステッドランナー

## 15.1 原則

動画処理は最初からGitHubホステッドランナーへ載せない。

優先順位:

```text
1. ローカル手動
2. WSL手動
3. セルフホステッドランナー手動
4. workflow_dispatch
5. 定期実行
```

## 15.2 workflow_dispatch入力

```yaml
inputs:
  tiktok_url:
    description: "許可済みTikTok動画URL"
    required: true
  dry_run:
    description: "dry-run"
    required: true
    default: true
    type: boolean
  publish:
    description: "TikTokへ投稿"
    required: true
    default: false
    type: boolean
  privacy_level:
    description: "公開範囲"
    required: true
    default: "SELF_ONLY"
```

`dry_run=false`かつ`publish=true`の二重条件を要求する。

## 15.3 artifact

保存対象:

- result.json
- metadata
- ffprobe
- ログ
- preview.mp4
- caption
- coverage report

秘密情報やCookieはartifactへ含めない。

元動画・加工動画のartifact保存は権利・容量・保持期間を考慮し、設定で制御する。

## 15.4 同時実行防止

```yaml
concurrency:
  group: tiktok-pipeline
  cancel-in-progress: false
```

## 15.5 完了条件

- 手動起動できる
- dry-runが既定
- セルフホステッドランナーで動画処理できる
- artifactで結果確認できる
- 秘密情報が出ない
- 同時実行を防げる
- 失敗ジョブを安全に再実行できる

---

# 16. Phase 10：限定運用と評価

## 16.1 試験期間

最初は公開せず、非公開またはdry-runで最低10件処理する。

## 16.2 記録する指標

- URL検証成功率
- ダウンロード成功率
- Cookie必要率
- 平均ダウンロード時間
- 取得解像度
- 動画検査成功率
- 顔検出成功率
- 顔検出漏れ件数
- スタンプ追従失敗件数
- 再エンコード時間
- 投稿文修正率
- API投稿成功率
- 二重投稿件数
- 人間レビュー所要時間
- 1動画あたり処理時間
- 1動画あたりAPI費用

## 16.3 Go判定

次を満たした場合のみ限定的な自動運用へ進む。

- ダウンロード成功率90%以上
- 投稿可能動画の検査成功率95%以上
- 顔検出漏れが人間レビューで許容可能
- 二重投稿0件
- 秘密情報漏えい0件
- 公式API投稿が安定
- すべての動画が許諾済み
- 投稿前レビュー工程が機能
- 障害時の復旧手順が文書化済み

---

# 17. エラー分類

実装では文字列メッセージだけでなく、機械判定可能なエラーコードを使用する。

## URL

```text
INVALID_URL
UNSUPPORTED_HOST
URL_RESOLUTION_FAILED
VIDEO_ID_NOT_FOUND
```

## yt-dlp

```text
YTDLP_NOT_INSTALLED
YTDLP_OUTDATED
YTDLP_EXTRACTION_FAILED
FORMAT_NOT_AVAILABLE
DOWNLOAD_FAILED
DOWNLOAD_TIMEOUT
```

## TikTok

```text
VIDEO_UNAVAILABLE
VIDEO_PRIVATE
VIDEO_DELETED
LOGIN_REQUIRED
AGE_RESTRICTED
REGION_RESTRICTED
HTTP_403
HTTP_429
RATE_LIMITED
```

## ファイル

```text
OUTPUT_NOT_FOUND
OUTPUT_EMPTY
OUTPUT_TOO_LARGE
INVALID_CONTAINER
VIDEO_STREAM_NOT_FOUND
AUDIO_STREAM_NOT_FOUND
FFPROBE_FAILED
DECODE_FAILED
```

## 顔処理

```text
FACE_MODEL_LOAD_FAILED
FACE_DETECTION_FAILED
FACE_COVERAGE_LOW
TRACKING_UNSTABLE
OVERLAY_FAILED
EDITED_VIDEO_INVALID
```

## 文章生成

```text
TRANSCRIPTION_FAILED
OCR_FAILED
CAPTION_GENERATION_FAILED
CAPTION_REVIEW_REQUIRED
```

## 投稿

```text
TIKTOK_AUTH_FAILED
TOKEN_EXPIRED
PUBLISH_INIT_FAILED
UPLOAD_FAILED
PUBLISH_STATUS_FAILED
PUBLISH_REJECTED
DUPLICATE_POST
```

---

# 18. テスト戦略

## 18.1 単体テスト

ネットワークなしで実行可能にする。

- URL検証
- コマンド生成
- JSON解析
- エラー分類
- ffprobe解析
- state遷移
- 重複判定
- 秘密情報マスク
- 顔座標平滑化
- スタンプサイズ計算

## 18.2 結合テスト

- yt-dlpをモック
- ffprobeをモック
- TikTok APIをモック
- LLMをモック
- 一時ディレクトリ使用
- 成功・失敗・中断・再開

## 18.3 手動実ネットワークテスト

許可済みURLのみ使用する。

テストケースをGitへ直接保存しない。

環境変数またはローカル設定を使用する。

例:

```bash
export TIKTOK_TEST_URL_1="..."
export TIKTOK_TEST_URL_2="..."
export TIKTOK_TEST_URL_3="..."
```

## 18.4 回帰テスト

既存のX投稿機能を壊していないことを確認する。

```bash
python3 -m pytest -q
shellcheck scripts/**/*.sh
```

使用可能なlint・formatツールはリポジトリ既存設定に従う。

---

# 19. セキュリティ・権利・運用制約

## 19.1 権利

顔を隠しても以下の権利は残る。

- 動画の著作権
- 音源の著作権・原盤権
- 出演者の肖像権
- プライバシー
- 字幕・画像・ロゴ等の権利
- 元投稿者の利用条件

したがって、allowlistは単なるユーザー名一覧ではなく、許諾根拠を持つ設計にする。

例:

```yaml
creators:
  - tiktok_username: example
    enabled: true
    ownership_type: owned
    permission_reference: "internal-contract-2026-001"
    allow_download: true
    allow_edit: true
    allow_republish: true
    allowed_destinations:
      - tiktok
      - x
```

## 19.2 秘密情報

以下をGitへ入れない。

- TikTok access token
- refresh token
- client secret
- Cookie
- browser profileデータ
- X auth token
- ct0
- APIキー
- 許諾文書そのもの

## 19.3 ログマスク

最低限、次をマスクする。

```text
Authorization
access_token
refresh_token
client_secret
cookie
sessionid
sid_tt
ttwid
csrf
```

---

# 20. 推奨ファイル構成

既存構造を確認したうえで、過剰な再編を避ける。

候補:

```text
scripts/
└── tiktok/
    ├── __init__.py
    ├── download_video.py
    ├── inspect_video.py
    ├── detect_faces.py
    ├── overlay_faces.py
    ├── generate_caption.py
    ├── publish_tiktok.py
    └── pipeline.py

scripts/lib/
├── tiktok_downloader.py
├── tiktok_video_inspector.py
├── tiktok_face_detector.py
├── tiktok_face_overlay.py
├── tiktok_caption.py
├── tiktok_publisher.py
├── tiktok_job_state.py
└── tiktok_errors.py

config/
├── tiktok_allowlist.yaml
├── tiktok_pipeline.yaml
└── tiktok_caption_prompt_ja.txt

assets/
└── face_stamps/
    └── default.png

tests/
├── test_tiktok_downloader.py
├── test_tiktok_video_inspector.py
├── test_tiktok_face_detector.py
├── test_tiktok_face_overlay.py
├── test_tiktok_caption.py
├── test_tiktok_publisher.py
└── test_tiktok_pipeline.py
```

ただし、既存設計と重複する場合は、新規ファイルを増やさず既存モジュールへ小さく追加する。

---

# 21. コミット単位

一つの巨大コミットにしない。

推奨:

```text
1. test: add baseline tests for TikTok downloader
2. feat: add standalone TikTok download CLI
3. feat: add download metadata and ffprobe validation
4. fix: support redirects and mp4 normalization
5. feat: add optional cookie handling with log masking
6. feat: add face detection output
7. feat: add face tracking and stamp overlay
8. feat: add caption candidate generation
9. feat: add dry-run TikTok processing pipeline
10. feat: add official TikTok publishing client
11. feat: add state and duplicate protection
12. ci: add manual TikTok workflow
13. docs: add operation and recovery runbook
```

各コミット前に関連テストを実行する。

---

# 22. CLIが各フェーズ終了時に報告する形式

各Phase終了時は、以下の形式で報告する。

```markdown
## Phase X 完了報告

### 実施内容
- ...

### 変更ファイル
- ...

### 実行したテスト
- コマンド:
- 結果:

### 手動確認
- 使用したURL件数:
- 成功:
- 失敗:

### 判明した問題
- ...

### 未解決
- ...

### 完了条件
- [x] ...
- [ ] ...

### Go / Conditional Go / No-Go
- 判定:
- 根拠:

### 次に実施する1フェーズ
- ...
```

複数フェーズをまとめて報告しない。

---

# 23. 最初にCLIへ実行させる具体的タスク

まずPhase 0とPhase 1だけを実施する。

以下を最初の依頼内容とする。

```text
このプラン.mdを最初から最後まで読み、今回はPhase 0とPhase 1だけを実施してください。

目的は、TikTok URLを1件指定して、投稿処理や顔加工を一切行わず、取得可能な最高品質の動画を安全にダウンロードし、メタデータとffprobe結果を保存できる状態にすることです。

最初に既存のTikTok関連実装、リポジトリルール、テスト構成を調査してください。その後、動画取得だけを独立実行できるCLIを小さく実装してください。

必須条件:
- 既存のtiktok_pipeline.pyを壊さない
- 既存のtiktok_downloader.pyを再利用または小さく拡張する
- dry-run対応
- 通常URLと短縮URL対応
- yt-dlpの最高品質指定
- MP4への統合または正規化
- yt-dlp情報JSON保存
- ffprobe JSON保存
- stdout/stderrログ保存
- Cookieなし・cookies-from-browser・cookie fileを選択可能
- Cookieやtokenをログへ出さない
- エラーコード分類
- 単体テスト追加
- 実TikTok URLをテストコードへ直書きしない
- 投稿処理を呼ばない
- 顔検出を実装しない
- TikTok投稿APIを実装しない
- GitHub Actionsを変更しない

作業前に現状調査結果を報告し、変更後はPhase 1完了報告形式で結果をまとめてください。
```

---

# 24. 最終的な実現可能性の判定基準

## 技術的に実現可能と判定する条件

- URLから動画を安定取得できる
- 取得動画を正常検査できる
- 顔検出・追従・スタンプ合成が十分機能する
- 投稿文候補を生成できる
- TikTok公式APIで投稿できる
- 再試行と重複防止が機能する
- セルフホステッドランナーで安定稼働する

## 運用可能と判定する条件

- 対象動画の許諾確認ができる
- 顔検出漏れをレビューできる
- 投稿文をレビューできる
- トークンとCookieを安全に管理できる
- TikTok API審査・公開条件を満たせる
- 障害時に復旧できる
- アカウント停止につながる不正な自動化を使用しない

## 代替案へ切り替える条件

TikTok URLからの取得が不安定な場合は、次へ切り替える。

```text
投稿者が元MP4を所定フォルダへ配置
↓
顔スタンプ加工
↓
投稿文生成
↓
TikTok公式API投稿
```

この方式は、画質・権利・安定性の面でURL取得方式より優先される場合がある。

---

# 25. 完成の定義

このプロジェクトは、単に1回投稿できただけでは完成としない。

完成条件:

- 許可済み動画のみ処理
- 同一入力で再現可能
- 全工程にdry-runがある
- 元動画を保持
- 顔加工結果をレビュー可能
- 投稿文をレビュー可能
- TikTok公式APIを使用
- 重複投稿防止
- 中断再開
- エラー分類
- ログと成果物
- 秘密情報保護
- テスト
- RUNBOOK
- 限定運用で安定性確認

以上を満たした時点で、TikTok動画自動投稿機能を実運用可能と判断する。
