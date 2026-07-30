/**
 * @file    app_actuator.c
 * @brief   MSPM0G3507 binding for the puzzle actuator drivers.
 */
#include "app_actuator.h"

#include "bsp_magnet.h"
#include "bsp_quadrature_encoder.h"
#include "bsp_tb6612.h"
#include "ti_msp_dl_config.h"

#define ROTATION_PWM_PERIOD_COUNTS    (1000U)

typedef struct {
    GPIO_Regs *port;
    uint32_t pin;
} app_gpio_output_t;

static const app_gpio_output_t s_ain1_output = {
    ROTATE_MOTOR_CTRL_PORT, ROTATE_MOTOR_CTRL_AIN1_PIN_PIN
};
static const app_gpio_output_t s_ain2_output = {
    ROTATE_MOTOR_CTRL_PORT, ROTATE_MOTOR_CTRL_AIN2_PIN_PIN
};
static const app_gpio_output_t s_magnet_output = {
    ACTUATOR_OUTPUT_A_PORT, ACTUATOR_OUTPUT_A_MAGNET_PIN_PIN
};

static bsp_tb6612_t s_rotation_motor;
static bsp_magnet_t s_magnet;
static bsp_quadrature_encoder_t s_rotation_encoder;
static bool s_initialized;
static bool s_encoder_enabled;
static bool s_led_on;
static bool s_buzzer_on;

static void App_Actuator_GpioWrite(void *handle, bool level)
{
    const app_gpio_output_t *output =
        (const app_gpio_output_t *)handle;

    if (level) {
        DL_GPIO_setPins(output->port, output->pin);
    } else {
        DL_GPIO_clearPins(output->port, output->pin);
    }
}

static void App_Actuator_PwmWrite(void *handle, uint8_t duty_percent)
{
    uint32_t compare;

    (void)handle;
    compare = ROTATION_PWM_PERIOD_COUNTS -
              ((ROTATION_PWM_PERIOD_COUNTS * duty_percent) / 100U);
    DL_TimerG_setCaptureCompareValue(
        ROTATE_MOTOR_PWM_INST, compare, GPIO_ROTATE_MOTOR_PWM_C1_IDX);
}

uint8_t App_RotationEncoder_ReadAB(void)
{
    uint32_t pins;
    uint8_t state = 0U;

    pins = DL_GPIO_readPins(
        ROTATION_ENCODER_PORT,
        ROTATION_ENCODER_ENCODER_A_PIN_PIN |
        ROTATION_ENCODER_ENCODER_B_PIN_PIN);

    if ((pins & ROTATION_ENCODER_ENCODER_A_PIN_PIN) != 0U) {
        state |= 0x02U;
    }
    if ((pins & ROTATION_ENCODER_ENCODER_B_PIN_PIN) != 0U) {
        state |= 0x01U;
    }
    return state;
}

static uint8_t App_Actuator_EncoderReadState(void *handle)
{
    (void)handle;
    return App_RotationEncoder_ReadAB();
}

bool App_Actuator_Init(void)
{
    const uint32_t encoder_pins =
        ROTATION_ENCODER_ENCODER_A_PIN_PIN |
        ROTATION_ENCODER_ENCODER_B_PIN_PIN;

    s_rotation_motor.ain1.handle = (void *)&s_ain1_output;
    s_rotation_motor.ain1.write = App_Actuator_GpioWrite;
    s_rotation_motor.ain2.handle = (void *)&s_ain2_output;
    s_rotation_motor.ain2.write = App_Actuator_GpioWrite;

    /* STBY is hard-wired to 3.3 V. */
    s_rotation_motor.stby.handle = NULL;
    s_rotation_motor.stby.write = NULL;
    s_rotation_motor.pwma.handle = NULL;
    s_rotation_motor.pwma.write = App_Actuator_PwmWrite;

    s_magnet.trigger_handle = (void *)&s_magnet_output;
    s_magnet.trigger_write = App_Actuator_GpioWrite;
    s_magnet.polarity = BSP_MAGNET_ACTIVE_HIGH;

    s_rotation_encoder.input_handle = NULL;
    s_rotation_encoder.read_state = App_Actuator_EncoderReadState;
    s_rotation_encoder.reverse_direction = false;
    s_rotation_encoder.count = 0;

    /*
     * SysConfig defines both-edge sensing, but the encoder remains fully
     * disabled until App_RotationEncoder_Enable() is called.
     */
    DL_GPIO_disableInterrupt(ROTATION_ENCODER_PORT, encoder_pins);
    DL_GPIO_clearInterruptStatus(ROTATION_ENCODER_PORT, encoder_pins);

    DL_GPIO_clearPins(STATUS_LED_PORT, STATUS_LED_LED_PIN_PIN);
    DL_GPIO_clearPins(
        ACTUATOR_OUTPUT_A_PORT, ACTUATOR_OUTPUT_A_BUZZER_PIN_PIN);
    s_led_on = false;
    s_buzzer_on = false;
    s_encoder_enabled = false;

    if (!Bsp_TB6612_Init(&s_rotation_motor) ||
        !Bsp_Magnet_Init(&s_magnet) ||
        !Bsp_TB6612_SetEnabled(&s_rotation_motor, true)) {
        s_initialized = false;
        return false;
    }

    DL_TimerG_startCounter(ROTATE_MOTOR_PWM_INST);
    s_initialized = true;
    return true;
}

