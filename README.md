# AdShield iOS

iPhone の **App Store 版 Brave** に URL を登録するだけで使える、補完用の広告・トラッカー対策フィルターリスト。
Brave に標準で入っている広告ブロック（adblock-rust）をそのまま使い、標準リストで取り切れない分だけを
GitHub で開発・配布します。Mac・Xcode・脱獄・Brave の改造は不要で、Windows だけで開発できます。

```
Windows PC ─ push ─> GitHub（検証・テスト）─ 合格時のみ ─> GitHub Pages ─> iPhone の Brave「URL で追加」
```

> **状態: v0.1.0（Phase 1）。iPhone 実機では未検証です。** 検証状況は [docs/verification.md](docs/verification.md)。

## 使い方

1. Brave の設定で、内蔵の **Japanese website ad blocker** を有効にする（日本の動画サイトの広告対策はここに入っています）
2. 次の URL を Brave の「カスタムフィルター」に追加する
   - 一括: `https://nao012345.github.io/adshield-ios/adshield-all.txt`
   - 個別: `adshield-core.txt` / `adshield-video.txt` / `adshield-privacy.txt` / `adshield-annoyances.txt`
3. `https://nao012345.github.io/adshield-ios/test/` を開き、「有効」と表示されることを確認する

詳しい手順: **[docs/install-ios.md](docs/install-ios.md)**

## できること・できないこと

- iOS 版 Brave の変換器（adblock-rust `content_blocking.rs`）が受け付ける構文だけを使います。
  スクリプトレット・手続き的フィルター・`$redirect` は使いません（[docs/ios-compatibility.md](docs/ios-compatibility.md)）。
- YouTube・TVer などの**動画広告の除去は Brave 本体と内蔵リストの担当**です。AdShield は動画サイトで通信を遮断せず、
  広告枠の要素を隠すだけです。完全な除去は保証しません。
- Brave がリストを再取得する時期はこちらで制御できません（`! Expires: 1 day` を指定しています）。

## リポジトリ構成

```
filters/            本番ルールの元ファイル（ここを編集する）
  core.txt  privacy.txt  annoyances.txt  video/{youtube,niconico,tver,abema}.txt
staging/            検証待ちの候補（公開されない）
dist/               生成された配布ファイル（直接編集しない）
scripts/            filterlib.py（構文・iOS 互換検査）, build.py, validate.py,
                    overlap_check.py（Brave 標準との重複）, upstream_watch.py, make_site.py
site/               GitHub Pages（導入ページ・導入チェックページ）
tests/              unittest（構文・ビルド・安全性・上流監視）
upstream/           出典とライセンスの登録、Brave 標準リストの URL、上流の確認済みコミット
.github/            CI・公開・上流監視のワークフロー、不具合報告フォーム
docs/               導入手順・調査結果・互換性一覧・検証記録・運用手順
```

## 開発（Windows / Python 3.10+、追加パッケージ不要）

```powershell
python scripts/validate.py --staging
python scripts/build.py
python -m unittest discover -s tests
python scripts/overlap_check.py
```

運用・リリース・ロールバック: [docs/maintenance.md](docs/maintenance.md) ／ 調査結果: [docs/research.md](docs/research.md)

## ライセンス

GPL-3.0（[LICENSE](LICENSE)）。現在のルールはすべて本プロジェクト独自のものです。上流（uBlock Origin uAssets:
GPL-3.0、AdGuard Filters: GPL-3.0、Brave adblock-lists: MPL-2.0）のルールを取り込む場合は、ルールの前に
`! @source:` で出典を明記し、`upstream/sources.json` で再利用の可否を判定します。
