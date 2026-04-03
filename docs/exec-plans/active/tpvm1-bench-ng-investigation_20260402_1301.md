# TPVM1 ベンチ NG 調査計画

## 背景

`Falcon_script/` 配下の TPVM1 変換後資材について、手動デバッグでは画像通信が通る一方、自動検査ベンチ経由では `startup` 自体は完了しているように見えるのに TPVM1 系が NG になる。

今回の主眼は、**どのファイルが実際にベンチで読まれているのかを特定し、手動結果とベンチ結果の差分、および FR/H7 の TPVM1 関連設定漏れや変換漏れを切り分けること**にある。  
GitHub 連携やコミット運用は今回のスコープ外とする。

## 現時点の確認結果

### ログ比較

- 手動デバッグ結果
  - `debug_result/手動デバック結果/192.168.0.3_20260402_190520.log`
  - `debug_result/手動デバック結果/192.168.0.4_20260402_190516.log`
  - `debug_result/手動デバック結果/対向機.txt`
- 検査ベンチ結果
  - `debug_result/検査ベンチ結果/20260402_194158_ASSY/20260402_193942_00000000000000000000000000_ETH_base.log`
  - `debug_result/検査ベンチ結果/20260402_194158_ASSY/20260402_193942_00000000000000000000000000_ETH_mid.log`
  - `debug_result/検査ベンチ結果/20260402_194158_ASSY/PCS52@FR@JP0397010063@V2@DESKTOP-D4DJOKQ@2026-0402-193941.csv`

### 重要な事実

- 手動 base 側では `./mipi base input base_rx1t` に対して `DMC OK`
- 手動 mid 側では `./mipi mid input base_rx1t` に対して `TPVM1 OK`
- ベンチ base 側では `./mipi base input base_rx1t` に対して `DMC pix error` → `DMC NG`
- ベンチ mid 側では `./mipi mid input base_rx1t` に対して
  - `devdrv_vin_startcapture(TPVM1-Bed) error`
  - `devdrv_vin_startcapture(TPVM1-Wifi) error`
  - `TPVM1-Bed/Wifi NG`
- ベンチ CSV では
  - `720,B_TPVM1,...,Data=0,...,LO`
  - `720,M_TPVM1,...,Data=0,...,LO`
  - `750,TPVM1_POC,...,8.985,...,HI`

### 実際にベンチが参照している場所

ベンチ結果 CSV より、実際に参照されているのは `dst/` ではなく次の系統。

- `PgInfoFileDirectory = C:\TesterRoot\PgDebug\Falcon\Info\PCS52\FR`
- `PgInfoFileName = PCS52@FR@JP0397010063@V2.falcon`

つまり、以後の本調査で優先すべき対象は **`PgDebug/Falcon/Info` / `PgDebug/Falcon/Script`** 側であり、`dst/` は比較対象であって本番参照先ではない。

### FR/H7 で見つかった差分

- ベンチで使われる `PgDebug/Falcon/Script/PCS52/FR/PCS52@FR@JP039701-H7@V2.script`
- 比較対象の `PgDebug/Falcon/dst/Script/PCS52/FR/PCS52@FR@JP039701-H7@V2.script`

上記比較で、使われている `Script` 側には次の変換漏れ候補がある。

- `MEAS_IMAGE_POC("GVIF1-2");`
  - `dst` 側では `MEAS_IMAGE_POC("GVIF1-3");`

TPVM1 が `GVIF1-3` に寄っている他箇所と整合しないため、**使われている本番側 script が stale / partially transformed である可能性が高い**。

### TPVM1 応答定義の怪しい点

ベンチで使われる `PgDebug/Falcon/Script/PCS52/Common/ADU/Ether_IF_3TEMP_H7@V2.h` では:

- `CMD_B_TPVM1_mipi = "mipi base input base_rx1t"`
- `RES_B_TPVM1_mipi = "[mipi]T-PVM1 OK"`
- `CMD_M_TPVM1_mipi = "mipi mid input base_rx1t"`
- `RES_M_TPVM1_mipi = "[mipi]T-PVM1 OK"`

一方で手動ログ上の成功応答は少なくとも次の形。

- base: `[mipi][input]DMC OK`
- mid: `[mipi][input]TPVM1 OK`

よって **TPVM1 変換後の期待応答文字列が実ログと噛み合っていない可能性**がある。

## 仮説（有力順）

1. **実運用側の `PgDebug/Falcon/Script` が `dst/` と一致しておらず、TPVM1 変換が取り切れていない**
   - 具体例: `MEAS_IMAGE_POC("GVIF1-2")` が残っている
   - ベンチは `dst/` ではなく `PgDebug/Falcon/Info` / `Script` を読んでいる

