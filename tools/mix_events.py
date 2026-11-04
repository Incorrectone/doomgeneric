#!/usr/bin/env python3
"""Mix Doom sound-event logs (from the SNDLOG patch) into one stereo WAV.

Each log line: tic sfx_id volume sep pitch
  tic    - game tic (35 per second)
  sfx_id - index into S_sfx[] in src/doom/sounds.c
  volume - 0..127
  sep    - stereo separation, 0 (left) .. 254 (right), 128 = centre
  pitch  - 128 = normal (ignored unless --pitch)

Simplifications vs the real engine (fine for a first comparison):
  * no 8-channel limit and no "same source cuts its old sound"
  * linear resampling from the WAD's 11025 Hz samples

Optional 6th column: wall-clock time (seconds since epoch) when the sound was
requested. With --t0 <recording start>, events are placed by wall time instead
of tic/35, which keeps real-time recordings in sync even if instances started
at different moments.

Usage:
  python3 mix_events.py --wad freedoom1.wad --sounds-c src/doom/sounds.c \
      --out mix.wav ev*.txt
  python3 mix_events.py ... --t0 $(cat t0.txt) ev*.txt   # wall-clock mode
"""
import argparse
import re
import struct
import wave

import numpy as np

TICRATE = 35


def read_wad(path):
    data = open(path, "rb").read()
    ident, numlumps, dirofs = struct.unpack_from("<4sii", data, 0)
    if ident not in (b"IWAD", b"PWAD"):
        raise SystemExit(f"{path}: not a WAD file")
    lumps = {}
    for i in range(numlumps):
        pos, size, name = struct.unpack_from("<ii8s", data, dirofs + 16 * i)
        name = name.split(b"\0")[0].decode("ascii", "replace").upper()
        lumps[name] = data[pos:pos + size]  # later lumps win, like the engine
    return lumps


def sfx_table(sounds_c):
    """List of (name, link_name_or_None); list index == sfx_id."""
    src = open(sounds_c).read()
    pat = re.compile(r'SOUND(?:_LINK)?\(\s*"(\w+)"\s*,\s*\d+\s*(?:,\s*sfx_(\w+))?')
    return [(m.group(1), m.group(2)) for m in pat.finditer(src)]


def load_dmx(raw):
    """Doom DMX sound lump -> (float32 samples in -1..1, sample_rate)."""
    if raw is None or len(raw) < 8:
        return None, None
    fmt, rate, n = struct.unpack_from("<HHI", raw, 0)
    if fmt != 3:
        return None, None
    body = raw[8:8 + n]
    if len(body) > 32:  # 16 padding bytes at each end
        body = body[16:-16]
    pcm = (np.frombuffer(body, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    return pcm, rate


def resample(pcm, src_rate, dst_rate, speed=1.0):
    step = (src_rate / dst_rate) * speed
    idx = np.arange(0.0, len(pcm) - 1, step)
    return np.interp(idx, np.arange(len(pcm)), pcm).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--wad", required=True)
    ap.add_argument("--sounds-c", required=True)
    ap.add_argument("--out", default="mix.wav")
    ap.add_argument("--rate", type=int, default=48000)
    ap.add_argument("--skip", type=float, default=0.0,
                    help="seconds to drop from the start (to line up with a video)")
    ap.add_argument("--pitch", action="store_true", help="apply logged pitch")
    ap.add_argument("--t0", type=float, default=None,
                    help="wall-clock start of the recording (seconds since epoch); "
                         "uses the 6th log column (wall time) instead of tic/35")
    args = ap.parse_args()

    lumps = read_wad(args.wad)
    table = sfx_table(args.sounds_c)
    if not table or table[0][0] != "none":
        raise SystemExit("could not parse S_sfx[] from sounds.c")

    def sample_for(sid):
        if sid <= 0 or sid >= len(table):
            return None, None
        name, link = table[sid]
        pcm, rate = load_dmx(lumps.get("DS" + name.upper()))
        if pcm is None and link:
            pcm, rate = load_dmx(lumps.get("DS" + link.upper()))
        return pcm, rate

    events = []
    for path in args.logs:
        with open(path) as f:
            for line in f:
                p = line.split()
                if len(p) < 4:
                    continue
                tic, sid, vol, sep = (int(x) for x in p[:4])
                pitch = int(p[4]) if len(p) > 4 else 128
                if args.t0 is not None:
                    if len(p) < 6:
                        raise SystemExit(f"{path}: --t0 needs a 6th (wall time) column")
                    when = float(p[5]) - args.t0
                else:
                    when = tic / TICRATE
                events.append((when, sid, vol, sep, pitch))
    if not events:
        raise SystemExit("no events found")

    cache = {}
    missing = set()
    last = max(e[0] for e in events)
    total = int((last - args.skip + 3.0) * args.rate)
    left = np.zeros(max(total, 1), dtype=np.float32)
    right = np.zeros_like(left)

    for when, sid, vol, sep, pitch in events:
        t = when - args.skip
        if t < 0:
            continue
        speed = pitch / 128.0 if args.pitch else 1.0
        key = (sid, round(speed, 3))
        if key not in cache:
            pcm, rate = sample_for(sid)
            cache[key] = None if pcm is None else resample(pcm, rate, args.rate, speed)
        s = cache[key]
        if s is None:
            missing.add(sid)
            continue
        start = int(t * args.rate)
        end = min(start + len(s), len(left))
        if end <= start:
            continue
        # same panning law as Chocolate Doom's SDL backend
        gl = max(0, min(255, (254 - sep) * vol // 127)) / 255.0
        gr = max(0, min(255, sep * vol // 127)) / 255.0
        left[start:end] += s[:end - start] * gl
        right[start:end] += s[:end - start] * gr

    peak = float(max(np.abs(left).max(), np.abs(right).max()))
    if peak > 0:
        scale = 0.89 / peak  # normalise to about -1 dBFS
        left *= scale
        right *= scale
    stereo = np.stack([left, right], axis=1)
    pcm16 = (np.clip(stereo, -1, 1) * 32767).astype("<i2")

    with wave.open(args.out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(args.rate)
        w.writeframes(pcm16.tobytes())

    print(f"{len(events)} events from {len(args.logs)} logs -> {args.out} "
          f"({len(left) / args.rate:.1f} s, peak before normalising {peak:.2f})")
    if missing:
        print("no sample found for sfx ids:", sorted(missing))


if __name__ == "__main__":
    main()
