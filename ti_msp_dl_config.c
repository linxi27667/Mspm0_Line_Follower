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

DL_TimerG_backupConfig gMonitor_Left_TimerBackup;
DL_TimerG_backupConfig gRight_Motor_TimerBackup;
DL_TimerG_backupConfig gEncoder_TimerBackup;

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
    SYSCFG_DL_Monitor_Left_Timer_init();
    SYSCFG_DL_Right_Motor_Timer_init();
    SYSCFG_DL_Encoder_Timer_init();
    SYSCFG_DL_MPU6050_I2C_init();
    SYSCFG_DL_UART_Debug_init();
    SYSCFG_DL_GRAYSCALE_ADC_init();
    SYSCFG_DL_DMA_init();
    /* Ensure backup structures have no valid state */
	gMonitor_Left_TimerBackup.backupRdy 	= false;
	gRight_Motor_TimerBackup.backupRdy 	= false;
	gEncoder_TimerBackup.backupRdy 	= false;


}
/*
 * User should take care to save and restore register configuration in application.
 * See Retention Configuration section for more details.
 */
SYSCONFIG_WEAK bool SYSCFG_DL_saveConfiguration(void)
{
    bool retStatus = true;

	retStatus &= DL_TimerG_saveConfiguration(Monitor_Left_Timer_INST, &gMonitor_Left_TimerBackup);
	retStatus &= DL_TimerG_saveConfiguration(Right_Motor_Timer_INST, &gRight_Motor_TimerBackup);
	retStatus &= DL_TimerG_saveConfiguration(Encoder_Timer_INST, &gEncoder_TimerBackup);

    return retStatus;
}


SYSCONFIG_WEAK bool SYSCFG_DL_restoreConfiguration(void)
{
    bool retStatus = true;

	retStatus &= DL_TimerG_restoreConfiguration(Monitor_Left_Timer_INST, &gMonitor_Left_TimerBackup, false);
	retStatus &= DL_TimerG_restoreConfiguration(Right_Motor_Timer_INST, &gRight_Motor_TimerBackup, false);
	retStatus &= DL_TimerG_restoreConfiguration(Encoder_Timer_INST, &gEncoder_TimerBackup, false);

    return retStatus;
}

SYSCONFIG_WEAK void SYSCFG_DL_initPower(void)
{
    DL_GPIO_reset(GPIOA);
    DL_GPIO_reset(GPIOB);
    DL_TimerG_reset(Monitor_Left_Timer_INST);
    DL_TimerG_reset(Right_Motor_Timer_INST);
    DL_TimerG_reset(Encoder_Timer_INST);
    DL_I2C_reset(MPU6050_I2C_INST);
    DL_UART_Main_reset(UART_Debug_INST);
    DL_ADC12_reset(GRAYSCALE_ADC_INST);


    DL_GPIO_enablePower(GPIOA);
    DL_GPIO_enablePower(GPIOB);
    DL_TimerG_enablePower(Monitor_Left_Timer_INST);
    DL_TimerG_enablePower(Right_Motor_Timer_INST);
    DL_TimerG_enablePower(Encoder_Timer_INST);
    DL_I2C_enablePower(MPU6050_I2C_INST);
    DL_UART_Main_enablePower(UART_Debug_INST);
    DL_ADC12_enablePower(GRAYSCALE_ADC_INST);

    delay_cycles(POWER_STARTUP_DELAY);
}

