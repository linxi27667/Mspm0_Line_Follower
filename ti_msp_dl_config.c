/*
 * Copyright (c) 2023, Texas Instruments Incorporated
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
 *  ============ ti_msp_dl_config.c =============
 *  Configured MSPM0 DriverLib module definitions
 *
 *  DO NOT EDIT - This file is generated for the MSPM0G350X
 *  by the SysConfig tool.
 */

#include "ti_msp_dl_config.h"

DL_TimerA_backupConfig gSTEPBackup;
DL_TimerA_backupConfig gSTEP2Backup;
DL_TimerG_backupConfig gROTATE_MOTOR_PWMBackup;

/*
 *  ======== SYSCFG_DL_init ========
 *  Perform any initialization needed before using any board APIs
 */
SYSCONFIG_WEAK void SYSCFG_DL_init(void)
{
    SYSCFG_DL_initPower();
    SYSCFG_DL_GPIO_init();
    /* Module-Specific Initializations*/
    SYSCFG_DL_SYSCTL_init();
    SYSCFG_DL_STEP_init();
    SYSCFG_DL_STEP2_init();
    SYSCFG_DL_ROTATE_MOTOR_PWM_init();
    /* Ensure backup structures have no valid state */
	gSTEPBackup.backupRdy 	= false;
	gSTEP2Backup.backupRdy 	= false;
	gROTATE_MOTOR_PWMBackup.backupRdy 	= false;

}
/*
 * User should take care to save and restore register configuration in application.
 * See Retention Configuration section for more details.
 */
SYSCONFIG_WEAK bool SYSCFG_DL_saveConfiguration(void)
{
    bool retStatus = true;

	retStatus &= DL_TimerA_saveConfiguration(STEP_INST, &gSTEPBackup);
	retStatus &= DL_TimerA_saveConfiguration(STEP2_INST, &gSTEP2Backup);
	retStatus &= DL_TimerG_saveConfiguration(ROTATE_MOTOR_PWM_INST, &gROTATE_MOTOR_PWMBackup);

    return retStatus;
}


SYSCONFIG_WEAK bool SYSCFG_DL_restoreConfiguration(void)
{
    bool retStatus = true;

	retStatus &= DL_TimerA_restoreConfiguration(STEP_INST, &gSTEPBackup, false);
	retStatus &= DL_TimerA_restoreConfiguration(STEP2_INST, &gSTEP2Backup, false);
	retStatus &= DL_TimerG_restoreConfiguration(ROTATE_MOTOR_PWM_INST, &gROTATE_MOTOR_PWMBackup, false);

    return retStatus;
}

SYSCONFIG_WEAK void SYSCFG_DL_initPower(void)
{
    DL_GPIO_reset(GPIOA);
    DL_GPIO_reset(GPIOB);
    DL_TimerA_reset(STEP_INST);
    DL_TimerA_reset(STEP2_INST);
    DL_TimerG_reset(ROTATE_MOTOR_PWM_INST);

    DL_GPIO_enablePower(GPIOA);
    DL_GPIO_enablePower(GPIOB);
    DL_TimerA_enablePower(STEP_INST);
    DL_TimerA_enablePower(STEP2_INST);
    DL_TimerG_enablePower(ROTATE_MOTOR_PWM_INST);
    delay_cycles(POWER_STARTUP_DELAY);
}

