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
OUT = ROOT / "dist" / "math_maze_v3.mcworld"
WIDTH, DEPTH, FLOOR, ROOF = 32, 32, 64, 80
CENTERS = (26, 16, 5)
LANES = ((22, 30), (12, 20), (1, 10))
FONT = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "+": ("000", "010", "111", "010", "000"),
    "-": ("000", "000", "111", "000", "000"),
    "=": ("000", "111", "000", "111", "000"),
    "?": ("111", "001", "011", "000", "010"),
}


def origin(i):
    return (i % 4 * WIDTH, i // 4 * DEPTH)


def entry(i):
    x, z = origin(i)
    return [x + 16.5, 65, z + 3.5]


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
                 "SpawnX": 16, "SpawnY": 65, "SpawnZ": 3, "spawnradius": 0,
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
    root["LevelName"] = StringTag("Math Maze v3")
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
    manifest = {"artifact": OUT.name, "format_version": list(VERSION), "spawn": entry(0),
                "geometry": {"width": WIDTH, "depth": DEPTH, "floor": FLOOR, "roof": ROOF},
                "controls": "stone_pressure_plate", "pixel_texts": [], "floor_arrows": [],
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

    def pixel_text(text, center_x, bottom, z, color):
        width = len(text) * 4 - 1
        start = center_x - width // 2
        pixels = []
        for c, char in enumerate(text):
            for row, pattern in enumerate(FONT[char]):
                for col, bit in enumerate(pattern):
                    if bit == "1":
                        pos = [start + width - 1 - (c * 4 + col), bottom + 4 - row, z]
                        put(*pos, "wool", color=color)
                        pixels.append(pos)
        manifest["pixel_texts"].append({"text": text, "origin": [start, bottom, z],
            "width": width, "height": 5, "view": "from_north_facing_south", "color": color, "pixels": pixels})

    def floor_arrow(x, z, color):
        pixels = []
        # View from the entry: the arrow points forward toward the answer plate.
        for row, pattern in enumerate(("00100", "00100", "00100", "00100", "11111", "01110", "00100")):
            for col, bit in enumerate(pattern):
                if bit == "1":
                    pos = [x - 2 + col, FLOOR, z + row]
                    put(*pos, "wool", color=color)
                    pixels.append(pos)
        manifest["floor_arrows"].append({"color": color, "pixels": pixels})

    def chain(x, z, commands, delay=0, plate=False):
        # Vertical arrow direction 0 = down. Four blocks fit below the floor.
        assert len(commands) <= 5
        for j, command in enumerate(commands):
            y = (63 if plate else 62) - j
            kind = ("command_block" if plate else "repeating_command_block") if j == 0 else "chain_command_block"
            auto = not (plate and j == 0)
            put(x, y, z, kind, facing_direction=0, conditional_bit=False)
            entity(x, y, z, "CommandBlock", {
                "Command": StringTag(command), "CustomName": StringTag("Math Maze"),
                "Version": IntTag(36), "SuccessCount": IntTag(0), "isMovable": ByteTag(0),
                "LastOutput": StringTag(""), "LastOutputParams": ListTag([]),
                "TrackOutput": ByteTag(0), "auto": ByteTag(auto), "powered": ByteTag(0),
                "conditionMet": ByteTag(0), "LPCommandMode": IntTag((0 if plate else 1) if j == 0 else 2),
                "LPCondionalMode": ByteTag(0), "LPRedstoneMode": ByteTag(not auto),
                "TickDelay": IntTag(delay if j == 0 else 0), "ExecuteOnFirstTick": ByteTag(1),
                "LastExecution": LongTag(-1), "UpdateLastExecution": ByteTag(1)})
            manifest["commands"].append({"position": [x, y, z], "kind": kind,
                                         "command": command, "delay": delay if j == 0 else 0,
                                         "auto": int(auto)})

    # Buffer chunks are baked too. Finished state prevents terrain population
    # from replacing the room shells when a new room is first visited.
    for cx in range(-1, 9):
        for cz in range(-1, 7):
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
        for x in range(ox, ox + WIDTH):
            for z in range(oz, oz + DEPTH):
                put(x, 64, z, "planks", wood_type="birch")
                put(x, ROOF, z, "glass")
                if x in (ox, ox + WIDTH - 1) or z in (oz, oz + 31):
                    for y in range(65, ROOF):
                        put(x, y, z, "stonebrick", stone_brick_type="default")
        for x in (ox + 2, ox + 10, ox + 21, ox + 29):
            for z in (oz + 4, oz + 14, oz + 27):
                put(x, ROOF, z, "glowstone")
        room_sel = f"@a[x={ox+1},y=65,z={oz+1},dx=29,dy=14,dz=29]"
        if i < 10:
            q = questions[i]
            answer = q["a"] + q["b"] if q["op"] == "+" else q["a"] - q["b"]
            assert len(set(q["choices"])) == 3 and q["choices"].count(answer) == 1
            expr = f'{q["a"]} {q["op"]} {q["b"]} = ?'
            room = {"index": i, "origin": [ox, oz], "entry": entry(i), "question": q,
                    "answer": answer, "routes": []}
            manifest["rooms"].append(room)
            choices = "   ".join(f'[{val}]' for val in q["choices"])
            chain(ox + 1, oz + 2, [f'execute as {room_sel} run titleraw @s actionbar {raw(f"{i+1}/10   {expr}   {choices}   STEP ON A PLATE")}'], delay=20)
            # Broad, high-contrast display panels and 5-block-tall arithmetic.
            for x in range(ox + 1, ox + 31):
                for y in range(73, 80):
                    put(x, y, oz + 31, "wool", color="white")
            pixel_text(f'{q["a"]}{q["op"]}{q["b"]}=?', ox + 16, 74, oz + 31, "black")
            for x in (ox + 11, ox + 21):
                for z in range(oz + 18, oz + 31):
                    for y in range(65, 74):
                        put(x, y, z, "stonebrick", stone_brick_type="default")
            for c, center in enumerate(CENTERS):
                for x in range(ox + LANES[c][0], ox + LANES[c][1] + 1):
                    for z in range(oz + 19, oz + 31):
                        put(x, 64, z, "wool", color=colors[c])
                    for y in range(65, 72):
                        put(x, y, oz + 31, "wool", color=colors[c])
                pixel_text(str(q["choices"][c]), ox + center, 66, oz + 31, "white" if c == 0 else "black")
                floor_arrow(ox + center, oz + 12, colors[c])
                sign(ox + center, 72, oz + 30, f"{q['choices'][c]}\nSTEP ON\nTHE PLATE\nNO CLICK")
                put(ox + center, 65, oz + 26, "stone_pressure_plate", redstone_signal=0)
                selector = f"@a[x={ox+center},y=65,z={oz+26},dx=0,dy=2,dz=0]"
                correct = q["choices"][c] == answer
                dest = entry(i + 1 if correct else i)
                feedback = "OK!" if correct else "TRY AGAIN"
                sound = "random.levelup" if correct else "note.bass"
                commands = [f'execute as {selector} run titleraw @s title {raw(feedback)}',
                            f'execute as {selector} at @s run playsound {sound} @s ~ ~ ~ 0.5 1',
                            f'execute as {selector} run tp @s {dest[0]} {dest[1]} {dest[2]} 0 0']
                chain(ox + center, oz + 26, commands, plate=True)
                room["routes"].append({"choice": q["choices"][c], "correct": correct,
                    "trigger": [ox + center, 65, oz + 26, 0, 2, 0], "plate": [ox + center, 65, oz + 26],
                    "tp_command_position": [ox + center, 61, oz + 26], "destination": dest})
            sign(ox + 16, 67, oz + 1, "MATH MAZE\nW = WALK\nFOLLOW ARROW\nSTEP ON PLATE", facing=3)
        else:
            goal_sel = room_sel[:-1] + ",tag=!maze_goal]"
            chain(ox + 16, oz + 3, [
                f'execute as {goal_sel} run titleraw @s subtitle {raw("10/10 CLEAR!")}',
                f'execute as {goal_sel} run titleraw @s title {raw("GREAT!")}',
                f'execute as {goal_sel} at @s run playsound random.levelup @s ~ ~ ~ 1 1',
                f'execute as {goal_sel} run tag @s add maze_goal'])
            sign(ox + 16, 67, oz + 30, "GOAL!\n10/10 CLEAR\nGREAT!\nPLAY AGAIN")
            for x in range(ox + 1, ox + 31):
                for y in range(73, 80):
                    put(x, y, oz + 31, "wool", color="white")
            pixel_text("10", ox + 16, 74, oz + 31, "lime")
            for x in range(ox + 5, ox + 11):
                for z in range(oz + 6, oz + 26):
                    put(x, 64, z, "gold_block")
            chain(ox + 1, oz + 3, [f'execute if entity {room_sel} run particle minecraft:totem_particle {ox+16.5} 67 {oz+8.5}'], delay=30)
            restart = f"@a[x={ox+5},y=65,z={oz+26},dx=0,dy=2,dz=0]"
            sign(ox + 5, 67, oz + 30, "PLAY AGAIN\nBLUE ARROW\nSTEP ON\nTHE PLATE")
            for x in range(ox + 3, ox + 8):
                for z in range(oz + 19, oz + 31):
                    put(x, 64, z, "wool", color="light_blue")
            floor_arrow(ox + 5, oz + 12, "light_blue")
            put(ox + 5, 65, oz + 26, "stone_pressure_plate", redstone_signal=0)
            manifest["restart_plate"] = [ox + 5, 65, oz + 26]
            chain(ox + 5, oz + 26, [f'execute as {restart} run tag @s remove maze_goal',
                f'execute as {restart} run tp @s 16.5 65 3.5 0 0'], plate=True)
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
