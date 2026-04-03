# 調査計画: TPVM1 検査ベンチ NG / 手動デバッグ OK 問題

**作成日時:** 2026-04-02 22:08  
**種別:** 調査・分析のみ（コード変更なし）  
**対象:** `Falcon_script/` 配下の TPVM1 関連スクリプト・設定・ログ  
**既存計画との重複:** なし（active/ にある falcon-readme-overhaul, falconscript-readme-overview はドキュメント系のみ）

---

## 1. 問題の要約

**現象:** FR ファミリ H7 ターゲット (`PCS52@FR@JP039701-H7@V2`) の検査ベンチ自動実行で、TPVM1 関連の以下2ステップが NG となる。一方、手動デバッグ（対向機ツール + V4X ボードへの手動コマンド）では同じシーケンスが成功する。

| ステップ | テスト項目 | ベンチ結果 | 手動結果 |
|----------|-----------|-----------|---------|
| 720 | B_TPVM1 (base board mipi input) | **LO (=0, NG)** | OK |
| 720 | M_TPVM1 (mid board mipi input) | **LO (=0, NG)** | OK |
| 750 | TPVM1_POC (POC電圧測定) | **HI (8.985V > 上限 8.640V)** | 未測定 |

---

## 2. 調査で発見したエビデンス

### 2.1 ベンチテスト ETH ログの実際のレスポンス

**Base board** (`ETH_base.log` Step 720):
```
send : ./mipi base input base_rx1t
[mipi][input][DMC]DMC pix error.
[mipi][input]DMC NG
```
→ base board の `base_rx1t` は **DMC** チャネルを検査している。そもそも TPVM1 ではない。

**Mid board** (`ETH_mid.log` Step 720):
```
send : ./mipi mid input base_rx1t
[mipi][input][TPVM1-Bed]devdrv_vin_startcapture(TPVM1-Bed) error
[mipi][input][TPVM1-Wifi]devdrv_vin_startcapture(TPVM1-Wifi) error
[mipi][input]TPVM1-Bed/Wifi NG
```
→ mid board の VIN (Video Input) キャプチャ自体が失敗。GVIF からの映像入力がない。

### 2.2 手動デバッグの成功レスポンス

**対向機 (192.168.1.100):**
- `gvif_setOutImage(Channel:3, TPVM1_OUT.csv)` → **0x0 (成功)**
- `gvif_startOutputImage(Channel:3, Mode:0)` → **0x0 (成功)**

**Base board (192.168.0.3):**
```
./mipi base input base_rx1t → [mipi][input]DMC OK
```

**Mid board (192.168.0.4):**
```
./mipi mid input base_rx1t → [mipi][input]TPVM1 OK
```

### 2.3 レスポンス文字列パターン不一致（二次的問題）

`Ether_IF_3TEMP_H7@V2.h` の定義比較:

| 定数名 | 定義値 | 実ファーム出力 | 不一致点 |
|--------|--------|--------------|---------|
| `RES_B_TPVM1_mipi` (L.600) | `"[mipi]T-PVM1 OK"` | `"[mipi][input]DMC OK"` | `[input]`欠落 + チャネル名違い + ダッシュ |
| `RES_M_TPVM1_mipi` (L.602) | `"[mipi]T-PVM1 OK"` | `"[mipi][input]TPVM1 OK"` | `[input]`欠落 + `T-PVM1` vs `TPVM1` |
| `RES_B_Trailer_mipi` (L.316) | `"[mipi][input]T-PVM1 OK"` | `"[mipi][input]DMC OK"` | `[input]`あり、しかしチャネル名違い |
| 他チャネル例: `RES_B_FCM_mipi` (L.310) | `"[mipi][input]FCM OK"` | `"[mipi][input]FCM OK"` | **一致** ✓ |

**要注意:** `RES_B_TPVM1_mipi` / `RES_M_TPVM1_mipi` は他の全チャネル (`FCM`, `DMC`, `PVM_*`) と異なり `[input]` が抜けている。さらに `T-PVM1` (ダッシュあり) は実ファーム出力 `TPVM1` (ダッシュなし) と不一致。

### 2.4 GVIF 接続の不安定性

`DESKTOP-D4DJOKQ_GVIF3-Eth.csv`:
- 2025年6月17日に `gvif_connectDevice socket connect error` が連続30回以上記録
- GVIF 対向機への TCP 接続が不安定な履歴あり