SYSCONFIG_WEAK void SYSCFG_DL_GPIO_init(void)
{

    DL_GPIO_initPeripheralOutputFunction(GPIO_STEP_C0_IOMUX,GPIO_STEP_C0_IOMUX_FUNC);
    DL_GPIO_enableOutput(GPIO_STEP_C0_PORT, GPIO_STEP_C0_PIN);
    DL_GPIO_initPeripheralOutputFunction(GPIO_STEP2_C0_IOMUX,GPIO_STEP2_C0_IOMUX_FUNC);
    DL_GPIO_enableOutput(GPIO_STEP2_C0_PORT, GPIO_STEP2_C0_PIN);
    DL_GPIO_initPeripheralOutputFunction(GPIO_ROTATE_MOTOR_PWM_C1_IOMUX,GPIO_ROTATE_MOTOR_PWM_C1_IOMUX_FUNC);
    DL_GPIO_enableOutput(GPIO_ROTATE_MOTOR_PWM_C1_PORT, GPIO_ROTATE_MOTOR_PWM_C1_PIN);

    DL_GPIO_initDigitalOutput(GPIO_GRP_1_STAGE1_DIR_PIN_IOMUX);

    DL_GPIO_initDigitalOutput(GPIO_GRP_2_STAGE2_DIR_PIN_IOMUX);

    DL_GPIO_initDigitalInputFeatures(GPIO_GRP_3_STAGE1_LIMIT_PIN_IOMUX,
		 DL_GPIO_INVERSION_DISABLE, DL_GPIO_RESISTOR_PULL_UP,
		 DL_GPIO_HYSTERESIS_DISABLE, DL_GPIO_WAKEUP_DISABLE);

    DL_GPIO_initDigitalInputFeatures(GPIO_GRP_4_STAGE2_LIMIT_PIN_IOMUX,
		 DL_GPIO_INVERSION_DISABLE, DL_GPIO_RESISTOR_PULL_UP,
		 DL_GPIO_HYSTERESIS_DISABLE, DL_GPIO_WAKEUP_DISABLE);

    DL_GPIO_initDigitalInputFeatures(KEY1_GPIO_KEY1_PIN_IOMUX,
		 DL_GPIO_INVERSION_DISABLE, DL_GPIO_RESISTOR_PULL_UP,
		 DL_GPIO_HYSTERESIS_DISABLE, DL_GPIO_WAKEUP_DISABLE);

    DL_GPIO_initDigitalInputFeatures(KEY2_GPIO_KEY2_PIN_IOMUX,
		 DL_GPIO_INVERSION_DISABLE, DL_GPIO_RESISTOR_PULL_UP,
		 DL_GPIO_HYSTERESIS_DISABLE, DL_GPIO_WAKEUP_DISABLE);

    DL_GPIO_initDigitalInputFeatures(KEY3_GPIO_KEY3_PIN_IOMUX,
		 DL_GPIO_INVERSION_DISABLE, DL_GPIO_RESISTOR_PULL_UP,
		 DL_GPIO_HYSTERESIS_DISABLE, DL_GPIO_WAKEUP_DISABLE);

    DL_GPIO_initDigitalInputFeatures(KEY4_GPIO_KEY4_PIN_IOMUX,
		 DL_GPIO_INVERSION_DISABLE, DL_GPIO_RESISTOR_PULL_UP,
		 DL_GPIO_HYSTERESIS_DISABLE, DL_GPIO_WAKEUP_DISABLE);

    DL_GPIO_initDigitalOutput(STATUS_LED_LED_PIN_IOMUX);

    DL_GPIO_initDigitalOutput(ROTATE_MOTOR_CTRL_AIN1_PIN_IOMUX);

    DL_GPIO_initDigitalOutput(ROTATE_MOTOR_CTRL_AIN2_PIN_IOMUX);

    DL_GPIO_initDigitalInput(ROTATION_ENCODER_ENCODER_A_PIN_IOMUX);

    DL_GPIO_initDigitalInput(ROTATION_ENCODER_ENCODER_B_PIN_IOMUX);

    DL_GPIO_initDigitalOutput(ACTUATOR_OUTPUT_A_BUZZER_PIN_IOMUX);

    DL_GPIO_initDigitalOutput(ACTUATOR_OUTPUT_A_MAGNET_PIN_IOMUX);

    DL_GPIO_clearPins(GPIOA, GPIO_GRP_1_STAGE1_DIR_PIN_PIN |
		GPIO_GRP_2_STAGE2_DIR_PIN_PIN |
		ACTUATOR_OUTPUT_A_BUZZER_PIN_PIN |
		ACTUATOR_OUTPUT_A_MAGNET_PIN_PIN);
    DL_GPIO_enableOutput(GPIOA, GPIO_GRP_1_STAGE1_DIR_PIN_PIN |
		GPIO_GRP_2_STAGE2_DIR_PIN_PIN |
		ACTUATOR_OUTPUT_A_BUZZER_PIN_PIN |
		ACTUATOR_OUTPUT_A_MAGNET_PIN_PIN);
    DL_GPIO_clearPins(GPIOB, STATUS_LED_LED_PIN_PIN |
		ROTATE_MOTOR_CTRL_AIN1_PIN_PIN |
		ROTATE_MOTOR_CTRL_AIN2_PIN_PIN);
    DL_GPIO_enableOutput(GPIOB, STATUS_LED_LED_PIN_PIN |
		ROTATE_MOTOR_CTRL_AIN1_PIN_PIN |
		ROTATE_MOTOR_CTRL_AIN2_PIN_PIN);
    DL_GPIO_setLowerPinsPolarity(GPIOB, DL_GPIO_PIN_11_EDGE_RISE_FALL |
		DL_GPIO_PIN_14_EDGE_RISE_FALL);
    DL_GPIO_clearInterruptStatus(GPIOB, ROTATION_ENCODER_ENCODER_A_PIN_PIN |
		ROTATION_ENCODER_ENCODER_B_PIN_PIN);
    DL_GPIO_enableInterrupt(GPIOB, ROTATION_ENCODER_ENCODER_A_PIN_PIN |
		ROTATION_ENCODER_ENCODER_B_PIN_PIN);

}


