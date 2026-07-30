/**
 * @file    bsp_magnet.h
 * @brief   Portable on/off driver for a MOS-controlled electromagnet.
 */
#ifndef BSP_MAGNET_H
#define BSP_MAGNET_H

#include <stdbool.h>

typedef void (*bsp_magnet_gpio_write_fn)(void *handle, bool level);

typedef enum {
    BSP_MAGNET_ACTIVE_HIGH = 0,
    BSP_MAGNET_ACTIVE_LOW
} bsp_magnet_polarity_t;

typedef struct {
    void *trigger_handle;
    bsp_magnet_gpio_write_fn trigger_write;
    bsp_magnet_polarity_t polarity;
    bool is_on;
} bsp_magnet_t;

bool Bsp_Magnet_Init(bsp_magnet_t *magnet);
bool Bsp_Magnet_Set(bsp_magnet_t *magnet, bool on);
bool Bsp_Magnet_IsOn(const bsp_magnet_t *magnet);

#endif /* BSP_MAGNET_H */