SYSCONFIG_WEAK void SYSCFG_DL_GPIO_init(void)
{

    DL_GPIO_initPeripheralOutputFunction(GPIO_Monitor_Left_Timer_C0_IOMUX,GPIO_Monitor_Left_Timer_C0_IOMUX_FUNC);
    DL_GPIO_enableOutput(GPIO_Monitor_Left_Timer_C0_PORT, GPIO_Monitor_Left_Timer_C0_PIN);
    DL_GPIO_initPeripheralOutputFunction(GPIO_Right_Motor_Timer_C0_IOMUX,GPIO_Right_Motor_Timer_C0_IOMUX_FUNC);
    DL_GPIO_enableOutput(GPIO_Right_Motor_Timer_C0_PORT, GPIO_Right_Motor_Timer_C0_PIN);

    DL_GPIO_initPeripheralInputFunction(GPIO_Encoder_Timer_PHA_IOMUX,GPIO_Encoder_Timer_PHA_IOMUX_FUNC);
    DL_GPIO_initPeripheralInputFunction(GPIO_Encoder_Timer_PHB_IOMUX,GPIO_Encoder_Timer_PHB_IOMUX_FUNC);

    DL_GPIO_initPeripheralInputFunctionFeatures(GPIO_MPU6050_I2C_IOMUX_SDA,
        GPIO_MPU6050_I2C_IOMUX_SDA_FUNC, DL_GPIO_INVERSION_DISABLE,
        DL_GPIO_RESISTOR_NONE, DL_GPIO_HYSTERESIS_DISABLE,
        DL_GPIO_WAKEUP_DISABLE);
    DL_GPIO_initPeripheralInputFunctionFeatures(GPIO_MPU6050_I2C_IOMUX_SCL,
        GPIO_MPU6050_I2C_IOMUX_SCL_FUNC, DL_GPIO_INVERSION_DISABLE,
        DL_GPIO_RESISTOR_NONE, DL_GPIO_HYSTERESIS_DISABLE,
        DL_GPIO_WAKEUP_DISABLE);
    DL_GPIO_enableHiZ(GPIO_MPU6050_I2C_IOMUX_SDA);
    DL_GPIO_enableHiZ(GPIO_MPU6050_I2C_IOMUX_SCL);

    DL_GPIO_initPeripheralOutputFunction(
        GPIO_UART_Debug_IOMUX_TX, GPIO_UART_Debug_IOMUX_TX_FUNC);
    DL_GPIO_initPeripheralInputFunction(
        GPIO_UART_Debug_IOMUX_RX, GPIO_UART_Debug_IOMUX_RX_FUNC);

    DL_GPIO_initDigitalOutput(Board_Led_PIN_0_IOMUX);

    DL_GPIO_initDigitalOutput(Grayscale_ADDR_B_AD2_IOMUX);

    DL_GPIO_initDigitalOutput(Monitor_Dir_Monitor_AIN1_IOMUX);

    DL_GPIO_initDigitalOutput(Monitor_Dir_Monitor_AIN2_IOMUX);

    DL_GPIO_initDigitalOutput(Right_Motor_Dir_AIN1_IOMUX);

    DL_GPIO_initDigitalOutput(Right_Motor_Dir_AIN2_IOMUX);

    DL_GPIO_initDigitalOutput(Grayscale_ADDR_A_AD0_IOMUX);

    DL_GPIO_initDigitalOutput(Grayscale_ADDR_A_AD1_IOMUX);

    DL_GPIO_initDigitalInputFeatures(Key_Group_KEY1_IOMUX,
		 DL_GPIO_INVERSION_DISABLE, DL_GPIO_RESISTOR_PULL_UP,
		 DL_GPIO_HYSTERESIS_DISABLE, DL_GPIO_WAKEUP_DISABLE);

    DL_GPIO_initDigitalInputFeatures(Key_Group_KEY2_IOMUX,
		 DL_GPIO_INVERSION_DISABLE, DL_GPIO_RESISTOR_PULL_UP,
		 DL_GPIO_HYSTERESIS_DISABLE, DL_GPIO_WAKEUP_DISABLE);

    DL_GPIO_initDigitalInputFeatures(Key_Group_KEY3_IOMUX,
		 DL_GPIO_INVERSION_DISABLE, DL_GPIO_RESISTOR_PULL_UP,
		 DL_GPIO_HYSTERESIS_DISABLE, DL_GPIO_WAKEUP_DISABLE);

    DL_GPIO_initDigitalInputFeatures(Key_PA30_KEY4_IOMUX,
		 DL_GPIO_INVERSION_DISABLE, DL_GPIO_RESISTOR_PULL_UP,
		 DL_GPIO_HYSTERESIS_DISABLE, DL_GPIO_WAKEUP_DISABLE);

    DL_GPIO_initDigitalOutput(Led_Group_LED1_IOMUX);

    DL_GPIO_initDigitalOutput(Led_Group_LED2_IOMUX);

    DL_GPIO_initDigitalOutput(Led_Group_LED3_IOMUX);

    DL_GPIO_initDigitalOutput(Led_Group_LED4_IOMUX);

    DL_GPIO_initDigitalInputFeatures(Right_Encoder_PHA_IOMUX,
		 DL_GPIO_INVERSION_DISABLE, DL_GPIO_RESISTOR_PULL_UP,
		 DL_GPIO_HYSTERESIS_DISABLE, DL_GPIO_WAKEUP_DISABLE);

    DL_GPIO_initDigitalInputFeatures(Right_Encoder_PHB_IOMUX,
		 DL_GPIO_INVERSION_DISABLE, DL_GPIO_RESISTOR_PULL_UP,
		 DL_GPIO_HYSTERESIS_DISABLE, DL_GPIO_WAKEUP_DISABLE);

    DL_GPIO_clearPins(GPIOA, Grayscale_ADDR_B_AD2_PIN |
		Monitor_Dir_Monitor_AIN1_PIN |
		Monitor_Dir_Monitor_AIN2_PIN |
		Right_Motor_Dir_AIN1_PIN |
		Right_Motor_Dir_AIN2_PIN |
		Grayscale_ADDR_A_AD0_PIN |
		Grayscale_ADDR_A_AD1_PIN);
    DL_GPIO_enableOutput(GPIOA, Grayscale_ADDR_B_AD2_PIN |
		Monitor_Dir_Monitor_AIN1_PIN |
		Monitor_Dir_Monitor_AIN2_PIN |
		Right_Motor_Dir_AIN1_PIN |
		Right_Motor_Dir_AIN2_PIN |
		Grayscale_ADDR_A_AD0_PIN |
		Grayscale_ADDR_A_AD1_PIN);
    DL_GPIO_clearPins(GPIOB, Board_Led_PIN_0_PIN |
		Led_Group_LED1_PIN |
		Led_Group_LED2_PIN |
		Led_Group_LED3_PIN |
		Led_Group_LED4_PIN);
    DL_GPIO_enableOutput(GPIOB, Board_Led_PIN_0_PIN |
		Led_Group_LED1_PIN |
		Led_Group_LED2_PIN |
		Led_Group_LED3_PIN |
		Led_Group_LED4_PIN);
    DL_GPIO_setLowerPinsPolarity(GPIOB, DL_GPIO_PIN_14_EDGE_RISE_FALL);
    DL_GPIO_clearInterruptStatus(GPIOB, Right_Encoder_PHA_PIN);
    DL_GPIO_enableInterrupt(GPIOB, Right_Encoder_PHA_PIN);

}



