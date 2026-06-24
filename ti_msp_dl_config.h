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



/* Defines for Monitor_Left_Timer */
#define Monitor_Left_Timer_INST                                            TIMG7
#define Monitor_Left_Timer_INST_IRQHandler                        TIMG7_IRQHandler
#define Monitor_Left_Timer_INST_INT_IRQN                        (TIMG7_INT_IRQn)
#define Monitor_Left_Timer_INST_CLK_FREQ                                 4000000
/* GPIO defines for channel 0 */
#define GPIO_Monitor_Left_Timer_C0_PORT                                    GPIOA
#define GPIO_Monitor_Left_Timer_C0_PIN                            DL_GPIO_PIN_17
#define GPIO_Monitor_Left_Timer_C0_IOMUX                         (IOMUX_PINCM39)
#define GPIO_Monitor_Left_Timer_C0_IOMUX_FUNC             IOMUX_PINCM39_PF_TIMG7_CCP0
#define GPIO_Monitor_Left_Timer_C0_IDX                       DL_TIMER_CC_0_INDEX

/* Defines for Right_Motor_Timer */
#define Right_Motor_Timer_INST                                             TIMG6
#define Right_Motor_Timer_INST_IRQHandler                        TIMG6_IRQHandler
#define Right_Motor_Timer_INST_INT_IRQN                         (TIMG6_INT_IRQn)
#define Right_Motor_Timer_INST_CLK_FREQ                                  4000000
/* GPIO defines for channel 0 */
#define GPIO_Right_Motor_Timer_C0_PORT                                     GPIOB
#define GPIO_Right_Motor_Timer_C0_PIN                             DL_GPIO_PIN_10
#define GPIO_Right_Motor_Timer_C0_IOMUX                          (IOMUX_PINCM27)
#define GPIO_Right_Motor_Timer_C0_IOMUX_FUNC             IOMUX_PINCM27_PF_TIMG6_CCP0
#define GPIO_Right_Motor_Timer_C0_IDX                        DL_TIMER_CC_0_INDEX




/* Defines for Encoder_Timer */
#define Encoder_Timer_INST                                                 TIMG8
#define Encoder_Timer_INST_IRQHandler                           TIMG8_IRQHandler
#define Encoder_Timer_INST_INT_IRQN                             (TIMG8_INT_IRQn)
/* Pin configuration defines for Encoder_Timer PHA Pin */
#define GPIO_Encoder_Timer_PHA_PORT                                        GPIOB
#define GPIO_Encoder_Timer_PHA_PIN                                DL_GPIO_PIN_21
#define GPIO_Encoder_Timer_PHA_IOMUX                             (IOMUX_PINCM49)
#define GPIO_Encoder_Timer_PHA_IOMUX_FUNC             IOMUX_PINCM49_PF_TIMG8_CCP0
/* Pin configuration defines for Encoder_Timer PHB Pin */
#define GPIO_Encoder_Timer_PHB_PORT                                        GPIOB
#define GPIO_Encoder_Timer_PHB_PIN                                DL_GPIO_PIN_22
#define GPIO_Encoder_Timer_PHB_IOMUX                             (IOMUX_PINCM50)
#define GPIO_Encoder_Timer_PHB_IOMUX_FUNC             IOMUX_PINCM50_PF_TIMG8_CCP1


/* Defines for UART_Debug */
#define UART_Debug_INST                                                    UART0
#define UART_Debug_INST_IRQHandler                              UART0_IRQHandler
#define UART_Debug_INST_INT_IRQN                                  UART0_INT_IRQn
#define GPIO_UART_Debug_RX_PORT                                            GPIOA
#define GPIO_UART_Debug_TX_PORT                                            GPIOA
#define GPIO_UART_Debug_RX_PIN                                     DL_GPIO_PIN_1
#define GPIO_UART_Debug_TX_PIN                                     DL_GPIO_PIN_0
#define GPIO_UART_Debug_IOMUX_RX                                  (IOMUX_PINCM2)
#define GPIO_UART_Debug_IOMUX_TX                                  (IOMUX_PINCM1)
#define GPIO_UART_Debug_IOMUX_RX_FUNC                   IOMUX_PINCM2_PF_UART0_RX
#define GPIO_UART_Debug_IOMUX_TX_FUNC                   IOMUX_PINCM1_PF_UART0_TX
#define UART_Debug_BAUD_RATE                                            (115200)
#define UART_Debug_IBRD_32_MHZ_115200_BAUD                                  (17)
#define UART_Debug_FBRD_32_MHZ_115200_BAUD                                  (23)