SYSCONFIG_WEAK void SYSCFG_DL_SYSCTL_init(void)
{

	//Low Power Mode is configured to be SLEEP0
    DL_SYSCTL_setBORThreshold(DL_SYSCTL_BOR_THRESHOLD_LEVEL_0);

    DL_SYSCTL_setSYSOSCFreq(DL_SYSCTL_SYSOSC_FREQ_BASE);
    DL_SYSCTL_setULPCLKDivider(DL_SYSCTL_ULPCLK_DIV_1);
    DL_SYSCTL_setMCLKDivider(DL_SYSCTL_MCLK_DIVIDER_DISABLE);

}


/*
 * Timer clock configuration to be sourced by  / 1 (32000000 Hz)
 * timerClkFreq = (timerClkSrc / (timerClkDivRatio * (timerClkPrescale + 1)))
 *   32000000 Hz = 32000000 Hz / (1 * (0 + 1))
 */
static const DL_TimerA_ClockConfig gSTEPClockConfig = {
    .clockSel = DL_TIMER_CLOCK_BUSCLK,
    .divideRatio = DL_TIMER_CLOCK_DIVIDE_1,
    .prescale = 0U
};

static const DL_TimerA_PWMConfig gSTEPConfig = {
    .pwmMode = DL_TIMER_PWM_MODE_EDGE_ALIGN,
    .period = 1000,
    .isTimerWithFourCC = true,
    .startTimer = DL_TIMER_STOP,
};

SYSCONFIG_WEAK void SYSCFG_DL_STEP_init(void) {

    DL_TimerA_setClockConfig(
        STEP_INST, (DL_TimerA_ClockConfig *) &gSTEPClockConfig);

    DL_TimerA_initPWMMode(
        STEP_INST, (DL_TimerA_PWMConfig *) &gSTEPConfig);

    DL_TimerA_setCaptureCompareValue(STEP_INST, 500, DL_TIMER_CC_0_INDEX);
    DL_TimerA_setCaptureCompareOutCtl(STEP_INST, DL_TIMER_CC_OCTL_INIT_VAL_LOW,
		DL_TIMER_CC_OCTL_INV_OUT_DISABLED, DL_TIMER_CC_OCTL_SRC_FUNCVAL,
		DL_TIMERA_CAPTURE_COMPARE_0_INDEX);

    DL_TimerA_setCaptCompUpdateMethod(STEP_INST, DL_TIMER_CC_UPDATE_METHOD_IMMEDIATE, DL_TIMERA_CAPTURE_COMPARE_0_INDEX);

    DL_TimerA_enableClock(STEP_INST);


    DL_TimerA_enableInterrupt(STEP_INST , DL_TIMER_INTERRUPT_ZERO_EVENT);

    DL_TimerA_setCCPDirection(STEP_INST , DL_TIMER_CC0_OUTPUT );

}
/*
 * Timer clock configuration to be sourced by  / 1 (32000000 Hz)
 * timerClkFreq = (timerClkSrc / (timerClkDivRatio * (timerClkPrescale + 1)))
 *   32000000 Hz = 32000000 Hz / (1 * (0 + 1))
 */
