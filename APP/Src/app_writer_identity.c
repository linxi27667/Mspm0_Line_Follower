/**
 * @file app_writer_identity.c
 * @brief Derive an eight-hex-digit boot token without Flash writes.
 */
#include "app_writer_identity.h"

#include <stdint.h>

#include "bsp_common.h"
#include "bsp_writer_protocol.h"

extern volatile uint32_t s_sys_tick;

static bool App_WriterIdentity_Read_Trng(uint32_t *value)
{
    uint32_t timeout;

    if (value == NULL) {
        return false;
    }
    DL_TRNG_reset(TRNG);
    DL_TRNG_enablePower(TRNG);
    delay_cycles(60u);
    DL_TRNG_setClockDivider(TRNG, DL_TRNG_CLOCK_DIVIDE_2);
    DL_TRNG_sendCommand(TRNG, DL_TRNG_CMD_NORM_FUNC);

    timeout = 100000u;
    while (!DL_TRNG_isCommandDone(TRNG) && (timeout > 0u)) {
        timeout--;
    }
    if ((timeout == 0u) || DL_TRNG_isCommandFail(TRNG) ||
        DL_TRNG_isHealthTestFail(TRNG)) {
        DL_TRNG_disablePower(TRNG);
        return false;
    }
    DL_TRNG_clearInterruptStatus(
        TRNG, DL_TRNG_INTERRUPT_CMD_DONE_EVENT);
    DL_TRNG_setDecimationRate(TRNG, DL_TRNG_DECIMATION_RATE_4);

    timeout = 100000u;
    while (!DL_TRNG_isCaptureReady(TRNG) && (timeout > 0u)) {
        timeout--;
    }
    if ((timeout == 0u) || DL_TRNG_isHealthTestFail(TRNG)) {
        DL_TRNG_disablePower(TRNG);
        return false;
    }
    *value = DL_TRNG_getCapture(TRNG);
    DL_TRNG_disablePower(TRNG);
    return true;
}

void App_WriterIdentity_Create_Boot_Id(char boot_id[9])
{
    uint32_t entropy;
    uint32_t random_word;

    if (boot_id == NULL) {
        return;
    }

    /*
     * TRACEID distinguishes MCUs. SysTick phase and elapsed homing time add
     * power-cycle variation without persisting old jobs in Flash.
     */
    entropy = s_sys_tick ^ SysTick->VAL;
    if (App_WriterIdentity_Read_Trng(&random_word)) {
        entropy ^= random_word;
    }
    Bsp_Writer_Make_Boot_Id(
        DL_FactoryRegion_getTraceID(), entropy, boot_id);
}
