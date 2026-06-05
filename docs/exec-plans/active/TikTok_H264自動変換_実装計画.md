# TikTok動画取得後のH.264自動変換 実装計画

## 0. 目的

`FPXszk/twitter-auto-poster` のTikTok動画取得専用CLIに、取得後の動画形式チェックとH.264/AACへの自動変換を組み込む。

今回のゴールは以下。

1. TikTok動画URLから動画を取得する
2. 元動画を `source.mp4` として保存する
3. `ffprobe` で動画形式を確認する
4. H.264 / AAC / yuv420p でない場合だけ変換する
5. 変換後を `normalized.mp4` として保存する
6. 変換後に `ffprobe` とデコード検査を行う
7. 後続処理では `normalized.mp4` を使う
8. 元動画は上書きしない
9. 既存の `tiktok_pipeline.py` と `download_tiktok_video()` の互換性を壊さない

今回は顔検出、顔スタンプ、投稿文生成、TikTok投稿APIまでは実装しない。

---

# 1. 今回の手動デバッグで確認できたこと

## 1.1 実行環境

リポジトリ:

```text
~/code/twitter-auto-poster
```

Python仮想環境:

```text
~/code/twitter-auto-poster/python/.venv
```

確認済みツール:

```text
yt-dlp 2026.03.17
ffmpeg 4.4.2
ffprobe 4.4.2
```

実際のパス:

```text
/home/fpxszk/code/twitter-auto-poster/python/.venv/bin/yt-dlp
/usr/bin/ffmpeg
/usr/bin/ffprobe
```

導入手順:

```bash
source python/.venv/bin/activate
python3 -m pip install -U yt-dlp
sudo apt update
sudo apt install -y ffmpeg
```

今後、READMEまたはRUNBOOKへ依存関係として追記すること。

---

## 1.2 テスト結果

実行:

```bash
python3 -m unittest \
  tests.test_tiktok_downloader \
  tests.test_tiktok_download_cli \
  tests.test_tiktok_pipeline
```

結果:

```text
Ran 23 tests
OK
```

途中の以下はエラー系テストの想定ログで、テスト全体は成功している。

```text
[ERROR] boom
[ERROR] Download failed ...
[WARNING] Fetch failed ...
```

---

## 1.3 dry-run確認

使用URL:

```text
https://www.tiktok.com/@man_fuwa/video/7617854844279393556?is_from_webapp=1&sender_device=pc
```

実行:

```bash
TIKTOK_URL='https://www.tiktok.com/@man_fuwa/video/7617854844279393556?is_from_webapp=1&sender_device=pc'

python3 scripts/tiktok/download_video.py \
  --url "$TIKTOK_URL" \
  --output-dir tmp/tiktok-debug/downloads \
  --dry-run true \
  --log-level DEBUG
```

確認結果:

```text
ok: true
video_id: 7617854844279393556
uploader: man_fuwa
download_strategy: metadata-only
message: validated TikTok URL and fetched metadata
```

`dry-run`では動画本体を取得しないため、`width`、`height`、`fps`、`duration_seconds`、`size_bytes`が0でも正常。

---

## 1.4 実ダウンロード確認

実行:

```bash
python3 scripts/tiktok/download_video.py \
  --url "$TIKTOK_URL" \
  --output-dir tmp/tiktok-debug/downloads \
  --dry-run false \
  --log-level DEBUG
```

確認結果:

```text
ok: true
output_path: .../source.mp4
container: mov
video_codec: hevc
audio_codec: aac
width: 1080
height: 1920
fps: 30
duration_seconds: 5
size_bytes: 343785
download_strategy: strategy-1
message: downloaded TikTok video
```

生成物:

```text
download.log
ffprobe.json
metadata.json
result.json
source.info.json
source.mp4
```

TikTok動画取得自体は成功した。

---

## 1.5 判明した問題

`source.mp4` の拡張子は `.mp4` だが、内部の映像コーデックはHEVC/H.265だった。

```text
container: mov
video_codec: hevc
audio_codec: aac
```

Windows標準プレイヤーで再生すると、HEVCビデオ拡張機能の購入画面が表示された。