static const DL_TimerA_ClockConfig gSTEP2ClockConfig = {
    .clockSel = DL_TIMER_CLOCK_BUSCLK,
    .divideRatio = DL_TIMER_CLOCK_DIVIDE_1,
    .prescale = 0U
};

static const DL_TimerA_PWMConfig gSTEP2Config = {
    .pwmMode = DL_TIMER_PWM_MODE_EDGE_ALIGN,
    .period = 1000,
    .isTimerWithFourCC = true,
    .startTimer = DL_TIMER_STOP,
};

SYSCONFIG_WEAK void SYSCFG_DL_STEP2_init(void) {

    DL_TimerA_setClockConfig(
        STEP2_INST, (DL_TimerA_ClockConfig *) &gSTEP2ClockConfig);

    DL_TimerA_initPWMMode(
        STEP2_INST, (DL_TimerA_PWMConfig *) &gSTEP2Config);

    DL_TimerA_setCaptureCompareValue(STEP2_INST, 500, DL_TIMER_CC_0_INDEX);
    DL_TimerA_setCaptureCompareOutCtl(STEP2_INST, DL_TIMER_CC_OCTL_INIT_VAL_LOW,
		DL_TIMER_CC_OCTL_INV_OUT_DISABLED, DL_TIMER_CC_OCTL_SRC_FUNCVAL,
		DL_TIMERA_CAPTURE_COMPARE_0_INDEX);

    DL_TimerA_setCaptCompUpdateMethod(STEP2_INST, DL_TIMER_CC_UPDATE_METHOD_IMMEDIATE, DL_TIMERA_CAPTURE_COMPARE_0_INDEX);

    DL_TimerA_enableClock(STEP2_INST);


    DL_TimerA_enableInterrupt(STEP2_INST , DL_TIMER_INTERRUPT_ZERO_EVENT);

    DL_TimerA_setCCPDirection(STEP2_INST , DL_TIMER_CC0_OUTPUT );

}
/*
 * Timer clock configuration to be sourced by  / 1 (32000000 Hz)
 * timerClkFreq = (timerClkSrc / (timerClkDivRatio * (timerClkPrescale + 1)))
 *   32000000 Hz = 32000000 Hz / (1 * (0 + 1))
 */
static const DL_TimerG_ClockConfig gROTATE_MOTOR_PWMClockConfig = {
    .clockSel = DL_TIMER_CLOCK_BUSCLK,
    .divideRatio = DL_TIMER_CLOCK_DIVIDE_1,
    .prescale = 0U
};

static const DL_TimerG_PWMConfig gROTATE_MOTOR_PWMConfig = {
    .pwmMode = DL_TIMER_PWM_MODE_EDGE_ALIGN,
    .period = 1000,
    .startTimer = DL_TIMER_START,
};

SYSCONFIG_WEAK void SYSCFG_DL_ROTATE_MOTOR_PWM_init(void) {

    DL_TimerG_setClockConfig(
        ROTATE_MOTOR_PWM_INST, (DL_TimerG_ClockConfig *) &gROTATE_MOTOR_PWMClockConfig);

    DL_TimerG_initPWMMode(
        ROTATE_MOTOR_PWM_INST, (DL_TimerG_PWMConfig *) &gROTATE_MOTOR_PWMConfig);

    DL_TimerG_setCaptureCompareValue(ROTATE_MOTOR_PWM_INST, 1000, DL_TIMER_CC_1_INDEX);
    DL_TimerG_setCaptureCompareOutCtl(ROTATE_MOTOR_PWM_INST, DL_TIMER_CC_OCTL_INIT_VAL_LOW,
		DL_TIMER_CC_OCTL_INV_OUT_DISABLED, DL_TIMER_CC_OCTL_SRC_FUNCVAL,
		DL_TIMERG_CAPTURE_COMPARE_1_INDEX);

    DL_TimerG_setCaptCompUpdateMethod(ROTATE_MOTOR_PWM_INST, DL_TIMER_CC_UPDATE_METHOD_IMMEDIATE, DL_TIMERG_CAPTURE_COMPARE_1_INDEX);

    DL_TimerG_enableClock(ROTATE_MOTOR_PWM_INST);


    
    DL_TimerG_setCCPDirection(ROTATE_MOTOR_PWM_INST , DL_TIMER_CC1_OUTPUT );

}