### 2.5 スクリプトのタイミング

H7 スクリプト (`PCS52@FR@JP039701-H7@V2.script`) のフロー:
1. L.926-981: `OUTPUT_IMAGE_SET` + `IMAGE_OUTPUT` で全チャネルの画像出力を開始
2. L.983: `WAIT(3000)` — 3秒の待機
3. L.985-1068: Step 625 - スタートアップシーケンス完了確認
4. L.3483-3657: Step 720 - `mipi input` による映像受信確認 (ベンチタイムスタンプ: 約85秒後)

ベンチログでは IMAGE_OUTPUT から Step 720 まで約45秒あるが、VIN キャプチャが失敗している。

### 2.6 Base board の `base_rx1t` チャネルマッピング

手動デバッグログ・ベンチログ共に、base board の `mipi base input base_rx1t` は **DMC** を返す。
しかしスクリプトは `CMD_B_TPVM1_mipi = "mipi base input base_rx1t"` で `RES_B_TPVM1_mipi = "[mipi]T-PVM1 OK"` を期待。

→ base board 上では `base_rx1t` は DMC チャネルにマッピングされており、TPVM1 のレスポンスは返らない。

---

## 3. 仮説（確度順）

### H1: GVIF 画像出力がベンチで正常に開始されていない ★最有力★
- **根拠:** mid board の `devdrv_vin_startcapture` エラーは「映像入力が来ていない」ことを示す
- **根拠:** GVIF 接続エラー履歴あり
- **確認方法:** ベンチ実行中の GVIF DLL ログを取得し、`gvif_connectDevice` / `OUTPUT_IMAGE_SET` / `IMAGE_OUTPUT` の戻り値を確認

### H2: SerDes リンク安定化のタイミング不足
- **根拠:** CXD4966 スタートアップは完了しているが、画像転送の安定には追加時間が必要な可能性
- **根拠:** 手動デバッグでは対向機ツールで画像出力開始後、十分な時間を置いてから mipi input を実行
- **確認方法:** `WAIT(3000)` を増やして再テスト、または Step 720 前に追加待機を挿入

### H3: `base_rx1t` のチャネルマッピング問題（Base board 側）
- **根拠:** base board の `base_rx1t` は DMC を返すが、スクリプトは TPVM1 のレスポンスを期待
- **影響:** B_TPVM1 は常に NG になる（DMC OK でも `[mipi]T-PVM1 OK` にマッチしない）
- **確認方法:** `CMD_B_TPVM1_mipi` のコマンドまたは `RES_B_TPVM1_mipi` のレスポンスパターンが正しいか確認

### H4: レスポンスパターン文字列の不一致
- **根拠:** `[mipi]T-PVM1 OK` vs 実際の `[mipi][input]TPVM1 OK`（`[input]` 欠落 + ダッシュ不一致）
- **影響:** 仮に VIN キャプチャが成功しても `ETH_BASE_CHKRECV` / `ETH_MID_CHKRECV` でマッチしない
- **確認方法:** `CHKRECV` 関数の部分一致 vs 完全一致のロジックを確認

### H5: TPVM1_POC 電圧異常（ハードウェア問題）
- **根拠:** POC 電圧 8.985V が上限 8.640V を超過
- **影響:** 高 POC 電圧は SerDes リンク品質に影響する可能性
- **確認方法:** ベンチの物理配線・終端抵抗・POC 回路の確認（ソフトウェア外のスコープ）

---

## 4. 調査対象ファイル一覧

### 最優先（確認必須）

| ファイル | 調査内容 |
|---------|---------|
| `PgDebug/Falcon/Script/PCS52/Common/ADU/Ether_IF_3TEMP_H7@V2.h` | L.599-602: `RES_B/M_TPVM1_mipi` のパターン修正候補 |
| `PgDebug/Falcon/Script/PCS52/FR/PCS52@FR@JP039701-H7@V2.script` | L.3528-3657: Step 720 の TPVM1 チェックロジック |
| `debug_result/検査ベンチ結果/20260402_194158_ASSY/20260402_193942_*_ETH_*.log` | ベンチ実行時の実レスポンス |
| `debug_result/手動デバック結果/対向機.txt` | 手動デバッグの GVIF API コール記録 |
| `debug_result/手動デバック結果/192.168.0.{3,4}_*.log` | 手動デバッグの V4X レスポンス |

