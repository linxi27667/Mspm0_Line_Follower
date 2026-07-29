/**
 * @file    comm_vision_uart.c
 * @brief   瑙嗚閫氫俊涓插彛瀹炵幇 (UART1: PB4=TX, PB5=RX)
 *          涓庤瑙夋ā鍧?OpenMV/K210绛?鍏ㄦ椂鍙屽伐閫氫俊
 */
#include "comm_vision_uart.h"
#include "bsp_common.h"
#include "ti_msp_dl_config.h"
#include "writer_test.h"
#include "elog.h"

#if ((VISION_UART_RX_RING_SIZE & (VISION_UART_RX_RING_SIZE - 1u)) != 0u) || \
    ((VISION_UART_TX_RING_SIZE & (VISION_UART_TX_RING_SIZE - 1u)) != 0u)
#error "UART ring sizes must be powers of two"
#endif

/* ================= 1. 纭欢搴曞眰鍑芥暟 (HW_ 鍓嶇紑) ================= */

static uint8_t s_vision_rx_ring[VISION_UART_RX_RING_SIZE];
static uint8_t s_vision_tx_ring[VISION_UART_TX_RING_SIZE];
static volatile uint16_t s_vision_rx_head = 0u;
static volatile uint16_t s_vision_rx_tail = 0u;
static uint16_t s_vision_tx_head = 0u;
static uint16_t s_vision_tx_tail = 0u;
static volatile uint32_t s_vision_rx_dropped = 0u;
static uint32_t s_vision_tx_rejected = 0u;
static uint32_t s_vision_rx_dropped_reported = 0u;
static uint32_t s_vision_tx_rejected_reported = 0u;

extern volatile uint32_t s_sys_tick;

static void App_Vision_UART_Log_Local_Frame(const char *direction,
                                            const uint8_t *data,
                                            uint16_t len)
{
    char preview[97u];
    uint16_t input_index;
    uint16_t output_index = 0u;
    bool truncated = false;

    if ((direction == NULL) || (data == NULL)) {
        return;
    }
    for (input_index = 0u; input_index < len; input_index++) {
        uint8_t value = data[input_index];

        if ((value == '\r') || (value == '\n')) {
            if (output_index > (uint16_t)(sizeof(preview) - 3u)) {
                truncated = true;
                break;
            }
            preview[output_index++] = '\\';
            preview[output_index++] = (value == '\r') ? 'r' : 'n';
        } else {
            if (output_index >= (uint16_t)(sizeof(preview) - 1u)) {
                truncated = true;
                break;
            }
            preview[output_index++] =
                ((value >= 0x20u) && (value <= 0x7Eu)) ?
                    (char)value : '.';
        }
    }
    preview[output_index] = '\0';
    if (input_index < len) {
        truncated = true;
    }
    elog_i("UART_IO", "uart=UART1 dir=%s mode=local bytes=%u "
           "data=\"%s\" truncated=%u",
           direction, len, preview, truncated ? 1u : 0u);
}

