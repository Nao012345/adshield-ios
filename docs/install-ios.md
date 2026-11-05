# iPhone の Brave に AdShield を導入する

> **状態: 2026-11-06 に iPhone 実機で、URL による追加と導入チェック「有効」を確認済み。**
> 「設定 → Brave Shieldsとプライバシー → コンテンツフィルター」は日本語表示の実際の画面名。
> それより先の項目名は、Brave のバージョンによって異なる場合がある。

## 必要なもの

- iPhone（App Store 版の Brave。脱獄・改造・Mac は不要）
- Brave 1.96.60 以降を推奨（iOS でフィルターリストの扱いが改善された版。[brave-browser#59112](https://github.com/brave/brave-browser/issues/59112)）

## 手順 0: Brave 内蔵の日本向けリストを有効にする（最も効果が大きい）

TVer・ニコニコ動画・ABEMA など日本のサイトの広告対策の多くは、Brave に内蔵された
**「Japanese website ad blocker」**（中身は AdGuard Japanese）に入っています。AdShield はこれと
重複しないように作っているため、先にこちらを有効にしてください。

1. Brave を開き、右下の「…」→「設定」
2. 「Brave Shieldsとプライバシー」
3. 「コンテンツフィルター」
4. フィルターリストの一覧から **Japanese** を含む項目をオンにする

## 手順 1: AdShield のリストを追加する

登録用 URL:

| リスト | URL | 内容 |
|---|---|---|
| **All（一括）** | `https://nao012345.github.io/adshield-ios/adshield-all.txt` | 下の 4 つをまとめたもの。**通常はこれだけ** |
| Core | `https://nao012345.github.io/adshield-ios/adshield-core.txt` | 一般サイトの広告（Brave 標準との差分） |
| Video | `https://nao012345.github.io/adshield-ios/adshield-video.txt` | 動画サイトの広告枠（要素非表示のみ） |
| Privacy | `https://nao012345.github.io/adshield-ios/adshield-privacy.txt` | ヒートマップ・セッション録画 |
| Annoyances | `https://nao012345.github.io/adshield-ios/adshield-annoyances.txt` | Web プッシュ通知の許可誘導 |

All と個別リストを両方登録する必要はありません（同じルールが二重に入るだけです）。

1. 上の URL をコピーする（公開ページ `https://nao012345.github.io/adshield-ios/` にコピーボタンがあります）
2. 「設定」→「Brave Shieldsとプライバシー」→「コンテンツフィルター」
3. 「カスタムフィルター」（Custom Filters）の欄で、URL でフィルターリストを追加する項目を開く
4. URL を貼り付けて追加する
5. 一覧に「AdShield iOS - All」などの名前が表示され、ダウンロードに失敗していないことを確認する

## 手順 2: 動いているか確認する

1. iPhone の Brave で `https://nao012345.github.io/adshield-ios/test/` を開く
2. 登録したリストの行が **「有効」** になれば成功
   - 「未適用」: まだリストが読み込まれていません。少し待つか、設定画面でリストを更新してから再読み込み
   - 「一部のみ」: 通信遮断か要素非表示の片方だけが動いています。結果を issue で報告してください
   - 「判定不可」: 確認用ファイル（cdn.jsdelivr.net）を読めませんでした。通信環境を確認
3. 結果を [verification.md](verification.md) に記録する

## 更新について

- リストには `! Expires: 1 day` を付けていますが、**Brave がいつ再取得するかはこちらで制御できません**。
  急ぐときは設定画面からリストを手動で更新してください。
- 問題のあるルールは GitHub 側で切り戻します（[maintenance.md](maintenance.md)）。Brave が次にリストを
  取得したときに反映されます。

## うまく動かないとき

- サイトが壊れた: AdShield のリストを一時的にオフにして直るか確認し、
  [誤ブロック報告](https://github.com/Nao012345/adshield-ios/issues/new/choose) を送ってください。
- 「Download failed」と表示される / Brave が落ちる: iOS 版 Brave でカスタムリストに関する同様の報告が
  あります（Brave Community, 2025〜2026）。Brave を最新版に更新し、URL が `.txt` で終わる直接リンクか確認してください。
- 個人情報（ログイン後の URL の ID、Cookie、トークンなど）は報告に書かないでください。
