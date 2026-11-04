#!/usr/bin/env bash
# run_mosaic.sh - N headless Doom instances -> one 16:9 mosaic video with event audio.
#
#   ./run_mosaic.sh N STEP NAME [MAXRES]
#     N       number of tiles (tile 0 = untouched baseline)
#     STEP    tile i is nudged at tic i*STEP (0 = no nudges)
#     NAME    output folder and file name
#     MAXRES  largest output frame, default 3840x2160
#
# Instances run with address randomisation off (setarch -R): a few renderer pixels
# read stray memory, and fixed addresses make those pixels identical run to run.
#
# Environment overrides: IWAD, DG (doomgeneric source dir), MAXF (stop after N frames),
#                        PRESET (x264 preset, default veryfast), CRF (default 20),
#                        THREADS (compositor threads, default nproc/4)
set -u
N=${1:-32}; STEP=${2:-200}; NAME=${3:-mosaic$N}; MAXRES=${4:-3840x2160}
IWAD=${IWAD:-/usr/share/games/doom/freedoom1.wad}
DG=${DG:-$HOME/doomgeneric/doomgeneric}
SCRIPTS=$(cd "$(dirname "$0")" && pwd)

# build the C compositor on first use (or after it changes)
if [ ! -x "$SCRIPTS/compositor" ] || [ "$SCRIPTS/compositor.c" -nt "$SCRIPTS/compositor" ]; then
  gcc -O2 -pthread -o "$SCRIPTS/compositor" "$SCRIPTS/compositor.c" || exit 1
fi

ulimit -n $(( N * 2 + 256 )) 2>/dev/null || { echo "raise the open-file limit (ulimit -n)"; exit 1; }

read COLS ROWS TW TH OW OH <<< "$(python3 "$SCRIPTS/layout.py" "$N" "$MAXRES")"
echo "layout: ${COLS}x${ROWS} grid, ${TW}x${TH} tiles, ${OW}x${OH} video"

mkdir -p "$NAME" && cd "$NAME"
rm -f fifo* ev*.txt doom*.log video.mp4 audio.wav

pids=""
for i in $(seq 0 $((N-1))); do
  mkfifo fifo$i
  if [ "$i" -eq 0 ] || [ "$STEP" -eq 0 ]; then NU=""; else NU="NUDGE_TIC=$((i*STEP))"; fi
  env $NU FRAMES=fifo$i TILE_W=$TW TILE_H=$TH SNDLOG=ev$i.txt setarch "$(uname -m)" -R "$DG/doomgeneric" \
      -iwad "$IWAD" -timedemo demo1 -nosound > doom$i.log 2>&1 &
  pids="$pids $!"
done

fifos=$(for i in $(seq 0 $((N-1))); do printf 'fifo%d ' "$i"; done)
"$SCRIPTS/compositor" -l "$COLS $ROWS $TW $TH $OW $OH" -b -j "${THREADS:-$(( $(nproc) / 4 > 1 ? $(nproc) / 4 : 1 ))}" ${MAXF:+-m $MAXF} \
    -d visible_split.txt $fifos \
  | ffmpeg -nostdin -loglevel error -y -f rawvideo -pix_fmt bgr0 -s "${OW}x${OH}" -r 35 -i - \
      -c:v libx264 -preset "${PRESET:-veryfast}" -crf "${CRF:-20}" -pix_fmt yuv420p video.mp4

kill $pids 2>/dev/null
wait 2>/dev/null
rm -f fifo*

python3 "$SCRIPTS/mix_events.py" --wad "$IWAD" --sounds-c "$DG/sounds.c" \
    --out audio.wav --skip 0.0286 ev*.txt    # video frame k = tic k+1
ffmpeg -nostdin -loglevel error -y -i video.mp4 -i audio.wav -map 0:v -map 1:a \
    -c:v copy -c:a aac -shortest "$NAME.mp4"
echo "wrote $PWD/$NAME.mp4"
