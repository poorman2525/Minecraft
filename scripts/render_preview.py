"""Exact block-grid schematic, not a screenshot from Minecraft."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import amulet

ROOT = Path(__file__).resolve().parents[1]
COLORS = {"white": "#eee9e0", "black": "#202027", "red": "#bc3546",
          "yellow": "#f2d551", "lime": "#91c750", "light_blue": "#67bce4"}


def main():
    level = amulet.load_level(str(ROOT / "build/math_maze"))
    cell = 24
    image = Image.new("RGB", (840, 850), "#faf8f1")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 19)
    draw.text((36, 18), "Question 1: wall display (block-grid schematic)", font=font, fill="#202027")
    for x in range(32):
        for y in range(65, 80):
            b = level.get_version_block(x, y, 31, "minecraft:overworld", ("bedrock", (1, 19, 50)))[0]
            color = COLORS.get(b.properties["color"].py_str, "#aaa59b") if "color" in b.properties else "#aaa59b"
            left, top = 36 + x * cell, 60 + (79 - y) * cell
            draw.rectangle((left, top, left + cell - 1, top + cell - 1), fill=color)
    draw.text((36, 440), "Floor: arrows lead to the three pressure plates", font=font, fill="#202027")
    small = 10
    for x in range(32):
        for z in range(32):
            b = level.get_version_block(x, 64, z, "minecraft:overworld", ("bedrock", (1, 19, 50)))[0]
            color = COLORS.get(b.properties["color"].py_str, "#aaa59b") if "color" in b.properties else "#dccda9"
            left, top = 260 + x * small, 490 + (31 - z) * small
            draw.rectangle((left, top, left + small - 1, top + small - 1), fill=color)
            above = level.get_version_block(x, 65, z, "minecraft:overworld", ("bedrock", (1, 19, 50)))[0]
            if above.base_name == "stone_pressure_plate":
                draw.rectangle((left + 1, top + 1, left + 8, top + 8), fill="#6b6b72", outline="#ffffff", width=1)
            elif above.base_name != "air":
                draw.rectangle((left, top, left + 9, top + 9), fill="#aaa59b")
    draw.text((307, 820), "Start here, facing forward", font=font, fill="#202027")
    level.close()
    image.save(ROOT / "dist/room1_wall_preview.png")


if __name__ == "__main__":
    main()
