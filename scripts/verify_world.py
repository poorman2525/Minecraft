"""Read the DELIVERED ZIP afresh; this is static QA, not a game test."""
from pathlib import Path
from collections import deque
import hashlib
import json
import math
import re
import struct
import tempfile
import zipfile
import amulet
from amulet_nbt import load

ROOT = Path(__file__).resolve().parents[1]
DIM = "minecraft:overworld"
VERSION = ("bedrock", (1, 19, 50))


def verify():
    artifact = ROOT / "dist/math_maze_v1.mcworld"
    layout = json.loads((ROOT / "dist/layout.json").read_text())
    checks = []
    counts = {}
    with tempfile.TemporaryDirectory() as folder:
        with zipfile.ZipFile(artifact) as archive:
            assert archive.testzip() is None
            names = archive.namelist()
            assert "level.dat" in names and "levelname.txt" in names
            assert any(n.startswith("db/") for n in names)
            assert not any(n.startswith(("behavior_packs/", "resource_packs/")) for n in names)
            assert not any(n.endswith((".js", ".mcfunction")) for n in names)
            for name in names:
                assert not name.startswith("/") and ".." not in Path(name).parts
            archive.extractall(folder)
        checks.append("ZIP CRC, root paths, required world files, no scripts or packs")
        path = Path(folder)
        for name in ("world_behavior_packs.json", "world_resource_packs.json"):
            assert json.loads((path / name).read_text()) == []
        blob = (path / "level.dat").read_bytes()
        header, size = struct.unpack("<ii", blob[:8])
        assert header in (8, 9, 10) and size == len(blob) - 8
        root = load(blob[8:], compressed=False, little_endian=True).compound
        for key, val in {"GameType": 2, "Difficulty": 0, "SpawnX": 8, "SpawnY": 65,
                         "SpawnZ": 3, "spawnradius": 0, "commandsEnabled": 1,
                         "commandblocksenabled": 1, "MultiplayerGame": 0}.items():
            assert root[key].py_int == val, key
        assert (path / "level.dat_old").read_bytes() == blob
        checks.append("Little-endian level.dat and header, adventure/peaceful/spawn/commands settings")
        level = amulet.load_level(folder)
        wrapper = level.level_wrapper
        def block(x, y, z):
            return level.get_version_block(x, y, z, DIM, VERSION)[0]
        def empty(x, y, z):
            return block(x, y, z).base_name == "air"
        def safe(p):
            x, y, z = map(math.floor, p)
            assert not empty(x, y - 1, z), p
            for dx in (0,):
                assert empty(x + dx, y, z) and empty(x + dx, y + 1, z), p
        try:
            chunks = set(level.all_chunk_coords(DIM))
            assert chunks == set(map(tuple, layout["prebuilt_chunks"]))
            for cx, cz in chunks:
                state = wrapper.level_db.get(struct.pack("<ii", cx, cz) + b"\x36")
                assert struct.unpack("<i", state)[0] == 2, (cx, cz)
            checks.append("All 30 prebuilt chunks readable and finalized in stored LevelDB")
            entities = {}
            for cx, cz in chunks:
                key = struct.pack("<ii", cx, cz) + b"\x31"
                try:
                    payload = wrapper.level_db.get(key)
                except KeyError:
                    continue
                while payload:
                    tag, offset = load(payload, compressed=False, little_endian=True, offset=True)
                    t = tag.compound
                    position = tuple(t[k].py_int for k in ("x", "y", "z"))
                    assert position not in entities
                    assert position[0] // 16 == cx and position[2] // 16 == cz
                    entities[position] = t
                    payload = payload[offset:]
            # Compare actual saved command NBT and translated block states.
            for record in layout["commands"]:
                pos = tuple(record["position"])
                tag = entities[pos]
                assert tag["id"].py_str == "CommandBlock"
                assert tag["Command"].py_str == record["command"]
                assert tag["auto"].py_int == 1 and tag["powered"].py_int == 0
                assert tag["Version"].py_int == 36
                assert tag["TickDelay"].py_int == record["delay"]
                b = block(*pos)
                assert b.base_name == record["kind"]
                assert b.properties["facing_direction"].py_int == 0
                assert b.properties["conditional_bit"].py_int == 0
                cmd = record["command"]
                assert not re.search(r"\b(fill|setblock|clone|structure|function)\b", cmd)
                if "titleraw" in cmd:
                    json.loads(cmd[cmd.index("{"):])
            for record in layout["signs"]:
                pos = tuple(record["position"])
                tag = entities[pos]
                assert block(*pos).base_name == "wall_sign"
                assert tag["id"].py_str == "Sign" and tag["Text"].py_str == record["text"]
                assert tag["FrontText"]["Text"].py_str == record["text"]
            assert len(entities) == len(layout["commands"]) + len(layout["signs"])
            checks.append("All saved command/sign NBT, downward chains, always-active flags and text checked")
            # Every room has no physical opening to another room/the outside.
            for i in range(11):
                ox, oz = (i % 4 * 16, i // 4 * 16)
                for x in range(ox, ox + 16):
                    for z in range(oz, oz + 16):
                        assert not empty(x, 64, z)
                        assert not empty(x, 70, z)
                        if x in (ox, ox + 15) or z in (oz, oz + 15):
                            for y in range(65, 70):
                                assert not empty(x, y, z)
                safe([ox + 8.5, 65, oz + 3.5])
            checks.append("All 11 rooms fully enclosed, floors/roofs/walls stored; all arrivals safe")
            assert len(layout["rooms"]) == 10
            for room in layout["rooms"]:
                q = room["question"]
                answer = q["a"] + q["b"] if q["op"] == "+" else q["a"] - q["b"]
                routes = room["routes"]
                assert len(routes) == 3 and len(set(q["choices"])) == 3
                assert sum(r["correct"] for r in routes) == 1
                sx, _, sz = map(math.floor, room["entry"])
                reachable = {(sx, sz)}
                todo = deque(reachable)
                while todo:
                    x, z = todo.popleft()
                    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        p = x + dx, z + dz
                        if p not in reachable and empty(p[0], 65, p[1]) and empty(p[0], 66, p[1]):
                            reachable.add(p)
                            todo.append(p)
                ox, oz = room["origin"]
                assert all(ox < x < ox + 15 and oz < z < oz + 15 for x, z in reachable)
                for route in routes:
                    assert route["correct"] == (route["choice"] == answer)
                    x, _, z, dx, _, dz = route["trigger"]
                    assert any((tx, tz) in reachable for tx in range(x, x + dx + 1) for tz in range(z, z + dz + 1))
                    safe(route["destination"])
                    j = room["index"] + 1 if route["correct"] else room["index"]
                    expected = [j % 4 * 16 + 8.5, 65, j // 4 * 16 + 3.5]
                    assert route["destination"] == expected
                    selector = f"@a[x={x},y=65,z={z},dx={dx},dy=2,dz={dz}]"
                    dest = route["destination"]
                    expected_tp = f"execute as {selector} run tp @s {dest[0]} {dest[1]} {dest[2]} 0 0"
                    assert entities[(x + 1, 60, z)]["Command"].py_str == expected_tp
                # Entry is outside every answer trigger, avoiding immediate re-trigger.
                assert all(not (r["trigger"][0] <= sx <= r["trigger"][0] + 2 and
                                    r["trigger"][2] <= sz <= r["trigger"][2] + 2) for r in routes)
            checks.append("Arithmetic, 30 reachable choice routes, 10 correct advances and 20 retries checked against saved TP commands")
            commands = [e["Command"].py_str for e in entities.values() if e["id"].py_str == "CommandBlock"]
            assert any("tag=!maze_goal" in c and "おめでとう" in c for c in commands)
            assert any("particle minecraft:totem_particle" in c for c in commands)
            assert any("remove maze_goal" in c for c in commands)
            counts = {"questions": 10, "addition": 5, "subtraction": 5, "routes": 30,
                      "correct_routes": 10, "retry_routes": 20, "rooms_including_goal": 11,
                      "chunks": len(chunks), "command_blocks": len(layout["commands"]), "signs": len(layout["signs"])}
            checks.append("Goal congratulations, sound/particle commands and replay route present")
        finally:
            level.close()
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    server_path = ROOT / "dist/server_validation.json"
    server_status = "NOT_TESTED"
    if server_path.exists() and json.loads(server_path.read_text())["artifact_sha256"] == digest:
        server_status = "SEE_SEPARATE_SERVER_VALIDATION_REPORT"
    report = {"artifact": artifact.name, "sha256": digest,
        "size_bytes": artifact.stat().st_size, "static_validation": "PASS", "counts": counts, "checks": checks,
        "minecraft_windows_import": "NOT_TESTED", "minecraft_gameplay": "NOT_TESTED",
        "bedrock_dedicated_server": server_status,
        "limitations": ["No Minecraft for Windows client is available in this environment.",
                        "This static validator does not execute commands; see the separate server report.",
                        "Sign rendering, first spawn, ticking/teleport timing, sounds and particles require Windows Bedrock playtesting."]}
    (ROOT / "dist/validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    verify()
