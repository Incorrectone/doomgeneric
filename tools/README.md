# Butterfly-effect tools

Scripts used to run thousands of headless Doom instances at once, nudge each one
by a single extra random number, and turn the result into one mosaic video with
sound. The engine side (the `NUDGE_TIC`, `STATELOG` and `SNDLOG` patches and the
headless platform) lives in this branch under `doomgeneric/`.

| File | What it does |
|---|---|
| `run_mosaic.sh` | Launches N Doom instances (tile *i* nudged at tic *i* × STEP), feeds them to the compositor, encodes the video and mixes the audio. |
| `layout.py` | Picks the grid (columns, rows, tile size) that best fills a 16:9 frame for N tiles. |
| `compositor.c` | Reads one frame per tile from N pipes in lockstep, assembles the mosaic, writes raw frames to ffmpeg, and records when each tile first looks different from tile 0 (`visible_split.txt`). |
| `mix_events.py` | Turns the per-tile sound logs into one stereo WAV, panned by tile position. |
| `align_audio.py` | Finds the offset between a live recording and the event mix (used for the early real-time grids). |
| `charts/make_charts.py` | Scaling, machine-usage and "chaos arrives in waves" charts from a run folder. |
| `charts/plot_butterfly32.py` | World vs player split timeline for the 32-tile run, from `gaps2.txt`. |

## Quick start (Ubuntu)

```bash
sudo apt install -y build-essential ffmpeg python3-numpy python3-matplotlib freedoom
git clone -b butterfly https://github.com/Incorrectone/doomgeneric ~/doomgeneric
cd ~/doomgeneric/doomgeneric && make -f Makefile.headless

cd ~/doomgeneric/tools
./run_mosaic.sh 32 200 mosaic32          # 32 tiles, tile i nudged at tic 200*i
MAXF=700 ./run_mosaic.sh 256 3 test      # quick test: stop after 700 frames
```

`run_mosaic.sh` builds `compositor` on first use. Environment overrides:
`IWAD`, `DG` (doomgeneric source dir), `MAXF`, `PRESET`, `CRF`, `THREADS`.

For thousands of instances, raise the limits first:

```bash
ulimit -n 65536
sudo sysctl -w fs.pipe-user-pages-soft=0
```

## Butterfly sweep (Chocolate Doom or doomgeneric)

```bash
STATELOG=a.txt ./doomgeneric -iwad $IWAD -timedemo demo1 -nosound      # baseline
export IWAD
seq 200 200 7000 | xargs -P8 -I{} sh -c \
  'STATELOG=n{}.txt NUDGE_TIC={} ./doomgeneric -iwad $IWAD -timedemo demo1 -nosound >/dev/null 2>&1 || true'

for t in $(seq 200 200 7000); do
  paste -d' ' a.txt n$t.txt | awk -v t=$t '
    BEGIN { w=-1; p=-1 }
    { if (w<0 && $6!=$12) w=$1
      if (p<0 && ($2!=$8 || $3!=$9 || $4!=$10 || $5!=$11)) p=$1 }
    END { print t, w, p }'
done | tee gaps2.txt

python3 charts/plot_butterfly32.py gaps2.txt
```

State-log line: `tic x y angle health worldhash` (x, y in 16.16 fixed point;
angle as a 32-bit binary angle). `gaps2.txt` line: `nudge_tic world_split_tic player_split_tic`.
