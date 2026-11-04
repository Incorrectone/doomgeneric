// compositor.c - lockstep mosaic compositor for headless doomgeneric instances.
//
// Same job as compositor.py, without Python's per-tile overhead:
//   * reads one tile per game tic from each FIFO (FRAMES=fifoN, TILE_W x TILE_H)
//   * places the tiles in a grid centred on the output canvas
//   * outlines a tile once its picture differs from tile 0 for CONFIRM frames
//   * writes raw BGR0 canvas frames to stdout (pipe it into ffmpeg)
//   * at the end writes "tile first_visibly_different_tic" to the divergence log
//   * splits the tiles across -j threads: each thread reads, compares and copies its
//     own tiles, so the pipe reads (one per tile per frame) run in parallel
//
// Video frame k shows game tic k+1 (the engine's first drawn tic is 1).
//
// Build:  gcc -O2 -pthread -o compositor compositor.c
// Usage:  ./compositor -l "COLS ROWS TW TH OW OH" [-b] [-j THREADS] [-m MAXFRAMES] [-d LOG] fifo0 fifo1 ...
//          then pipe into: ffmpeg -f rawvideo -pix_fmt bgr0 -s OWxOH -r 35 -i - ... out.mp4

#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define CONFIRM 5                      // frames a difference must last to count
static const uint8_t OUTLINE[4] = { 0x34, 0x68, 0xeb, 0x00 };   // #eb6834 as B,G,R,X

// Read exactly n bytes. Returns 1 on success, 0 at end of stream.
static int read_exact(int fd, uint8_t *buf, size_t n)
{
    size_t got = 0;
    while (got < n)
    {
        ssize_t k = read(fd, buf + got, n - got);
        if (k > 0)
            got += (size_t) k;
        else if (k == 0)
            return 0;
        else if (errno != EINTR)
            return 0;
    }
    return 1;
}

static void write_all(int fd, const uint8_t *buf, size_t n)
{
    while (n > 0)
    {
        ssize_t k = write(fd, buf, n);
        if (k > 0)
        {
            buf += k;
            n -= (size_t) k;
        }
        else if (k < 0 && errno != EINTR)
        {
            perror("compositor: write to stdout (is ffmpeg still running?)");
            exit(1);
        }
    }
}

static void fill(uint8_t *px, int count)
{
    int i;
    for (i = 0; i < count; i++)
        memcpy(px + 4 * i, OUTLINE, 4);
}

// ---- shared state (each tile's entries are touched only by the thread that owns it)
static int n, cols, tw, th, ow, x_off, y_off, border, borders;
static size_t tile_bytes, row_bytes;
static int *fds, *alive, *split_at, *run_len, *cand;
static uint8_t *last, *canvas;
static int frame, stop, any_flag;
static pthread_barrier_t frame_start, reads_done, frame_done;

typedef struct { int lo, hi; } span_t;

static void place_tile(int i)
{
    const uint8_t *tile = last + (size_t) i * tile_bytes;
    int r = i / cols, c = i % cols;
    uint8_t *dst = canvas + (((size_t) (y_off + r * th)) * ow + x_off + c * tw) * 4;

    if (i && split_at[i] < 0)
    {
        if (memcmp(tile, last, tile_bytes) == 0)          // tile 0 is the baseline
            run_len[i] = 0;
        else
        {
            if (run_len[i] == 0)
                cand[i] = frame;
            if (++run_len[i] >= CONFIRM)
                split_at[i] = cand[i];
        }
    }

    for (int y = 0; y < th; y++)
        memcpy(dst + (size_t) y * ow * 4, tile + (size_t) y * row_bytes, row_bytes);

    if (borders && split_at[i] >= 0)
    {
        for (int y = 0; y < th; y++)
        {
            uint8_t *line = dst + (size_t) y * ow * 4;
            if (y < border || y >= th - border)
                fill(line, tw);
            else
            {
                fill(line, border);
                fill(line + (size_t) (tw - border) * 4, border);
            }
        }
    }
}

static void *worker(void *arg)
{
    span_t *sp = arg;
    for (;;)
    {
        pthread_barrier_wait(&frame_start);
        if (stop)
            return NULL;

        int any = 0;
        for (int i = sp->lo; i < sp->hi; i++)
        {
            if (!alive[i])
                continue;
            if (read_exact(fds[i], last + (size_t) i * tile_bytes, tile_bytes))
                any = 1;
            else
                alive[i] = 0;          // instance finished: keep its last picture
        }
        if (any)
            __atomic_store_n(&any_flag, 1, __ATOMIC_RELAXED);

        pthread_barrier_wait(&reads_done);      // tile 0 (the baseline) is now read
        if (__atomic_load_n(&any_flag, __ATOMIC_RELAXED))
            for (int i = sp->lo; i < sp->hi; i++)
                place_tile(i);
        pthread_barrier_wait(&frame_done);
    }
}