### 二次優先（関連確認）

| ファイル | 調査内容 |
|---------|---------|
| `PgDebug/Falcon/Script/PCS52/Common/ADU/Ether_IF_3TEMP_H6@V2.h` | H6 との差分確認（H6 も同じ問題がないか） |
| `PgDebug/Falcon/Script/PCS52/FR/Part/PCS52@FR@JP039701-H7@Std@V2.h` | L.418,425,445: 判定基準値 |
| `PgDebug/Falcon/Script/PCS52/Common/LocalMacros@V32.h` | `OUTPUT_IMAGE_SET`, `IMAGE_OUTPUT` マクロ定義 |
| `PgDebug/Falcon/Script/PCS52/Common/InitMacros@V24.h` | `GVIF_INIT` マクロ定義 |
| `IMG/020_setOutputImage/ImageSetting_TPVM1_OUT.csv` | TPVM1 画像出力設定 |
| `DESKTOP-D4DJOKQ_GVIF3-Eth.csv` | GVIF 接続エラー履歴 |
| `Tester.cfg` | テスター基本設定（Debug モード設定等） |

### 将来修正候補ファイル

| ファイル | 修正内容候補 |
|---------|-------------|
| `PgDebug/Falcon/Script/PCS52/Common/ADU/Ether_IF_3TEMP_H7@V2.h` L.600 | `RES_B_TPVM1_mipi` を `"[mipi][input]TPVM1 OK"` または適切な値に修正 |
| `PgDebug/Falcon/Script/PCS52/Common/ADU/Ether_IF_3TEMP_H7@V2.h` L.602 | `RES_M_TPVM1_mipi` を `"[mipi][input]TPVM1 OK"` または適切な値に修正 |
| `PgDebug/Falcon/Script/PCS52/Common/ADU/Ether_IF_3TEMP_H6@V2.h` L.600,602 | H6 にも同じ修正が必要な場合 |
| `PgDebug/Falcon/Script/PCS52/FR/PCS52@FR@JP039701-H7@V2.script` | Step 720 前の WAIT 時間調整・エラーハンドリング追加 |
| `PgDebug/Falcon/modify_script.py` | src→dst 変換で TPVM1 パターンが適切にパッチされているか確認 |

---

## 5. 調査ステップ

### Phase 1: ルートコーズ特定（ソフトウェア側）

- [ ] **1-1.** `ETH_BASE_CHKRECV` / `ETH_MID_CHKRECV` の部分一致ロジックを `Functions@V33.h` または `LocalMacros@V32.h` で確認し、`[mipi]T-PVM1 OK` が `[mipi][input]TPVM1 OK` にマッチするかどうか確定する
- [ ] **1-2.** base board の `base_rx1t` が DMC を返す仕様を確認。V4X ファームウェアの `mipi` コマンドの引数 `base_rx1t` がどのチャネルにマッピングされるかドキュメント等で確認
- [ ] **1-3.** `RES_B_TPVM1_mipi` の base board 側が本来何を期待すべきか（DMC OK なら DMC 判定ステップと重複していないか）を確認
- [ ] **1-4.** ベンチ実行中の GVIF DLL ログ (`dlllog-api.txt`) の 2026/04/02 付近のエントリを確認し、`gvif_connectDevice` / `gvif_setOutImage` / `gvif_startOutputImage` が成功しているか確認
- [ ] **1-5.** `modify_script.py` が src→dst 変換時に `RES_B_TPVM1_mipi` / `RES_M_TPVM1_mipi` を変更していないか diff で確認

### Phase 2: タイミング検証

- [ ] **2-1.** 手動デバッグのタイムライン整理: 対向機の `gvif_startOutputImage(Ch:3)` 完了時刻 (19:08:20) → mid board の `mipi input base_rx1t` 実行時刻 (19:10:51) = **約2分31秒**
- [ ] **2-2.** ベンチのタイムライン整理: `IMAGE_OUTPUT("GVIF1-3")` 完了推定時刻 → Step 720 の `mipi mid input base_rx1t` 実行時刻 (92.824s) との差分
- [ ] **2-3.** ベンチの Step 625 で `CXD4966(Des_FRONT, T-PVM1) スタートアップシーケンス完了` が出るタイミング (42.270s) から Step 720 (85-93s) までの間隔が十分か確認

