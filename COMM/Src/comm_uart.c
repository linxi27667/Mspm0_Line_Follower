/**
 * @file    comm_uart.c
 * @brief   UART通讯层业务逻辑实现（MSPM0G3507）
 */
#include "comm_uart.h"
#include "bsp_common.h"
#include "ti_msp_dl_config.h"

/* ================= 1. 硬件底层函数 (HW_ 前缀) ================= */

#define COMM_UART_RX_BUF_SIZE 256u

static uint8_t s_rx_buf[COMM_UART_RX_BUF_SIZE];
static uint16_t s_rx_idx = 0;
static uint16_t s_rx_timeout_ms = 0;
static bool s_frame_ready = false;

static void HW_UART_Periph_Init(void)
{
    DL_UART_enablePower(UART0);
    DL_UART_reset(UART0);
    DL_GPIO_initPeripheralInputFunction(IOMUX_PINCM22, IOMUX_PINCM22_PF_UART0_RX);
    DL_GPIO_initPeripheralOutputFunction(IOMUX_PINCM21, IOMUX_PINCM21_PF_UART0_TX);

    DL_UART_Config config = {
        .mode = DL_UART_MODE_NORMAL,
        .direction = DL_UART_DIRECTION_TX_RX,
        .flowControl = DL_UART_FLOW_CONTROL_NONE,
        .parity = DL_UART_PARITY_NONE,
        .wordLength = DL_UART_WORD_LENGTH_8_BITS,
        .stopBits = DL_UART_STOP_BITS_ONE,
    };

    DL_UART_init(UART0, &config);
    DL_UART_configBaudRate(UART0, CPUCLK_FREQ, 115200);
    DL_UART_enableInterrupt(UART0, DL_UART_INTERRUPT_RX);
    NVIC_EnableIRQ(UART0_INT_IRQn);
    DL_UART_enable(UART0);
}

void App_UART_Send(const uint8_t *data, uint16_t len)
{
    for (uint16_t i = 0; i < len; i++) {
        DL_UART_transmitDataBlocking(UART0, data[i]);
    }
}

static void HW_UART_Rx_Callback(uint8_t data)
{
    if (s_rx_idx < COMM_UART_RX_BUF_SIZE) {
        s_rx_buf[s_rx_idx++] = data;
        s_rx_timeout_ms = 5;
    }
}

/* ================= 2. 对外业务切入点 ================= */

void App_UART_System_Init(void)
{
    HW_UART_Periph_Init();
}

void App_UART_Task_Run(void)
{
    uint8_t frame_buf[256];
    uint16_t frame_len = 0;

    if (s_rx_timeout_ms > 0) {
        s_rx_timeout_ms--;
        if (s_rx_timeout_ms == 0 && s_rx_idx > 0) {
            s_frame_ready = true;
        }
    }

    if (s_frame_ready && s_rx_idx > 0) {
        frame_len = s_rx_idx;
        if (frame_len >= sizeof(frame_buf)) {
            frame_len = (uint16_t)(sizeof(frame_buf) - 1u);
        }
        for (uint16_t i = 0; i < frame_len; i++) {
            frame_buf[i] = s_rx_buf[i];
        }
        frame_buf[frame_len] = '\0';
        /* 在此编写业务判断逻辑 */
        s_rx_idx = 0;
        s_frame_ready = false;
    }
}

/* UART中断回调 */
void UART0_IRQHandler(void)
{
    uint8_t data = DL_UART_receiveData(UART0);
    HW_UART_Rx_Callback(data);
}
