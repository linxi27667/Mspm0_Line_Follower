/**
 * @file    bsp_uart.c
 * @brief   UART 不定长接收实现（MSPM0，中断 + 超时截断）
 */
#include "bsp_uart.h"
#include "bsp_common.h"

#include <ti/driverlib/driverlib.h>
#include <ti/devices/msp/msp.h>

/* 使用 UART0 实例 */
#define BSP_UART_PERIPH   UART0

static uint8_t  s_rx_buf[BSP_UART_RX_BUF_SIZE];
static uint16_t s_rx_idx  = 0;
static uint16_t s_rx_timeout_ms = 0;
static bool     s_frame_ready = false;
static uint8_t  s_rx_temp = 0;

/* ================= 1. 硬件初始化（底层函数以 HW_ 前缀） ================= */

static void HW_UART_Periph_Init(void)
{
    /* 使能 UART0 时钟与 GPIO */
    DL_UART_enablePower(BSP_UART_PERIPH);
    DL_UART_reset(BSP_UART_PERIPH);

    DL_UART_Main_enablePower(GPIOA);

    DL_UART_initUARTConfig(BSP_UART_PERIPH);

    /* 波特率 115200, 8N1 */
    DL_UART_Main_setBaudRate(BSP_UART_PERIPH,
        DL_UART_Main_calcClockDivider(SYSCTL_UART_CLK_FREQ_HZ, 115200, SYSCTL_UART_CLK_FREQ_HZ));

    /* 配置 UART0 引脚: PA2(UART0_RX), PA3(UART0_TX) */
    DL_GPIO_initPeripheralInputFunction(GPIOA, GPIO_PIN_2, GPIO_PIN_MUX_UART0_RX);
    DL_GPIO_initPeripheralOutputFunction(GPIOA, GPIO_PIN_3, GPIO_PIN_MUX_UART0_TX);

    /* 使能 RX 中断 */
    DL_UART_Main_enableInterrupt(BSP_UART_PERIPH,
        DL_UART_INTERRUPT_RX | DL_UART_INTERRUPT_IDLE);

    DL_UART_enableInterrupt(BSP_UART_PERIPH, DL_UART_INTERRUPT_RX);

    DL_UART_Main_enable(BSP_UART_PERIPH);

    /* 开启 NVIC */
    NVIC_EnableIRQ(UART0_INT_IRQn);
}

/* ================= 2. 核心初始化 ================= */

void BSP_UART_Init(void)
{
    HW_UART_Periph_Init();
}

/* ================= 3. 发送接口 ================= */

void BSP_UART_Send(const uint8_t *data, uint16_t len)
{
    for (uint16_t i = 0; i < len; i++) {
        while (!DL_UART_isTXFIFOEmpty(BSP_UART_PERIPH)) { }
        DL_UART_Main_transmitData(BSP_UART_PERIPH, data[i]);
    }
}

/* ================= 4. 接收钩子函数 ================= */

void BSP_UART_RxCallback(uint8_t data)
{
    if (s_rx_idx < BSP_UART_RX_BUF_SIZE) {
        s_rx_buf[s_rx_idx++] = data;
        s_rx_timeout_ms = 5;   /* 5ms 超时判定一帧结束 */
    }
}

void BSP_UART_Timeout_Tick(void)
{
    if (s_rx_timeout_ms > 0) {
        s_rx_timeout_ms--;
        if (s_rx_timeout_ms == 0 && s_rx_idx > 0) {
            s_frame_ready = true;
        }
    }
}

/* ================= 5. APP 拉取接口 ================= */

bool BSP_UART_Get_Frame(uint8_t *out_buf, uint16_t *out_len)
{
    if (s_frame_ready) {
        *out_len = s_rx_idx;
        for (uint16_t i = 0; i < s_rx_idx; i++) out_buf[i] = s_rx_buf[i];
        s_rx_idx = 0;
        s_frame_ready = false;
        return true;
    }
    return false;
}

/* ================= 6. UART0 中断服务函数 ================= */

void UART0_INT_IRQHandler(void)
{
    uint32_t int_status = DL_UART_Main_getEnabledInterruptStatus(BSP_UART_PERIPH);

    if (int_status & DL_UART_INTERRUPT_RX) {
        while (DL_UART_isRXFIFOEmpty(BSP_UART_PERIPH) == false) {
            uint8_t ch = (uint8_t)DL_UART_Main_receiveData(BSP_UART_PERIPH);
            BSP_UART_RxCallback(ch);
        }
    }
}
