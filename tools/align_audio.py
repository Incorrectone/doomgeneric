#!/usr/bin/env python3
"""Find the time offset between a live recording and the event mix.

Both tracks contain the same game sounds, so their loudness envelopes line up.
Prints how many seconds to ADD to mix_events.py --skip.

Also measures the offset separately on the first and last part of the audio:
if those two numbers differ, the tracks drift (speed mismatch), not just offset.

Usage:
  ffmpeg -y -i grid16.mp4 -vn -ac 1 -ar 8000 live.wav
  python3 align_audio.py live.wav mix16.wav
"""
import sys
import wave

import numpy as np

ENV_RATE = 100  # envelope samples per second (10 ms resolution)


def load_mono(path):
    with wave.open(path, "rb") as w:
        n, ch, width, rate = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    if width != 2:
        raise SystemExit(f"{path}: expected 16-bit WAV")
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, rate


def envelope(x, rate):
    block = max(1, rate // ENV_RATE)
    n = len(x) // block
    env = np.abs(x[: n * block]).reshape(n, block).mean(axis=1)
    env = np.log1p(env)          # compress loud peaks so quiet sounds count too
    env -= env.mean()
    return env


def best_lag(live, mix, max_lag_s=15.0):
    """Lag k (in envelope samples) maximising sum live[t] * mix[t + k]."""
    n = len(live) + len(mix)
    size = 1 << (n - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(mix, size) * np.conj(np.fft.rfft(live, size)), size)
    max_lag = int(max_lag_s * ENV_RATE)
    lags = np.concatenate([np.arange(0, max_lag + 1), np.arange(-max_lag, 0)])
    vals = np.concatenate([corr[: max_lag + 1], corr[size - max_lag:]])
    i = int(np.argmax(vals))
    return lags[i], vals[i] / (np.linalg.norm(live) * np.linalg.norm(mix) + 1e-9)


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    live, lr = load_mono(sys.argv[1])
    mix, mr = load_mono(sys.argv[2])
    le, me = envelope(live, lr), envelope(mix, mr)

    lag, score = best_lag(le, me)
    print(f"whole track: mix is {lag / ENV_RATE:+.2f} s relative to live "
          f"(match score {score:.2f})")

    seg = min(len(le), len(me)) // 3
    if seg > 10 * ENV_RATE:
        lag1, _ = best_lag(le[:seg], me[:seg])
        lag2, _ = best_lag(le[-seg:], me[-seg:])
        print(f"first third: {lag1 / ENV_RATE:+.2f} s   last third: {lag2 / ENV_RATE:+.2f} s")
        if abs(lag1 - lag2) > 0.1 * ENV_RATE:
            print("-> the offset changes over time: the tracks DRIFT, not just offset")

    print(f"\nadd {lag / ENV_RATE:+.2f} to your --skip value and re-run mix_events.py")


if __name__ == "__main__":
    main()
