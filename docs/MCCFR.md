# ナッシュ均衡に向けた学習器

Outcome Sampling MCCFR の表形式学習器を実装しました。自己対戦で反実仮想後悔を更新し、
到達確率で重み付けした平均戦略を保存します。最終回の方策や最大確率の一手ではなく、
平均戦略の確率に従って行動します。既存の Easy / Normal / Hard とは独立した実験機能です。

## 解くゲームの範囲

| 指定 | 学習対象 | 評価できること |
|---|---|---|
| `kuhn` | 3枚の Kuhn Poker | 全情報集合に対する厳密な最善応答・exploitability |
| `endgame` | 固定した両者11枚の盤面と、共通知識の8枚プールから各3枚を配る終盤 | 全560配牌・全合法手による厳密な最善応答 |
| `ofc` | 実際の52枚・最初5枚、その後3枚から2枚配置する通常1ハンド | 学習・保存・再開・未使用配牌での評価。全体の最善応答は未計算 |

`ofc` は現在ターンの合法手を省略せず、自分の過去の観測と行動も情報集合に保持します。
相手の手札・捨て札・同じストリートで未公開の配置・将来の配牌はキーに入りません。
学習用シミュレータには両者の状態がありますが、戦略表の参照には観測履歴だけを使います。
配牌は一様なルート確率事象としてサンプルし、その共通確率因子は到達確率の比で相殺します。

報酬は本体と同じ段の勝敗・スクープ・ロイヤリティによる零和得点です。
次回FL権のヒューリスティック加点は使いません。**このモデルには次ハンドやFL継続がありません。**
したがって、この有限ゲームの学習が進んでも、無期限のFL付き対局の均衡を解いたことにはなりません。
`endgame` の8枚プールは両者が知っている条件です。一方だけの秘密の捨て札から作ったプールではなく、
通常対局の任意の終盤へそのまま適用できる戦略でもありません。

## 学習と再開

リポジトリ直下で Python 環境を準備して実行します。学習器自体には追加ライブラリは不要です。

```powershell
python -m tools.train_mccfr --game kuhn --iterations 100000 --checkpoint work/kuhn.json --report work/kuhn-results.json
python -m tools.train_mccfr --game endgame --iterations 100000 --checkpoint work/endgame.json --report work/endgame-results.json
python -m tools.train_mccfr --game ofc --iterations 1000 --checkpoint work/ofc.json --report work/ofc-results.json
python -m tools.train_mccfr --game ofc --resume --iterations 1000 --checkpoint work/ofc.json --report work/ofc-resumed.json
```

`--iterations` は追加学習回数です。1回につき更新対象を交代した2エピソードを行います。
`--save-every 1000` ごと、および正常終了時にJSONを一時ファイルから置換して保存します。
後悔・平均戦略・更新数・乱数状態を保存するため、中断再開後も同じ系列を継続できます。
再開時はチェックポイントの探索率と乱数状態を使い、指定し直した `--seed` / `--exploration` は使いません。
既存ファイルを新規学習で上書きする操作は拒否します。

`--seconds 3600` は反復の区切りで停止する時間上限です。保存時間等を含む厳密な壁時計制限ではありません。
`--max-nodes 100000` は情報集合数の上限で、到達したら保存して停止します。
情報集合を勝手に削除・統合しません。上限を増やして `--resume` で継続できます。
Ctrl+C の場合は前回保存済みファイルを残し、未保存分は破棄します。
長い学習ではメモリとファイルサイズも監視してください。今回の1000回のOFC保存ファイルは約21.8 MBでした。

## 保存戦略の検証と実戦への接続

```powershell
python -m tools.evaluate_mccfr --game kuhn --checkpoint work/kuhn.json --output work/kuhn-eval.json
python -m tools.evaluate_mccfr --game endgame --checkpoint work/endgame.json --output work/endgame-eval.json
python -m tools.evaluate_mccfr --game ofc --checkpoint work/ofc.json --pairs 20 --output work/ofc-eval.json
python -m chinesepoker --strategy work/ofc.json
# 配布exeも同じオプションに対応
.\ChinesePoker-CPU.exe --strategy .\ofc-mccfr.json
```