問題は拡張子ではなく内部コーデックである。

```text
.mp4 = コンテナ
HEVC / H.265 = 映像コーデック
```

Windows互換性、後続の顔加工、TikTok/X投稿互換性を考えると、H.264/AACへ正規化するのが適切。

---

## 1.6 手動変換で成功した内容

実行:

```bash
VIDEO_DIR="tmp/tiktok-debug/downloads/7617854844279393556"

ffmpeg \
  -i "$VIDEO_DIR/source.mp4" \
  -map 0:v:0 \
  -map 0:a? \
  -c:v libx264 \
  -preset medium \
  -crf 18 \
  -pix_fmt yuv420p \
  -c:a aac \
  -b:a 192k \
  -movflags +faststart \
  "$VIDEO_DIR/source_h264.mp4"
```

変換後の確認結果:

```text
video codec: h264
audio codec: aac
pixel format: yuv420p
width: 1080
height: 1920
fps: 30
duration: 5秒
container: MP4互換
```

確認コマンド:

```bash
ffprobe \
  -v error \
  -show_entries \
  format=duration,size,format_name:stream=index,codec_type,codec_name,width,height,pix_fmt,r_frame_rate \
  -of json \
  "$VIDEO_DIR/source_h264.mp4"
```

破損確認:

```bash
ffmpeg \
  -v error \
  -i "$VIDEO_DIR/source_h264.mp4" \
  -f null -
```

エラー出力なし。

Windowsでも `source_h264.mp4` を正常再生できた。

したがって、以下の形式で問題ないことを確認済み。

```text
container: MP4
video codec: H.264
 audio codec: AAC
pixel format: yuv420p
movflags: +faststart
```

---

# 2. 次に実装する内容

## 2.1 処理フロー

```text
TikTok URL
↓
メタデータ取得
↓
動画ダウンロード
↓
source.mp4保存
↓
ffprobeで形式確認
↓
互換形式なら再エンコードしない
↓
非互換形式ならH.264/AACへ変換
↓
normalized.mp4保存
↓
ffprobe再検査
↓
ffmpegデコード検査
↓
result.json更新
```

---

## 2.2 採用する最終形式

```text
ファイル名: normalized.mp4
コンテナ: MP4
映像: H.264 / AVC
音声: AAC
ピクセル形式: yuv420p
解像度: 元動画維持
フレームレート: 元動画維持
Web最適化: movflags +faststart
```

変換パラメータ初期値:

```text
video codec: libx264
preset: medium
CRF: 18
pixel format: yuv420p
audio codec: aac
audio bitrate: 192k
movflags: +faststart
```

---

# 3. 実装ルール

## 3.1 元動画を上書きしない

必ず次の2ファイルを分ける。

```text
source.mp4
normalized.mp4
```

役割:

```text
source.mp4
  TikTokから取得した元ファイル

normalized.mp4
  H.264/AACへ正規化した後続処理用ファイル
```

`source.mp4`は絶対に上書きしない。

---

## 3.2 無条件再エンコードをしない

`ffprobe`で以下をすべて満たす場合は再エンコードしない。

```text
video codec == h264
audio codec == aac または音声なし
pixel format == yuv420p
コンテナがMP4互換
```

この場合は `source.mp4` を `normalized.mp4` へ安全にコピーするか、後続処理が常に同じパスを使える設計にする。

---

## 3.3 再エンコード条件

以下のいずれかに該当する場合はH.264/AACへ変換する。

```text
video codecがhevc / h265
video codecがvp9
video codecがav1
video codecがh264以外
audio codecがaac以外
pixel formatがyuv420p以外
MP4互換コンテナでない
ffprobe結果が不足
```

---

## 3.4 変換方法

基本コマンド:

```bash
ffmpeg \
  -y \
  -i source.mp4 \
  -map 0:v:0 \
  -map 0:a? \
  -c:v libx264 \
  -preset medium \
  -crf 18 \
  -pix_fmt yuv420p \
  -c:a aac \
  -b:a 192k \
  -movflags +faststart \
  normalized.tmp.mp4
```