SYSCONFIG_WEAK void SYSCFG_DL_SYSCTL_init(void)
{

	//Low Power Mode is configured to be SLEEP0
    DL_SYSCTL_setBORThreshold(DL_SYSCTL_BOR_THRESHOLD_LEVEL_0);

    DL_SYSCTL_setSYSOSCFreq(DL_SYSCTL_SYSOSC_FREQ_BASE);
	/* Set default configuration */
	DL_SYSCTL_disableHFXT();
	DL_SYSCTL_disableSYSPLL();

}


/*
 * Timer clock configuration to be sourced by  / 8 (4000000 Hz)
 * timerClkFreq = (timerClkSrc / (timerClkDivRatio * (timerClkPrescale + 1)))
 *   4000000 Hz = 4000000 Hz / (8 * (0 + 1))
 */
static const DL_TimerG_ClockConfig gMonitor_Left_TimerClockConfig = {
    .clockSel = DL_TIMER_CLOCK_BUSCLK,
    .divideRatio = DL_TIMER_CLOCK_DIVIDE_8,
    .prescale = 0U
};

static const DL_TimerG_PWMConfig gMonitor_Left_TimerConfig = {
    .pwmMode = DL_TIMER_PWM_MODE_EDGE_ALIGN,
    .period = 100,
    .startTimer = DL_TIMER_START,
};

