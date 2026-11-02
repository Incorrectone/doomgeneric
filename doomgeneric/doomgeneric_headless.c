// doomgeneric_headless.c - a doomgeneric "platform" with no window and no input.
//
// Runs as fast as the CPU allows (never sleeps), which is what -timedemo wants.
// Frames are keyed by gametic, not by call count: during screen wipes the engine
// draws several frames for the same tic, and how many depends on wall-clock time.
// Keying by tic keeps everything deterministic.
//
// Environment variables (all optional):
//   FRAMES=path    append one raw frame per tic (RESX*RESY*4 bytes, XRGB8888)
//   DUMP_TIC=N     also write the frame of tic N as frameN.ppm (quick visual check)

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "doomgeneric.h"
#include "doomkeys.h"

extern int gametic;

static FILE *frames_out = NULL;
static int dump_tic = -1;
static int last_tic = -1;

static void write_ppm(int tic)
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
        uint32_t px = DG_ScreenBuffer[i];
        unsigned char rgb[3] = { (px >> 16) & 0xff, (px >> 8) & 0xff, px & 0xff };
        fwrite(rgb, 1, 3, p);
    }
    fclose(p);
}

void DG_Init()
{
    const char *f = getenv("FRAMES");
    const char *d = getenv("DUMP_TIC");

    if (f)
        frames_out = fopen(f, "wb");
    dump_tic = d ? atoi(d) : -1;
}

void DG_DrawFrame()
{
    if (gametic == last_tic)
        return;                         // extra wipe frame for the same tic: skip
    last_tic = gametic;

    if (frames_out)
        fwrite(DG_ScreenBuffer, sizeof(uint32_t),
               DOOMGENERIC_RESX * DOOMGENERIC_RESY, frames_out);
    if (gametic == dump_tic)
        write_ppm(gametic);
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