int main(int argc, char **argv)
{
    int rows = 0, th_ = 0, oh = 0, threads = 8, max_frames = 0, opt;
    const char *log_path = "visible_split.txt";

    while ((opt = getopt(argc, argv, "l:bj:m:d:")) != -1)
    {
        switch (opt)
        {
        case 'l':
            if (sscanf(optarg, "%d %d %d %d %d %d", &cols, &rows, &tw, &th_, &ow, &oh) != 6)
            {
                fprintf(stderr, "-l needs \"COLS ROWS TW TH OW OH\"\n");
                return 2;
            }
            break;
        case 'b': borders = 1; break;
        case 'j': threads = atoi(optarg); break;
        case 'm': max_frames = atoi(optarg); break;
        case 'd': log_path = optarg; break;
        default:
            fprintf(stderr, "usage: %s -l \"COLS ROWS TW TH OW OH\" [-b] [-j N] [-m N] [-d LOG] fifo...\n",
                    argv[0]);
            return 2;
        }
    }
    th = th_;
    n = argc - optind;
    if (n < 1 || cols < 1 || n > cols * rows || cols * tw > ow || rows * th > oh)
    {
        fprintf(stderr, "compositor: bad layout or no FIFOs (%d tiles, %dx%d grid)\n", n, cols, rows);
        return 2;
    }
    if (threads < 1)
        threads = 1;
    if (threads > n)
        threads = n;

    tile_bytes = (size_t) tw * th * 4;
    row_bytes = (size_t) tw * 4;
    size_t canvas_bytes = (size_t) ow * oh * 4;
    x_off = (ow - cols * tw) / 2;
    y_off = (oh - rows * th) / 2;
    border = (tw + 50) / 100;
    if (border < 1)
        border = 1;

    fds = malloc(sizeof(int) * n);
    alive = malloc(sizeof(int) * n);
    split_at = malloc(sizeof(int) * n);
    run_len = calloc(n, sizeof(int));
    cand = calloc(n, sizeof(int));
    last = calloc((size_t) n, tile_bytes);
    canvas = calloc(1, canvas_bytes);
    if (!fds || !alive || !split_at || !run_len || !cand || !last || !canvas)
    {
        fprintf(stderr, "compositor: out of memory\n");
        return 1;
    }

    // open in order; each Doom instance is already blocked opening its FIFO for writing
    for (int i = 0; i < n; i++)
    {
        fds[i] = open(argv[optind + i], O_RDONLY);
        if (fds[i] < 0)
        {
            perror(argv[optind + i]);
            return 1;
        }
        fcntl(fds[i], F_SETPIPE_SZ, 1 << 20);   // let instances run a few frames ahead
        alive[i] = 1;
        split_at[i] = -1;
    }
    fprintf(stderr, "compositor: %d tiles, %dx%d grid of %dx%d on %dx%d, %d threads\n",
            n, cols, rows, tw, th, ow, oh, threads);

    pthread_barrier_init(&frame_start, NULL, threads + 1);
    pthread_barrier_init(&reads_done, NULL, threads + 1);
    pthread_barrier_init(&frame_done, NULL, threads + 1);
    pthread_t *tid = malloc(sizeof(pthread_t) * threads);
    span_t *spans = malloc(sizeof(span_t) * threads);
    for (int t = 0; t < threads; t++)
    {
        spans[t].lo = (int) ((long) n * t / threads);
        spans[t].hi = (int) ((long) n * (t + 1) / threads);
        pthread_create(&tid[t], NULL, worker, &spans[t]);
    }

    frame = 0;
    for (;;)
    {
        stop = max_frames && frame >= max_frames;
        any_flag = 0;
        pthread_barrier_wait(&frame_start);
        if (stop)
            break;
        pthread_barrier_wait(&reads_done);
        int any = __atomic_load_n(&any_flag, __ATOMIC_RELAXED);
        pthread_barrier_wait(&frame_done);
        if (!any)
        {
            stop = 1;                          // every instance has finished
            pthread_barrier_wait(&frame_start);
            break;
        }
        write_all(1, canvas, canvas_bytes);
        frame++;
        if (frame % 350 == 0)
            fprintf(stderr, "frame %d  (%d s of video)\n", frame, frame / 35);
    }
    for (int t = 0; t < threads; t++)
        pthread_join(tid[t], NULL);

    for (int i = 0; i < n; i++)
        close(fds[i]);

    FILE *f = fopen(log_path, "w");
    if (f)
    {
        fprintf(f, "# tile first_visibly_different_tic (-1 = never)\n");
        for (int i = 1; i < n; i++)
            fprintf(f, "%d %d\n", i, split_at[i] >= 0 ? split_at[i] + 1 : -1);
        fclose(f);
    }
    fprintf(stderr, "compositor: done, %d frames; visible splits in %s\n", frame, log_path);
    return 0;
}