SYSCONFIG_WEAK void SYSCFG_DL_Monitor_Left_Timer_init(void) {

    DL_TimerG_setClockConfig(
        Monitor_Left_Timer_INST, (DL_TimerG_ClockConfig *) &gMonitor_Left_TimerClockConfig);

    DL_TimerG_initPWMMode(
        Monitor_Left_Timer_INST, (DL_TimerG_PWMConfig *) &gMonitor_Left_TimerConfig);

    DL_TimerG_setCaptureCompareValue(Monitor_Left_Timer_INST, 100, DL_TIMER_CC_0_INDEX);
    DL_TimerG_setCaptureCompareOutCtl(Monitor_Left_Timer_INST, DL_TIMER_CC_OCTL_INIT_VAL_LOW,
		DL_TIMER_CC_OCTL_INV_OUT_DISABLED, DL_TIMER_CC_OCTL_SRC_FUNCVAL,
		DL_TIMERG_CAPTURE_COMPARE_0_INDEX);

    DL_TimerG_setCaptCompUpdateMethod(Monitor_Left_Timer_INST, DL_TIMER_CC_UPDATE_METHOD_IMMEDIATE, DL_TIMERG_CAPTURE_COMPARE_0_INDEX);

    DL_TimerG_enableClock(Monitor_Left_Timer_INST);


    
    DL_TimerG_setCCPDirection(Monitor_Left_Timer_INST , DL_TIMER_CC0_OUTPUT );

}
/*
 * Timer clock configuration to be sourced by  / 8 (4000000 Hz)
 * timerClkFreq = (timerClkSrc / (timerClkDivRatio * (timerClkPrescale + 1)))
 *   4000000 Hz = 4000000 Hz / (8 * (0 + 1))
 */
static const DL_TimerG_ClockConfig gRight_Motor_TimerClockConfig = {
    .clockSel = DL_TIMER_CLOCK_BUSCLK,
    .divideRatio = DL_TIMER_CLOCK_DIVIDE_8,
    .prescale = 0U
};

static const DL_TimerG_PWMConfig gRight_Motor_TimerConfig = {
    .pwmMode = DL_TIMER_PWM_MODE_EDGE_ALIGN,
    .period = 100,
    .startTimer = DL_TIMER_START,
};

SYSCONFIG_WEAK void SYSCFG_DL_Right_Motor_Timer_init(void) {

    DL_TimerG_setClockConfig(
        Right_Motor_Timer_INST, (DL_TimerG_ClockConfig *) &gRight_Motor_TimerClockConfig);

    DL_TimerG_initPWMMode(
        Right_Motor_Timer_INST, (DL_TimerG_PWMConfig *) &gRight_Motor_TimerConfig);

    DL_TimerG_setCaptureCompareValue(Right_Motor_Timer_INST, 100, DL_TIMER_CC_0_INDEX);
    DL_TimerG_setCaptureCompareOutCtl(Right_Motor_Timer_INST, DL_TIMER_CC_OCTL_INIT_VAL_LOW,
		DL_TIMER_CC_OCTL_INV_OUT_DISABLED, DL_TIMER_CC_OCTL_SRC_FUNCVAL,
		DL_TIMERG_CAPTURE_COMPARE_0_INDEX);

    DL_TimerG_setCaptCompUpdateMethod(Right_Motor_Timer_INST, DL_TIMER_CC_UPDATE_METHOD_IMMEDIATE, DL_TIMERG_CAPTURE_COMPARE_0_INDEX);

    DL_TimerG_enableClock(Right_Motor_Timer_INST);


    
    DL_TimerG_setCCPDirection(Right_Motor_Timer_INST , DL_TIMER_CC0_OUTPUT );

}


static const DL_TimerG_ClockConfig gEncoder_TimerClockConfig = {
    .clockSel = DL_TIMER_CLOCK_BUSCLK,
    .divideRatio = DL_TIMER_CLOCK_DIVIDE_1,
    .prescale = 0U
};


