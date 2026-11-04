#!/usr/bin/env python3
"""Butterfly-effect timeline for the 32-tile run (tile i nudged at tic 200*i).

Columns per row: nudge_tic world_split_tic player_split_tic  (from gaps2.txt).
Writes butterfly32.png. Usage: python3 plot_butterfly32.py [gaps2.txt]
"""
import sys

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

TIC = 35.0
SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
WORLD, PLAYER = "#2a78d6", "#eb6834"      # categorical slots 1 and 2 (validated)

EMBEDDED = """\
200 201 207
400 400 470
600 600 841
800 800 843
1000 1001 1084
1200 1200 1446
1400 1401 1857
1600 1606 1771
1800 1800 1832
2000 2002 2283
2200 2202 2620
2400 2400 2715
2600 2601 2715
2800 2802 2861
3000 3006 3838
3200 3200 3838
3400 3400 3698
3600 3600 3838
3800 3802 3838
4000 4000 4079
4200 4200 4224
4400 4401 4469
4600 4600 4762
4800 4800 5284
5000 5004 5288
5200 5200 5286
5400 5400 5470
5600 5600 5613
5800 5804 5929
6000 6000 6109
6200 6201 6425
"""


def load(path=None):
    text = open(path).read() if path else EMBEDDED
    rows = []
    for line in text.splitlines():
        p = line.split()
        if len(p) == 3 and p[1] != "-1" and p[2] != "-1":
            n, w, pl = (int(x) for x in p)
            if n % 200 == 0 and n <= 6200:          # the 31 nudged tiles of the 32 grid
                rows.append((n // 200, n, w, pl))
    return rows


def mmss(sec):
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


def main():
    rows = load(sys.argv[1] if len(sys.argv) > 1 else None)

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, ax = plt.subplots(figsize=(11, 8.6), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    for tile, n, w, pl in rows:
        y = tile
        # hidden chaos: world already different, player can't tell yet
        ax.plot([w / TIC, pl / TIC], [y, y], color=MUTED, lw=2, solid_capstyle="round", zorder=1)
        ax.scatter([w / TIC], [y], s=46, color=WORLD, edgecolor=SURFACE, linewidth=2, zorder=3)
        ax.scatter([pl / TIC], [y], s=46, color=PLAYER, edgecolor=SURFACE, linewidth=2, zorder=3)

    # the moments where several tiles' players get hit at once
    clusters = {}
    for _, _, _, pl in rows:
        clusters.setdefault(pl // 10, []).append(pl)
    for group in clusters.values():
        if len(group) >= 2:
            t = sum(group) / len(group) / TIC
            ax.axvline(t, color=GRID, lw=1, zorder=0)
            ax.text(t, 0.15, f"{len(group)} tiles at {mmss(t)}", ha="center", va="bottom",
                    fontsize=8.5, color=INK2)

    # longest hidden-chaos stretch
    tile, n, w, pl = max(rows, key=lambda r: r[3] - r[2])
    ax.annotate(f"world split at {mmss(w / TIC)},\nplayer found out {(pl - w) / TIC:.0f} s later",
                xy=((w + pl) / 2 / TIC, tile), xytext=((w + pl) / 2 / TIC - 6, tile + 2.6),
                fontsize=8.5, color=INK2, ha="right",
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=1))

    ax.set_ylim(len(rows) + 0.8, -0.6)
    ax.set_yticks([r[0] for r in rows])
    ax.set_yticklabels([f"tile {r[0]}" for r in rows], fontsize=7.5, color=INK2)
    xmax = max(r[3] for r in rows) / TIC + 5
    ax.set_xlim(0, xmax)
    ticks = list(range(0, int(xmax) + 1, 30))
    ax.set_xticks(ticks)
    ax.set_xticklabels([mmss(t) for t in ticks], color=INK2)
    ax.set_xlabel("time into the demo (min:sec)", color=INK2)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0)

    fig.text(0.06, 0.965, "One extra dice roll splits the world instantly. The player finds out later.",
             fontsize=14, weight="bold", color=INK, ha="left")
    fig.text(0.06, 0.937,
             "32 copies of Freedoom demo1, tile 0 untouched, tile i given one extra random roll at tic 200·i. "
             "Grey line = hidden chaos.",
             fontsize=9.5, color=INK2, ha="left")

    handles = [
        Line2D([], [], marker="o", ls="", ms=7, color=WORLD, label="world diverges (any monster, door or item differs)"),
        Line2D([], [], marker="o", ls="", ms=7, color=PLAYER, label="player diverges (position, angle or health)"),
        Line2D([], [], color=MUTED, lw=2, label="hidden chaos: world different, player unaware"),
    ]
    ax.legend(handles=handles, loc="upper right", bbox_to_anchor=(1.0, 0.94),
              frameon=False, fontsize=8.5, labelcolor=INK2)

    fig.subplots_adjust(left=0.07, right=0.98, top=0.91, bottom=0.07)
    fig.savefig("butterfly32.png", facecolor=SURFACE)
    print("wrote butterfly32.png")


if __name__ == "__main__":
    main()
