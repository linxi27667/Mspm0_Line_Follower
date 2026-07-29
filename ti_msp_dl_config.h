/*
 * Copyright (c) 2023, Texas Instruments Incorporated - http://www.ti.com
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 *
 * *  Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 *
 * *  Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * *  Neither the name of Texas Instruments Incorporated nor the names of
 *    its contributors may be used to endorse or promote products derived
 *    from this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
 * THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 * PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR
 * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
 * EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
 * PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
 * OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
 * WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
 * OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
 * EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

/*
 *  ============ ti_msp_dl_config.h =============
 *  Configured MSPM0 DriverLib module declarations
 *
 *  DO NOT EDIT - This file is generated for the MSPM0G350X
 *  by the SysConfig tool.
 */
#ifndef ti_msp_dl_config_h
#define ti_msp_dl_config_h

#define CONFIG_MSPM0G350X

#if defined(__ti_version__) || defined(__TI_COMPILER_VERSION__)
#define SYSCONFIG_WEAK __attribute__((weak))
#elif defined(__IAR_SYSTEMS_ICC__)
#define SYSCONFIG_WEAK __weak
#elif defined(__GNUC__)
#define SYSCONFIG_WEAK __attribute__((weak))
#endif

#include <ti/devices/msp/msp.h>
#include <ti/driverlib/driverlib.h>
#include <ti/driverlib/m0p/dl_core.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 *  ======== SYSCFG_DL_init ========
 *  Perform all required MSP DL initialization
 *
 *  This function should be called once at a point before any use of
 *  MSP DL.
 */


/* clang-format off */

#define POWER_STARTUP_DELAY                                                (16)


#define CPUCLK_FREQ                                                     32000000



/* Defines for STEP */
#define STEP_INST                                                          TIMA1
#define STEP_INST_IRQHandler                                    TIMA1_IRQHandler
#define STEP_INST_INT_IRQN                                      (TIMA1_INT_IRQn)
#define STEP_INST_CLK_FREQ                                              32000000
/* GPIO defines for channel 0 */
#define GPIO_STEP_C0_PORT                                                  GPIOA
#define GPIO_STEP_C0_PIN                                          DL_GPIO_PIN_10
#define GPIO_STEP_C0_IOMUX                                       (IOMUX_PINCM21)
#define GPIO_STEP_C0_IOMUX_FUNC                      IOMUX_PINCM21_PF_TIMA1_CCP0
#define GPIO_STEP_C0_IDX                                     DL_TIMER_CC_0_INDEX

/* Defines for STEP2 */
#define STEP2_INST                                                         TIMA0
#define STEP2_INST_IRQHandler                                   TIMA0_IRQHandler
#define STEP2_INST_INT_IRQN                                     (TIMA0_INT_IRQn)
#define STEP2_INST_CLK_FREQ                                             32000000
/* GPIO defines for channel 0 */
#define GPIO_STEP2_C0_PORT                                                 GPIOA
#define GPIO_STEP2_C0_PIN                                          DL_GPIO_PIN_8
#define GPIO_STEP2_C0_IOMUX                                      (IOMUX_PINCM19)
#define GPIO_STEP2_C0_IOMUX_FUNC                     IOMUX_PINCM19_PF_TIMA0_CCP0
#define GPIO_STEP2_C0_IDX                                    DL_TIMER_CC_0_INDEX




/* Port definition for Pin Group GPIO_GRP_1 */
#define GPIO_GRP_1_PORT                                                  (GPIOA)

/* Defines for STAGE1_DIR_PIN: GPIOA.11 with pinCMx 22 on package pin 57 */
#define GPIO_GRP_1_STAGE1_DIR_PIN_PIN                           (DL_GPIO_PIN_11)
#define GPIO_GRP_1_STAGE1_DIR_PIN_IOMUX                          (IOMUX_PINCM22)
/* Port definition for Pin Group GPIO_GRP_2 */
#define GPIO_GRP_2_PORT                                                  (GPIOA)

/* Defines for STAGE2_DIR_PIN: GPIOA.9 with pinCMx 20 on package pin 55 */
#define GPIO_GRP_2_STAGE2_DIR_PIN_PIN                            (DL_GPIO_PIN_9)
#define GPIO_GRP_2_STAGE2_DIR_PIN_IOMUX                          (IOMUX_PINCM20)
/* Port definition for Pin Group GPIO_GRP_3 */
#define GPIO_GRP_3_PORT                                                  (GPIOA)

/* Defines for STAGE1_LIMIT_PIN: GPIOA.26 with pinCMx 59 on package pin 30 */
#define GPIO_GRP_3_STAGE1_LIMIT_PIN_PIN                         (DL_GPIO_PIN_26)
#define GPIO_GRP_3_STAGE1_LIMIT_PIN_IOMUX                        (IOMUX_PINCM59)
/* Port definition for Pin Group GPIO_GRP_4 */
#define GPIO_GRP_4_PORT                                                  (GPIOA)

/* Defines for STAGE2_LIMIT_PIN: GPIOA.27 with pinCMx 60 on package pin 31 */
#define GPIO_GRP_4_STAGE2_LIMIT_PIN_PIN                         (DL_GPIO_PIN_27)
#define GPIO_GRP_4_STAGE2_LIMIT_PIN_IOMUX                        (IOMUX_PINCM60)
/* Port definition for Pin Group KEY1_GPIO */
#define KEY1_GPIO_PORT                                                   (GPIOB)

/* Defines for KEY1_PIN: GPIOB.26 with pinCMx 57 on package pin 28 */
#define KEY1_GPIO_KEY1_PIN_PIN                                  (DL_GPIO_PIN_26)
#define KEY1_GPIO_KEY1_PIN_IOMUX                                 (IOMUX_PINCM57)
/* Port definition for Pin Group KEY2_GPIO */
#define KEY2_GPIO_PORT                                                   (GPIOA)

/* Defines for KEY2_PIN: GPIOA.29 with pinCMx 4 on package pin 36 */
#define KEY2_GPIO_KEY2_PIN_PIN                                  (DL_GPIO_PIN_29)
#define KEY2_GPIO_KEY2_PIN_IOMUX                                  (IOMUX_PINCM4)
/* Port definition for Pin Group KEY3_GPIO */
#define KEY3_GPIO_PORT                                                   (GPIOB)

/* Defines for KEY3_PIN: GPIOB.23 with pinCMx 51 on package pin 22 */
#define KEY3_GPIO_KEY3_PIN_PIN                                  (DL_GPIO_PIN_23)
#define KEY3_GPIO_KEY3_PIN_IOMUX                                 (IOMUX_PINCM51)
/* Port definition for Pin Group KEY4_GPIO */
#define KEY4_GPIO_PORT                                                   (GPIOB)

/* Defines for KEY4_PIN: GPIOB.27 with pinCMx 58 on package pin 29 */
#define KEY4_GPIO_KEY4_PIN_PIN                                  (DL_GPIO_PIN_27)
#define KEY4_GPIO_KEY4_PIN_IOMUX                                 (IOMUX_PINCM58)

/* clang-format on */

void SYSCFG_DL_init(void);
void SYSCFG_DL_initPower(void);
void SYSCFG_DL_GPIO_init(void);
void SYSCFG_DL_SYSCTL_init(void);
void SYSCFG_DL_STEP_init(void);
void SYSCFG_DL_STEP2_init(void);


bool SYSCFG_DL_saveConfiguration(void);
bool SYSCFG_DL_restoreConfiguration(void);

#ifdef __cplusplus
}
#endif

#endif /* ti_msp_dl_config_h */
