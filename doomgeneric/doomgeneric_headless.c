// doomgeneric_headless.c - a doomgeneric "platform" with no window and no input.
//
// Runs as fast as the CPU allows (never sleeps), which is what -timedemo wants.
// Frames are keyed by gametic, not by call count: during screen wipes the engine
// draws several frames for the same tic, and how far the wipe has got in each one
// depends on wall-clock time. So we keep only the LAST picture drawn for each tic
// (the finished one) and write it when the next tic starts. That keeps every
// written frame deterministic.
//
// Environment variables (all optional):
//   FRAMES=path        append one frame per tic (XRGB8888, little-endian)
//   TILE_W, TILE_H     shrink each frame to this size before writing (box filter);
//                      default is the full RESX x RESY picture
//   DUMP_TIC=N         also write the full-size frame of tic N as frameN.ppm

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "doomgeneric.h"
#include "doomkeys.h"

extern int gametic;

static FILE *frames_out = NULL;
static int dump_tic = -1;
static int tile_w = DOOMGENERIC_RESX, tile_h = DOOMGENERIC_RESY;
static uint32_t *tile = NULL;
static uint32_t *pending = NULL;        // last picture drawn for pending_tic
static int pending_tic = -1;
static void flush(void);
static int *x0s, *x1s, *y0s, *y1s;      // source span for each output column / row

static void write_ppm(int tic, const uint32_t *src)
{
    char name[64];
    FILE *p;
    int i;

    snprintf(name, sizeof name, "frame%d.ppm", tic);
    p = fopen(name, "wb");
    if (!p)
        return;
    fprintf(p, "P6\n%d %d\n255\n", DOOMGENERIC_RESX, DOOMGENERIC_RESY);
    for (i = 0; i < DOOMGENERIC_RESX * DOOMGENERIC_RESY; i++)
    {
        uint32_t px = src[i];
        unsigned char rgb[3] = { (px >> 16) & 0xff, (px >> 8) & 0xff, px & 0xff };
        fwrite(rgb, 1, 3, p);
    }
    fclose(p);
}

// Average every source pixel that falls inside each output pixel (box filter).
static void shrink(const uint32_t *src)
{
    int ox, oy, sx, sy;

    for (oy = 0; oy < tile_h; oy++)
    {
        for (ox = 0; ox < tile_w; ox++)
        {
            uint32_t r = 0, g = 0, b = 0, n = 0;
            for (sy = y0s[oy]; sy < y1s[oy]; sy++)
            {
                const uint32_t *row = src + sy * DOOMGENERIC_RESX;
                for (sx = x0s[ox]; sx < x1s[ox]; sx++)
                {
                    uint32_t px = row[sx];
                    r += (px >> 16) & 0xff;
                    g += (px >> 8) & 0xff;
                    b += px & 0xff;
                    n++;
                }
            }
            tile[oy * tile_w + ox] = ((r / n) << 16) | ((g / n) << 8) | (b / n);
        }
    }
}

static int *spans(int out, int in, int upper)
{
    int *v = malloc(sizeof(int) * out);
    int i;
    for (i = 0; i < out; i++)
    {
        int a = (int) ((long) i * in / out);
        int b = (int) ((long) (i + 1) * in / out);
        if (b <= a)
            b = a + 1;                  // never an empty span
        v[i] = upper ? b : a;
    }
    return v;
}

void DG_Init()
{
    const char *f = getenv("FRAMES");
    const char *d = getenv("DUMP_TIC");
    const char *tw = getenv("TILE_W");
    const char *th = getenv("TILE_H");

    if (f)
        frames_out = fopen(f, "wb");
    pending = malloc(sizeof(uint32_t) * DOOMGENERIC_RESX * DOOMGENERIC_RESY);
    atexit(flush);                      // write the final tic when the demo ends
    dump_tic = d ? atoi(d) : -1;

    if (tw && th && atoi(tw) > 0 && atoi(th) > 0
        && atoi(tw) <= DOOMGENERIC_RESX && atoi(th) <= DOOMGENERIC_RESY)
    {
        tile_w = atoi(tw);
        tile_h = atoi(th);
    }
    if (tile_w != DOOMGENERIC_RESX || tile_h != DOOMGENERIC_RESY)
    {
        tile = malloc(sizeof(uint32_t) * tile_w * tile_h);
        x0s = spans(tile_w, DOOMGENERIC_RESX, 0);
        x1s = spans(tile_w, DOOMGENERIC_RESX, 1);
        y0s = spans(tile_h, DOOMGENERIC_RESY, 0);
        y1s = spans(tile_h, DOOMGENERIC_RESY, 1);
    }
}

static void flush(void)
{
    if (pending_tic < 0)
        return;
    if (pending_tic == dump_tic)
        write_ppm(pending_tic, pending);
    if (frames_out)
    {
        if (tile)
        {
            shrink(pending);
            fwrite(tile, sizeof(uint32_t), tile_w * tile_h, frames_out);
        }
        else
        {
            fwrite(pending, sizeof(uint32_t), DOOMGENERIC_RESX * DOOMGENERIC_RESY, frames_out);
        }
        fflush(frames_out);
    }
    pending_tic = -1;
}

void DG_DrawFrame()
{
    if (gametic != pending_tic)
        flush();                        // previous tic is finished: write its last picture
    memcpy(pending, DG_ScreenBuffer, sizeof(uint32_t) * DOOMGENERIC_RESX * DOOMGENERIC_RESY);
    pending_tic = gametic;
}

void DG_SleepMs(uint32_t ms)
{
    (void) ms;                          // never sleep: run flat out
}

uint32_t DG_GetTicksMs()
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint32_t) (ts.tv_sec * 1000u + ts.tv_nsec / 1000000u);
}

int DG_GetKey(int *pressed, unsigned char *doomKey)
{
    (void) pressed;
    (void) doomKey;
    return 0;                           // no keyboard: demos only
}

void DG_SetWindowTitle(const char *title)
{
    (void) title;
}

int main(int argc, char **argv)
{
    doomgeneric_Create(argc, argv);
    for (;;)
        doomgeneric_Tick();
    return 0;
}
