# Falcon_script README 概要刷新計画

## 背景

`Falcon_script/` には既に `README.md` があるが、現行の実ディレクトリ構造より古い前提で書かれている箇所があり、フォルダ全体を初見で理解するための「プロジェクト概要」としては不足がある。  
今回の目的は、`Falcon_script/` 配下の実コード・設定・資材配置をもとに、既存 README を信頼できる概要ドキュメントへ更新すること。

## 調査サマリ

- `Falcon_script/` は Falcon 自動検査テスター向けの Windows ベース資材一式を含む大きな作業ディレクトリ
- 主要な実体は次の3層に分かれる
  1. テスター実行基盤: `Driver/`, `Tester/`, `Programs/Falcon/`, `Tester.cfg`
  2. ハードウェア・周辺資材: `Device/`, `RELAY/`, `IMG/`, `Media/`, `Data/`
  3. 開発・デバッグ作業領域: `PgDebug/Falcon/`
- `PgDebug/Falcon/modify_script.py` が唯一の Python 自動化スクリプトで、`src/Info`・`src/Script` を `dst/` にコピー後、Falcon スクリプト群へ家系別パッチを適用する
- `Tester.cfg` では `ProgramType=Falcon`, `MachineType=PCS52` が定義され、`Driver\testerPgStart.exe` や `ateliercmd -connect -falcon2` などの実行基盤参照がある
- 実構成上の中心は `PgDebug/Falcon/src/Info/PCS52/{ETH,FH,FL,FR}`、`PgDebug/Falcon/src/Script/PCS52/{Common,ETH,FH,FL,FR}`、および生成先の `PgDebug/Falcon/dst/...` 系
- あわせて `Tester/{Info,Machine,Process,Product,Script}` がテスター側資材の配置先として存在し、`PgDebug/Falcon/` 側とは役割が分かれている
- 既存 `Falcon_script/README.md` には有用な説明とテンプレートがある一方、トップレベル構造・役割分担・運用フローの俯瞰説明が不足している

## 変更・作成・削除ファイル

### 変更

- `Falcon_script/README.md`

### 作成

- `docs/exec-plans/active/falconscript-readme-overview_20260402_1223.md`（この計画ファイル）

### 削除

- なし

## 実装内容

`Falcon_script/README.md` は**現行ツリーに合わせて全面再構成する前提**で更新する。  
既存 README の内容はそのまま温存せず、**実ディレクトリ・実ファイル・`modify_script.py`・`Tester.cfg` で確認できた事実だけを再採用**する。  
そのうえで、必要なテンプレート／ノウハウ記述は整合性を確認したものに限って再配置する。

1. プロジェクト概要
2. ディレクトリ構造
3. 技術スタックと主要ファイル種別
4. 主要エントリポイント
5. 設定ファイル一覧
6. Falcon 検査工程（ETH / FH / FL / FR）の概要
7. `Tester/` と `PgDebug/Falcon/` の役割分担
8. `PgDebug/Falcon/modify_script.py` の役割と処理フロー
9. `src/`・`dst/`・`00_need_deploy/` の関係
10. 運用上の注意点・ドキュメント範囲

既存 README 下部の「機能追加テンプレート」などは、内容を事実確認したうえで必要なら再配置し、現行構成とズレる説明は残さない。

## 影響範囲

- 変更は `Falcon_script/README.md` のみで、コード・設定・バイナリ・スクリプト資材は変更しない
- 他の `twitter-auto-poster` 側コードやテストには影響しない
- ユーザー体験上は、`Falcon_script/` を開いた人が最初に読むべき導線が整う

## スコープ外

- `PgDebug/Falcon/modify_script.py` の改修やリファクタ
- Falcon スクリプトや `.h` ファイル群の中身の編集
- `Tester.cfg` や `Driver/` 配下設定の変更
- `Falcon_script/` 用のテスト基盤新設
- 英語版 README の追加

## 実装ステップ

- [ ] 既存 `Falcon_script/README.md` を読み直し、現行構成と一致する情報／一致しない情報を切り分ける
- [ ] 実ディレクトリ構造・主要エントリポイント・設定ファイルの説明を README 用の概要文として再構成する
- [ ] `Tester/` と `PgDebug/Falcon/` の役割分担、および `src/`・`dst/`・`00_need_deploy/` の関係を README 内で明示する
- [ ] `PgDebug/Falcon/modify_script.py` の `src -> dst` 変換フローと家系別パッチ処理を、過不足なく要約する
- [ ] 既存のテンプレート／運用メモは事実確認できたものだけ再採用し、README 全体を現行実態ベースで書き直す
- [ ] 変更後 README を見直し、実パス・用語・工程名が調査結果と一致することを確認する

## TDD / テスト方針

今回はドキュメント更新のみのため、通常の RED → GREEN → REFACTOR はコード変更タスクほど厳密には適用しない。  
代わりに以下の文書検証で品質を担保する。

- RED 相当: 既存 README の不足点（実構造とのズレ、概要不足）を明確化する
- GREEN 相当: 実構造に基づく新しい概要セクションを追加し、README 単体で全体像が把握できる状態にする
- REFACTOR 相当: 既存の有用なテンプレートを保ちながら見出し構造と説明順を整理する

## 検証方法

- `Falcon_script/README.md` に記載したディレクトリ名・ファイル名・役割説明が実ファイル構造と一致することを確認
- 既存の有用情報が不必要に削除されていないことを差分で確認
- Markdown として不自然な見出し崩れやコードブロック崩れがないことを確認

## リスクと対策

- **リスク:** 古い README の説明を残した結果、概要ドキュメントとして不正確になる  
  **対策:** 既存記述は無条件で保持せず、確認済み事実だけを再採用する

- **リスク:** 既存 README の実務テンプレートを必要以上に落としてしまう  
  **対策:** テンプレート群は一つずつ実在ファイルや現在の運用前提と照合し、再採用可否を判断する

- **リスク:** 社内固有用語や工程名を推測で書いてしまう  
  **対策:** 実ファイル名、既存 README、`modify_script.py`、`Tester.cfg` から確認できる事実だけを書く

- **リスク:** 古い説明を新しい概要に混ぜてしまう  
  **対策:** 実ディレクトリ構造を一次情報として扱い、現状と一致しない説明は注記または更新する

## バリデーションコマンド

ドキュメント専用タスクのため、追加のビルドやテストは不要。  
実施する確認は次のとおり。

- `git --no-pager diff -- Falcon_script/README.md`
- `Falcon_script/README.md` の記述と実ディレクトリ名・主要ファイル名の突合
- Markdown 見出しとコードブロックの崩れがないかの目視確認

## 競合確認

`docs/exec-plans/active/` には `buz-text-only-and-workflow-pause_20260401_0053.md` が存在するが、対象は Twitter 投稿ワークフローであり、`Falcon_script/README.md` とは競合しない。