### Phase 3: 修正方針策定

- [ ] **3-1.** `RES_B_TPVM1_mipi` / `RES_M_TPVM1_mipi` の正しいパターンを特定し修正案を作成
- [ ] **3-2.** base board の `B_TPVM1` 判定が意味のあるテストかどうか評価（DMC を返すなら判定ロジックの再設計が必要）
- [ ] **3-3.** GVIF 画像出力の安定性向上策（WAIT 延長、retry、ステータス確認追加等）を検討
- [ ] **3-4.** `TPVM1_POC` 上限値 (8.640V) が H7 ターゲットに適切かどうか確認（他グレードとの比較）

---

## 6. スコープ

### スコープ内
- Falcon スクリプト (`PgDebug/Falcon/Script/PCS52/`) のソフトウェア分析
- ETH ログ・デバッグ結果の比較分析
- GVIF API 関連の設定・ログ分析
- レスポンスパターン定義の正確性検証
- `modify_script.py` の変換ロジック確認

### スコープ外
- ハードウェア（基板・配線・コネクタ）の物理的検査
- V4X ファームウェア (`mipi`, `init` コマンド) のソースコード分析
- GVIF DLL (`ADU_DLL.dll`) のソースコード分析
- CXD4966/CXD4964/CXD4967 SerDes IC のレジスタレベル分析
- 他ファミリ (FH, FL, ETH) の同等問題調査（FR のみ対象）
- 実機でのテスト実行（調査計画の策定のみ）

---

## 7. テスト・検証アプローチ

### ソフトウェア検証（実機不要）
1. `CHKRECV` のマッチングロジックをコードレビューし、パターン不一致の影響を確認
2. 全 Ether_IF ヘッダ (H1-H7) の `RES_*_TPVM1_mipi` 定義の一貫性を確認
3. `modify_script.py` の src→dst 変換後の diff で意図しない変更がないか検証

### 実機検証（将来実施）
1. **修正前テスト:** 現行スクリプトで Step 720 実行直前に `Print()` でデバッグ情報出力
2. **パターン修正テスト:** `RES_M_TPVM1_mipi` を `"[mipi][input]TPVM1 OK"` に修正して再実行
3. **タイミング修正テスト:** Step 720 前に `WAIT(5000)` を追加して再実行
4. **POC 検証:** `TPVM1_POC` 上限を暫定的に 9.0V に緩和して他項目への影響を確認

---

## 8. リスク

| リスク | 影響度 | 対策 |
|--------|--------|------|
| レスポンスパターン修正が既存の H1-H6 に影響 | 高 | H6 以前のヘッダも同じ定義なので、全グレード一括修正が必要 |
| TPVM1_POC の上限緩和が品質基準を逸脱 | 高 | 設計部門と上限値の妥当性を協議 |
| GVIF 接続不安定性がベンチ環境固有の問題 | 中 | 複数ベンチでの再現性確認が必要 |
| base board `base_rx1t` のマッピングが H7 固有 | 中 | V4X ファームウェア仕様書での確認が必要 |
| `modify_script.py` の変換ロジックが修正を上書き | 中 | src 側で修正し、dst 再生成で検証 |
| 手動デバッグとベンチの物理的な差異（ケーブル長、終端等） | 低 | ソフトウェア修正では解決不可。HW チームと連携 |

---

## 9. 補足: ファイル構成メモ

```
debug_result/
├── 手動デバック結果/
│   ├── 対向機.txt                    ← GVIF API ログ（全 API コール成功）
│   ├── 192.168.0.3_20260402_190520.log  ← base board ログ（TPVM1 startup OK, DMC OK）
│   └── 192.168.0.4_20260402_190516.log  ← mid board ログ（TPVM1 OK, PVM各チャネル OK）
└── 検査ベンチ結果/
    └── 20260402_194158_ASSY/
        ├── *_ETH_base.log            ← base board ログ（DMC pix error → NG）
        ├── *_ETH_mid.log             ← mid board ログ（TPVM1 VIN capture error → NG）
        ├── PCS52@FR@...csv           ← 全ステップ判定結果（Result=NG）
        └── PrintBox.buf1             ← 印字バッファ（B_TPVM1=LO, M_TPVM1=LO, TPVM1_POC=HI）
```
