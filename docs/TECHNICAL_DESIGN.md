# Bedrockワールド生成の調査と採用方式

調査日：2026-10-08。対象：Minecraft for Windows（Bedrock版）。

| 方式 | 建築の保存 | パック | 判断 |
|---|---|---|---|
| Script APIで起動時に建築するmcpack | プレイ開始後 | 必須 | 採用しない。未読込チャンクと建築失敗をプレイへ持ち込む |
| Minecraft本体で建築しエクスポート | 済 | 不要にもできる | 確実だが、この環境にWindows本体がない |
| Javaワールドを作りBedrockへ変換 | 済 | 不要にもできる | コマンド・看板・ブロック状態の変換差が増える |
| Amuletで直接Bedrock LevelDBを作成 | 済 | 不要 | **採用**。Bedrock形式を読み直して検査できる |

Amuletの`LevelDBFormat.create_and_open("bedrock", version)`で新規ワールドを作成し、
`World`経由でブロックを保存します。看板・コマンドブロックNBTは、ブロック翻訳で
フィールドを落とさないよう、地形保存後に各チャンクの`0x31`レコードへ保存します。
MojangのLevelDB派生実装を包む`amulet-leveldb`を使用し、汎用LevelDBで代用しません。
`level.dat`には8バイトのヘッダーとlittle-endian NBTを使用し、一式をZIPに入れて`.mcworld`とします。
`.mcpack`の拡張子だけを変える方法ではありません。

## 仕様

- 足し算5問・引き算5問。前半は10以内、後半は繰り上がり・繰り下がりも含みます。
- 32×32の室を2×2チャンクに合わせ、128×96内に10室とゴールを配置します。
- 床Y=64、足元Y=65、天井Y=80。全室を完全に閉じます。
- 生成完了状態=2で保存し、周辺を含む80チャンクを生成済みとします。
- 問題は毎秒のアクションバーと壁の高さ5ブロックの数字で表示します。補助説明は看板に表示します。
- 回答は床の石の感圧板を踏むことで行います。板の真下の羊毛ブロックを通して、その下のインパルスコマンドブロックへレッドストーン信号が届きます。通路の座標検出だけでは回答しません。
- 感圧板の信号を必要とするインパルス（auto=0）→常時有効な下向きチェーンで結果表示・音・移動を実行します。問題表示とゴール演出は従来どおりリピートです。
- 正解は次室入口、不正解は同室入口へ戻します。入口は判定域から離して再判定を防ぎます。
- ゴールは`maze_goal`タグで文字・音を一度だけ再生し、粒子は滞在中に繰り返します。
- 青い矢印の先の感圧板でタグを消し、1問目へ戻します。
- 一人用、冒険モード。通常操作では囲いから脱出・破壊できません。
- コマンドブロックは床下。プレイ中に`fill`・`setblock`・`structure`・`function`を実行しません。

外部パックは空の一覧。チート／コマンドブロックが必要です。実績獲得用ワールドではありません。
保存形式を1.19.50とし、新しいexecute構文を使用します。コマンドブロックの`Version`は36です。
現在のWindows版でのアップグレード、看板、コマンド実行は実機確認項目です。
管理者コマンドや設定変更による脱出を制限するセキュリティ機能ではありません。

## 検証の区別

検証スクリプトは配布ZIPそのものを展開して新しくLevelDBを開き、ZIP CRC、NBT、
チャンク、ブロック状態、看板、コマンド保存内容を検査します。実ブロックから幅1・高さ2の
移動経路を探索し、回答域への到達、囲い、全移動先の床と空間を確認します。
Minecraftのコマンドパーサー・描画・インポートUIの検証とは別です。
グリッド探索は簡略化した衝突判定で、ゲームの当たり判定・ティック順序は実機確認が必要です。
旧パック現物を調査していないため、以前の3問目の原因は断定しません。
今回の構成では、建築タイミングを移動・チャンク読込から切り離します。

## 公式サーバーの補助検証（v2）

