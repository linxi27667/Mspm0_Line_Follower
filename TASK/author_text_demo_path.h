/**
 * @file    author_text_demo_path.h
 * @brief   Generated V44 one-file A4 3x3 local calibration path.
 */
#ifndef AUTHOR_TEXT_DEMO_PATH_H
#define AUTHOR_TEXT_DEMO_PATH_H

#include <stdint.h>

typedef struct {
    int16_t x_x10;
    int16_t y_x10;
    uint8_t draw;
} author_text_demo_path_point_t;

#define AUTHOR_TEXT_DEMO_PATH_POINT_COUNT       (88u)
#define AUTHOR_TEXT_DEMO_PATH_MOVE_COUNT        (34u)
#define AUTHOR_TEXT_DEMO_PATH_DRAW_COUNT        (54u)
#define AUTHOR_TEXT_DEMO_PATH_CRC32             (0x058FBC5Cu)
#define AUTHOR_TEXT_DEMO_PATH_X_MIN_X10         (1500)
#define AUTHOR_TEXT_DEMO_PATH_X_MAX_X10         (4160)
#define AUTHOR_TEXT_DEMO_PATH_Y_MIN_X10         (-80)
#define AUTHOR_TEXT_DEMO_PATH_Y_MAX_X10         (1420)
#define AUTHOR_TEXT_DEMO_PATH_MAX_SPAN_X10      (1403)
#define AUTHOR_TEXT_DEMO_STAGE_COUNT            (1u)
#define AUTHOR_TEXT_DEMO_ZONE_COUNT             (9u)
#define AUTHOR_TEXT_DEMO_STROKE_COUNT           (27u)
#define AUTHOR_TEXT_DEMO_MARKER_SIZE_X10        (200)
#define AUTHOR_TEXT_DEMO_PAPER_SHIFT_X_X10      (1360)
#define AUTHOR_TEXT_DEMO_PAPER_SHIFT_Y_X10      (-380)
#define AUTHOR_TEXT_DEMO_ALIGN_PAPER_X_X10      (140)
#define AUTHOR_TEXT_DEMO_ALIGN_PAPER_Y_X10      (580)
#define AUTHOR_TEXT_DEMO_DRAW_PAPER_X_MIN_X10   (300)
#define AUTHOR_TEXT_DEMO_DRAW_PAPER_X_MAX_X10   (2800)
#define AUTHOR_TEXT_DEMO_DRAW_PAPER_Y_MIN_X10   (300)
#define AUTHOR_TEXT_DEMO_DRAW_PAPER_Y_MAX_X10   (1800)
#define AUTHOR_TEXT_DEMO_RIGHT_BOTTOM_INSET_X10 (300)
#define AUTHOR_TEXT_DEMO_AUX_TOGGLE_MIN_X_X10   (1500)
#define AUTHOR_TEXT_DEMO_CONTOUR_MARGIN_MDEG    (15000)

/*
 * One automatic stage:
 *   ALIGN -> known-safe ingress -> nine 20x20 mm squares with center crosses
 *   -> paper center -> verified center -> ALIGN.
 *
 * Each zone contains three strokes: one closed square, one horizontal line,
 * and one vertical line. The first point of every stroke is pen-up.
 */
static const author_text_demo_path_point_t
    s_author_text_demo_path[AUTHOR_TEXT_DEMO_PATH_POINT_COUNT] = {
    /* ALIGN and V40/V41/V43 verified ingress. */
    {1500, 200, 0u},
    {1510, 200, 0u},
    {2050, 650, 0u},
    {2845, 670, 0u},

    /* Zone 1: photo bottom-right, paper center (40,40), 30 mm inset. */
    {1660, -80, 0u},
    {1860, -80, 1u},
    {1860, 120, 1u},
    {1660, 120, 1u},
    {1660, -80, 1u},
    {1660, 20, 0u},
    {1860, 20, 1u},
    {1760, -80, 0u},
    {1760, 120, 1u},

    /* Zone 2: photo bottom-center, paper center (40,105). */
    {1660, 570, 0u},
    {1860, 570, 1u},
    {1860, 770, 1u},
    {1660, 770, 1u},
    {1660, 570, 1u},
    {1660, 670, 0u},
    {1860, 670, 1u},
    {1760, 570, 0u},
    {1760, 770, 1u},

    /* Zone 3: photo bottom-left, shifted inward for the clipped corner. */
    {2060, 1220, 0u},
    {2260, 1220, 1u},
    {2260, 1420, 1u},
    {2060, 1420, 1u},
    {2060, 1220, 1u},
    {2060, 1320, 0u},
    {2260, 1320, 1u},
    {2160, 1220, 0u},
    {2160, 1420, 1u},

    /* Zone 4: photo middle-left, paper center (148.5,170). */
    {2745, 1220, 0u},
    {2945, 1220, 1u},
    {2945, 1420, 1u},
    {2745, 1420, 1u},
    {2745, 1220, 1u},
    {2745, 1320, 0u},
    {2945, 1320, 1u},
    {2845, 1220, 0u},
    {2845, 1420, 1u},

    /* Zone 5: paper center, paper center (148.5,105). */
    {2745, 570, 0u},
    {2945, 570, 1u},
    {2945, 770, 1u},
    {2745, 770, 1u},
    {2745, 570, 1u},
    {2745, 670, 0u},
    {2945, 670, 1u},
    {2845, 570, 0u},
    {2845, 770, 1u},

    /* Zone 6: photo middle-right, paper center (148.5,40). */
    {2745, -80, 0u},
    {2945, -80, 1u},
    {2945, 120, 1u},
    {2745, 120, 1u},
    {2745, -80, 1u},
    {2745, 20, 0u},
    {2945, 20, 1u},
    {2845, -80, 0u},
    {2845, 120, 1u},

    /* Zone 7: photo top-right, paper center (270,40). */
    {3960, -80, 0u},
    {4160, -80, 1u},
    {4160, 120, 1u},
    {3960, 120, 1u},
    {3960, -80, 1u},
    {3960, 20, 0u},
    {4160, 20, 1u},
    {4060, -80, 0u},
    {4060, 120, 1u},

    /* Zone 8: photo top-center, paper center (270,105). */
    {3960, 570, 0u},
    {4160, 570, 1u},
    {4160, 770, 1u},
    {3960, 770, 1u},
    {3960, 570, 1u},
    {3960, 670, 0u},
    {4160, 670, 1u},
    {4060, 570, 0u},
    {4060, 770, 1u},

    /* Zone 9: photo top-left, shifted inward for the clipped corner. */
    {3860, 1170, 0u},
    {4060, 1170, 1u},
    {4060, 1370, 1u},
    {3860, 1370, 1u},
    {3860, 1170, 1u},
    {3860, 1270, 0u},
    {4060, 1270, 1u},
    {3960, 1170, 0u},
    {3960, 1370, 1u},

    /* Safe automatic return. */
    {2845, 670, 0u},
    {2050, 650, 0u},
    {1500, 200, 0u},
};

static const uint8_t
    s_author_text_demo_stage_offset[AUTHOR_TEXT_DEMO_STAGE_COUNT] = {
    0u,
};

static const uint8_t
    s_author_text_demo_stage_count[AUTHOR_TEXT_DEMO_STAGE_COUNT] = {
    88u,
};

#endif /* AUTHOR_TEXT_DEMO_PATH_H */