SYSCONFIG_WEAK void SYSCFG_DL_Encoder_Timer_init(void) {

    DL_TimerG_setClockConfig(
        Encoder_Timer_INST, (DL_TimerG_ClockConfig *) &gEncoder_TimerClockConfig);

    DL_TimerG_configQEI(Encoder_Timer_INST, DL_TIMER_QEI_MODE_2_INPUT,
        DL_TIMER_CC_INPUT_INV_NOINVERT, DL_TIMER_CC_0_INDEX);
    DL_TimerG_configQEI(Encoder_Timer_INST, DL_TIMER_QEI_MODE_2_INPUT,
        DL_TIMER_CC_INPUT_INV_NOINVERT, DL_TIMER_CC_1_INDEX);
    DL_TimerG_setLoadValue(Encoder_Timer_INST, 65535);
    DL_TimerG_enableClock(Encoder_Timer_INST);
    DL_TimerG_startCounter(Encoder_Timer_INST);
}


static const DL_I2C_ClockConfig gMPU6050_I2CClockConfig = {
    .clockSel = DL_I2C_CLOCK_BUSCLK,
    .divideRatio = DL_I2C_CLOCK_DIVIDE_1,
};

SYSCONFIG_WEAK void SYSCFG_DL_MPU6050_I2C_init(void) {

    DL_I2C_setClockConfig(MPU6050_I2C_INST,
        (DL_I2C_ClockConfig *) &gMPU6050_I2CClockConfig);
    DL_I2C_setAnalogGlitchFilterPulseWidth(MPU6050_I2C_INST,
        DL_I2C_ANALOG_GLITCH_FILTER_WIDTH_50NS);
    DL_I2C_enableAnalogGlitchFilter(MPU6050_I2C_INST);




}


static const DL_UART_Main_ClockConfig gUART_DebugClockConfig = {
    .clockSel    = DL_UART_MAIN_CLOCK_BUSCLK,
    .divideRatio = DL_UART_MAIN_CLOCK_DIVIDE_RATIO_1
};

static const DL_UART_Main_Config gUART_DebugConfig = {
    .mode        = DL_UART_MAIN_MODE_NORMAL,
    .direction   = DL_UART_MAIN_DIRECTION_TX_RX,
    .flowControl = DL_UART_MAIN_FLOW_CONTROL_NONE,
    .parity      = DL_UART_MAIN_PARITY_NONE,
    .wordLength  = DL_UART_MAIN_WORD_LENGTH_8_BITS,
    .stopBits    = DL_UART_MAIN_STOP_BITS_ONE
};

SYSCONFIG_WEAK void SYSCFG_DL_UART_Debug_init(void)
{
    DL_UART_Main_setClockConfig(UART_Debug_INST, (DL_UART_Main_ClockConfig *) &gUART_DebugClockConfig);

    DL_UART_Main_init(UART_Debug_INST, (DL_UART_Main_Config *) &gUART_DebugConfig);
    /*
     * Configure baud rate by setting oversampling and baud rate divisors.
     *  Target baud rate: 115200
     *  Actual baud rate: 115211.52
     */
    DL_UART_Main_setOversampling(UART_Debug_INST, DL_UART_OVERSAMPLING_RATE_16X);
    DL_UART_Main_setBaudRateDivisor(UART_Debug_INST, UART_Debug_IBRD_32_MHZ_115200_BAUD, UART_Debug_FBRD_32_MHZ_115200_BAUD);


    /* Configure Interrupts */
    DL_UART_Main_enableInterrupt(UART_Debug_INST,
                                 DL_UART_MAIN_INTERRUPT_RX_TIMEOUT_ERROR);

    /* Configure DMA Receive Event */
    DL_UART_Main_enableDMAReceiveEvent(UART_Debug_INST, DL_UART_DMA_INTERRUPT_RX);
    /* Configure DMA Transmit Event */
    DL_UART_Main_enableDMATransmitEvent(UART_Debug_INST);
    /* Configure FIFOs */
    DL_UART_Main_enableFIFOs(UART_Debug_INST);
    DL_UART_Main_setRXFIFOThreshold(UART_Debug_INST, DL_UART_RX_FIFO_LEVEL_1_4_FULL);
    DL_UART_Main_setTXFIFOThreshold(UART_Debug_INST, DL_UART_TX_FIFO_LEVEL_1_2_EMPTY);

    DL_UART_Main_setRXInterruptTimeout(UART_Debug_INST, 15);

    DL_UART_Main_enable(UART_Debug_INST);
}