void App_Actuator_AllOutputsOff(void)
{
    if (s_initialized) {
        (void)Bsp_TB6612_Coast(&s_rotation_motor);
        (void)Bsp_Magnet_Set(&s_magnet, false);
    }
    App_StatusLed_Set(false);
    App_Buzzer_Set(false);
}

bool App_RotationMotor_SetSignedDuty(int16_t signed_duty_percent)
{
    return s_initialized &&
           Bsp_TB6612_SetSignedDuty(
               &s_rotation_motor, signed_duty_percent);
}

bool App_RotationMotor_Coast(void)
{
    return s_initialized && Bsp_TB6612_Coast(&s_rotation_motor);
}

bool App_RotationMotor_Brake(void)
{
    return s_initialized && Bsp_TB6612_Brake(&s_rotation_motor);
}

int8_t App_RotationMotor_GetSignedDuty(void)
{
    return s_initialized ? s_rotation_motor.signed_duty_percent : 0;
}

bool App_Magnet_Set(bool on)
{
    return s_initialized && Bsp_Magnet_Set(&s_magnet, on);
}

bool App_Magnet_IsOn(void)
{
    return s_initialized && Bsp_Magnet_IsOn(&s_magnet);
}

void App_StatusLed_Set(bool on)
{
    if (on) {
        DL_GPIO_setPins(STATUS_LED_PORT, STATUS_LED_LED_PIN_PIN);
    } else {
        DL_GPIO_clearPins(STATUS_LED_PORT, STATUS_LED_LED_PIN_PIN);
    }
    s_led_on = on;
}

void App_StatusLed_Toggle(void)
{
    App_StatusLed_Set(!s_led_on);
}

bool App_StatusLed_IsOn(void)
{
    return s_led_on;
}

void App_Buzzer_Set(bool on)
{
    if (on) {
        DL_GPIO_setPins(
            ACTUATOR_OUTPUT_A_PORT, ACTUATOR_OUTPUT_A_BUZZER_PIN_PIN);
    } else {
        DL_GPIO_clearPins(
            ACTUATOR_OUTPUT_A_PORT, ACTUATOR_OUTPUT_A_BUZZER_PIN_PIN);
    }
    s_buzzer_on = on;
}

bool App_Buzzer_IsOn(void)
{
    return s_buzzer_on;
}

bool App_RotationEncoder_Enable(bool reverse_direction)
{
    const uint32_t encoder_pins =
        ROTATION_ENCODER_ENCODER_A_PIN_PIN |
        ROTATION_ENCODER_ENCODER_B_PIN_PIN;

    if (!s_initialized) {
        return false;
    }

    DL_GPIO_disableInterrupt(ROTATION_ENCODER_PORT, encoder_pins);
    DL_GPIO_clearInterruptStatus(ROTATION_ENCODER_PORT, encoder_pins);
    s_rotation_encoder.reverse_direction = reverse_direction;
    if (!Bsp_QuadratureEncoder_Init(&s_rotation_encoder)) {
        return false;
    }

    NVIC_ClearPendingIRQ(ROTATION_ENCODER_INT_IRQN);
    NVIC_EnableIRQ(ROTATION_ENCODER_INT_IRQN);
    DL_GPIO_enableInterrupt(ROTATION_ENCODER_PORT, encoder_pins);
    s_encoder_enabled = true;
    return true;
}

void App_RotationEncoder_Disable(void)
{
    const uint32_t encoder_pins =
        ROTATION_ENCODER_ENCODER_A_PIN_PIN |
        ROTATION_ENCODER_ENCODER_B_PIN_PIN;

    DL_GPIO_disableInterrupt(ROTATION_ENCODER_PORT, encoder_pins);
    DL_GPIO_clearInterruptStatus(ROTATION_ENCODER_PORT, encoder_pins);
    s_encoder_enabled = false;
}

bool App_RotationEncoder_IsEnabled(void)
{
    return s_encoder_enabled;
}

int32_t App_RotationEncoder_GetCount(void)
{
    return s_rotation_encoder.count;
}

void App_RotationEncoder_Reset(void)
{
    const uint32_t encoder_pins =
        ROTATION_ENCODER_ENCODER_A_PIN_PIN |
        ROTATION_ENCODER_ENCODER_B_PIN_PIN;
    bool was_enabled = s_encoder_enabled;

    if (was_enabled) {
        DL_GPIO_disableInterrupt(ROTATION_ENCODER_PORT, encoder_pins);
    }
    Bsp_QuadratureEncoder_Reset(&s_rotation_encoder);
    s_rotation_encoder.previous_state = App_RotationEncoder_ReadAB();
    DL_GPIO_clearInterruptStatus(ROTATION_ENCODER_PORT, encoder_pins);
    if (was_enabled) {
        DL_GPIO_enableInterrupt(ROTATION_ENCODER_PORT, encoder_pins);
    }
}

void GROUP1_IRQHandler(void)
{
    const uint32_t encoder_pins =
        ROTATION_ENCODER_ENCODER_A_PIN_PIN |
        ROTATION_ENCODER_ENCODER_B_PIN_PIN;
    uint32_t pending = DL_GPIO_getEnabledInterruptStatus(
        ROTATION_ENCODER_PORT, encoder_pins);

    if ((pending & encoder_pins) != 0U) {
        DL_GPIO_clearInterruptStatus(
            ROTATION_ENCODER_PORT, pending & encoder_pins);
        Bsp_QuadratureEncoder_OnEdge(&s_rotation_encoder);
    }
}
