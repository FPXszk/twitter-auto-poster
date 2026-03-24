ある構想があるので実現してほしい
いまpost investの投稿はgoogle翻訳で引っ張て来た文章だけど
今回からcopilotcliをpython内などで呼び出して要約+決められた文体に整えてそれをツイートにしたい
もともとのgoogle翻訳で動いていたやつはわかりやすく名前をつけて
別ファイルで置いておいて　

さっきデバックして動いたコマンドがいかになる
こちらのモデルを使用してほしい　指示文はまだ考え途中だけど
いったん以下でいいかな

copilot \
  --model "gpt-5-mini" \
  -p "以下の文章を日本語で簡潔に要約してください:
ここに持ってきたツイートをいれる"


そのうえで上記で呼び出したcopilotに以下の文体守らせたい
要約するうえでインパクトを出したいので以下のツイート要約を参考にして

元ツイート↓
🇮🇷🇺🇸 Iran’s Foreign Minister Araghchi told U.S. envoy Steve Witkoff that talks are approved from the top.

According to Israeli outled Yedioth he said Supreme Leader Mojtaba Khamenei has given the green light for negotiations and even a possible deal.

Publicly it is no talks, but behind the scenes, something might already be moving.

Source: 
@AlArabiya_Eng
,  Yedioth Ahronoth

↓要約あと
🚨速報⚡️
イラン🇮🇷アメリカ🇺🇸間の水面下での交渉をイスラエル🇮🇱メディア報じる

イランのアラグチ外相は、アメリカの特使スティーブ・ウィトコフ氏に対し、最高指導層から交渉の承認が下りたことを伝えた。
イスラエルのメディア「イディオト・アハロノト（Yedioth Ahronoth）」によると、アラグチ外相は最高指導者モジュタバ・ハメネイ氏が、交渉および合意の成立についても「ゴーサイン」を出したと述べている。


コツは絵文字とか箇条書きとか使うこと

2つ目の例は以下
元ツイート↓
🚨🇺🇸🇮🇷 Forget what Trump says. Watch what he does.

He just sent some of America's most elite military units to the Middle East while talking about a possible peace deal.

Night Stalkers fly special forces into enemy territory in complete darkness. Delta Force takes out high-value targets. Navy SEALs hit from the sea. Rangers seize airfields within hours. These are not defensive units. This is a surgical strike roster.

So where are they headed? 3 targets make the most sense.

The points Iran uses to block the Strait of Hormuz, the chokepoint through which 20% of the world's entire oil supply flows every single day. Seize those, and global trade breathes again.

Kharg Island, where 90% of Iran's oil gets exported and which earned the regime $53 billion last year alone. Hit that, and Iran's economy collapses.

Iran's nuclear sites. The underground ones they've spent decades building while calling it "peaceful energy."

Trump didn't send diplomats. He sent the guys who specialize in hitting these 3 things.

You do the math.

Source: Clash Report

↓要約あと
🌟交渉で解決は本当か

トランプは「和平」を口にしつつ、実際には米軍の最精鋭部隊を中東に展開している。
配備されたのは攻撃任務向けの特殊部隊で、防御目的ではない。

想定される標的は3つ👇

❶ホルムズ海峡の封鎖拠点（石油輸送の要所）
❷ハルグ島（イランの石油輸出の中枢）
❸イランの地下核施設

言っていること、やっていることが矛盾している。
最初に最高指導者が始末された時も、トランは交渉をしていたはずだ。
