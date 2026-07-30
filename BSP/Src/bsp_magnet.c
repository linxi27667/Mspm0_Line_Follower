/**
 * @file    bsp_magnet.c
 * @brief   Portable on/off driver for a MOS-controlled electromagnet.
 */
#include "bsp_magnet.h"

#include <stddef.h>

bool Bsp_Magnet_Init(bsp_magnet_t *magnet)
{
    if ((magnet == NULL) || (magnet->trigger_write == NULL)) {
        return false;
    }

    return Bsp_Magnet_Set(magnet, false);
}

bool Bsp_Magnet_Set(bsp_magnet_t *magnet, bool on)
{
    bool output_level;

    if ((magnet == NULL) || (magnet->trigger_write == NULL)) {
        return false;
    }

    output_level = on;
    if (magnet->polarity == BSP_MAGNET_ACTIVE_LOW) {
        output_level = !output_level;
    }

    magnet->trigger_write(magnet->trigger_handle, output_level);
    magnet->is_on = on;
    return true;
}

bool Bsp_Magnet_IsOn(const bsp_magnet_t *magnet)
{
    return (magnet != NULL) && magnet->is_on;
}