Linux版Bedrock Dedicated Server 1.26.52.3を使用します。配布ZIPのコピーをパックなし・冒険・ピースフルで読み込みます。
元ワールドでは全11到着地点の床・空間と31感圧板を確認し、107コマンドをコンソールへ投入します。
プレイヤー未接続の対象なしという結果は想定どおりで、文字や音の表示・再生確認にはなりません。

別のテストコピーでは`@a[...]`を`@e[type=pig,name=maze_probe,...]`へ変更します。
ブタは実際に石の感圧板を押せるので、板、支持ブロック、信号を受けるインパルス、下向きチェーンと移動先を維持して検証できます。
各板へブタを生成し、移動抑制効果を与え、回答後の到着域で検出します。
これはプレイヤーの権限、画面、音や操作のしやすさを確認するものではありません。
配布ファイルをサーバー変換済み／対象置換済みのテストコピーに置換しません。

最新結果は`dist/server_validation.json`、初版結果は`dist/server_validation_v1.json`。
投入コマンドは`docs/server_probe_console.txt`と`docs/server_surrogate_console.txt`。
テストコピーは`python scripts/make_server_test_world.py /path/to/server [--surrogate]`で作成できます。
専用テストサーバーでlevel-nameを表示された名前へ変更し、チート有効・冒険・ピースフルで起動します。
先に`tickingarea add -16 0 -16 143 90 111 maze_qa true`を投入し、全域の読込を確認してから一覧を投入します。
ブタ用一覧の前に入口で`summon pig maze_probe 16.5 65 3.5`しておくと、最初のkillも対象を持ちます。
到着の判定範囲は床上の小さな領域で、テレポート後のブタの微小な動きを許容します。
サーバーのバイナリや公式リソースはリポジトリへ同梱しません。

## 一次資料

- Amulet公式のPython API／Bedrock対応説明：https://www.amuletmc.com/python
- Amulet公式のLevelDBFormat／新規作成API：https://amulet-core.readthedocs.io/en/stable/api_reference/level.formats/leveldb_world.html
- 使用ライブラリ実装（配布版1.9.49も確認）：https://github.com/Amulet-Team/Amulet-Core
- Microsoft公式のコマンドブロック：https://github.com/MicrosoftDocs/minecraft-creator/blob/main/creator/Documents/CommandBlocks.md
- Minecraft公式の1.19.50 execute変更：https://feedback.minecraft.net/hc/en-us/articles/10833168748557-Minecraft-1-19-50-Bedrock
- Microsoft公式execute：https://learn.microsoft.com/en-us/minecraft/creator/reference/content/commandsreference/examples/commands/execute?view=minecraft-bedrock-stable
- Microsoft公式titleraw：https://learn.microsoft.com/en-us/minecraft/creator/reference/content/commandsreference/examples/commands/titleraw?view=minecraft-bedrock-stable
- Microsoft公式particle：https://github.com/MicrosoftDocs/minecraft-creator/blob/main/creator/Reference/Content/CommandsReference/Examples/Commands/particle.md

- Microsoft公式のブロック状態（感圧板のredstone_signal）：https://learn.microsoft.com/en-us/minecraft/creator/reference/content/vanillalistingsreference/blocks?view=minecraft-bedrock-stable

## v3修正

北側の入口から南の壁を見る場合、画面の右はワールドXの負方向になるため、ブロック文字のX配置を反転しました。選択肢の赤・黄・緑もX=26、16、5に配置し、入口視点の順序に合わせています。配置図もXを反転して、実際の視点に合わせました。
□表示の正確な原因は未特定です。日本語・Unicodeの矢印・文字装飾を画面と看板から除き、英数字のみ保存することを検証します。矢印は床のブロックで示します。v3は静的検証のみで、v2のサーバー検証結果を引き継いだ扱いにはしません。

## v4：子ども向け日本語の復元

英語化はやり過ぎだったため、説明とお祝いをひらがなに戻します。特殊な矢印の文字や色装飾は使わず、床のブロック矢印と大きな数字を維持します。画面文字のJSONはensure_ascii=TrueでUnicodeエスケープを保存し、看板は通常のひらがな文字列を保存します。日本語の表示が□になる原因の特定・ゲーム本体での修正確認は未実施です。
