/**
 * @file    bsp_quadrature_encoder.h
 * @brief   Portable 4x software quadrature encoder counter.
 */
#ifndef BSP_QUADRATURE_ENCODER_H
#define BSP_QUADRATURE_ENCODER_H

#include <stdbool.h>
#include <stdint.h>

typedef uint8_t (*bsp_quadrature_read_state_fn)(void *handle);

typedef struct {
    void *input_handle;
    bsp_quadrature_read_state_fn read_state;

    volatile int32_t count;
    uint8_t previous_state;
    bool reverse_direction;
} bsp_quadrature_encoder_t;

bool Bsp_QuadratureEncoder_Init(bsp_quadrature_encoder_t *encoder);
void Bsp_QuadratureEncoder_OnEdge(bsp_quadrature_encoder_t *encoder);
void Bsp_QuadratureEncoder_Reset(bsp_quadrature_encoder_t *encoder);

#endif /* BSP_QUADRATURE_ENCODER_H */
