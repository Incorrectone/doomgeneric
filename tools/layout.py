"""Pick the grid that fills a 16:9 frame best for N Doom tiles (Doom's 320x200 = 1.6:1).

plan(n, max_w, max_h) -> (cols, rows, tile_w, tile_h, out_w, out_h)
  * the grid is chosen so the tiles cover as much of a 16:9 frame as possible
  * tiles are never enlarged past 320x200; when they are shrunk, the output is
    exactly max_w x max_h; when they are full size, the frame shrinks to the
    smallest 16:9 size around the grid
  * out_w and out_h are even (needed for yuv420p video)
"""
import math

SRC_W, SRC_H = 320, 200


def even(x):
    return int(math.ceil(x / 2.0) * 2)


def plan(n, max_w=3840, max_h=2160):
    best = None
    for cols in range(1, n + 1):
        rows = math.ceil(n / cols)
        if cols * rows - n >= cols:                 # a whole empty row: skip
            continue
        scale = min(max_w / (cols * SRC_W), max_h / (rows * SRC_H))
        fill = n * (SRC_W * scale) * (SRC_H * scale) / (max_w * max_h)
        if best is None or fill > best[0]:
            best = (fill, cols, rows, scale)
    _, cols, rows, scale = best
    scale = min(scale, 1.0)
    tw, th = int(SRC_W * scale), int(SRC_H * scale)
    if tw < 8 or th < 5:
        raise SystemExit(f"{n} tiles don't fit in {max_w}x{max_h}")
    gw, gh = cols * tw, rows * th
    if scale < 1.0:                                 # tiles shrunk: use the full frame
        return cols, rows, tw, th, max_w, max_h
    # tiles at full size: smallest 16:9 frame (at most max_w x max_h) around the grid
    out_w = max(gw, gh * 16 / 9)
    out_h = out_w * 9 / 16
    out_w, out_h = min(even(out_w), max_w), min(even(out_h), max_h)
    return cols, rows, tw, th, out_w, out_h


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1])
    w, h = (int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "3840x2160").split("x"))
    print(*plan(n, w, h))