成功後に原子的に確定する。

```text
normalized.tmp.mp4
↓
検査成功
↓
normalized.mp4
```

失敗時は一時ファイルを削除する。

---

# 4. 変更候補ファイル

```text
scripts/lib/tiktok_downloader.py
scripts/lib/tiktok_video_normalizer.py
scripts/tiktok/download_video.py
tests/test_tiktok_downloader.py
tests/test_tiktok_video_normalizer.py
tests/test_tiktok_download_cli.py
README.md
docs/RUNBOOK.md
```

推奨:

```text
正規化ロジック: scripts/lib/tiktok_video_normalizer.py
CLI統合: scripts/tiktok/download_video.py
既存互換維持: scripts/lib/tiktok_downloader.py
```

既存構成が小さい場合は過剰に分割しない。

---

# 5. 必要な関数

## 5.1 probe_video

```python
def probe_video(path: str | Path) -> dict:
    ...
```

取得項目:

```text
映像コーデック
音声コーデック
pixel format
解像度
fps
duration
container
size
stream情報
```

---

## 5.2 is_normalized_video

```python
def is_normalized_video(metadata: Mapping[str, Any]) -> bool:
    ...
```

条件:

```text
video_codec == "h264"
audio_codec in {"aac", ""}
pix_fmt == "yuv420p"
container is MP4 compatible
```

---

## 5.3 normalize_video

```python
def normalize_video(
    source_path: str | Path,
    output_path: str | Path,
    *,
    crf: int = 18,
    preset: str = "medium",
    audio_bitrate: str = "192k",
) -> Path:
    ...
```

役割:

```text
ffmpeg存在確認
一時ファイルへ変換
stdout/stderr保存
変換後ffprobe
デコード検査
成功後に確定
失敗時一時ファイル削除
元ファイル保持
```

---

## 5.4 ensure_normalized_video

```python
def ensure_normalized_video(
    source_path: str | Path,
    output_dir: str | Path,
    *,
    force: bool = False,
) -> dict:
    ...
```

戻り値例:

```json
{
  "ok": true,
  "source_path": ".../source.mp4",
  "normalized_path": ".../normalized.mp4",
  "normalization_required": true,
  "normalization_reused": false,
  "source_video_codec": "hevc",
  "normalized_video_codec": "h264",
  "source_audio_codec": "aac",
  "normalized_audio_codec": "aac",
  "normalized_pix_fmt": "yuv420p",
  "duration_seconds": 5.0,
  "width": 1080,
  "height": 1920,
  "fps": 30.0
}
```

---

# 6. CLIへ追加する項目

追加候補引数:

```text
--normalize true|false
--normalize-force
--normalize-crf 18
--normalize-preset medium
--normalize-audio-bitrate 192k
```

推奨既定値:

```text
--normalize true
--normalize-crf 18
--normalize-preset medium
--normalize-audio-bitrate 192k
```

`dry-run true`では実変換しない。

---

# 7. result.jsonへ追加する項目

```json
{
  "source_path": ".../source.mp4",
  "normalized_path": ".../normalized.mp4",
  "normalization_enabled": true,
  "normalization_required": true,
  "normalization_performed": true,
  "normalization_reused": false,
  "source_container": "mov",
  "source_video_codec": "hevc",
  "source_audio_codec": "aac",
  "source_pix_fmt": "...",
  "normalized_container": "mov,mp4,m4a,3gp,3g2,mj2",
  "normalized_video_codec": "h264",
  "normalized_audio_codec": "aac",
  "normalized_pix_fmt": "yuv420p",
  "normalized_width": 1080,
  "normalized_height": 1920,
  "normalized_fps": 30.0,
  "normalized_duration_seconds": 5.0,
  "normalized_size_bytes": 2286250,
  "normalization_log_path": ".../normalize.log",
  "normalized_ffprobe_json_path": ".../normalized.ffprobe.json"
}
```

既存キーは削除しない。

---

# 8. 生成物構成

```text
tmp/tiktok-debug/downloads/<video_id>/
├── source.mp4
├── source.info.json
├── metadata.json
├── ffprobe.json
├── normalized.mp4
├── normalized.ffprobe.json
├── download.log
├── normalize.log
└── result.json
```

