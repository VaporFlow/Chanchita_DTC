"""Generate modern icon from C-130J image with gradient background."""
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import math

def rounded_mask(size, radius):
    """Create a rounded rectangle mask."""
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size[0]-1, size[1]-1], radius=radius, fill=255)
    return mask

def gradient_bg(size, radius):
    """Create gradient background (dark blue-purple to teal)."""
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for y in range(h):
        t = y / h
        # Top: dark navy/purple  ->  Bottom: dark teal
        r = int(20 + t * 15)
        g = int(30 + t * 50)
        b = int(70 + t * 30)
        for x in range(w):
            # Add subtle radial light from upper-right
            dx = (x / w) - 0.7
            dy = (y / h) - 0.3
            dist = math.sqrt(dx*dx + dy*dy)
            glow = max(0, 1.0 - dist * 1.5) * 35
            pr = min(255, int(r + glow * 0.5))
            pg = min(255, int(g + glow * 0.8))
            pb = min(255, int(b + glow))
            img.putpixel((x, y), (pr, pg, pb, 255))
    # Apply rounded corners
    mask = rounded_mask((w, h), radius)
    img.putalpha(mask)
    return img

def create_icon():
    src = Image.open("G:\\Chanchita_DTC\\C130.png").convert("RGBA")

    # Remove white/light background
    data = src.getdata()
    new_data = []
    for r, g, b, a in data:
        # If pixel is very light (near white), make transparent
        if r > 220 and g > 220 and b > 220:
            new_data.append((r, g, b, 0))
        # Fade light greys at edges
        elif r > 200 and g > 200 and b > 200:
            fade = max(0, min(255, (255 - max(r, g, b)) * 8))
            new_data.append((r, g, b, fade))
        else:
            new_data.append((r, g, b, a))
    src.putdata(new_data)

    sizes = [256, 128, 64, 48, 32, 16]
    images = []

    for sz in sizes:
        radius = max(4, sz // 8)

        # Create gradient background
        bg = gradient_bg((sz, sz), radius)

        # Resize aircraft to fit with padding
        padding = int(sz * 0.08)
        avail = sz - padding * 2
        # Scale preserving aspect ratio, fill the square nicely
        src_w, src_h = src.size
        scale = max(avail / src_w, avail / src_h) * 1.15
        new_w = int(src_w * scale)
        new_h = int(src_h * scale)
        aircraft = src.resize((new_w, new_h), Image.LANCZOS)

        # Center the aircraft, shift slightly down-left for composition
        ox = (sz - new_w) // 2 - int(sz * 0.02)
        oy = (sz - new_h) // 2 + int(sz * 0.04)

        # Add subtle drop shadow
        shadow = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
        shadow_offset = max(1, sz // 64)
        shadow.paste((0, 0, 0, 60), (ox + shadow_offset, oy + shadow_offset, ox + new_w + shadow_offset, oy + new_h + shadow_offset))
        if sz >= 48:
            shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(1, sz // 40)))

        # Composite: bg + shadow + aircraft
        bg = Image.alpha_composite(bg, shadow)
        bg.paste(aircraft, (ox, oy), aircraft)

        # Add "DTC" text in white, bold, over the aircraft
        txt_layer = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
        txt_draw = ImageDraw.Draw(txt_layer)
        font_size = max(8, int(sz * 0.28))
        try:
            font = ImageFont.truetype("arialbd.ttf", font_size)
        except (OSError, IOError):
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except (OSError, IOError):
                font = ImageFont.load_default()
        text = "DTC"
        bbox = txt_draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (sz - tw) // 2
        ty = (sz - th) // 2
        # Dark shadow behind text for readability
        if sz >= 32:
            shadow_txt = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
            shadow_draw = ImageDraw.Draw(shadow_txt)
            so = max(1, sz // 80)
            shadow_draw.text((tx + so, ty + so), text, font=font, fill=(0, 0, 0, 140))
            if sz >= 64:
                shadow_txt = shadow_txt.filter(ImageFilter.GaussianBlur(radius=max(1, sz // 80)))
            bg = Image.alpha_composite(bg, shadow_txt)
        txt_draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 230))
        bg = Image.alpha_composite(bg, txt_layer)

        # Re-apply rounded mask to clip everything
        mask = rounded_mask((sz, sz), radius)
        bg.putalpha(ImageDraw.Draw(Image.new("L", (sz, sz), 0))
                     .rounded_rectangle([0, 0, sz-1, sz-1], radius=radius, fill=255)
                     or mask)
        # Simpler approach: just apply mask
        final = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
        final.paste(bg, (0, 0))
        final.putalpha(mask)

        images.append(final)

    images[0].save(
        "G:\\Chanchita_DTC\\chanchita.ico",
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:]
    )
    images[0].save("G:\\Chanchita_DTC\\chanchita_preview.png")
    print("Icon saved")

create_icon()