GUIでは追加された **CPU - Learned (test)** を選択します。`ofc` 形式だけを受け付けます。
未学習の情報集合、またはどちらかがFLのハンドでは Normal に戻ります。
この混合方策に均衡保証はありません。既存の3段階CPUはこれまでどおり使えます。

一方、評価コマンドはモデルの実力を隠さないため、未学習局面を**一様ランダム方策**として評価し、
学習済み情報集合の一致率を報告します。GUIのNormal代用を学習器の性能として数えません。
対Easyの得点は最善応答や exploitability の測定ではありません。

## 測定結果（2026-10-18）

| 対象 | 学習回数 | 情報集合数 | exploitability |
|---|---:|---:|---:|
| Kuhn Poker | 100,000 | 12 | 0.004980 |
| 固定OFC終盤 | 100,000 | 112 | 0.046694点 |
| 52枚・通常1ハンド | 1,000 | 19,999 | 未計算 |

ここで exploitability は両プレイヤーの最善応答による改善量の和（NashConv）の半分です。
小さいほど均衡に近いことを示します。小規模ゲームでは隠れた相手カードごとに別の行動を選ぶ
誤った全知の最善応答を使わず、同じ情報集合の期待値を足してから最大化しています。
OFC終盤のNashConvは0.093388点です。この値はこの固定ゲームだけに対するものです。
学習曲線は毎回単調に下がるとは限りません。

52枚モデルを未使用配牌40ハンド・座席交換20ペアで評価したところ、200判断の学習済み一致数は0でした。
対Easyの平均得点は−5.20点（ペア平均の近似95%区間−6.92〜−3.48）です。
**初期モデルは実用的な強さに達していません。** 正確な情報集合の数が極めて多く、短期の表形式学習では
ほぼ再訪できないためです。3日動かせば解けるという保証もありません。
実戦向けにはスート対称性、検証した状態・行動抽象化、関数近似、有限複数ハンドとFLのモデル化が次の課題です。
それらを導入する際は、元ゲームの保証と抽象化ゲームの保証を区別する必要があります。

生データ: `mccfr-kuhn-results.json`, `mccfr-endgame-results.json`,
`mccfr-ofc-results.json`, `mccfr-ofc-evaluation.json`。
チェックポイントは生成物として配布し、Gitには学習器・テスト・再現コマンド・測定結果を保存します。

## 根拠と実装検証

- [Lanctot et al. (2009), Monte Carlo Sampling for Regret Minimization in Extensive Games](https://proceedings.neurips.cc/paper/2009/hash/00411460f7c92d2124a67ea0f4cb5f85-Abstract.html)
  にある outcome sampling の考え方を使用しています。
- [OpenSpiel の Outcome Sampling 実装](https://github.com/google-deepmind/open_spiel/blob/master/open_spiel/python/algorithms/outcome_sampling_mccfr.py)
  は到達確率と重要度補正の確認に参照しました。

反復中は方策を固定し、2エピソードの更新をまとめて反映します。自分の探索混合確率、相手の到達確率、
サンプリング到達確率を分離し、選ばれなかった行動も後悔更新に含めます。
テストではKuhnの既知の値への接近、厳密な最善応答評価、OFC得点との一致、非公開情報の遮断、
観測履歴の保持、保存再開の完全一致、情報集合上限で未完了更新が反映されないことを確認します。

全37件の自動テストが成功しました。Windows exeを再ビルドし、リポジトリ外から
`--strategy` で実際のチェックポイントを読み込み、子プロセスでの判断とNormal代用を含む
1ハンドの進行・得点精算・観測履歴保持を確認しました。追加メニューの描画も確認済みです。
