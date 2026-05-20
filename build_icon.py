"""Generate a forex candlestick chart icon for the app."""
from PIL import Image, ImageDraw

BG      = (26, 26, 46)       # #1a1a2e
GREEN   = (0, 184, 148)      # #00b894
RED     = (225, 112, 85)     # #e17055
AMBER   = (232, 168, 56)     # #e8a838
GRID    = (15, 52, 96, 80)   # #0f3460 semi-transparent


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), BG)
    d = ImageDraw.Draw(img)

    s = size
    pad = max(2, s // 10)

    # Draw subtle grid lines
    for frac in (0.33, 0.66):
        y = int(s * frac)
        d.line([(pad, y), (s - pad, y)], fill=(15, 52, 96, 100), width=max(1, s // 64))

    # Candlestick layout: 4 candles evenly spaced
    # columns at roughly 20%, 38%, 58%, 78% of width
    candle_w = max(3, s // 9)
    half_w = candle_w // 2
    wick_w = max(1, s // 28)

    candles = [
        # (x_center_frac, body_top_frac, body_bot_frac, wick_top_frac, wick_bot_frac, color)
        (0.20, 0.62, 0.80, 0.55, 0.87, RED),    # bearish
        (0.38, 0.28, 0.55, 0.18, 0.62, GREEN),  # bullish tall
        (0.58, 0.42, 0.62, 0.35, 0.70, RED),    # small bearish
        (0.78, 0.18, 0.42, 0.12, 0.50, GREEN),  # bullish — highest
    ]

    for xf, bt, bb, wt, wb, color in candles:
        xc = int(s * xf)
        body_top = int(s * bt)
        body_bot = int(s * bb)
        wick_top = int(s * wt)
        wick_bot = int(s * wb)

        # Wick
        d.rectangle(
            [xc - wick_w, wick_top, xc + wick_w, wick_bot],
            fill=color,
        )
        # Body
        d.rectangle(
            [xc - half_w, body_top, xc + half_w, body_bot],
            fill=color,
        )

    # Thin trend line connecting candle highs (amber)
    points = [(int(s * xf), int(s * wt)) for xf, bt, bb, wt, wb, _ in candles]
    if len(points) >= 2:
        d.line(points, fill=AMBER, width=max(1, s // 32))

    return img


def main():
    sizes = [256, 128, 64, 48, 32, 16]   # largest first required by some ICO writers
    frames = [draw_icon(sz).convert("RGBA") for sz in sizes]

    # Save each size as individual PNG then build ICO — most compatible approach
    frames[0].save(
        "app_icon.ico",
        format="ICO",
        sizes=[(sz, sz) for sz in sizes],
        append_images=frames[1:],
    )
    frames[0].save("app_icon_preview.png")
    print(f"Icon saved: app_icon.ico  ({len(sizes)} sizes: {sizes})")


if __name__ == "__main__":
    main()
