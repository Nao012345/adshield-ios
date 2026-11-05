# 変更履歴

## 0.1.0 — 未公開（Phase 1）

- リポジトリの基盤: 構文と iOS 互換の検証、`dist/` の生成、テスト、GitHub Actions（CI・公開・上流監視）
- 導入チェックページ（`site/test/`）と、リストごとの確認用ルール
- 本番ルール 4 件（すべて実機未検証）
  - Video: `m.youtube.com##ad-slot-renderer`、`www.youtube.com##ytd-ad-slot-renderer`
  - Privacy: `||userheat.com^$third-party`
  - Annoyances: `||cdn.onesignal.com/sdks/$script,third-party`
- 初期候補 57 件のうち 53 件は不採用: 31 件は Brave 標準リスト・Japanese リストと重複（docs/research.md §3）、
  22 件は根拠不足（実在や現役を確認できない）または範囲が広すぎる（上流がより狭く意図的に指定している）もの
