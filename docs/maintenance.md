# 運用手順（Windows）

すべて標準の Python 3.10 以上だけで動く（追加パッケージ不要）。リポジトリ直下で実行する。

```powershell
python scripts/validate.py --staging   # 構文・iOS 互換・重複・ライセンスの検査
python scripts/build.py                # dist/ を生成
python -m unittest discover -s tests   # テスト
python scripts/overlap_check.py        # Brave 標準リストとの重複を確認（ネット接続が必要）
```

## ルールを追加・変更する

1. 候補を `staging/` に書き、`validate.py --staging` で iOS 変換の可否を確認
2. `overlap_check.py` で Brave 標準リストと重複しないことを確認
3. 実機で効果と副作用を確認し、[verification.md](verification.md) に記録
4. `filters/` に移す → `python scripts/build.py` → テスト
5. `VERSION` を上げ、`CHANGELOG.md` に追記してコミット・push

## 公開の流れ（GitHub Actions）

| ワークフロー | いつ | 内容 |
|---|---|---|
| `ci.yml` | push / PR | 検証・`dist/` の更新漏れ確認・テスト・重複レポート |
| `publish.yml` | main への push | 検証とテストが通ったときだけ GitHub Pages に公開。失敗したら前の版が残る |
| `upstream-watch.yml` | 毎週月曜 09:17 JST | 上流 4 リポジトリの更新と重複を報告し、issue を作る。**自動では反映しない** |

## リリースとタグ

```powershell
# VERSION と CHANGELOG.md を更新してコミットした後
git tag v0.1.0
git push origin v0.1.0
```

`dist/*.txt` の先頭に `Version` と `Content-Hash` が入るので、Brave がどの版を読んだか確認できる。

## ロールバック（問題のあるルールを切り戻す）

1. **すぐに戻す**: GitHub の Actions →「Publish filters」→「Run workflow」→ `ref` に正常だったタグ（例 `v0.1.0`）を入れて実行。
   その版をもう一度検証してから Pages に公開する。
2. **恒久対応**: main で問題のコミットを `git revert` して push。これをしないと、次の push で問題の版がまた公開される。
3. Brave は次にリストを取得したときに反映する。急ぐ利用者には、設定画面での手動更新を案内する。

## 上流の更新を取り込む

1. `upstream-watch` が作った issue の差分リンクを読む
2. AdShield に必要な補完ルールがあれば `staging/` に `! @source: <id>` 付きで書く（無条件の大量コピーはしない）
3. 上の「ルールを追加・変更する」の手順で検証する
4. `python scripts/upstream_watch.py --update-lock` で確認済みのコミットを記録してコミットする
