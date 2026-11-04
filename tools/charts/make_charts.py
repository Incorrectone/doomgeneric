#!/usr/bin/env python3
"""Charts for the Doom mosaic sweep (c7a.32xlarge, 128 vCPUs).

Reads from DATA (the downloaded S3 'runs' folder):
  scaling_c7a48.csv, sysmon.csv, bigN/visible_split.txt
and the Chocolate Doom nudge sweep gaps2.txt (one level up).
Writes scaling.png, machine.png, butterfly8192.png.
"""
import csv
import os
import sys
from collections import OrderedDict

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

DATA = sys.argv[1] if len(sys.argv) > 1 else "runs"
OUT = sys.argv[2] if len(sys.argv) > 2 else "."
TIC = 35.0
DEMO_TICS = 7116
DEMO_SECONDS = 7117 / TIC                     # ~203 s of gameplay per instance

SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
BLUE, ORANGE = "#2a78d6", "#eb6834"           # categorical slots 1 and 2 (validated)

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})


def style(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(length=0, colors=INK2)


def titles(fig, title, subtitle):
    fig.text(0.06, 0.955, title, fontsize=14, weight="bold", color=INK, ha="left")
    fig.text(0.06, 0.935, subtitle, fontsize=9.5, color=INK2, ha="left", va="top")


def mmss(sec):
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


# ---------------------------------------------------------------- scaling
def scaling():
    rows = list(csv.DictReader(open(os.path.join(DATA, "scaling_c7a48.csv"))))
    tiles = [int(r["tiles"]) for r in rows]
    secs = [int(r["seconds"]) for r in rows]
    # gameplay simulated per wall-clock second = how many "real-time Dooms" it sustained
    speed = [n * DEMO_SECONDS / s for n, s in zip(tiles, secs)]

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 5.2), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    for ax in (a1, a2):
        style(ax)
        ax.set_xscale("log", base=2)
        ax.set_xticks(tiles)
        ax.set_xticklabels([f"{n:,}" for n in tiles])
        ax.set_xlabel("Doom instances in the mosaic", color=INK2)

    a1.plot(tiles, [s / 60 for s in secs], color=BLUE, lw=2, marker="o", ms=7,
            markeredgecolor=SURFACE, markeredgewidth=2, zorder=3)
    a1.set_ylim(0, max(secs) / 60 * 1.18)
    a1.set_ylabel("wall-clock time for the whole demo (minutes)", color=INK2)
    a1.set_title("Run time grows far slower than the work", loc="left", fontsize=10.5,
                 color=INK, pad=10)
    for n, s in zip(tiles, secs):
        if n in (128, 1024, 8192):
            a1.annotate(f"{mmss(s)}", (n, s / 60), textcoords="offset points",
                        xytext=(0, 10), ha="center", fontsize=8.5, color=INK2)
    a1.annotate("64x the Dooms,\n3.3x the time", xy=(8192, secs[-1] / 60),
                xytext=(1400, secs[-1] / 60 * 1.02), fontsize=8.5, color=INK2, ha="center",
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=1))

    a2.plot(tiles, speed, color=ORANGE, lw=2, marker="o", ms=7,
            markeredgecolor=SURFACE, markeredgewidth=2, zorder=3)
    a2.set_yscale("log", base=2)
    yt = [2 ** k for k in range(6, 12)]
    a2.set_yticks(yt)
    a2.set_yticklabels([f"{v:,}" for v in yt])
    a2.set_ylabel("Doom-seconds simulated per real second", color=INK2)
    a2.set_title("Throughput keeps climbing", loc="left", fontsize=10.5, color=INK, pad=10)
    a2.annotate(f"{speed[-1]:,.0f}x real time", (tiles[-1], speed[-1]), textcoords="offset points",
                xytext=(-8, 8), ha="right", fontsize=8.5, color=INK2)

    titles(fig, "8,192 copies of Doom in 13 minutes on one machine",
           "Whole 203 s demo per instance, composited into one 4K video. c7a.32xlarge spot, 128 vCPUs.")
    fig.subplots_adjust(left=0.07, right=0.98, top=0.80, bottom=0.12, wspace=0.28)
    fig.savefig(os.path.join(OUT, "scaling.png"), facecolor=SURFACE)