/* GRAYSCALE_ADC Initialization */
static const DL_ADC12_ClockConfig gGRAYSCALE_ADCClockConfig = {
    .clockSel       = DL_ADC12_CLOCK_ULPCLK,
    .divideRatio    = DL_ADC12_CLOCK_DIVIDE_8,
    .freqRange      = DL_ADC12_CLOCK_FREQ_RANGE_24_TO_32,
};
SYSCONFIG_WEAK void SYSCFG_DL_GRAYSCALE_ADC_init(void)
{
    DL_ADC12_setClockConfig(GRAYSCALE_ADC_INST, (DL_ADC12_ClockConfig *) &gGRAYSCALE_ADCClockConfig);
    DL_ADC12_configConversionMem(GRAYSCALE_ADC_INST, GRAYSCALE_ADC_ADCMEM_0,
        DL_ADC12_INPUT_CHAN_0, DL_ADC12_REFERENCE_VOLTAGE_VDDA, DL_ADC12_SAMPLE_TIMER_SOURCE_SCOMP0, DL_ADC12_AVERAGING_MODE_DISABLED,
        DL_ADC12_BURN_OUT_SOURCE_DISABLED, DL_ADC12_TRIGGER_MODE_AUTO_NEXT, DL_ADC12_WINDOWS_COMP_MODE_DISABLED);
    DL_ADC12_setPowerDownMode(GRAYSCALE_ADC_INST,DL_ADC12_POWER_DOWN_MODE_MANUAL);
    DL_ADC12_setSampleTime0(GRAYSCALE_ADC_INST,500);
    DL_ADC12_enableConversions(GRAYSCALE_ADC_INST);
}

static const DL_DMA_Config gDMA_CH0Config = {
    .transferMode   = DL_DMA_SINGLE_TRANSFER_MODE,
    .extendedMode   = DL_DMA_NORMAL_MODE,
    .destIncrement  = DL_DMA_ADDR_INCREMENT,
    .srcIncrement   = DL_DMA_ADDR_UNCHANGED,
    .destWidth      = DL_DMA_WIDTH_BYTE,
    .srcWidth       = DL_DMA_WIDTH_BYTE,
    .trigger        = UART_Debug_INST_DMA_TRIGGER_0,
    .triggerType    = DL_DMA_TRIGGER_TYPE_EXTERNAL,
};

SYSCONFIG_WEAK void SYSCFG_DL_DMA_CH0_init(void)
{
    DL_DMA_initChannel(DMA, DMA_CH0_CHAN_ID , (DL_DMA_Config *) &gDMA_CH0Config);
}
static const DL_DMA_Config gDMA_CH1Config = {
    .transferMode   = DL_DMA_SINGLE_TRANSFER_MODE,
    .extendedMode   = DL_DMA_NORMAL_MODE,
    .destIncrement  = DL_DMA_ADDR_UNCHANGED,
    .srcIncrement   = DL_DMA_ADDR_INCREMENT,
    .destWidth      = DL_DMA_WIDTH_BYTE,
    .srcWidth       = DL_DMA_WIDTH_BYTE,
    .trigger        = UART_Debug_INST_DMA_TRIGGER_1,
    .triggerType    = DL_DMA_TRIGGER_TYPE_EXTERNAL,
};

SYSCONFIG_WEAK void SYSCFG_DL_DMA_CH1_init(void)
{
    DL_DMA_clearInterruptStatus(DMA, DL_DMA_INTERRUPT_CHANNEL1);
    DL_DMA_enableInterrupt(DMA, DL_DMA_INTERRUPT_CHANNEL1);
    DL_DMA_initChannel(DMA, DMA_CH1_CHAN_ID , (DL_DMA_Config *) &gDMA_CH1Config);
}
SYSCONFIG_WEAK void SYSCFG_DL_DMA_init(void){
    SYSCFG_DL_DMA_CH0_init();
    SYSCFG_DL_DMA_CH1_init();
}