/* Defines for GRAYSCALE_ADC */
#define GRAYSCALE_ADC_INST                                                  ADC0
#define GRAYSCALE_ADC_INST_IRQHandler                            ADC0_IRQHandler
#define GRAYSCALE_ADC_INST_INT_IRQN                              (ADC0_INT_IRQn)
#define GRAYSCALE_ADC_ADCMEM_0                                DL_ADC12_MEM_IDX_0
#define GRAYSCALE_ADC_ADCMEM_0_REF               DL_ADC12_REFERENCE_VOLTAGE_VDDA
#define GRAYSCALE_ADC_ADCMEM_0_REF_VOLTAGE                                      -1 // VDDA cannot be determined
#define GPIO_GRAYSCALE_ADC_C0_PORT                                         GPIOA
#define GPIO_GRAYSCALE_ADC_C0_PIN                                 DL_GPIO_PIN_27



/* Defines for DMA_CH0 */
#define DMA_CH0_CHAN_ID                                                      (0)
#define UART_Debug_INST_DMA_TRIGGER_0                        (DMA_UART0_RX_TRIG)

/* Defines for DMA_CH1 */
#define DMA_CH1_CHAN_ID                                                      (1)
#define UART_Debug_INST_DMA_TRIGGER_1                        (DMA_UART0_TX_TRIG)



/* Port definition for Pin Group Board_Led */
#define Board_Led_PORT                                                   (GPIOB)

/* Defines for PIN_0: GPIOB.13 with pinCMx 30 on package pin 1 */
#define Board_Led_PIN_0_PIN                                     (DL_GPIO_PIN_13)
#define Board_Led_PIN_0_IOMUX                                    (IOMUX_PINCM30)
/* Port definition for Pin Group Monitor_Dir */
#define Monitor_Dir_PORT                                                 (GPIOA)

/* Defines for Monitor_AIN1: GPIOA.14 with pinCMx 36 on package pin 7 */
#define Monitor_Dir_Monitor_AIN1_PIN                            (DL_GPIO_PIN_14)
#define Monitor_Dir_Monitor_AIN1_IOMUX                           (IOMUX_PINCM36)
/* Defines for Monitor_AIN2: GPIOA.15 with pinCMx 37 on package pin 8 */
#define Monitor_Dir_Monitor_AIN2_PIN                            (DL_GPIO_PIN_15)
#define Monitor_Dir_Monitor_AIN2_IOMUX                           (IOMUX_PINCM37)
/* Port definition for Pin Group Right_Motor_Dir */
#define Right_Motor_Dir_PORT                                             (GPIOA)

/* Defines for AIN1: GPIOA.13 with pinCMx 35 on package pin 6 */
#define Right_Motor_Dir_AIN1_PIN                                (DL_GPIO_PIN_13)
#define Right_Motor_Dir_AIN1_IOMUX                               (IOMUX_PINCM35)
/* Defines for AIN2: GPIOA.18 with pinCMx 40 on package pin 11 */
#define Right_Motor_Dir_AIN2_PIN                                (DL_GPIO_PIN_18)
#define Right_Motor_Dir_AIN2_IOMUX                               (IOMUX_PINCM40)
/* Port definition for Pin Group Grayscale_ADDR_A */
#define Grayscale_ADDR_A_PORT                                            (GPIOA)

/* Defines for AD0: GPIOA.16 with pinCMx 38 on package pin 9 */
#define Grayscale_ADDR_A_AD0_PIN                                (DL_GPIO_PIN_16)
#define Grayscale_ADDR_A_AD0_IOMUX                               (IOMUX_PINCM38)
/* Defines for AD1: GPIOA.12 with pinCMx 34 on package pin 5 */
#define Grayscale_ADDR_A_AD1_PIN                                (DL_GPIO_PIN_12)
#define Grayscale_ADDR_A_AD1_IOMUX                               (IOMUX_PINCM34)
/* Port definition for Pin Group Grayscale_ADDR_B */
#define Grayscale_ADDR_B_PORT                                            (GPIOB)

/* Defines for AD2: GPIOB.3 with pinCMx 16 on package pin 51 */
#define Grayscale_ADDR_B_AD2_PIN                                 (DL_GPIO_PIN_3)
#define Grayscale_ADDR_B_AD2_IOMUX                               (IOMUX_PINCM16)

/* clang-format on */

void SYSCFG_DL_init(void);
void SYSCFG_DL_initPower(void);
void SYSCFG_DL_GPIO_init(void);
void SYSCFG_DL_SYSCTL_init(void);
void SYSCFG_DL_Monitor_Left_Timer_init(void);
void SYSCFG_DL_Right_Motor_Timer_init(void);
void SYSCFG_DL_Encoder_Timer_init(void);
void SYSCFG_DL_UART_Debug_init(void);
void SYSCFG_DL_GRAYSCALE_ADC_init(void);
void SYSCFG_DL_DMA_init(void);


bool SYSCFG_DL_saveConfiguration(void);
bool SYSCFG_DL_restoreConfiguration(void);

#ifdef __cplusplus
}
#endif

#endif /* ti_msp_dl_config_h */
