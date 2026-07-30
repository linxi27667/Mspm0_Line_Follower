/**
 * @file    bsp_quadrature_encoder.c
 * @brief   Portable 4x software quadrature encoder counter.
 */
#include "bsp_quadrature_encoder.h"

#include <stddef.h>

static bool Bsp_QuadratureEncoder_HasReadCallback(
    const bsp_quadrature_encoder_t *encoder)
{
    return (encoder != NULL) && (encoder->read_state != NULL);
}

static uint8_t Bsp_QuadratureEncoder_ReadState(
    const bsp_quadrature_encoder_t *encoder)
{
    return encoder->read_state(encoder->input_handle) & 0x03U;
}

bool Bsp_QuadratureEncoder_Init(bsp_quadrature_encoder_t *encoder)
{
    if (!Bsp_QuadratureEncoder_HasReadCallback(encoder)) {
        return false;
    }

    encoder->count = 0;
    encoder->previous_state = Bsp_QuadratureEncoder_ReadState(encoder);
    return true;
}

void Bsp_QuadratureEncoder_OnEdge(bsp_quadrature_encoder_t *encoder)
{
    static const int8_t transition_delta[16] = {
         0,  1, -1,  0,
        -1,  0,  0,  1,
         1,  0,  0, -1,
         0, -1,  1,  0
    };
    uint8_t current_state;
    int8_t delta;

    if (!Bsp_QuadratureEncoder_HasReadCallback(encoder)) {
        return;
    }

    current_state = Bsp_QuadratureEncoder_ReadState(encoder);
    delta = transition_delta[(encoder->previous_state << 2U) |
                             current_state];
    encoder->previous_state = current_state;

    if (encoder->reverse_direction) {
        delta = -delta;
    }

    encoder->count += delta;
}

void Bsp_QuadratureEncoder_Reset(bsp_quadrature_encoder_t *encoder)
{
    if (encoder != NULL) {
        encoder->count = 0;
    }
}
