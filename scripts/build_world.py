"""Bake an enclosed Bedrock math maze. No runtime construction or packs.

Amulet serializes the terrain; native little-endian NBT block entities are
written afterwards to avoid lossy command/sign translation.
"""
from pathlib import Path
from collections import defaultdict
import json
import shutil
import struct
import zipfile
import amulet
from amulet.api.block import Block
from amulet.api.level import World
from amulet.level.formats.leveldb_world import LevelDBFormat
from amulet_nbt import NamedTag, CompoundTag, StringTag, IntTag, ByteTag, LongTag, ListTag

ROOT = Path(__file__).resolve().parents[1]
VERSION = (1, 19, 50)
DIM = "minecraft:overworld"
WORLD = ROOT / "build" / "math_maze"
OUT = ROOT / "dist" / "math_maze_v1.mcworld"


def origin(i):
    return (i % 4 * 16, i // 4 * 16)


def entry(i):
    x, z = origin(i)
    return [x + 8.5, 65, z + 3.5]


def raw(text):
    return json.dumps({"rawtext": [{"text": text}]}, ensure_ascii=False, separators=(",", ":"))


def build():
    questions = json.loads((ROOT / "data/questions.json").read_text())
    assert len(questions) == 10
    assert sum(q["op"] == "+" for q in questions) == 5
    WORLD.parent.mkdir(parents=True, exist_ok=True)
    if WORLD.exists():
        shutil.rmtree(WORLD)
    wrapper = LevelDBFormat(str(WORLD))
    wrapper.create_and_open("bedrock", VERSION)
    root = wrapper.root_tag.compound
    for k, v in {"GameType": 2, "Difficulty": 0, "Generator": 2,
                 "SpawnX": 8, "SpawnY": 65, "SpawnZ": 3, "spawnradius": 0,
                 "serverChunkTickRange": 4, "maxcommandchainlength": 128,
                 "permissionsLevel": 1, "playerPermissionsLevel": 1}.items():
        root[k] = IntTag(v)
    for k, v in {"commandsEnabled": 1, "cheatsEnabled": 1, "commandblocksenabled": 1,
                 "commandblockoutput": 0, "sendcommandfeedback": 0,
                 "dodaylightcycle": 0, "doweathercycle": 0, "domobspawning": 0,
                 "spawnMobs": 0, "dofiretick": 0, "mobgriefing": 0,
                 "keepinventory": 1, "falldamage": 0, "pvp": 0,
                 "MultiplayerGame": 0, "MultiplayerGameIntent": 0,
                 "LANBroadcast": 0, "LANBroadcastIntent": 0,
                 "hasBeenLoadedInCreative": 1, "ForceGameType": 1}.items():
        root[k] = ByteTag(v)
    root["LevelName"] = StringTag("さんすう 3たく めいろ 10もん")
    root["Time"] = LongTag(6000)
    root["RandomSeed"] = LongTag(20261008)
    root["FlatWorldLayers"] = StringTag(json.dumps({"biome_id": 1,
        "block_layers": [{"block_name": "minecraft:bedrock", "count": 1},
                         {"block_name": "minecraft:dirt", "count": 2},
                         {"block_name": "minecraft:grass", "count": 1}],
        "encoding_version": 5, "world_version": "version.post_1_18"}))
    wrapper.save()
    wrapper.close()
    level = World(str(WORLD), wrapper)
    entities = defaultdict(list)
    manifest = {"format_version": list(VERSION), "spawn": entry(0),
                "rooms": [], "commands": [], "signs": [], "prebuilt_chunks": []}
    cache = {}

    def put(x, y, z, name, **props):
        key = (name, tuple(sorted(props.items())))
        if key not in cache:
            tags = {k: ByteTag(v) if isinstance(v, bool) else IntTag(v) if isinstance(v, int)
                    else StringTag(v) for k, v in props.items()}
            cache[key] = level.translation_manager.get_version("bedrock", VERSION).block.to_universal(
                Block("minecraft", name, tags))[0]
        chunk = level.get_chunk(x // 16, z // 16, DIM)
        chunk.set_block(x % 16, y, z % 16, cache[key])
        chunk.changed = True

    def entity(x, y, z, kind, fields):
        tag = CompoundTag({"id": StringTag(kind), "x": IntTag(x), "y": IntTag(y), "z": IntTag(z), **fields})
        entities[(x // 16, z // 16)].append(NamedTag(tag))

    def sign(x, y, z, text, facing=2):
        put(x, y, z, "wall_sign", facing_direction=facing)
        text_fields = {"Text": StringTag(text), "TextOwner": StringTag(""),
            "IgnoreLighting": ByteTag(1), "SignTextColor": IntTag(-16777216), "PersistFormatting": ByteTag(1)}
        entity(x, y, z, "Sign", {**text_fields, "FrontText": CompoundTag(text_fields),
            "BackText": CompoundTag(text_fields), "IsWaxed": ByteTag(1), "isMovable": ByteTag(0)})
        manifest["signs"].append({"position": [x, y, z], "text": text})

    def chain(x, z, commands, delay=0):
        # Vertical arrow direction 0 = down. Four blocks fit below the floor.
        assert len(commands) <= 5
        for j, command in enumerate(commands):
            y = 62 - j
            kind = "repeating_command_block" if j == 0 else "chain_command_block"
            put(x, y, z, kind, facing_direction=0, conditional_bit=False)
            entity(x, y, z, "CommandBlock", {
                "Command": StringTag(command), "CustomName": StringTag("さんすう"),
                "Version": IntTag(36), "SuccessCount": IntTag(0), "isMovable": ByteTag(0),
                "LastOutput": StringTag(""), "LastOutputParams": ListTag([]),
                "TrackOutput": ByteTag(0), "auto": ByteTag(1), "powered": ByteTag(0),
                "conditionMet": ByteTag(0), "LPCommandMode": IntTag(1 if j == 0 else 2),
                "LPCondionalMode": ByteTag(0), "LPRedstoneMode": ByteTag(0),
                "TickDelay": IntTag(delay if j == 0 else 0), "ExecuteOnFirstTick": ByteTag(1),
                "LastExecution": LongTag(-1), "UpdateLastExecution": ByteTag(1)})
            manifest["commands"].append({"position": [x, y, z], "kind": kind,
                                         "command": command, "delay": delay if j == 0 else 0})

    # Buffer chunks are baked too. Finished state prevents terrain population
    # from replacing the room shells when a new room is first visited.
    for cx in range(-1, 5):
        for cz in range(-1, 4):
            chunk = level.create_chunk(cx, cz, DIM)
            chunk.status.value = 2.0
            manifest["prebuilt_chunks"].append([cx, cz])
            for x in range(cx * 16, cx * 16 + 16):
                for z in range(cz * 16, cz * 16 + 16):
                    put(x, 63, z, "bedrock")
                    put(x, 64, z, "stone")

    colors = ["red", "yellow", "lime"]
    for i in range(11):
        ox, oz = origin(i)
        for x in range(ox, ox + 16):
            for z in range(oz, oz + 16):
                put(x, 64, z, "planks", wood_type="birch")
                put(x, 70, z, "glass")
                if x in (ox, ox + 15) or z in (oz, oz + 15):
                    for y in range(65, 70):
                        put(x, y, z, "stonebrick", stone_brick_type="default")
        for x in (ox + 2, ox + 13):
            for z in (oz + 2, oz + 7, oz + 13):
                put(x, 70, z, "glowstone")
        room_sel = f"@a[x={ox+1},y=65,z={oz+1},dx=13,dy=3,dz=13]"
        if i < 10:
            q = questions[i]
            answer = q["a"] + q["b"] if q["op"] == "+" else q["a"] - q["b"]
            assert len(set(q["choices"])) == 3 and q["choices"].count(answer) == 1
            expr = f'{q["a"]} {q["op"]} {q["b"]} = ?'
            room = {"index": i, "origin": [ox, oz], "entry": entry(i), "question": q,
                    "answer": answer, "routes": []}
            manifest["rooms"].append(room)
            choices = "   ".join(f'{label}:{val}' for label, val in zip(["ひだり", "まんなか", "みぎ"], q["choices"]))
            chain(ox + 1, oz + 2, [f'execute as {room_sel} run titleraw @s actionbar {raw(f"{i+1}/10   {expr}   {choices}")}'], delay=20)
            for x in (ox + 5, ox + 10):
                for z in range(oz + 8, oz + 15):
                    for y in range(65, 70):
                        put(x, y, z, "stonebrick", stone_brick_type="default")
            for c, center in enumerate((3, 8, 13)):
                for x in range(ox + center - 1, ox + center + 2):
                    for z in range(oz + 9, oz + 15):
                        put(x, 64, z, "wool", color=colors[c])
                sign(ox + center, 67, oz + 14, f"{i+1}/10\n{expr}\nこたえ {q['choices'][c]}\nこのみちへ")
                selector = f"@a[x={ox+center-1},y=65,z={oz+12},dx=2,dy=2,dz=2]"
                correct = q["choices"][c] == answer
                dest = entry(i + 1 if correct else i)
                feedback = "せいかい！" if correct else "もういちど！"
                sound = "random.levelup" if correct else "note.bass"
                commands = [f'execute as {selector} run titleraw @s title {raw(feedback)}',
                            f'execute as {selector} at @s run playsound {sound} @s ~ ~ ~ 0.5 1',
                            f'execute as {selector} run tp @s {dest[0]} {dest[1]} {dest[2]} 0 0']
                chain(ox + center, oz + 12, commands)
                room["routes"].append({"choice": q["choices"][c], "correct": correct,
                    "trigger": [ox + center - 1, 65, oz + 12, 2, 2, 2], "destination": dest})
            sign(ox + 7, 67, oz + 1, "さんすう めいろ\nW で あるく\nこたえの みちへ\nすすもう！", facing=3)
        else:
            goal_sel = room_sel[:-1] + ",tag=!maze_goal]"
            chain(ox + 8, oz + 3, [
                f'execute as {goal_sel} run titleraw @s subtitle {raw("10もん クリア！ よく がんばったね！")}',
                f'execute as {goal_sel} run titleraw @s title {raw("おめでとう！")}',
                f'execute as {goal_sel} at @s run playsound random.levelup @s ~ ~ ~ 1 1',
                f'execute as {goal_sel} run tag @s add maze_goal'])
            sign(ox + 8, 67, oz + 14, "ゴール！\n10もん クリア\nおめでとう！\nまた あそぼう")
            for x in range(ox + 5, ox + 11):
                for z in range(oz + 6, oz + 12):
                    put(x, 64, z, "gold_block")
            chain(ox + 1, oz + 3, [f'execute if entity {room_sel} run particle minecraft:totem_particle {ox+8.5} 67 {oz+8.5}'], delay=30)
            restart = f"@a[x={ox+1},y=65,z={oz+12},dx=2,dy=2,dz=2]"
            sign(ox + 2, 67, oz + 14, "もういちど\nあそぶときは\nあおい みちへ\nあるこう")
            for x in range(ox + 1, ox + 4):
                for z in range(oz + 10, oz + 15):
                    put(x, 64, z, "wool", color="light_blue")
            chain(ox + 2, oz + 12, [f'execute as {restart} run tag @s remove maze_goal',
                f'execute as {restart} run tp @s 8.5 65 3.5 0 0'])
    level.save()
    # Native block entities are serialized only AFTER translated terrain save.
    for (cx, cz), tags in entities.items():
        key = struct.pack("<ii", cx, cz) + b"\x31"
        wrapper.level_db.put(key, b"".join(t.save_to(compressed=False, little_endian=True) for t in tags))
    level.close()
    shutil.copyfile(WORLD / "level.dat", WORLD / "level.dat_old")
    (WORLD / "world_behavior_packs.json").write_text("[]\n")
    (WORLD / "world_resource_packs.json").write_text("[]\n")
    OUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(WORLD.rglob("*")):
            if path.is_file() and path.name != "LOCK":
                archive.write(path, path.relative_to(WORLD))
    (ROOT / "dist/layout.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"Created {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build()
