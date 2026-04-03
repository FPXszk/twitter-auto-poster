# FR常温 H7 デバッグ派生 script 作成計画

## 背景

TPVM1 ベンチ NG 調査では、手動成功時の API フローに `gvif_setHandShakeGPIO` が含まれる一方、ベンチ実行に使っている `Falcon_script/PgDebug/Falcon/Script/PCS52/FR/PCS52@FR@JP039701-H7@V2.script` には `IMAGE_HANDSHAKE_SET(...)` 呼び出しが見えていない。

また、画像設定・画像出力・TPVM1 画像検査コマンドの前後に十分な待ち時間がなく、手動時より厳しいタイミングで判定に入っている可能性がある。

今回の目的は **本番 script を一切変更せず**、同一ディレクトリにデバッグ用の派生 script を 1 本作成し、以下の仮説を切り分けること。

1. handshake 設定不足
2. image set / image output 周辺の安定化待ち不足
3. TPVM1 画像検査コマンド送信前後の待ち不足

## この計画を新規 exec-plan にする理由

既存の `docs/exec-plans/active/tpvm1-bench-ng-investigation_20260402_1301.md` と `docs/exec-plans/active/falcon-tpvm1-bench-ng-investigation_20260402_2208.md` は、どちらも **原因調査** が主目的であり、恒久修正やデバッグ派生物の作成は中心スコープではない。

今回は成果物が「調査結果」ではなく **デバッグ用派生 script の作成** なので、別 plan として切り出す。

## 変更・作成ファイル

### 作成

- `Falcon_script/PgDebug/Falcon/Script/PCS52/FR/PCS52@FR@JP039701-H7@V2-Debug.script`
  - 元の FR 常温 H7 script のコピー
  - 実験用変更はこのファイルのみに入れる

### 参照のみ

- `Falcon_script/PgDebug/Falcon/Script/PCS52/FR/PCS52@FR@JP039701-H7@V2.script`
- `Falcon_script/PgDebug/Falcon/Script/PCS52/Common/LocalMacros@V32ADU.h`
- `Falcon_script/PgDebug/Falcon/Script/PCS52/Common/Functions@V33.h`
- `Falcon_script/debug_result/手動デバック結果/対向機.txt`

### 変更しない

- `Falcon_script/PgDebug/Falcon/Script/PCS52/FR/PCS52@FR@JP039701-H7@V2.script`
- `Falcon_script/PgDebug/Falcon/Script/PCS52/Common/LocalMacros@V32ADU.h`
- そのほか `Falcon_script` 配下の既存本番資材

## 実装方針

### 1. ファイル名

- まずはユーザー要望に合わせて、元ファイルのコピーを `PCS52@FR@JP039701-H7@V2-Debug.script` として同一ディレクトリに作成する
- 既存の本番 script 名は変更しない
- 命名上の都合で bench 側が読み込みづらい場合は、後続で別名に再調整する

### 2. handshake 追加の扱い

- `LocalMacros@V32ADU.h` に `IMAGE_HANDSHAKE_SET(NAME, ID)` は既に存在する
- ただし、どのチャネルに対してどの GPIO ID を入れるべきかは **手動成功ログで確定している範囲だけ** を使う
- そのため初回実装では、手動ログに合わせて **`IMAGE_HANDSHAKE_SET("GVIF1-4", 30);` を 1 箇所だけ** 追加する方針とする
- 挿入位置は、`gvif_setParams(...)` の後かつ `OUTPUT_IMAGE_SET(...)` 群の前とし、手動フローの順序に寄せる
- もし周辺構造を読んでこの位置が不自然な場合は、同じ step 内で「setParams 完了後 / image set 開始前」の位置に限定して微調整する

### 3. 1 秒待ちの追加対象

以下の各呼び出しの **前後** に `WAIT(1000);` を追加する。

- `OUTPUT_IMAGE_SET("GVIF1-1", FILE_OUTPUT_FCM);`
- `OUTPUT_IMAGE_SET("GVIF1-3", FILE_OUTPUT_TPVM1);`
- `OUTPUT_IMAGE_SET("GVIF1-4", FILE_OUTPUT_REAR);`
- `OUTPUT_IMAGE_SET("GVIF1-5", FILE_OUTPUT_FRONT);`
- `OUTPUT_IMAGE_SET("GVIF1-6", FILE_OUTPUT_LEFT);`
- `OUTPUT_IMAGE_SET("GVIF1-7", FILE_OUTPUT_RIGHT);`
- `IMAGE_OUTPUT("GVIF1-1", 0);`
- `IMAGE_OUTPUT("GVIF1-3", 0);`
- `IMAGE_OUTPUT("GVIF1-4", 0);`
- `IMAGE_OUTPUT("GVIF1-5", 0);`
- `IMAGE_OUTPUT("GVIF1-6", 0);`
- `IMAGE_OUTPUT("GVIF1-7", 0);`

### 4. 3 秒待ちの追加対象

