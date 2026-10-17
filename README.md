# Chinese Poker — Pineapple OFC

Python / Pygame で遊ぶ、2人用の Pineapple Open Face Chinese Poker です。
現在は同じ PC を交代で操作する対人戦に対応しています。CPU 対戦は未実装です。

## Windows で遊ぶ

ビルド済みの `ChinesePoker.exe` を実行してください。Python のインストールは不要です。
カード52枚と裏面画像を実行ファイルに同梱しているため、起動時の通信や画像の追加ダウンロードは不要です。
このリポジトリのソースから作成する場合は、下記のビルド手順を使ってください。

## ソースから起動

Python 3.10 の Windows 環境で動作確認しています。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python gui.py
```

ターミナル版は `python main.py` で起動します。
`assets/` の画像は同梱済みです。再取得が必要な開発時のみ `python download_assets.py` を実行します。

## 操作

1. 手番開始画面をクリックして手札を表示します。
2. 手札のカードを選択し、配置先の空き枠をクリックします。
3. この手番で置いたカードは、もう一度クリックすると手札に戻せます。
4. 必要枚数を配置して Confirm を押します。余ったカードは捨て札になります。
5. 結果画面の Next Round で次のラウンドに進みます。

## 採用ルール

- 上段3枚・中段5枚・下段5枚に配置します。強さが「下段 ≥ 中段 ≥ 上段」を満たさない場合はファウルです。
- 通常は最初に5枚をすべて配置し、その後4回、3枚から2枚を配置して1枚捨てます。
- ファンタジーランドでは14〜17枚から13枚を配置します。
- 通常プレイヤーのすべての手番が終わった後、ファンタジーランドのプレイヤーが配置します。GUI とターミナル版で共通です。
- ファウルせず上段に QQ / KK / AA / スリーカードを作ると、次回はそれぞれ14 / 15 / 16 / 17枚です。
- 継続条件は上段スリーカード、中段フルハウス以上、下段フォーカード以上のいずれかです。
- **ファンタジーランド継続時は現在の枚数を維持します。14枚へのリセットや上位枚数への変更はありません。**
- 各段の勝敗に加えて、全段勝利ボーナスとロイヤリティ差を精算します。

カードの内部表記は S/H/D/C と 10 です。`Card` は ♠/♥/♦/♣ および T も受け付け、内部表記へ変換します。
ターミナル入力は `H10 top` のような英字表記を使います。

## Windows 実行ファイルのビルド

```powershell
.\.venv\Scripts\python -m pip install -r requirements-build.txt
.\.venv\Scripts\python build.py
```

出力は `dist/ChinesePoker.exe` です。`gui.spec` で画像と画像ライセンスを同梱します。
必要な画像が不足している場合はビルドを中止します。詳細ログは `build_log.txt` に保存します。

## テスト

```powershell
python -m unittest discover -v
```

役判定、表記の変換、ファンタジーランド進入・継続、通常手番が先になる進行を確認します。
配布前には Python 未導入の Windows でも手動で起動・対局を確認してください。

## 主なファイル

| ファイル | 役割 |
|---|---|
| gui.py / main.py | 画面版 / ターミナル版 |
| card.py | カード・山札・表記変換 |
| evaluator.py | 役判定・盤面の有効性判定 |
| player.py | プレイヤー・ロイヤリティ・ファンタジーランド |
| game.py | 得点精算 |
| assets/ | 同梱画像とライセンス |
| build.py / gui.spec | 実行ファイルのビルド |

## カード画像

[deckofcards](https://github.com/crobertsbmw/deckofcards) の画像を同梱しています。
MIT ライセンス全文と出典は `assets/` に収録しています。