---

# 9. 変換後の検査

## 9.1 ffprobe検査

必須確認:

```text
video codec == h264
audio codec == aac または音声なし
pix_fmt == yuv420p
width > 0
height > 0
duration > 0
size > 0
```

## 9.2 デコード検査

```bash
ffmpeg \
  -v error \
  -i normalized.mp4 \
  -f null -
```

stderrにエラーがあれば失敗扱い。

## 9.3 前後比較

```text
source.duration と normalized.duration の差が0.1秒以内
source.width == normalized.width
source.height == normalized.height
fpsが大きく変わっていない
音声有無が維持されている
```

---

# 10. エラーコード

```text
FFMPEG_NOT_INSTALLED
FFPROBE_NOT_INSTALLED
SOURCE_PROBE_FAILED
NORMALIZATION_FAILED
NORMALIZED_OUTPUT_NOT_FOUND
NORMALIZED_PROBE_FAILED
NORMALIZED_VIDEO_CODEC_INVALID
NORMALIZED_AUDIO_CODEC_INVALID
NORMALIZED_PIXEL_FORMAT_INVALID
NORMALIZED_DECODE_FAILED
NORMALIZED_DURATION_MISMATCH
NORMALIZED_DIMENSION_MISMATCH
```

失敗時は後続処理へ進まない。

---

# 11. テスト項目

## 11.1 単体テスト

追加:

```text
tests/test_tiktok_video_normalizer.py
```

最低限:

```text
ffmpeg未インストール
ffprobe未インストール
sourceファイルなし
probe成功
probe失敗
H.264/AAC/yuv420pは再変換不要
HEVCは変換対象
VP9は変換対象
AV1は変換対象
AAC以外は変換対象
yuv420p以外は変換対象
音声なし動画
変換成功
変換失敗
一時ファイル削除
normalized.mp4再利用
--forceで再変換
デコード検査成功
デコード検査失敗
duration差検出
解像度差検出
```

## 11.2 CLIテスト

```text
dry-runでは変換しない
normalize=trueで正規化
normalize=falseでsourceのみ
result.jsonに正規化情報追加
既存source再利用時も正規化判定
Cookie引数をログへ出さない
```

## 11.3 回帰テスト

```bash
python3 -m unittest \
  tests.test_tiktok_downloader \
  tests.test_tiktok_video_normalizer \
  tests.test_tiktok_download_cli \
  tests.test_tiktok_pipeline
```

---

# 12. 手動確認手順

## 12.1 実行

```bash
TIKTOK_URL='https://www.tiktok.com/@man_fuwa/video/7617854844279393556?is_from_webapp=1&sender_device=pc'

python3 scripts/tiktok/download_video.py \
  --url "$TIKTOK_URL" \
  --output-dir tmp/tiktok-debug/downloads \
  --dry-run false \
  --force \
  --normalize true \
  --log-level DEBUG
```

## 12.2 生成物確認

```bash
find tmp/tiktok-debug/downloads/7617854844279393556 \
  -type f \
  -printf '%f  %s bytes\n' \
  | sort
```

期待:

```text
source.mp4
normalized.mp4
normalized.ffprobe.json
normalize.log
```

## 12.3 ffprobe確認

```bash
VIDEO_DIR="tmp/tiktok-debug/downloads/7617854844279393556"

ffprobe \
  -v error \
  -show_entries \
  format=duration,size,format_name:stream=index,codec_type,codec_name,width,height,pix_fmt,r_frame_rate \
  -of json \
  "$VIDEO_DIR/normalized.mp4"
```

期待:

```text
codec_name: h264
codec_name: aac
pix_fmt: yuv420p
width: 1080
height: 1920
r_frame_rate: 30/1
duration: 5秒
```

## 12.4 デコード検査

```bash
ffmpeg \
  -v error \
  -i "$VIDEO_DIR/normalized.mp4" \
  -f null -
```

エラー出力なしを確認。

## 12.5 Windows再生確認

