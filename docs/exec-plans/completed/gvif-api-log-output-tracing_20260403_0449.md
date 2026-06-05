# 調査計画: Falcon/GVIF API ログ出力経路の解明

**計画 ID**: `gvif-api-log-output-tracing`  
**作成日**: 2026-04-03  
**ステータス**: PLAN（承認待ち）  
**種別**: 調査（コード変更なし）

---

## 背景

`Falcon_script/DESKTOP-D4DJOKQ_GVIF3-Eth.csv` および `Falcon_script/dlllog-api.txt` には、GVIF/API に関するログが出力されている。  
一方で、**どのコンポーネントが、どの契機で、どのパスへ出力しているか** という「出力経路・出力仕様」は未整理である。

既存 active plan のうち、特に `falcon-tpvm1-bench-ng-investigation_20260402_2208` は **TPVM1 ベンチ NG の原因調査** を主目的としており、ログ内容の解釈や NG 仮説評価が中心である。  
本計画はそれと分離し、**GVIF/API ログの出力元・出力先・出力契機・相互関係の特定** に限定して調査する。

---

## この計画のゴール

以下を文書化する。

1. `DESKTOP-D4DJOKQ_GVIF3-Eth.csv` が **どの命名規則・どの出力元推定** で生成されているか
2. `dlllog-api.txt` が **どの粒度の API ログ** で、CSV とどう対応するか
3. script / config / 既存ログから追える範囲で、**どのコンポーネントがどのパスへ何を出すか**
4. `EthLog/`、`ETH_base.log`、`ETH_mid.log`、`StartPg.log`、`testerPgExecution.log` がこの GVIF/API ログ群とどう関係するか

---

## スコープ

### スコープ内

- `Falcon_script/` 配下の **GVIF/API ログ出力経路** の調査
- `DESKTOP-D4DJOKQ_GVIF3-Eth.csv` と `dlllog-api.txt` の対応関係整理
- `Tester.cfg` / script / header / macro から追えるログ出力先定義の確認
- 関連ログ同士の役割分担整理（API ログ、Ether ログ、実行ログ）

### スコープ外

- TPVM1 ベンチ NG の根本原因特定
- `dlllog-api.txt` / CSV の内容を使った不具合仮説の評価
- script 修正、設定変更、ログ仕様変更
- ADU_DLL.cpp 実ソース取得や外部環境（SVN/Windows実機）での追加確認
- issue 化、恒久修正 plan の起票

---

## 既存 active plan との境界

| 既存 Plan | 既存 plan の主目的 | 本計画との差分 |
|---|---|---|
| `falcon-tpvm1-bench-ng-investigation_20260402_2208` | TPVM1 ベンチ NG 原因調査 | 本計画は **原因分析を行わず**、ログの出力経路・出力仕様のみ扱う |
| `tpvm1-bench-ng-investigation_20260402_1301` | TPVM1 関連設定・script整合の調査 | 本計画は **GVIF/API ログファイルの生成と関係図** に限定 |
| `falcon-h7-debug-script-variant_20260403_0002` | debug script 変更 | 本計画は **読み取り専用**、変更なし |
| `session-handoff-log_20260403_0027` | セッション引継ぎ整理 | 本計画は **調査結果そのものの整理** であり、handoff 追記は直接目的にしない |

**境界ルール**
- 本計画では「この API 失敗が NG 原因か」は判断しない
- 本計画では「どのログに、どのイベントが、どの形式で出るか」だけを扱う
- 既存 TPVM1 plan にある個別失敗事象の解釈は参照のみとし、再分析しない

---

## 調査対象ファイル（読み取り専用）

- `Falcon_script/DESKTOP-D4DJOKQ_GVIF3-Eth.csv`
- `Falcon_script/dlllog-api.txt`
- `Falcon_script/Tester.cfg`
- `Falcon_script/PCS52@FR@JP039701-H7@V2-Debug.script`
- `Falcon_script/PgDebug/Falcon/Script/PCS52/Common/ADU/Ether_IF_3TEMP_H7@V2.h`
- `Falcon_script/PgDebug/Falcon/Script/PCS52/Common/LocalMacros/*.h`
- `Falcon_script/PgDebug/Falcon/Script/PCS52/Common/Functions/*.h`
- `Falcon_script/debug_result/手動デバック結果/対向機.txt`
- `Falcon_script/debug_result/検査ベンチ結果/**/*`
- `Falcon_script/StartPg.log`
- `Falcon_script/testerPgExecution.log`
- `Falcon_script/EthLog/`
- `Falcon_script/Driver/`

---

## 成果物

- `docs/exec-plans/active/gvif-api-log-output-tracing_20260403_0449.md`  
  - 調査計画書
- 調査結果サマリ  
  - この計画書へ追記するか、必要なら別 plan/文書化を検討

---

## 調査ステップ

