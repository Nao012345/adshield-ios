# 既存 OSS と iOS 版 Brave の調査（2026-11-06）

## 1. 参考プロジェクトの比較

ライセンス・最終更新は GitHub API（2026-11-06 取得）による。

| プロジェクト | ライセンス | 最終 push | 本プロジェクトでの使い方 |
|---|---|---|---|
| [brave/adblock-rust](https://github.com/brave/adblock-rust) | MPL-2.0 | 2026-10-28 | 構文と iOS 変換仕様の根拠。コード・ルールは複製しない |
| [brave/adblock-lists](https://github.com/brave/adblock-lists) | MPL-2.0 | 2026-11-05 | Brave が既に配布しているルールの把握（重複回避） |
| [uBlockOrigin/uAssets](https://github.com/uBlockOrigin/uAssets) | GPL-3.0 | 2026-11-05 | 同上。サイト固有ルールと例外ルールの設計の参考 |
| [AdguardTeam/AdguardFilters](https://github.com/AdguardTeam/AdguardFilters) | GPL-3.0 | 2026-11-05 | 日本語フィルター（Brave 内蔵の Japanese リストの元）の把握 |

**ライセンス方針**: AdShield は GPL-3.0。将来 uAssets / AdGuard（GPL-3.0）や Brave（MPL-2.0、GPL と両立）の
ルールを取り込む場合は、`! @source: <id>` で出典を明記し、`upstream/sources.json` の登録と
`validate.py` のライセンス判定を通す。**現時点で上流から複製したルールはない**（すべて `original`）。

## 2. iOS 版 Brave のフィルター処理

### 2.1 ネットワークルール → WebKit コンテンツブロッカー

iOS 版 Brave はフィルターリストを adblock-rust の `src/content_blocking.rs` で WebKit の
コンテンツブロッカー形式（JSON）に変換する。変換できないルールは捨てられる。

変換される: `||host^` などのパターン、`$third-party`/`$first-party`、`$domain=`（含む・除外の片方のみ）、
`$script` `$image` `$stylesheet` `$font` `$media` `$subdocument` `$xmlhttprequest`、`$match-case`、`@@` 例外。

変換されない（エラー）: `$redirect` `$csp` `$removeparam` `$generichide`、正規表現ルール、
`$from`/`$to`、`$domain` の含む・除外の混在、ASCII 以外の文字を含むルール、対応する種別が残らないルール。

### 2.2 要素非表示・スクリプトレット

- 同じ変換器は、要素非表示ルールを `css-display-none` に変換できる。ただし `:style()`、
  スクリプトレット（`+js()`）、手続き的フィルター（`:has-text()` など）、`example.*` は変換できない。
- iOS 版 Brave は、Swift 側で全フィルターリストを 1 つにまとめて adblock-rust エンジンにも渡している
  （[brave-browser#59112](https://github.com/brave/brave-browser/issues/59112)）。このエンジン経由で
  スクリプトレットも動く。2026-09 の変更（[brave-core#39978](https://github.com/brave/brave-core/pull/39978)、
  1.96.60 以降・2026-10-01 に QA 合格）で、iOS の**全フィルターリストに完全な権限**が与えられた。
  カスタムリストのスクリプトレットも実行されうる。
- Brave は 1.73 で全プラットフォームに手続き的要素非表示を導入したと発表している
  （[Brave privacy update #31](https://brave.com/privacy-updates/31-procedural-filtering/)）。
  ただし、カスタムリストから iOS で動くかは公式に明記がない。

**方針**: 指示書（5・10）に従い、本番リストではスクリプトレット・手続き的フィルター・`:has()` を使わない。
理由は、任意の JavaScript 実行を前提にしないことと、実機で未検証であること。iOS の変換器が受け付ける
ルールだけを使う。詳細は [ios-compatibility.md](ios-compatibility.md)。

### 2.3 リストのメタ情報

adblock-rust（`src/lists.rs`）は先頭 1024 バイト以内のコメントから `Title` `Homepage` `Expires` `Redirect`
を読む。`Expires` は `1〜14 days` または `1〜336 hours`。AdShield はこの範囲で `1 day` を指定する。
ただし再取得の時期を Brave が守るかは保証されない。

### 2.4 既知の不具合報告

- iOS でカスタムリストが「Download failed」になる、更新・削除で Brave が落ちる、という報告が
  Brave Community にある（例: [2026-10-25 / 1.97](https://community.brave.app/t/crashes-with-custom-filtering-on-ios/660131)、
  [brave-browser#49277](https://github.com/brave/brave-browser/issues/49277)）。リストは小さく保つ。

## 3. Brave 標準リストとの重複（overlap_check.py の結果）

Brave のリストカタログ（brave/adblock-resources `filter_lists/list_catalog.json`）によると、既定で有効なのは
Default Adblock（uBO + EasyList + Brave 独自）、Default Privacy（EasyPrivacy + uBO privacy）、
iOS-Specific、First Party、Cookie notice blocker、Mobile app promo blocker。
「Japanese website ad blocker」（AdGuard Japanese）は既定では無効。

最初の候補 57 ルールを照合した結果、31 ルールは既に収録済みだった（日本の主要アドネットワーク、
ヒートマップ、Web プッシュの大半）。残りのうち 22 ルールは、実在・現役を確認できないか、上流がより狭く
意図的に指定しているため外した（例: popIn は上流がおすすめ記事を許可している）。本番に残したのは 4 ルール。

| 対象 | 既存の対策 | 収録リスト |
|---|---|---|
| YouTube 動画広告 | `trusted-replace-xhr-response` などのスクリプトレット | Brave iOS-Specific |
| TVer の CM | `json-prune`、`google-ima` の差し替え | AdGuard Japanese |
| ニコニコ動画 | `\|\|ads.nicovideo.jp^` ほか | AdGuard Japanese |
| ABEMA | `\|\|ad.abema.io^` | AdGuard Japanese |

このため、導入手順では **Brave 内蔵の Japanese リストを有効にする**ことを最初の手順にしている。

## 4. 参照元

- adblock-rust `src/content_blocking.rs` / `src/lists.rs`（master, 2026-11-06 時点）
- https://github.com/brave/brave-browser/issues/59112
- https://github.com/brave/brave-core/pull/39978
- https://brave.com/privacy-updates/31-procedural-filtering/
- https://brave.com/privacy-updates/10-custom-filter-lists/
- https://raw.githubusercontent.com/brave/adblock-resources/master/filter_lists/list_catalog.json
- https://community.brave.app/t/crashes-with-custom-filtering-on-ios/660131
