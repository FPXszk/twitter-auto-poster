# Copilot 指示文

以下の日本株Twitter自動投稿システムを実装して。
まず stock_fetcher.py だけ作らせて動作確認
次に morning_summary.py を作らせて手動でツイート確認
問題なければ evening_summary.py
最後にGitHub Actions

投稿内容は以下を参考に
/home/fpxszk/code/twitter-auto-poster/docs/POSTING_STRATEGY.md
---

## やりたいこと

yfinanceで東証プライム全銘柄（約1800銘柄）のデータを取得し、
毎日2回Twitterに自動投稿するPythonスクリプトとGitHub Actionsを作成する。

https://github.com/FPXszk/MinerviLism/blob/main/python/scripts/update_tickers_extended.py
上記のリンクのスクレイピングツールを参考に今回のプロジェクトに応用できそうなところを判断してほしい。
ほかのAIは以下のように言ってるけど再度確認してほしい
↓
MinerviLismから参考にすべき部分はここだけ
バッチ処理（一度に全部取らず100銘柄ずつ）
レート制限対策（time.sleep）
エラー時にスキップして次に進む
---

## ファイル構成（作成するファイル）

```
python/
├── stock_fetcher.py       # yfinanceデータ取得共通モジュール
├── morning_summary.py     # 朝まとめ実行スクリプト
└── evening_summary.py     # 夜総括実行スクリプト
config/
└── tickers_jp.csv         # 東証プライム監視銘柄リスト（ticker,name,sector）
.github/workflows/
├── morning_post.yml       # 朝まとめ cron
└── evening_post.yml       # 夜総括 cron
```

---

## stock_fetcher.py の仕様

- yfinanceを使って日本株データを取得する
- ティッカーは `.T` サフィックス形式（例：`7203.T`）
- 対象は `config/tickers_jp.csv` に記載された銘柄
- 100銘柄ずつバッチ処理してレート制限を避ける（バッチ間に1秒スリープ）
- エラーが出た銘柄はスキップして次に進む
- 取得するデータは以下：
  - 前日終値（previousClose）
  - 当日終値（currentPrice or regularMarketPrice）
  - 騰落率（前日比%）
  - 出来高（volume）
  - 売買代金（出来高 × 株価）
  - 5日平均出来高（averageVolume）
  - 52週高値（fiftyTwoWeekHigh）

## morning_summary.py の仕様

実行タイミング：毎日 08:00 JST（GitHub Actions cron: `0 23 * * *`）

処理内容：
1. stock_fetcher.py を呼び出して全銘柄データ取得
2. 以下のランキングを算出する
   - 売買代金ランキング上位5銘柄
   - 出来高急増銘柄（5日平均出来高比2倍以上）上位3銘柄
   - 52週高値更新銘柄（当日高値 >= 52週高値）上位3銘柄
3. 以下のテンプレートでツイート投稿する

投稿テンプレート：
```
【本日の注目銘柄】8:00更新

🔥売買代金TOP3
1. 銘柄名(コード) ¥終値 (+X.X%)
2. 銘柄名(コード) ¥終値 (+X.X%)
3. 銘柄名(コード) ¥終値 (+X.X%)

📈出来高急増TOP3
・銘柄名 平均比XXX%

#日本株 #株式投資
```

4. 投稿したツイートIDを `tmp/posted_ids.txt` に追記して重複投稿を防ぐ
5. twitter-cli の `twitter post` コマンドで投稿する
   - 実行パスは `python/.venv/bin/twitter`
   - 認証は環境変数 `TWITTER_AUTH_TOKEN` と `TWITTER_CT0` を使う

---

## evening_summary.py の仕様

実行タイミング：平日 18:00 JST（GitHub Actions cron: `0 9 * * 1-5`）

処理内容：
1. stock_fetcher.py を呼び出して全銘柄データ取得
2. 以下のランキングを算出する
   - 当日売買代金上位5銘柄
   - 値上がり率トップ3銘柄
   - 値下がり率トップ3銘柄
3. 以下のテンプレートでツイート投稿する

投稿テンプレート：
```
【本日の市場総括】18:00更新

📈値上がりTOP3
1. 銘柄名 +X.X%
2. 銘柄名 +X.X%
3. 銘柄名 +X.X%

📉値下がりTOP3
1. 銘柄名 -X.X%
2. 銘柄名 -X.X%
3. 銘柄名 -X.X%

💴売買代金TOP3
1. 銘柄名 XXX億円
2. 銘柄名 XXX億円
3. 銘柄名 XXX億円

#日本株 #株式投資
```

4. 投稿したツイートIDを `tmp/posted_ids.txt` に追記する
5. twitter-cli の `twitter post` コマンドで投稿する

---

## GitHub Actions の仕様

### morning_post.yml
- cron: `0 23 * * *`（毎日 08:00 JST）
- Python 3.11 を使用
- `python/.venv` を作成して依存パッケージをインストール
- 必要パッケージ：`yfinance`, `pandas`
- Secrets から `TWITTER_AUTH_TOKEN` と `TWITTER_CT0` を環境変数に渡す
- `python/morning_summary.py` を実行する

### evening_post.yml
- cron: `0 9 * * 1-5`（平日 18:00 JST）
- morning_post.yml と同じ構成
- `python/evening_summary.py` を実行する

---

## config/tickers_jp.csv の仕様

`config/tickers_jp.csv` は JPX 公式 XLS から生成し、以下の形式で保持する：
```
ticker,name,sector
7203.T,トヨタ自動車,自動車
6758.T,ソニーグループ,電機
9984.T,ソフトバンクグループ,情報通信
```

- ソース: `https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls`
- 対象: `市場・商品区分` が `東証プライム（内国株式）` / `プライム（内国株式）` / `名証プレミア（内国株式）` / `プレミア（内国株式）`
- `33業種区分` を `sector` に使う
- `ETF` / `REIT` / `優先株` は除外する

---

## 注意事項

- try/except で適切にエラーハンドリングすること
- print() は使わず logging モジュールを使うこと
- 1ファイルあたり400行以内に収めること
- 140字制限を超えないようにツイート文字数を事前にチェックすること
- データが取得できなかった場合は投稿をスキップしてエラーログを残すこと
