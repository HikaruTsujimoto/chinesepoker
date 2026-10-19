# 旧CPUの保管と復元

通常のアプリではExpectimaxと対人戦のみを有効にしています。
Easy / Normal / Hard / Hybrid / Adaptive / Learnedは、メニュー、GUI対局の生成、
起動時の旧CPU指定や保存戦略指定から実行できません。旧CPUの自動学習・バックグラウンド実行もありません。

## 残している情報

- `chinesepoker/ai/`：旧方策・学習器とモデル。研究用ツールから明示的に呼ぶためのAPIは保持。
- `tools/`、`tests/`：研究・評価・互換性の検証コード。
- `docs/`：以前の方式の設計、学習結果、対戦評価。

`search.py`の合法手列挙・貪欲ロールアウト・FL探索や、`action_advantage.json`のFL継続価値などは
Expectimax自身も利用しています。その共有処理は必要なため残していますが、旧CPUを対戦相手として
選択したり、旧CPUへ自動で切り替える経路は通常アプリで無効です。
旧学習戦略のGUIモジュールは、旧CPUを実際に有効化して起動するまで読み込みません。

## 必要になった場合のみ復元する

1. `chinesepoker/features.py` の `LEGACY_CPUS_ENABLED = False` を `True` に変更します。
2. ソースから `python -m chinesepoker` で起動します。
3. **Other CPUs** が復活します。Learnedは `--strategy 保存戦略.json` を指定すると選べます。
4. exeにも反映する場合は `python tools/build.py` で再ビルドします。

Falseへ戻して起動・再ビルドすれば再び無効になります。ユーザー向けのオン・オフ設定は設けていません。
旧研究ツールは保存資料の再検証用として手動実行可能ですが、通常のゲーム起動からは呼び出しません。
