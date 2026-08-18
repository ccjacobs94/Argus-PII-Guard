from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

def generate_argus_icon():
    size = 1024
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = size // 2, size // 2

    # 1. Outer Shield / Rounded Crest background
    shield_pts = [
        (cx, 80),
        (size - 140, 180),
        (size - 140, 520),
        (cx, size - 80),
        (140, 520),
        (140, 180),
    ]
    # Draw soft glow behind shield
    glow_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_img)
    glow_draw.polygon(shield_pts, fill=(58, 186, 140, 70))
    glow_img = glow_img.filter(ImageFilter.GaussianBlur(30))
    img.paste(glow_img, (0, 0), glow_img)

    # Draw shield body
    draw.polygon(shield_pts, fill=(11, 25, 56, 230), outline=(58, 186, 140, 255), width=18)

    # 2. Concentric Circular Orbit Ring
    orbit_r = 340
    draw.ellipse(
        [cx - orbit_r, cy - orbit_r, cx + orbit_r, cy + orbit_r],
        outline=(126, 222, 12, 200),
        width=12
    )

    # 3. Tilted Elliptical Orbit Rings
    # Tilted Orbit 1 (Periwinkle)
    ellipse_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    el_draw = ImageDraw.Draw(ellipse_layer)
    el_draw.ellipse([cx - 320, cy - 160, cx + 320, cy + 160], outline=(120, 142, 224, 230), width=14)
    ellipse_layer = ellipse_layer.rotate(-28, center=(cx, cy), resample=Image.Resampling.BICUBIC)
    img.paste(ellipse_layer, (0, 0), ellipse_layer)

    # Tilted Orbit 2 (Teal)
    ellipse_layer2 = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    el_draw2 = ImageDraw.Draw(ellipse_layer2)
    el_draw2.ellipse([cx - 320, cy - 160, cx + 320, cy + 160], outline=(58, 186, 140, 230), width=14)
    ellipse_layer2 = ellipse_layer2.rotate(28, center=(cx, cy), resample=Image.Resampling.BICUBIC)
    img.paste(ellipse_layer2, (0, 0), ellipse_layer2)

    # 4. Planetary Nodes on orbits
    nodes = [
        (cx - 240, cy - 120, (126, 222, 12, 255), 24),
        (cx + 250, cy + 110, (56, 189, 248, 255), 22),
        (cx, cy - 340, (237, 190, 177, 255), 18),
    ]
    for nx, ny, color, r in nodes:
        node_glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        nd = ImageDraw.Draw(node_glow)
        nd.ellipse([nx - r*2, ny - r*2, nx + r*2, ny + r*2], fill=(color[0], color[1], color[2], 120))
        node_glow = node_glow.filter(ImageFilter.GaussianBlur(8))
        img.paste(node_glow, (0, 0), node_glow)
        draw.ellipse([nx - r, ny - r, nx + r, ny + r], fill=color)

    # 5. Center Eye Shape
    eye_w, eye_h = 240, 130
    eye_box = [cx - eye_w, cy - eye_h, cx + eye_w, cy + eye_h]
    draw.chord(eye_box, start=0, end=180, fill=(14, 27, 56, 255), outline=(58, 186, 140, 255), width=16)
    draw.chord(eye_box, start=180, end=360, fill=(14, 27, 56, 255), outline=(58, 186, 140, 255), width=16)

    # 6. Eye Iris & Glowing Pupil
    iris_r = 90
    draw.ellipse([cx - iris_r, cy - iris_r, cx + iris_r, cy + iris_r], fill=(11, 25, 56, 255), outline=(58, 186, 140, 255), width=10)

    # Glowing Pupil
    pupil_glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pg_draw = ImageDraw.Draw(pupil_glow)
    pupil_r = 50
    pg_draw.ellipse([cx - pupil_r*2, cy - pupil_r*2, cx + pupil_r*2, cy + pupil_r*2], fill=(56, 189, 248, 180))
    pupil_glow = pupil_glow.filter(ImageFilter.GaussianBlur(16))
    img.paste(pupil_glow, (0, 0), pupil_glow)

    draw.ellipse([cx - pupil_r, cy - pupil_r, cx + pupil_r, cy + pupil_r], fill=(56, 189, 248, 255))
    # Specular reflection dot
    draw.ellipse([cx - 22, cy - 22, cx - 6, cy - 6], fill=(255, 255, 255, 255))

    # Save PNG and multi-resolution Windows ICO
    assets_dir = Path(__file__).parent.parent / "frontend" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    png_path = assets_dir / "argus-icon.png"
    ico_path = assets_dir / "argus-icon.ico"

    img.save(str(png_path), format="PNG")
    
    icon_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    img.save(str(ico_path), format="ICO", sizes=icon_sizes)
    print(f"Generated {png_path} and {ico_path}")

if __name__ == "__main__":
    generate_argus_icon()
