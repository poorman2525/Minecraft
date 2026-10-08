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
- 16×16の室をチャンクに合わせ、64×48内に10室とゴールを配置します。
- 床Y=64、足元Y=65、天井Y=70。全室を完全に閉じます。
- 生成完了状態=2で保存し、周辺を含む30チャンクを生成済みとします。
- 問題は毎秒のアクションバーと通路奥の看板で表示します。
- 回答は色付き通路奥の座標範囲で検出。クリックや感圧板のレッドストーンに依存しません。
- リピート→下向きチェーンで結果表示・音・移動を実行します。
- 正解は次室入口、不正解は同室入口へ戻します。入口は判定域から離して再判定を防ぎます。
- ゴールは`maze_goal`タグで文字・音を一度だけ再生し、粒子は滞在中に繰り返します。
- 青い通路でタグを消し、1問目へ戻します。
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

## 公式サーバーの補助検証

Linux版Bedrock Dedicated Server 1.26.52.3を公式配布から取得し、配布ZIPのコピーを読み込みました。
パックスタックはNone、冒険モード、ピースフルで起動しました。
全11到着地点の床・足元・頭上を`testforblock`で確認（33件成功）。
107コマンドのコンソール投入で構文エラー0件。プレイヤーがいないため106件は対象なし、
1件はif entity不成立でした。粒子の直接コマンドは受理されましたが、見た目は未確認です。
サーバー保存後、42看板すべてのFrontTextが非空、107コマンドが保存されていることも確認しました。

次に別のテストコピーで`@a[...]`を`@e[type=armor_stand,name=maze_probe,...]`に変更しました。
地形・コマンドブロック設定・TPコマンドと移動先を維持したまま、各回答域へ防具立てを生成し、
チェーンによる自動移動後の位置を`testfor`で検出。全30経路で到着確認、エラー0件でした。
これはコマンドブロックの実行・移動処理の補助検証であり、プレイヤーの権限、画面、音や
操作しやすさを確認するものではありません。配布ファイルをサーバー変換済みコピーに置換していません。

検証記録は`dist/server_validation.json`。
投入コマンドは`docs/server_probe_console.txt`と`docs/server_surrogate_console.txt`。
テストコピーは`python scripts/make_server_test_world.py /path/to/server [--surrogate]`で作成できます。
専用のテスト用サーバーでlevel-nameを表示された名前へ変更し、チート有効・冒険・ピースフルで起動します。
先に`tickingarea add -16 0 -16 79 80 63 maze_qa true`を投入し、読込を待ってから各コマンド一覧を投入します。
元ワールド用一覧のプレイヤー対象なしは想定どおり。防具立て用一覧では`Found maze_probe`が30件になることを確認します。
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