# ---------------------------------------------------------------- machine
def machine():
    rows = list(csv.DictReader(open(os.path.join(DATA, "sysmon.csv"))))
    t0 = int(rows[0]["unix_time"])
    t = [(int(r["unix_time"]) - t0) / 60 for r in rows]
    mem = [int(r["mem_used_MB"]) / 1024 for r in rows]
    cpu = [float(r["cpu_busy_pct"]) for r in rows]
    runs = OrderedDict()
    for x, r in zip(t, rows):
        runs.setdefault(r["run"], [x, x])[1] = x

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 6.8), dpi=200, sharex=True)
    fig.patch.set_facecolor(SURFACE)
    for ax in (a1, a2):
        style(ax)
        for k, (lo, hi) in runs.items():
            ax.axvline(lo, color=GRID, lw=1, zorder=0)
    for k, (lo, hi) in runs.items():
        top = max(m for x, m in zip(t, mem) if lo <= x <= hi)
        mid = [x for x, m in zip(t, mem) if lo <= x <= hi and m > 0.8 * top]
        label = f"{int(k.replace('big', '')):,} Dooms"
        if top == max(mem):
            label += f", peak {top:.0f} GB"
        a1.text(sum(mid) / len(mid), top + 8, label, ha="center", fontsize=8.5, color=INK2)

    a1.fill_between(t, mem, color=BLUE, alpha=0.18, lw=0)
    a1.plot(t, mem, color=BLUE, lw=2)
    a1.axhline(246, color=MUTED, lw=1, ls=(0, (4, 3)))
    a1.text(t[-1], 236, "246 GB installed", fontsize=8.5, color=INK2, va="top", ha="right")
    a1.set_ylim(0, 260)
    a1.set_ylabel("memory used (GB)", color=INK2)

    a2.plot(t, cpu, color=ORANGE, lw=1.4)
    a2.set_ylim(0, 105)
    a2.set_ylabel("CPU busy, all 128 vCPUs (%)", color=INK2)
    a2.set_xlabel("minutes since monitoring started", color=INK2)
    # average only while a run is rendering (memory near its plateau), not during the
    # audio-mix / upload gap that follows it
    avgs = []
    for k, (lo, hi) in runs.items():
        seg = [(m, c) for x, m, c in zip(t, mem, cpu) if lo <= x <= hi]
        top = max(m for m, _ in seg)
        busy = [c for m, c in seg if m > 0.8 * top]
        avg = sum(busy) / len(busy)
        avgs.append(avg)
        mid = sum(x for x, m in zip(t, mem) if lo <= x <= hi and m > 0.8 * top) / len(busy)
        a2.text(mid, 88, f"avg {avg:.0f}%", ha="center", fontsize=8.5, color=INK2)

    titles(fig, "The machine was never the bottleneck",
           "Even 8,192 Dooms used under a third of the memory and about half the CPU (averages cover "
           "rendering only;\nspikes are thousands of processes launching). Monitoring started "
           "partway through the 1,024 run.")
    fig.subplots_adjust(left=0.08, right=0.98, top=0.84, bottom=0.08, hspace=0.12)
    fig.savefig(os.path.join(OUT, "machine.png"), facecolor=SURFACE)


# ---------------------------------------------------------------- butterfly at 8192
def butterfly8192():
    nudge, delay = [], []
    never = 0
    for line in open(os.path.join(DATA, "big8192", "visible_split.txt")):
        if line.startswith("#"):
            continue
        tile, split = (int(x) for x in line.split())
        if tile > DEMO_TICS:
            continue                      # nudge would come after the demo ends
        if split < 0:
            never += 1
            continue
        nudge.append(tile / TIC)          # 8192 run: tile i nudged at tic i
        delay.append(max(split - tile, 0) / TIC)
    late = 8191 - DEMO_TICS

    gaps = os.path.join(os.path.dirname(DATA.rstrip("/")), "gaps2.txt")
    pn, pd = [], []
    if os.path.exists(gaps):
        for line in open(gaps):
            n, w, p = (int(x) for x in line.split())
            if p >= 0:
                pn.append(n / TIC)
                pd.append((p - n) / TIC)

    srt = sorted(delay)
    med = srt[len(srt) // 2]
    within1 = sum(d <= 1 for d in delay) / len(delay)

    fig, ax = plt.subplots(figsize=(11, 6.6), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    style(ax)
    ax.scatter(nudge, delay, s=4, color=BLUE, alpha=0.55, lw=0, zorder=2)
    if pn:
        ax.scatter(pn, pd, s=46, color=ORANGE, edgecolor=SURFACE, linewidth=1.5, zorder=3)

    ticks = list(range(0, int(DEMO_SECONDS) + 1, 30))
    ax.set_xticks(ticks)
    ax.set_xticklabels([mmss(x) for x in ticks])
    ax.set_xlim(0, DEMO_SECONDS + 3)
    ax.set_ylim(-0.5, max(max(delay), max(pd) if pd else 0) * 1.08)
    ax.set_xlabel("when the extra dice roll happened (demo time)", color=INK2)
    ax.set_ylabel("seconds until it showed", color=INK2)

    handles = [
        Line2D([], [], marker="o", ls="", ms=5, color=BLUE,
               label=f"picture first looks different ({len(delay):,} tiles of the 8,192 run)"),
        Line2D([], [], marker="o", ls="", ms=7, color=ORANGE,
               label="player's position or health first differs (state-log sweep)"),
    ]
    ax.legend(handles=handles, loc="upper left", frameon=False, fontsize=8.5, labelcolor=INK2)
    ax.text(0.99, 0.97,
            f"median {med:.1f} s; {within1:.0%} visible within 1 s\n"
            f"{never} never looked different before the end;\n"
            f"{late:,} nudges fell after the demo ended",
            transform=ax.transAxes, ha="right", va="top", fontsize=8.5, color=INK2)

    titles(fig, "Chaos arrives in waves",
           "One extra random roll per Doom. Each sloping run of dots ends at a single moment that "
           "reveals many different nudges at once.")
    fig.subplots_adjust(left=0.07, right=0.98, top=0.86, bottom=0.09)
    fig.savefig(os.path.join(OUT, "butterfly8192.png"), facecolor=SURFACE)


if __name__ == "__main__":
    scaling()
    machine()
    butterfly8192()
    print("wrote scaling.png, machine.png, butterfly8192.png")