2. **ベンチ時は TPVM1 チャネルの画像入力自体が本当に失敗している**
   - base: `DMC pix error`
   - mid: `devdrv_vin_startcapture(TPVM1-Bed/Wifi) error`
   - API 出力設定・起動順・TPVM1 側のチャネル割り当て・実行対象 script の組み合わせが不整合の可能性

3. **手動とベンチで SerDes / 画像系の安定化待ち時間が足りていない**
   - 手動ログは `init` 後に画像系確認まで比較的長い待ち時間がある
   - ベンチ script 側には `WAIT(3000)` が散見され、TPVM1 系では 3 秒待ちのまま入力判定へ入っている
   - TPVM1 系の startup / capture が手動時より早く評価され、NG 化している可能性がある

4. **TPVM1 用の期待応答文字列が実機ログと不一致**
   - `RES_*_TPVM1_mipi = "[mipi]T-PVM1 OK"` だが、確認できた成功ログは `[mipi][input]TPVM1 OK` または `DMC OK`
   - 特に `"[input]"` 欠落とラベル差がある
   - そのため、実際に画像が通っても判定だけ NG になる可能性がある

5. **API の固定設定自体は存在するが、手動時とベンチ時で同じ初期化系列が踏まれていない**
   - `対向機.txt` では `gvif_startupAPI`, `gvif_connectDevice`, `gvif_initialize`, `gvif_setOutImage`, `gvif_startOutputImage` が成功
   - ベンチ側で同等の API ログが見えておらず、比較材料が不足

6. **TPVM1_POC の異常値が別系統の不具合として併発している**
   - ベンチ CSV で `TPVM1_POC = 8.985V`、上限 `8.640V` を超えている
   - これは Step 720 の通信 NG とは別に、TPVM1 系統の物理側異常を示している可能性がある

## 変更・調査対象ファイル

### 優先調査対象

- `Falcon_script/debug_result/手動デバック結果/192.168.0.3_20260402_190520.log`
- `Falcon_script/debug_result/手動デバック結果/192.168.0.4_20260402_190516.log`
- `Falcon_script/debug_result/手動デバック結果/対向機.txt`
- `Falcon_script/debug_result/検査ベンチ結果/20260402_194158_ASSY/20260402_193942_00000000000000000000000000_ETH_base.log`
- `Falcon_script/debug_result/検査ベンチ結果/20260402_194158_ASSY/20260402_193942_00000000000000000000000000_ETH_mid.log`
- `Falcon_script/debug_result/検査ベンチ結果/20260402_194158_ASSY/PCS52@FR@JP0397010063@V2@DESKTOP-D4DJOKQ@2026-0402-193941.csv`
- `Falcon_script/PgDebug/Falcon/Info/PCS52/FR/PCS52@FR@JP0397010063@V2.falcon`
- `Falcon_script/PgDebug/Falcon/Script/PCS52/FR/PCS52@FR@JP039701-H7@V2.script`
- `Falcon_script/PgDebug/Falcon/Script/PCS52/Common/ADU/Ether_IF_3TEMP_H7@V2.h`
- `Falcon_script/PgDebug/Falcon/Script/PCS52/PCS52@01@V2.tii`
- `Falcon_script/PgDebug/Falcon/Script/PCS52/FR/Part/PCS52@FR@JP039701-H7@Comm@V1.h`
- `Falcon_script/PgDebug/Falcon/Script/PCS52/FR/Part/PCS52@FR@JP039701-H7@Std@V2.h`

### 比較対象

- `Falcon_script/PgDebug/Falcon/dst/Script/PCS52/FR/PCS52@FR@JP039701-H7@V2.script`
- `Falcon_script/PgDebug/Falcon/dst/Script/PCS52/Common/ADU/Ether_IF_3TEMP_H7@V2.h`
- `Falcon_script/PgDebug/Falcon/modify_script.py`
- `Falcon_script/IMG/010_Setparams/SetParams_MM.csv`
- `Falcon_script/IMG/020_setOutputImage/ImageSetting_TPVM1_OUT.csv`
- `Falcon_script/Driver/Device.cfg`
- `Falcon_script/Tester.cfg`

### 後で修正候補になりうるファイル

- `Falcon_script/PgDebug/Falcon/Script/PCS52/FR/PCS52@FR@JP039701-H7@V2.script`
- `Falcon_script/PgDebug/Falcon/Script/PCS52/Common/ADU/Ether_IF_3TEMP_H7@V2.h`
- 必要なら `Falcon_script/PgDebug/Falcon/modify_script.py`

