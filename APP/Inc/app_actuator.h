/**
 * @file    app_actuator.h
 * @brief   Puzzle rotation motor, encoder, magnet, LED and buzzer interface.
 *
 * Pin assignment:
 *   TB6612 PWMA PA7/TIMG7_CCP1, AIN1 PB0, AIN2 PB1
 *   TB6612 STBY is hard-wired to 3.3 V and is not controlled by software
 *   Encoder A PB11, Encoder B PB14
 *   Electromagnet MOS trigger PA30, active high
 *   Status LED PB10, active high
 *   Buzzer PA2, active high
 */
#ifndef APP_ACTUATOR_H
#define APP_ACTUATOR_H

#include <stdbool.h>
#include <stdint.h>

bool App_Actuator_Init(void);
void App_Actuator_AllOutputsOff(void);

bool App_RotationMotor_SetSignedDuty(int16_t signed_duty_percent);
bool App_RotationMotor_Coast(void);
bool App_RotationMotor_Brake(void);
int8_t App_RotationMotor_GetSignedDuty(void);

bool App_Magnet_Set(bool on);
bool App_Magnet_IsOn(void);

void App_StatusLed_Set(bool on);
void App_StatusLed_Toggle(void);
bool App_StatusLed_IsOn(void);

void App_Buzzer_Set(bool on);
bool App_Buzzer_IsOn(void);

/*
 * The encoder is intentionally disabled by App_Actuator_Init().
 * Call this function only after PB11/PB14 are physically connected.
 */
bool App_RotationEncoder_Enable(bool reverse_direction);
void App_RotationEncoder_Disable(void);
bool App_RotationEncoder_IsEnabled(void);
int32_t App_RotationEncoder_GetCount(void);
void App_RotationEncoder_Reset(void);
uint8_t App_RotationEncoder_ReadAB(void);

#endif /* APP_ACTUATOR_H */
