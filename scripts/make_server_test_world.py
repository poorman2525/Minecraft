"""Create disposable BDS QA fixtures. Never modify the distributed mcworld."""
import argparse
from pathlib import Path
import zipfile
from amulet_nbt import load, StringTag
from leveldb import LevelDB

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("server_root", type=Path, help="An isolated test server directory")
    parser.add_argument("--surrogate", action="store_true")
    args = parser.parse_args()
    name = "math_maze_surrogate" if args.surrogate else "math_maze_original"
    destination = args.server_root / "worlds" / name
    if destination.exists():
        raise SystemExit(f"Refusing to overwrite {destination}; use a fresh test folder.")
    with zipfile.ZipFile(ROOT / "dist/math_maze_v1.mcworld") as archive:
        archive.extractall(destination)
    changed = 0
    if args.surrogate:
        db = LevelDB(str(destination / "db"))
        try:
            for key, payload in list(db.items()):
                if len(key) != 9 or key[-1] != 0x31:
                    continue
                tags = []
                while payload:
                    tag, size = load(payload, compressed=False, little_endian=True, offset=True)
                    c = tag.compound
                    if c["id"].py_str == "CommandBlock":
                        c["Command"] = StringTag(c["Command"].py_str.replace(
                            "@a[", "@e[type=armor_stand,name=maze_probe,"))
                        changed += 1
                    tags.append(tag.save_to(compressed=False, little_endian=True))
                    payload = payload[size:]
                db.put(key, b"".join(tags))
        finally:
            db.close()
    print(f"Test world: {destination}\nSet server.properties level-name={name}")
    print(f"Modified command selectors: {changed}")


if __name__ == "__main__":
    main()