static void HW_Vision_UART_Periph_Init(void)
{
    static const DL_UART_ClockConfig clock_config = {
        .clockSel = DL_UART_CLOCK_BUSCLK,
        .divideRatio = DL_UART_CLOCK_DIVIDE_RATIO_1,
    };
    DL_GPIO_reset(GPIOB);
    DL_UART_reset(VISION_UART_INST);
    DL_GPIO_enablePower(GPIOB);
    DL_UART_enablePower(VISION_UART_INST);
    delay_cycles(POWER_STARTUP_DELAY);

    DL_GPIO_initPeripheralOutputFunction(VISION_UART_TX_IOMUX, VISION_UART_TX_IOMUX_FUNC);
    DL_GPIO_initPeripheralInputFunction(VISION_UART_RX_IOMUX, VISION_UART_RX_IOMUX_FUNC);
    DL_UART_setClockConfig(VISION_UART_INST,
                           (DL_UART_ClockConfig *)&clock_config);

    DL_UART_Config config = {
        .mode = DL_UART_MODE_NORMAL,
        .direction = DL_UART_DIRECTION_TX_RX,
        .flowControl = DL_UART_FLOW_CONTROL_NONE,
        .parity = DL_UART_PARITY_NONE,
        .wordLength = DL_UART_WORD_LENGTH_8_BITS,
        .stopBits = DL_UART_STOP_BITS_ONE,
    };

    DL_UART_init(VISION_UART_INST, &config);
    DL_UART_configBaudRate(VISION_UART_INST, CPUCLK_FREQ, VISION_UART_BAUDRATE);
    DL_UART_enableFIFOs(VISION_UART_INST);
    DL_UART_setRXFIFOThreshold(VISION_UART_INST,
                               DL_UART_RX_FIFO_LEVEL_ONE_ENTRY);
    DL_UART_setTXFIFOThreshold(VISION_UART_INST,
                               DL_UART_TX_FIFO_LEVEL_EMPTY);
    DL_UART_enableInterrupt(VISION_UART_INST, DL_UART_INTERRUPT_RX);
    NVIC_ClearPendingIRQ(UART1_INT_IRQn);
    NVIC_EnableIRQ(UART1_INT_IRQn);
    DL_UART_enable(VISION_UART_INST);
}

static void HW_Vision_UART_Rx_Callback(uint8_t data)
{
    uint16_t next =
        (uint16_t)((s_vision_rx_head + 1u) &
                   (VISION_UART_RX_RING_SIZE - 1u));

    if (next == s_vision_rx_tail) {
        s_vision_rx_dropped++;
        return;
    }
    s_vision_rx_ring[s_vision_rx_head] = data;
    s_vision_rx_head = next;
}

static uint32_t HW_Vision_UART_Drain_Rx_FIFO(void)
{
    uint32_t count = 0u;

    while (!DL_UART_isRXFIFOEmpty(VISION_UART_INST)) {
        HW_Vision_UART_Rx_Callback(
            DL_UART_receiveData(VISION_UART_INST));
        count++;
    }
    return count;
}

/* ================= 2. 瀵瑰涓氬姟鍒囧叆鐐?================= */

void App_Vision_UART_Init(void)
{
    s_vision_rx_head = 0u;
    s_vision_rx_tail = 0u;
    s_vision_tx_head = 0u;
    s_vision_tx_tail = 0u;
    s_vision_rx_dropped = 0u;
    s_vision_tx_rejected = 0u;
    s_vision_rx_dropped_reported = 0u;
    s_vision_tx_rejected_reported = 0u;
    HW_Vision_UART_Periph_Init();
    elog_i("UART", "[UART] UART1 ready tx=PB4 rx=PB5 baud=%u "
           "rx_ring=%u tx_ring=%u",
           VISION_UART_BAUDRATE,
           VISION_UART_RX_RING_SIZE,
           VISION_UART_TX_RING_SIZE);
}

void App_Vision_UART_Send(const uint8_t *data, uint16_t len)
{
    uint16_t index;

    if (data == NULL) {
        return;
    }
    App_Vision_UART_Log_Local_Frame("TX", data, len);
    for (index = 0u; index < len; index++) {
        DL_UART_transmitDataBlocking(VISION_UART_INST, data[index]);
    }
}

bool App_Vision_UART_Try_Send(const uint8_t *data, uint16_t len)
{
    uint16_t used;
    uint16_t free_count;
    uint16_t index;

    if ((data == NULL) || (len == 0u)) {
        return false;
    }
    used = (uint16_t)((s_vision_tx_head - s_vision_tx_tail) &
                      (VISION_UART_TX_RING_SIZE - 1u));
    free_count = (uint16_t)(VISION_UART_TX_RING_SIZE - 1u - used);
    if (len > free_count) {
        s_vision_tx_rejected++;
        return false;
    }
    for (index = 0u; index < len; index++) {
        s_vision_tx_ring[s_vision_tx_head] = data[index];
        s_vision_tx_head =
            (uint16_t)((s_vision_tx_head + 1u) &
                       (VISION_UART_TX_RING_SIZE - 1u));
    }
    return true;
}

