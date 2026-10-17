# Chinese Poker — Pineapple OFC

Python / Pygame で遊ぶ、2人用の Pineapple Open Face Chinese Poker です。
GUI は CPU 対戦（Easy / Normal / Hard）と、同じ PC を交代で操作する2人対戦に対応しています。

## Windows で遊ぶ

ビルド済みの `ChinesePoker.exe` を実行してください。Python のインストールは不要です。
カード52枚と裏面画像を実行ファイルに同梱しているため、起動時の通信や画像の追加ダウンロードは不要です。
このリポジトリのソースから作成する場合は、下記のビルド手順を使ってください。

## ソースから起動

Python 3.10 の Windows 環境で動作確認しています。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements/runtime.txt
.\.venv\Scripts\python -m chinesepoker
```

ターミナル版は `python -m chinesepoker --terminal` で起動します。
`assets/` の画像は同梱済みです。再取得が必要な開発時のみ `python tools/download_assets.py` を実行します。

## CPU 対戦

起動後に CPU - Easy / Normal / Hard を選ぶと、Player 1 が自分、CPU が相手になります。
Normal は約1.5秒、Hard は約5秒を目安に未知の配牌をシミュレーションします。
思考中も画面は動作し、Esc でメニューに戻れます。CPU の手札は表示しません。
Two players を選ぶと従来の2人対戦です。ターミナル版は対人戦のままです。

CPU はナッシュ均衡を解いたものではありません。探索の範囲、検証結果の読み方、
既知の限界と今後の均衡計算への方針は [CPU の設計と検証](docs/CPU.md) を参照してください。

研究用の **Outcome Sampling MCCFR 学習器**も利用できます。通常1ハンドの学習・保存・再開、
小規模ゲームでの厳密な均衡誤差測定、保存戦略の実験用GUI読み込みに対応します。
全ルールの均衡や実戦での強さを達成したモデルではありません。
実行方法と測定結果は [MCCFR 学習器](docs/MCCFR.md) を参照してください。

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
.\.venv\Scripts\python -m pip install -r requirements/build.txt
.\.venv\Scripts\python tools/build.py
```

出力は `dist/ChinesePoker.exe` です。`packaging/ChinesePoker.spec` で画像と画像ライセンスを同梱します。
必要な画像が不足している場合はビルドを中止します。詳細ログは `build_log.txt` に保存します。

## テスト

```powershell
python -m unittest discover -v
```

役判定・表記変換・ファンタジーランド進入と継続・手番順に加え、CPU の合法手、非公開情報の境界、GUI の CPU 対戦進行を確認します。GUI テストには requirements/runtime.txt のインストールが必要です。
配布前には Python 未導入の Windows でも手動で起動・対局を確認してください。

## フォルダ構成

```text
chinesepoker/
├── chinesepoker/        # ゲーム本体の Python パッケージ
│   ├── __main__.py      # python -m chinesepoker の起動口
│   ├── ai/              # CPU の情報境界・評価・探索
│   ├── core/            # カード・役判定・プレイヤー・得点精算
│   └── ui/              # 画面版 (gui.py)・ターミナル版 (cli.py)
├── docs/                # CPU の設計・性能測定
├── assets/              # 同梱カード画像・ライセンス
├── tests/               # 自動テスト
├── tools/               # ビルド・画像再取得・CPU 性能測定
├── packaging/           # PyInstaller 設定と実行ファイルの起動口
├── requirements/        # 実行時・ビルド時の依存関係
└── README.md
```

コマンドはリポジトリのルートで実行します。以前の `python gui.py` は
`python -m chinesepoker`、`python main.py` は `python -m chinesepoker --terminal` に変更しました。
Python ファイルの整理に伴う起動方法の変更で、ゲームルールは変更していません。

## カード画像

[deckofcards](https://github.com/crobertsbmw/deckofcards) の画像を同梱しています。
MIT ライセンス全文と出典は `assets/` に収録しています。