## 実装 / 調査ステップ

- [ ] ベンチが `dst/` ではなく `PgDebug/Falcon/Info` / `Script` を読んでいる前提を、関連 `.falcon` と CSV で確定する
- [ ] 手動ログとベンチログで、`base_rx1t` / TPVM1 周辺の応答差分を時系列で整理する
- [ ] `PgDebug/Falcon/Script/...H7@V2.script` と `dst/...H7@V2.script` を比較し、TPVM1 変換漏れを列挙する
- [ ] `.falcon` → `script` → `Common/ADU/Ether_IF_3TEMP_H7@V2.h` の参照/include 経路を確認する
- [ ] `H7@V2.script` 内の `ETH_BASE_CHKRECV(RES_B_TPVM1_mipi, ...)` / `ETH_MID_CHKRECV(RES_M_TPVM1_mipi, ...)` の評価経路を確認する
- [ ] `Ether_IF_3TEMP_H7@V2.h` の `CMD_*` / `RES_*` 定義が実ログに合っているか確認する
- [ ] `.tii` の GVIF IP / port / channel 割り当てと、script 側の `GVIF1-*` 利用箇所を付き合わせる
- [ ] 手動ログと bench script の待ち時間差（`WAIT(3000)` など）が TPVM1 startup / capture に影響しうるか確認する
- [ ] API 側の初期化・画像出力設定が手動時とベンチ時で同じ前提かを、残っているログから確認する
- [ ] 原因が script 側の変換漏れか、期待応答の不一致か、ベンチ時の実行条件差かを切り分ける
- [ ] 切り分け結果に応じて、修正対象を `Script` 実運用側・変換ロジック・両方のどれにするか決める

## スコープ

### 対象

- TPVM1 関連の FR/H7 実運用 script / info / common header
- 手動デバッグ結果と検査ベンチ結果の比較
- TPVM1 に関係する API / GVIF / 画像設定 / 応答文字列の整合性

### スコープ外

- GitHub 操作、コミット、プッシュ
- Twitter auto poster 側コード
- TPVM1 と無関係な他家系全体の横断修正
- 実機側ファームや外部 API 実装自体の変更

## TDD / テスト方針

今回はまず原因調査が主目的なので、最初のフェーズは RED/GREEN の前段階である**観測と切り分け**を優先する。  
実際にコード修正へ進む場合は、少なくとも次の順で進める。

1. **RED**
   - 変換漏れまたは期待応答ミスマッチを再現条件として固定
   - 必要なら差分比較用の最小検証観点を作る
2. **GREEN**
   - 実運用側 script / header / 変換ロジックの最小修正で TPVM1 判定を正しい状態に寄せる
3. **REFACTOR**
   - `dst/` と実運用 `Script` の乖離が再発しないように整理する

## バリデーション方針

既存の自動テスト基盤はこの Falcon_script 配下では確認できていないため、主な検証は次の観点で行う。

- 手動ログとベンチログの TPVM1 応答差分確認
- `.falcon` が実際に指している script / header の確認
- `Script` 実運用側と `dst` の差分確認
- ベンチ結果 CSV の `720` / `750` 系ステップ値の改善確認

### 仮説ごとの採否条件

- **変換漏れ仮説を採用する条件**
  - 実運用 `Script` と `dst` の TPVM1 関連差分が、ベンチ症状と対応している

- **実入力失敗仮説を採用する条件**
  - `capture error` / `pix error` が判定前段で再現しており、応答文字列変更だけでは説明できない

- **期待応答文字列不一致仮説を採用する条件**
  - 画像入力成功相当のログがあるのに、Falcon 側判定だけ NG になる

- **待ち時間不足仮説を採用する条件**
  - 手動では成功する同一コマンドが、bench script の短い待ち時間直後だけ失敗している

## リスク

- **実際に読まれているファイルを `dst/` と誤認したまま修正してしまう**
  - 対策: `.csv` / `.falcon` で参照先を先に固定する

- **TPVM1 ラベル変更と実チャネル変更が混在しており、一部だけ直して別箇所を壊す**
  - 対策: script と common header と `.tii` をセットで確認する

- **ログに API 実行痕跡が十分残っておらず、手動 / ベンチ差を断定しきれない**
  - 対策: まず残ログで確定できる事実と未確定事項を分ける

## 競合確認

`docs/exec-plans/active/` には既存の別タスク計画があるが、今回の対象は `Falcon_script/` 配下のみであり、直接の競合はない。