```bash
explorer.exe "$(wslpath -w "$VIDEO_DIR")"
```

`normalized.mp4`をWindows標準プレイヤーで開き、HEVC拡張機能購入画面が出ず、映像・音声が正常であることを確認する。

---

# 13. 今回CLIに実施させる範囲

実施する:

```text
ffprobe形式判定
H.264/AAC/yuv420p判定
必要時だけffmpeg変換
normalized.mp4生成
変換後再検査
デコード検査
result.json拡張
ログ保存
単体テスト
既存テスト維持
README/RUNBOOK更新
```

実施しない:

```text
顔検出
顔追跡
スタンプ合成
文字起こし
投稿文生成
TikTok公式API投稿
GitHub Actions変更
自動スケジュール
```

---

# 14. CLIへ渡す実装指示

```text
この計画書を読み、TikTok動画取得後のH.264正規化処理を実装してください。

今回の手動検証で、TikTok動画の取得には成功しましたが、取得したsource.mp4の映像コーデックがHEVCで、Windows標準プレイヤーでは有料のHEVC拡張機能を要求されました。

手動で以下へ変換したところ、Windowsで正常再生できることを確認済みです。

- container: MP4
- video codec: H.264 / libx264
- audio codec: AAC
- pixel format: yuv420p
- preset: medium
- CRF: 18
- audio bitrate: 192k
- movflags: +faststart
- resolution: 1080x1920維持
- fps: 30維持
- duration: 5秒維持

まず既存のscripts/lib/tiktok_downloader.py、scripts/tiktok/download_video.py、tests関連を確認してください。

実装要件:

1. source.mp4は上書きしない
2. 変換後はnormalized.mp4として保存する
3. ffprobeでsource.mp4を確認する
4. video=h264、audio=aacまたは音声なし、pix_fmt=yuv420p、MP4互換の場合は再エンコードしない
5. 条件不一致の場合だけffmpegでH.264/AAC/yuv420pへ変換する
6. 一時ファイルへ出力し、検査成功後にnormalized.mp4へ確定する
7. 変換後にffprobeで再検査する
8. ffmpeg -v error -i normalized.mp4 -f null -でデコード検査する
9. duration、width、height、fps、音声有無をsourceと比較する
10. result.jsonへsourceとnormalizedの情報を追加する
11. normalize.logとnormalized.ffprobe.jsonを保存する
12. dry-runでは動画変換しない
13. 既存のdownload_tiktok_video()互換とtiktok_pipeline.py互換を壊さない
14. 既存テストをすべて通す
15. 正規化処理の単体テストを追加する
16. READMEまたはRUNBOOKへyt-dlp、ffmpeg、ffprobeの依存関係と確認手順を追記する

今回の実装では、顔検出、顔スタンプ、投稿文生成、TikTok投稿API、GitHub Actions変更は行わないでください。

実装後は、変更ファイル、テスト結果、手動確認コマンド、未解決事項を日本語で報告してください。
```

---

# 15. 完了条件

```text
[ ] source.mp4が保持される
[ ] normalized.mp4が生成される
[ ] normalized.mp4の映像がH.264
[ ] 音声がAACまたは音声なし
[ ] pix_fmtがyuv420p
[ ] 解像度が維持される
[ ] fpsが維持される
[ ] durationが維持される
[ ] ffprobe検査成功
[ ] デコード検査成功
[ ] Windowsで追加コーデックなしで再生可能
[ ] 不要な再エンコードをしない
[ ] 既存source再利用に対応
[ ] force再変換に対応
[ ] result.jsonに正規化結果が入る
[ ] normalize.logが保存される
[ ] 既存テストが通る
[ ] 新規テストが通る
[ ] 既存tiktok_pipeline.py互換を維持
```

---

# 16. 次フェーズ

この実装と手動確認が完了した後、次へ進む。

```text
Phase 3: 顔検出のみ
↓
Phase 4: 顔追跡とスタンプ合成
↓
Phase 5: 投稿文候補生成
↓
Phase 6: dry-run統合
↓
Phase 7: TikTok公式API投稿
```

今回の作業では、H.264正規化までで止めること。