以下の TPVM1 画像検査コマンド送信の **前後** に `WAIT(3000);` を追加する。

- `ETH_BASE_SEND("./" CMD_B_TPVM1_mipi);`
- `ETH_MID_SEND("./" CMD_M_TPVM1_mipi);`

「後」は send 行の直後ではなく、各 TPVM1 判定ブロックが終わった位置に入れて、コマンド送信から受信・判定までを 1 セットとして扱う。

### 5. デバッグ差分の見える化

- 追加した変更点には `// DEBUG:` コメントを付ける
- 元ファイルとの差分を追いやすくして、後で実験を戻しやすくする

## 実装ステップ

- [ ] 元 script の対象ブロックを再確認し、handshake 挿入位置を最終決定する
- [ ] `PCS52@FR@JP039701-H7@V2-Debug.script` を元 script のコピーとして作成する
- [ ] 派生 file の冒頭に「デバッグ用派生 script」であることを示すコメントを追加する
- [ ] `gvif_setParams(...)` 後〜`OUTPUT_IMAGE_SET(...)` 前の範囲に `IMAGE_HANDSHAKE_SET("GVIF1-4", 30);` を追加する
- [ ] `OUTPUT_IMAGE_SET(...)` 6 箇所の前後に `WAIT(1000);` を追加する
- [ ] `IMAGE_OUTPUT(...)` 6 箇所の前後に `WAIT(1000);` を追加する
- [ ] `ETH_BASE_SEND("./" CMD_B_TPVM1_mipi);` の前後に `WAIT(3000);` を追加する
- [ ] `ETH_MID_SEND("./" CMD_M_TPVM1_mipi);` の前後に `WAIT(3000);` を追加する
- [ ] 追加差分に `// DEBUG:` コメントを付けて、意図しない変更がないかを確認する

## TDD / 検証方針

この `.script` には既存の自動テストやビルド検証は見当たらないため、今回は **テキスト差分ベースの RED → GREEN → REFACTOR** で進める。

### RED

- 元 script に `IMAGE_HANDSHAKE_SET(...)` が入っていないことを確認する
- 元 script に今回追加する `WAIT(1000)` / `WAIT(3000)` / `// DEBUG:` が無いことを確認する

### GREEN

- 派生 script を作成し、指定した handshake / wait / comment を追加する
- 元 script には変更を入れない

### REFACTOR

- 追加位置が不自然でないかを見直し、コメントの粒度を揃える
- debug 差分以外の不要変更を取り除く

## バリデーション方針

実装後は、既存の repo ツールで次を確認する。

1. 対象箇所の存在確認
   - `rg -n "IMAGE_HANDSHAKE_SET|OUTPUT_IMAGE_SET|IMAGE_OUTPUT|CMD_B_TPVM1_mipi|CMD_M_TPVM1_mipi" Falcon_script/PgDebug/Falcon/Script/PCS52/FR/PCS52@FR@JP039701-H7@V2-Debug.script`
2. debug コメントの確認
   - `rg -n "// DEBUG:" Falcon_script/PgDebug/Falcon/Script/PCS52/FR/PCS52@FR@JP039701-H7@V2-Debug.script`
3. 元ファイルとのテキスト差分確認
   - `git --no-pager diff --no-index -- Falcon_script/PgDebug/Falcon/Script/PCS52/FR/PCS52@FR@JP039701-H7@V2.script Falcon_script/PgDebug/Falcon/Script/PCS52/FR/PCS52@FR@JP039701-H7@V2-Debug.script`
4. 元ファイル不変確認
   - `git --no-pager diff --no-index -- /dev/null Falcon_script/PgDebug/Falcon/Script/PCS52/FR/PCS52@FR@JP039701-H7@V2-Debug.script`
   - 必要に応じて元 file の再読で spot check する

## リスク

- `GVIF1-4 / GPIO 30` が手動成功ログには出ていても、今回の TPVM1 実験として十分条件とは限らない
- wait 追加でデバッグ script の実行時間は伸びる
- Falcon 側の運用で `-Debug` 命名が扱いづらい可能性がある
- 大きい script のため、余計な差分を混ぜると切り戻ししづらい

## スコープ外

- 元の `PCS52@FR@JP039701-H7@V2.script` の直接修正
- `Ether_IF_3TEMP_H7@V2.h` など応答文字列側の修正
- `.tii` や画像ファイルの設定変更
- `modify_script.py` の変更
- GitHub 操作、コミット、push

## 競合確認

- `docs/exec-plans/active/tpvm1-bench-ng-investigation_20260402_1301.md` とは、同じ TPVM1 系の話題だが「原因調査」と「デバッグ派生 script 作成」で役割が異なる
- `docs/exec-plans/active/falcon-tpvm1-bench-ng-investigation_20260402_2208.md` とも、今回の変更成果物は別であり直接競合しない
- `Falcon_script/README.md` 系の plan 群とも対象ファイルが異なる
