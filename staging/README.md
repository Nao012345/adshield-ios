# staging/ — 検証待ちの候補ルール

ここに置いたルールは **公開されません**（`build.json` の対象外）。

1. 候補を `staging/<分類>.txt` に書く（`! @source:` で出典を明記）
2. `python scripts/validate.py --staging` で iOS 変換可否を確認
3. `python scripts/overlap_check.py` 相当の確認で Brave 標準リストと重複しないことを確認
4. 実機（iPhone の Brave）で効果と副作用を確認し、`docs/verification.md` に記録
5. 問題がなければ `filters/` へ移し、`python scripts/build.py` で `dist/` を再生成

検証できない変更は staging に留めます（指示書 7）。