### Phase 1: GVIF/API ログ本体の把握

- [ ] `DESKTOP-D4DJOKQ_GVIF3-Eth.csv` の列構造、命名規則、行数、主要エラーコード分布を確認する
- [ ] CSV の `file line` をユニーク化し、**行番号クラスタとメッセージ/API 種別の対応** を整理する
- [ ] `dlllog-api.txt` の1行フォーマットを分解し、API名・開始/完了・戻り値・引数らしき項目を整理する
- [ ] CSV と `dlllog-api.txt` の時刻・API 名・コードの対応をサンプルベースで突合する
- [ ] `対向機.txt` と `dlllog-api.txt` の形式差/共通点を整理し、同系統ログか別用途ログかを判定する

### Phase 2: 出力経路の追跡

- [ ] `Tester.cfg` のログ関連設定を抽出し、各設定がどのログに効いていそうかを整理する
- [ ] script/header/macro から `ETHER_LOG_PATH`、`etherBaseLog.Init()`、`etherMidLog.Init()` の出力先決定経路を追う
- [ ] `ETH_base.log` / `ETH_mid.log` の出力先と `EthLog/` の関係を確認する
- [ ] `StartPg.log` / `testerPgExecution.log` の生成主体と、GVIF/API ログとの時間的関係を把握する

### Phase 3: 関係図の整理

- [ ] ログファイルごとに **出力元コンポーネント / 出力契機 / 出力パス / 主な内容** を表にまとめる
- [ ] GVIF/API 関連ログに限定した関係図を作る
- [ ] 未確認事項・推定事項・外部依存事項を明確に分けて記録する

---

## 現時点の既知情報（事実と仮説を分離）

### 事実

- `DESKTOP-D4DJOKQ_GVIF3-Eth.csv` が存在する
- `dlllog-api.txt` が存在する
- `Tester.cfg` には一般ログ関連設定がある
- debug script 内に `etherBaseLog.Init()` / `etherMidLog.Init()` 呼び出しがある
- `EthLog/` ディレクトリが存在し、現時点では空である

### 仮説（未確認）

- CSV のホスト名部分は `Tester.cfg` の `TesterName` と関係する
- CSV / `dlllog-api.txt` は ADU_DLL 系コンポーネント由来である
- `dlllog-api.txt` は API 呼び出し粒度、CSV はエラー/結果粒度の可能性がある
- `EthLog/` は script 側 Ether ログの出力先候補である

---

## バリデーション方針

### 調査完了条件

- [ ] `DESKTOP-D4DJOKQ_GVIF3-Eth.csv` と `dlllog-api.txt` の役割差が説明できる
- [ ] 少なくとも主要ログ群について、出力元・出力契機・出力先の表が埋まっている
- [ ] 既存 TPVM1 原因調査 plan と重ならない説明になっている
- [ ] 推定事項と未確認事項が明確に区別されている

### 検証コマンド候補

```bash
cd /home/fpxszk/code/twitter-auto-poster/Falcon_script

awk -F',' 'NR>1 {print $6}' DESKTOP-D4DJOKQ_GVIF3-Eth.csv | sort -n | uniq -c | sort -rn
awk -F',' 'NR>1 {print $3}' DESKTOP-D4DJOKQ_GVIF3-Eth.csv | sort | uniq -c | sort -rn
grep -nE 'ETHER_LOG_PATH|etherBaseLog|etherMidLog|dlllog|LogFlag' -r --include='*.h' --include='*.script' .
grep -inE 'log' Tester.cfg
find . \( -name '*.log' -o -name '*.csv' -o -name '*.txt' \) | grep -iE 'gvif|eth|log|debug'
```

---

## リスク

| リスク | 影響 | 対策 |
|---|---|---|
| ADU_DLL.cpp 実体がない | 行番号から関数名を断定できない | 関数名断定はせず、行番号クラスタとメッセージ/API対応に留める |
| Windows 実機パスを直接検証できない | 出力先を断定できない箇所が残る | config / script / 既存ログからの推定と未確認注記を分離する |
| 既存 TPVM1 plan と読解対象が重なる | 作業重複 | 「原因分析をしない」ルールを明示し、出力経路の記述に限定する |
| 関連ログの範囲を広げすぎる | 調査が拡散する | GVIF/API 出力経路に直接関係するログ群を優先対象とする |

---

## TDD / テスト方針

本計画は **コード変更を伴わない調査タスク** のため、RED/GREEN/REFACTOR は適用しない。  
代わりに、**事実・推定・未確認を分離した調査結果の再現可能性** を品質基準とする。

---

## Pre-Implementation Completeness Checklist

- [x] Files listed
- [x] Scope bounded
- [x] Test strategy stated（調査タスク向け代替方針）
- [x] Validation commands identified
- [x] Risks noted
- [x] No overlap with existing plans（境界ルール明記）