uint16_t App_Vision_UART_Read(uint8_t *data, uint16_t capacity)
{
    uint16_t count = 0u;

    if (data == NULL) {
        return 0u;
    }
    while ((count < capacity) &&
           (s_vision_rx_tail != s_vision_rx_head)) {
        data[count++] = s_vision_rx_ring[s_vision_rx_tail];
        s_vision_rx_tail =
            (uint16_t)((s_vision_rx_tail + 1u) &
                       (VISION_UART_RX_RING_SIZE - 1u));
    }
    return count;
}

void App_Vision_UART_Service(void)
{
    uint8_t budget = 16u;
    uint32_t rx_dropped;
    uint32_t tx_rejected;

    while ((s_vision_tx_tail != s_vision_tx_head) && (budget > 0u)) {
        if (!DL_UART_transmitDataCheck(
                VISION_UART_INST,
                s_vision_tx_ring[s_vision_tx_tail])) {
            break;
        }
        s_vision_tx_tail =
            (uint16_t)((s_vision_tx_tail + 1u) &
                       (VISION_UART_TX_RING_SIZE - 1u));
        budget--;
    }

    rx_dropped = s_vision_rx_dropped;
    if (rx_dropped != s_vision_rx_dropped_reported) {
        elog_e("UART_ERR", "uart=UART1 fault=rx_ring_overflow "
               "new_drops=%lu total_drops=%lu",
               (unsigned long)(rx_dropped - s_vision_rx_dropped_reported),
               (unsigned long)rx_dropped);
        s_vision_rx_dropped_reported = rx_dropped;
    }
    tx_rejected = s_vision_tx_rejected;
    if (tx_rejected != s_vision_tx_rejected_reported) {
        elog_w("UART_ERR", "uart=UART1 condition=tx_ring_backpressure "
               "result=deferred new_rejects=%lu total_rejects=%lu",
               (unsigned long)(tx_rejected - s_vision_tx_rejected_reported),
               (unsigned long)tx_rejected);
        s_vision_tx_rejected_reported = tx_rejected;
    }
}

void App_Vision_UART_Task(void)
{
    static uint8_t frame[192u];
    static uint16_t frame_len = 0u;
    static bool discard_frame = false;
    static uint32_t last_rx_ms = 0u;
    uint8_t rx_chunk[32u];
    uint16_t count;
    uint16_t index;

    App_Vision_UART_Service();
    count = App_Vision_UART_Read(rx_chunk, sizeof(rx_chunk));
    if (count > 0u) {
        last_rx_ms = s_sys_tick;
    }
    for (index = 0u; index < count; index++) {
        uint8_t data = rx_chunk[index];

        if ((data == '\r') || (data == '\n')) {
            if (!discard_frame && (frame_len > 0u)) {
                App_Vision_UART_Log_Local_Frame("RX", frame, frame_len);
                (void)WriterTest_Process_Serial_Frame(frame, frame_len);
            }
            frame_len = 0u;
            discard_frame = false;
            continue;
        }
        if (discard_frame) {
            continue;
        }
        if (frame_len >= sizeof(frame) - 1u) {
            elog_e("UART_ERR", "uart=UART1 fault=local_frame_too_long "
                   "capacity=%u", (uint32_t)sizeof(frame));
            frame_len = 0u;
            discard_frame = true;
            continue;
        }
        frame[frame_len++] = data;
    }
    if ((count == 0u) && (frame_len > 0u) &&
        ((uint32_t)(s_sys_tick - last_rx_ms) >= 5u)) {
        if (!discard_frame) {
            App_Vision_UART_Log_Local_Frame("RX", frame, frame_len);
            (void)WriterTest_Process_Serial_Frame(frame, frame_len);
        }
        frame_len = 0u;
        discard_frame = false;
    }
}

uint32_t App_Vision_UART_Get_Rx_Dropped(void)
{
    return s_vision_rx_dropped;
}

uint32_t App_Vision_UART_Get_Tx_Rejected(void)
{
    return s_vision_tx_rejected;
}

/* ================= 3. UART1 涓柇鍥炶皟 ================= */

void UART1_IRQHandler(void)
{
    (void)HW_Vision_UART_Drain_Rx_FIFO();
}
