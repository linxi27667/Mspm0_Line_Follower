/**
 * @file    app_stepper.c
 * @brief   Hardware binding for the X-axis stepper on MSPM0G3507.
 */
#include "app_stepper.h"
#include "bsp_common.h"
#include "main.h"
#include "elog.h"

static volatile uint8_t s_zero_state = 0u;
static uint32_t s_zero_freq_hz = 300u;
static uint32_t s_zero_both_since_ms = 0u;
static bool s_zero_both_pending = false;
static volatile uint32_t s_tima0_irq_seen = 0u;
static volatile uint32_t s_tima1_irq_seen = 0u;
static bool s_stepper_irq_enabled = false;

typedef struct {
    volatile bool active;
    volatile bool pulse_high;
    app_stepper_dual_block_t current_block;
    uint32_t master_steps;
    volatile uint32_t master_index;
    uint32_t dda_denominator;
    uint32_t dda_event_count;
    volatile uint32_t dda_event_index;
    uint8_t amass_level;
    uint32_t stage1_steps;
    uint32_t stage2_steps;
    uint32_t stage1_error;
    uint32_t stage2_error;
    uint32_t high_mask;
    int8_t stage1_position_sign;
    int8_t stage2_position_sign;
    uint32_t nominal_master_freq_hz;
    uint32_t current_master_freq_hz;
    volatile uint32_t exit_master_freq_hz;
} app_stepper_dda_t;

static app_stepper_dda_t s_dda;
static app_stepper_dual_block_t
    s_dual_queue[APP_STEPPER_DUAL_QUEUE_CAPACITY];
static volatile uint32_t s_dual_queue_head = 0u;
static volatile uint32_t s_dual_queue_tail = 0u;
static volatile uint32_t s_dual_queue_completed = 0u;
static volatile int32_t s_dual_stage1_position_steps = 0;
static volatile int32_t s_dual_stage2_position_steps = 0;
static volatile bool s_dual_queue_mode = false;
static uint32_t s_dual_current_freq_hz = 0u;

#define APP_STEPPER_HOME_LIMIT_STABLE_MS (50u)
#define APP_STEPPER_QUEUE_START_FREQ_HZ (40u)
#define APP_STEPPER_QUEUE_ACCEL_STEP_HZ (8u)
#define APP_STEPPER_QUEUE_ACCEL_INTERVAL_STEPS (2u)
#define APP_STEPPER_QUEUE_BRAKE_GUARD_STEPS (2u)
#define APP_STEPPER_JUNCTION_VECTOR_SCALE (1024)
#define APP_STEPPER_JUNCTION_STRAIGHT_PERCENT (9)
#define APP_STEPPER_JUNCTION_GENTLE_PERCENT (36)
#define APP_STEPPER_JUNCTION_MEDIUM_PERCENT (84)
#define APP_STEPPER_AMASS_LEVEL3_MAX_MASTER_HZ (2000u)
#define APP_STEPPER_AMASS_LEVEL2_MAX_MASTER_HZ (4000u)
#define APP_STEPPER_AMASS_LEVEL1_MAX_MASTER_HZ (8000u)

extern volatile uint32_t s_sys_tick;

static void App_Stepper_Enable_Timer_Irq(void)
{
    if (s_stepper_irq_enabled) {
        return;
    }

    DL_Timer_clearInterruptStatus(STEPPER_X_PWM_INST, STEPPER_X_PWM_INT_FLAG);
    DL_TimerA_clearInterruptStatus(STEPPER_Y_PWM_INST, STEPPER_Y_PWM_INT_FLAG);
    NVIC_ClearPendingIRQ(STEPPER_X_PWM_IRQn);
    NVIC_ClearPendingIRQ(STEPPER_Y_PWM_IRQn);
    NVIC_EnableIRQ(STEPPER_X_PWM_IRQn);
    NVIC_EnableIRQ(STEPPER_Y_PWM_IRQn);
    s_stepper_irq_enabled = true;
    elog_i("IRQ", "stepper timer irq enabled x=%d y=%d", STEPPER_X_PWM_IRQn, STEPPER_Y_PWM_IRQn);
}

static void HW_Gpio_Write(void *port, uint32_t pin, uint8_t level)
{
    if (port == NULL) {
        return;
    }

    if (level != 0u) {
        DL_GPIO_setPins((GPIO_Regs *)port, pin);
    } else {
        DL_GPIO_clearPins((GPIO_Regs *)port, pin);
    }
}

static void HW_PWM_Start(void *inst)
{
    if (inst != NULL) {
        DL_Timer_startCounter((GPTIMER_Regs *)inst);
    }
}

static void HW_PWM_Stop(void *inst)
{
    if (inst != NULL) {
        DL_Timer_stopCounter((GPTIMER_Regs *)inst);
    }
}

static void HW_PWM_SetFreq(void *inst, uint32_t freq_hz)
{
    if ((inst == NULL) || (freq_hz == 0u)) {
        elog_w("PWM", "skip set freq inst=%p freq=%u", inst, freq_hz);
        return;
    }

    pwm_params_t p = BSP_PWM_Calc_Params(STEPPER_X_PWM_CLK_FREQ, freq_hz, 50u);
    elog_i("PWM", "set freq=%uHz psc=%u load=%u cc=%u", freq_hz, p.psc, p.load, p.cc);

    DL_Timer_stopCounter((GPTIMER_Regs *)inst);

    DL_Timer_ClockConfig clk_cfg = {
        .clockSel = DL_TIMER_CLOCK_BUSCLK,
        .divideRatio = DL_TIMER_CLOCK_DIVIDE_1,
        .prescale = (uint8_t)p.psc,
    };
    DL_Timer_setClockConfig((GPTIMER_Regs *)inst, &clk_cfg);
    DL_Timer_setLoadValue((GPTIMER_Regs *)inst, p.load);
    DL_Timer_setCaptureCompareValue((GPTIMER_Regs *)inst, p.cc, STEPPER_X_PWM_CC_IDX);
    DL_Timer_setTimerCount((GPTIMER_Regs *)inst, p.load);
}

static void HW_PWM_SetFreq_Y(void *inst, uint32_t freq_hz)
{
    if ((inst == NULL) || (freq_hz == 0u)) {
        elog_w("PWM", "skip set freq Y inst=%p freq=%u", inst, freq_hz);
        return;
    }

    pwm_params_t p = BSP_PWM_Calc_Params(STEPPER_Y_PWM_CLK_FREQ, freq_hz, 50u);
    elog_i("PWM", "set Y freq=%uHz psc=%u load=%u cc=%u", freq_hz, p.psc, p.load, p.cc);

    DL_Timer_stopCounter((GPTIMER_Regs *)inst);

    DL_TimerA_ClockConfig clk_cfg = {
        .clockSel = DL_TIMER_CLOCK_BUSCLK,
        .divideRatio = DL_TIMER_CLOCK_DIVIDE_1,
        .prescale = (uint8_t)p.psc,
    };
    DL_Timer_setClockConfig((GPTIMER_Regs *)inst, &clk_cfg);
    DL_Timer_setLoadValue((GPTIMER_Regs *)inst, p.load);
    DL_Timer_setCaptureCompareValue((GPTIMER_Regs *)inst, p.cc, STEPPER_Y_PWM_CC_IDX);
    DL_Timer_setTimerCount((GPTIMER_Regs *)inst, p.load);
}

static uint32_t App_Stepper_Dual_Queue_Next(uint32_t index)
{
    index++;
    if (index >= APP_STEPPER_DUAL_QUEUE_CAPACITY) {
        index = 0u;
    }
    return index;
}

static uint32_t App_Stepper_Dual_Queue_Previous(uint32_t index)
{
    return (index == 0u) ?
           (APP_STEPPER_DUAL_QUEUE_CAPACITY - 1u) :
           (index - 1u);
}

static uint32_t App_Stepper_Dual_Master_Steps(
    const app_stepper_dual_block_t *block)
{
    return (block->stage1_steps > block->stage2_steps) ?
           block->stage1_steps : block->stage2_steps;
}

/*
 * Match Grbl's AMASS frequency bins.  At low master-step rates the DDA is
 * over-driven by 2/4/8 while the real axis pulse totals remain unchanged.
 * This improves the time placement of the non-dominant joint's pulses.
 */
static uint8_t App_Stepper_Dual_Amass_Level(uint32_t master_freq_hz)
{
#if APP_STEPPER_AMASS_ENABLE
    if (master_freq_hz <=
        APP_STEPPER_AMASS_LEVEL3_MAX_MASTER_HZ) {
        return 3u;
    }
    if (master_freq_hz <=
        APP_STEPPER_AMASS_LEVEL2_MAX_MASTER_HZ) {
        return 2u;
    }
    if (master_freq_hz <=
        APP_STEPPER_AMASS_LEVEL1_MAX_MASTER_HZ) {
        return 1u;
    }
#else
    (void)master_freq_hz;
#endif
    return 0u;
}

static uint32_t App_Stepper_Dual_Amass_Factor(void)
{
    return 1u << s_dda.amass_level;
}

static uint32_t App_Stepper_Dual_Irq_Freq(uint32_t master_freq_hz)
{
    uint32_t factor = App_Stepper_Dual_Amass_Factor();

    if ((master_freq_hz == 0u) ||
        (master_freq_hz >
         (UINT32_MAX / (2u * factor)))) {
        return 0u;
    }
    return master_freq_hz * 2u * factor;
}

static uint32_t App_Stepper_Dual_Min_U32(uint32_t a, uint32_t b)
{
    return (a < b) ? a : b;
}

static uint32_t App_Stepper_Dual_Add_Saturate_U32(uint32_t a,
                                                  uint32_t b)
{
    return (a > (UINT32_MAX - b)) ? UINT32_MAX : (a + b);
}

static uint32_t App_Stepper_Dual_Rate_Change_Capacity(
    uint32_t master_steps)
{
    uint32_t updates =
        master_steps / APP_STEPPER_QUEUE_ACCEL_INTERVAL_STEPS;

    if (updates >
        (UINT32_MAX / APP_STEPPER_QUEUE_ACCEL_STEP_HZ)) {
        return UINT32_MAX;
    }
    return updates * APP_STEPPER_QUEUE_ACCEL_STEP_HZ;
}

static int32_t App_Stepper_Dual_Normalized_Component(
    uint32_t steps, int8_t sign, uint32_t master_steps)
{
    int32_t component;

    if ((steps == 0u) || (master_steps == 0u) ||
        (sign == 0)) {
        return 0;
    }
    component = (int32_t)(((uint64_t)steps *
                          APP_STEPPER_JUNCTION_VECTOR_SCALE) /
                         master_steps);
    return (sign < 0) ? -component : component;
}

static uint64_t App_Stepper_Dual_Abs_I64(int64_t value)
{
    return (value < 0) ? (uint64_t)(-value) :
                         (uint64_t)value;
}

/*
 * Integer joint-space junction limiter derived from the same geometric idea
 * as Grbl's junction-deviation planner. A real joint reversal is always
 * treated as an exact-stop junction. Non-reversing corners retain a
 * progressively smaller fraction of the neighboring nominal rates.
 */
static uint32_t App_Stepper_Dual_Junction_Freq(
    const app_stepper_dual_block_t *previous,
    const app_stepper_dual_block_t *current)
{
    uint32_t previous_master =
        App_Stepper_Dual_Master_Steps(previous);
    uint32_t current_master =
        App_Stepper_Dual_Master_Steps(current);
    uint32_t base_freq =
        App_Stepper_Dual_Min_U32(previous->master_freq_hz,
                                 current->master_freq_hz);
    int32_t previous_stage1;
    int32_t previous_stage2;
    int32_t current_stage1;
    int32_t current_stage2;
    int64_t dot;
    int64_t cross;
    uint64_t scaled_cross;
    uint64_t scaled_dot;
    uint32_t limited_freq;

    if ((previous_master == 0u) || (current_master == 0u)) {
        return APP_STEPPER_QUEUE_START_FREQ_HZ;
    }
    if (((previous->stage1_steps != 0u) &&
         (current->stage1_steps != 0u) &&
         (previous->stage1_position_sign !=
          current->stage1_position_sign)) ||
        ((previous->stage2_steps != 0u) &&
         (current->stage2_steps != 0u) &&
         (previous->stage2_position_sign !=
          current->stage2_position_sign))) {
        return APP_STEPPER_QUEUE_START_FREQ_HZ;
    }

    previous_stage1 = App_Stepper_Dual_Normalized_Component(
        previous->stage1_steps,
        previous->stage1_position_sign,
        previous_master);
    previous_stage2 = App_Stepper_Dual_Normalized_Component(
        previous->stage2_steps,
        previous->stage2_position_sign,
        previous_master);
    current_stage1 = App_Stepper_Dual_Normalized_Component(
        current->stage1_steps,
        current->stage1_position_sign,
        current_master);
    current_stage2 = App_Stepper_Dual_Normalized_Component(
        current->stage2_steps,
        current->stage2_position_sign,
        current_master);

    dot = (int64_t)previous_stage1 * current_stage1 +
          (int64_t)previous_stage2 * current_stage2;
    if (dot <= 0) {
        return APP_STEPPER_QUEUE_START_FREQ_HZ;
    }
    cross = (int64_t)previous_stage1 * current_stage2 -
            (int64_t)previous_stage2 * current_stage1;
    scaled_cross = App_Stepper_Dual_Abs_I64(cross) * 100u;
    scaled_dot = (uint64_t)dot;

    if (scaled_cross <=
        scaled_dot * APP_STEPPER_JUNCTION_STRAIGHT_PERCENT) {
        limited_freq = base_freq;
    } else if (scaled_cross <=
               scaled_dot *
               APP_STEPPER_JUNCTION_GENTLE_PERCENT) {
        limited_freq =
            (uint32_t)(((uint64_t)base_freq * 3u) / 4u);
    } else if (scaled_cross <=
               scaled_dot *
               APP_STEPPER_JUNCTION_MEDIUM_PERCENT) {
        limited_freq = base_freq / 2u;
    } else {
        limited_freq = base_freq / 4u;
    }

    return (limited_freq < APP_STEPPER_QUEUE_START_FREQ_HZ) ?
           APP_STEPPER_QUEUE_START_FREQ_HZ : limited_freq;
}

/*
 * Replan all queued blocks whenever a block is appended. The reverse pass
 * guarantees that every block can decelerate to its exit rate. The forward
 * pass guarantees that the preceding block can accelerate to the same
 * boundary rate. This is a compact, integer version of Grbl's planner passes.
 * Interrupts must be disabled by the caller.
 */
static void App_Stepper_Dual_Replan_Queue_Locked(void)
{
    uint32_t queue_count;
    uint32_t index;
    uint32_t exit_freq = APP_STEPPER_QUEUE_START_FREQ_HZ;
    uint32_t boundary_freq;

    if (s_dual_queue_head >= s_dual_queue_tail) {
        queue_count = s_dual_queue_head -
                      s_dual_queue_tail;
    } else {
        queue_count = APP_STEPPER_DUAL_QUEUE_CAPACITY -
                      (s_dual_queue_tail -
                       s_dual_queue_head);
    }

    index = s_dual_queue_head;
    for (uint32_t count = 0u; count < queue_count; count++) {
        app_stepper_dual_block_t *block;
        uint32_t entry_limit;
        uint32_t rate_capacity;

        index = App_Stepper_Dual_Queue_Previous(index);
        block = &s_dual_queue[index];
        block->planned_exit_freq_hz = exit_freq;
        rate_capacity =
            App_Stepper_Dual_Rate_Change_Capacity(
                App_Stepper_Dual_Master_Steps(block));
        entry_limit =
            App_Stepper_Dual_Add_Saturate_U32(
                exit_freq, rate_capacity);
        block->planned_entry_freq_hz =
            App_Stepper_Dual_Min_U32(
                block->max_entry_freq_hz,
                App_Stepper_Dual_Min_U32(
                    block->master_freq_hz,
                    entry_limit));
        if (block->planned_entry_freq_hz <
            APP_STEPPER_QUEUE_START_FREQ_HZ) {
            block->planned_entry_freq_hz =
                APP_STEPPER_QUEUE_START_FREQ_HZ;
        }
        exit_freq = block->planned_entry_freq_hz;
    }

    if (s_dda.active) {
        uint32_t remaining_steps =
            s_dda.master_steps - s_dda.master_index;
        uint32_t active_exit_limit =
            App_Stepper_Dual_Add_Saturate_U32(
                s_dda.current_master_freq_hz,
                App_Stepper_Dual_Rate_Change_Capacity(
                    remaining_steps));

        boundary_freq =
            App_Stepper_Dual_Min_U32(
                exit_freq,
                App_Stepper_Dual_Min_U32(
                    s_dda.nominal_master_freq_hz,
                    active_exit_limit));
        if (boundary_freq <
            APP_STEPPER_QUEUE_START_FREQ_HZ) {
            boundary_freq =
                APP_STEPPER_QUEUE_START_FREQ_HZ;
        }
        s_dda.exit_master_freq_hz = boundary_freq;
    } else {
        boundary_freq = APP_STEPPER_QUEUE_START_FREQ_HZ;
    }

    index = s_dual_queue_tail;
    for (uint32_t count = 0u; count < queue_count; count++) {
        app_stepper_dual_block_t *block =
            &s_dual_queue[index];
        uint32_t exit_limit;
        uint32_t rate_capacity;

        block->planned_entry_freq_hz =
            App_Stepper_Dual_Min_U32(
                block->planned_entry_freq_hz,
                boundary_freq);
        rate_capacity =
            App_Stepper_Dual_Rate_Change_Capacity(
                App_Stepper_Dual_Master_Steps(block));
        exit_limit =
            App_Stepper_Dual_Add_Saturate_U32(
                block->planned_entry_freq_hz,
                rate_capacity);
        block->planned_exit_freq_hz =
            App_Stepper_Dual_Min_U32(
                block->planned_exit_freq_hz,
                App_Stepper_Dual_Min_U32(
                    block->master_freq_hz,
                    exit_limit));
        if (block->planned_exit_freq_hz <
            APP_STEPPER_QUEUE_START_FREQ_HZ) {
            block->planned_exit_freq_hz =
                APP_STEPPER_QUEUE_START_FREQ_HZ;
        }
        boundary_freq = block->planned_exit_freq_hz;
        index = App_Stepper_Dual_Queue_Next(index);
    }
}

static void App_Stepper_Dual_Set_Freq_Silent(uint32_t irq_freq_hz)
{
    pwm_params_t p;
    DL_Timer_ClockConfig clk_cfg;

    if ((irq_freq_hz == 0u) ||
        (irq_freq_hz == s_dual_current_freq_hz)) {
        return;
    }

    p = BSP_PWM_Calc_Params(STEPPER_X_PWM_CLK_FREQ,
                            irq_freq_hz, 50u);
    DL_Timer_stopCounter(STEPPER_X_PWM_INST);
    clk_cfg.clockSel = DL_TIMER_CLOCK_BUSCLK;
    clk_cfg.divideRatio = DL_TIMER_CLOCK_DIVIDE_1;
    clk_cfg.prescale = (uint8_t)p.psc;
    DL_Timer_setClockConfig(STEPPER_X_PWM_INST, &clk_cfg);
    DL_Timer_setLoadValue(STEPPER_X_PWM_INST, p.load);
    DL_Timer_setCaptureCompareValue(STEPPER_X_PWM_INST, p.cc,
                                   STEPPER_X_PWM_CC_IDX);
    DL_Timer_setTimerCount(STEPPER_X_PWM_INST, p.load);
    s_dual_current_freq_hz = irq_freq_hz;
}

static bool App_Stepper_Dual_Load_Queued_Block(void)
{
    app_stepper_dual_block_t block;
    uint32_t master_steps;
    bool continuing;

    if (s_dual_queue_tail == s_dual_queue_head) {
        return false;
    }

    block = s_dual_queue[s_dual_queue_tail];
    s_dual_queue_tail =
        App_Stepper_Dual_Queue_Next(s_dual_queue_tail);
    master_steps = (block.stage1_steps > block.stage2_steps) ?
                   block.stage1_steps : block.stage2_steps;
    if ((master_steps == 0u) || (block.master_freq_hz == 0u)) {
        return false;
    }
    if (master_steps >
        (UINT32_MAX >> APP_STEPPER_AMASS_MAX_LEVEL)) {
        return false;
    }
    continuing = s_dual_queue_mode && s_dda.active;

    HW_Gpio_Write(App_Stepper_X.dir_pin.port,
                  App_Stepper_X.dir_pin.pin,
                  block.stage1_dir ? 1u : 0u);
    HW_Gpio_Write(App_Stepper_Y.dir_pin.port,
                  App_Stepper_Y.dir_pin.pin,
                  block.stage2_dir ? 1u : 0u);

    App_Stepper_X.step_count = 0u;
    App_Stepper_X.target_steps = block.stage1_steps;
    App_Stepper_X.current_dir = block.stage1_dir ? 1u : 0u;
    App_Stepper_X.running = (block.stage1_steps != 0u);
    App_Stepper_Y.step_count = 0u;
    App_Stepper_Y.target_steps = block.stage2_steps;
    App_Stepper_Y.current_dir = block.stage2_dir ? 1u : 0u;
    App_Stepper_Y.running = (block.stage2_steps != 0u);

    s_dda.current_block = block;
    s_dda.master_steps = master_steps;
    s_dda.master_index = 0u;
    s_dda.amass_level =
        App_Stepper_Dual_Amass_Level(block.master_freq_hz);
    s_dda.dda_denominator =
        master_steps << APP_STEPPER_AMASS_MAX_LEVEL;
    s_dda.dda_event_count =
        master_steps << s_dda.amass_level;
    s_dda.dda_event_index = 0u;
    s_dda.stage1_steps =
        block.stage1_steps <<
        (APP_STEPPER_AMASS_MAX_LEVEL -
         s_dda.amass_level);
    s_dda.stage2_steps =
        block.stage2_steps <<
        (APP_STEPPER_AMASS_MAX_LEVEL -
         s_dda.amass_level);
    s_dda.stage1_error = s_dda.dda_denominator / 2u;
    s_dda.stage2_error = s_dda.dda_denominator / 2u;
    s_dda.high_mask = 0u;
    s_dda.pulse_high = false;
    s_dda.stage1_position_sign = block.stage1_position_sign;
    s_dda.stage2_position_sign = block.stage2_position_sign;
    s_dda.nominal_master_freq_hz = block.master_freq_hz;
    s_dda.exit_master_freq_hz =
        (block.planned_exit_freq_hz <
         APP_STEPPER_QUEUE_START_FREQ_HZ) ?
        APP_STEPPER_QUEUE_START_FREQ_HZ :
        block.planned_exit_freq_hz;
    if (!continuing || (s_dda.current_master_freq_hz == 0u)) {
        s_dda.current_master_freq_hz =
            (block.master_freq_hz <
             APP_STEPPER_QUEUE_START_FREQ_HZ) ?
            block.master_freq_hz :
            APP_STEPPER_QUEUE_START_FREQ_HZ;
    }
    s_dda.active = true;
    s_dual_queue_mode = true;

    App_Stepper_Dual_Set_Freq_Silent(
        App_Stepper_Dual_Irq_Freq(
            s_dda.current_master_freq_hz));
    DL_Timer_startCounter(STEPPER_X_PWM_INST);
    return true;
}

static void App_Stepper_Dual_Update_Rate_From_Irq(void)
{
    uint32_t target_freq;
    uint32_t remaining_steps;
    uint32_t exit_freq;
    uint32_t brake_steps = 0u;

    if (!s_dual_queue_mode ||
        (s_dda.current_master_freq_hz == 0u) ||
        ((s_dda.master_index %
          APP_STEPPER_QUEUE_ACCEL_INTERVAL_STEPS) != 0u)) {
        return;
    }

    remaining_steps = s_dda.master_steps -
                      s_dda.master_index;
    target_freq = s_dda.nominal_master_freq_hz;
    exit_freq = s_dda.exit_master_freq_hz;
    if (exit_freq > target_freq) {
        exit_freq = target_freq;
    }
    if (s_dda.current_master_freq_hz > exit_freq) {
        uint32_t delta =
            s_dda.current_master_freq_hz - exit_freq;
        uint32_t updates =
            (delta + APP_STEPPER_QUEUE_ACCEL_STEP_HZ - 1u) /
            APP_STEPPER_QUEUE_ACCEL_STEP_HZ;

        if (updates >
            ((UINT32_MAX -
              APP_STEPPER_QUEUE_BRAKE_GUARD_STEPS) /
             APP_STEPPER_QUEUE_ACCEL_INTERVAL_STEPS)) {
            brake_steps = UINT32_MAX;
        } else {
            brake_steps =
                updates *
                APP_STEPPER_QUEUE_ACCEL_INTERVAL_STEPS +
                APP_STEPPER_QUEUE_BRAKE_GUARD_STEPS;
        }
    }
    if (remaining_steps <= brake_steps) {
        target_freq = exit_freq;
    }

    if (s_dda.current_master_freq_hz < target_freq) {
        uint32_t next_freq =
            s_dda.current_master_freq_hz +
            APP_STEPPER_QUEUE_ACCEL_STEP_HZ;
        s_dda.current_master_freq_hz =
            (next_freq > target_freq) ?
            target_freq : next_freq;
    } else if (s_dda.current_master_freq_hz > target_freq) {
        uint32_t delta =
            s_dda.current_master_freq_hz - target_freq;
        s_dda.current_master_freq_hz -=
            (delta > APP_STEPPER_QUEUE_ACCEL_STEP_HZ) ?
            APP_STEPPER_QUEUE_ACCEL_STEP_HZ : delta;
    }

    App_Stepper_Dual_Set_Freq_Silent(
        App_Stepper_Dual_Irq_Freq(
            s_dda.current_master_freq_hz));
    DL_Timer_startCounter(STEPPER_X_PWM_INST);
}

static void App_Stepper_Use_Gpio_Step_Pins(void)
{
    DL_Timer_stopCounter(STEPPER_X_PWM_INST);
    DL_Timer_stopCounter(STEPPER_Y_PWM_INST);
    DL_GPIO_initDigitalOutput(GPIO_STEP_C0_IOMUX);
    DL_GPIO_initDigitalOutput(GPIO_STEP2_C0_IOMUX);
    DL_GPIO_enableOutput(GPIOA, STEPPER_X_STEP_PIN | STEPPER_Y_STEP_PIN);
    DL_GPIO_clearPins(GPIOA, STEPPER_X_STEP_PIN | STEPPER_Y_STEP_PIN);
}

static void App_Stepper_Use_Stage1_Pwm_Step_Pin(void)
{
    DL_GPIO_clearPins(GPIOA, STEPPER_X_STEP_PIN);
    DL_GPIO_initPeripheralOutputFunction(GPIO_STEP_C0_IOMUX,
                                         GPIO_STEP_C0_IOMUX_FUNC);
}

static void App_Stepper_Use_Stage2_Pwm_Step_Pin(void)
{
    DL_GPIO_clearPins(GPIOA, STEPPER_Y_STEP_PIN);
    DL_GPIO_initPeripheralOutputFunction(GPIO_STEP2_C0_IOMUX,
                                         GPIO_STEP2_C0_IOMUX_FUNC);
}

static void App_Stepper_Dual_Finish_From_Irq(void)
{
    if (s_dual_queue_mode) {
        s_dual_queue_completed++;
        if (App_Stepper_Dual_Load_Queued_Block()) {
            return;
        }
    }

    DL_Timer_stopCounter(STEPPER_X_PWM_INST);
    DL_GPIO_clearPins(GPIOA, STEPPER_X_STEP_PIN | STEPPER_Y_STEP_PIN);
    s_dda.high_mask = 0u;
    s_dda.pulse_high = false;
    s_dda.active = false;
    s_dda.stage1_position_sign = 0;
    s_dda.stage2_position_sign = 0;
    s_dda.nominal_master_freq_hz = 0u;
    s_dda.current_master_freq_hz = 0u;
    s_dda.exit_master_freq_hz = 0u;
    s_dda.dda_denominator = 0u;
    s_dda.dda_event_count = 0u;
    s_dda.dda_event_index = 0u;
    s_dda.amass_level = 0u;
    s_dual_queue_mode = false;
    s_dual_current_freq_hz = 0u;
    App_Stepper_X.running = false;
    App_Stepper_Y.running = false;
}

static void App_Stepper_Dual_On_Timer(void)
{
    uint32_t high_mask = 0u;

    if (!s_dda.active) {
        return;
    }

    if (s_dda.pulse_high) {
        DL_GPIO_clearPins(GPIOA, s_dda.high_mask);
        s_dda.high_mask = 0u;
        s_dda.pulse_high = false;
        if (s_dda.dda_event_index >=
            s_dda.dda_event_count) {
            App_Stepper_Dual_Finish_From_Irq();
        }
        return;
    }

    s_dda.stage1_error += s_dda.stage1_steps;
    if (s_dda.stage1_error >= s_dda.dda_denominator) {
        s_dda.stage1_error -= s_dda.dda_denominator;
        high_mask |= STEPPER_X_STEP_PIN;
        App_Stepper_X.step_count++;
        s_dual_stage1_position_steps +=
            s_dda.stage1_position_sign;
        s_tima1_irq_seen++;
    }

    s_dda.stage2_error += s_dda.stage2_steps;
    if (s_dda.stage2_error >= s_dda.dda_denominator) {
        s_dda.stage2_error -= s_dda.dda_denominator;
        high_mask |= STEPPER_Y_STEP_PIN;
        App_Stepper_Y.step_count++;
        s_dual_stage2_position_steps +=
            s_dda.stage2_position_sign;
        s_tima0_irq_seen++;
    }

    s_dda.dda_event_index++;
    if ((s_dda.dda_event_index &
         (App_Stepper_Dual_Amass_Factor() - 1u)) == 0u) {
        s_dda.master_index =
            s_dda.dda_event_index >>
            s_dda.amass_level;
        App_Stepper_Dual_Update_Rate_From_Irq();
    }
    s_dda.high_mask = high_mask;
    if (high_mask != 0u) {
        DL_GPIO_setPins(GPIOA, high_mask);
    }
    s_dda.pulse_high = true;
}

static bool HW_Limit_Read(void *port, uint32_t pin)
{
    return (port != NULL) ? (GPIO_ReadPin((GPIO_Regs *)port, pin) != 0u) : false;
}

bsp_stepper_t App_Stepper_X = {
    .dir_pin = {STEPPER_X_DIR_PORT, STEPPER_X_DIR_PIN},
    .pwm_inst = (void *)STEPPER_X_PWM_INST,
    .Gpio_Write = HW_Gpio_Write,
    .PWM_Start = HW_PWM_Start,
    .PWM_Stop = HW_PWM_Stop,
    .PWM_SetFreq = HW_PWM_SetFreq,
    .step_count = 0u,
    .target_steps = 0u,
    .current_dir = 0u,
    .running = false,
};

bsp_stepper_t App_Stepper_Y = {
    .dir_pin = {STEPPER_Y_DIR_PORT, STEPPER_Y_DIR_PIN},
    .pwm_inst = (void *)STEPPER_Y_PWM_INST,
    .Gpio_Write = HW_Gpio_Write,
    .PWM_Start = HW_PWM_Start,
    .PWM_Stop = HW_PWM_Stop,
    .PWM_SetFreq = HW_PWM_SetFreq_Y,
    .step_count = 0u,
    .target_steps = 0u,
    .current_dir = 0u,
    .running = false,
};

static bool HW_Stage1_Limit_Hit(void)
{
    return HW_Limit_Read(LIMIT_STAGE1_PORT, LIMIT_STAGE1_PIN);
}

static bool HW_Stage2_Limit_Hit(void)
{
    return HW_Limit_Read(LIMIT_STAGE2_PORT, LIMIT_STAGE2_PIN);
}

void TIMA1_IRQHandler(void)
{
    if (DL_Timer_getRawInterruptStatus(STEPPER_X_PWM_INST, STEPPER_X_PWM_INT_FLAG) != 0u) {
        DL_Timer_clearInterruptStatus(STEPPER_X_PWM_INST, STEPPER_X_PWM_INT_FLAG);
        if (s_dda.active) {
            App_Stepper_Dual_On_Timer();
            return;
        }
        BSP_Stepper_OnPulse(&App_Stepper_X);
        s_tima1_irq_seen++;
        if ((s_tima1_irq_seen <= 3u) || ((s_tima1_irq_seen % 200u) == 0u)) {
            elog_i("IRQ", "TIMA1 pulse=%u step=%u running=%d",
                   s_tima1_irq_seen, App_Stepper_X.step_count, App_Stepper_X.running);
        }
    }
}

void TIMA0_IRQHandler(void)
{
    if (DL_TimerA_getRawInterruptStatus(STEPPER_Y_PWM_INST, STEPPER_Y_PWM_INT_FLAG) != 0u) {
        DL_TimerA_clearInterruptStatus(STEPPER_Y_PWM_INST, STEPPER_Y_PWM_INT_FLAG);
        if (s_dda.active) {
            return;
        }
        BSP_Stepper_OnPulse(&App_Stepper_Y);
        s_tima0_irq_seen++;
        if ((s_tima0_irq_seen <= 3u) || ((s_tima0_irq_seen % 200u) == 0u)) {
            elog_i("IRQ", "TIMA0 pulse=%u step=%u running=%d",
                   s_tima0_irq_seen, App_Stepper_Y.step_count, App_Stepper_Y.running);
        }
    }
}

void App_Stepper_Stage1_Run(uint8_t dir, uint32_t steps, uint32_t freq_hz)
{
    App_Stepper_Enable_Timer_Irq();
    App_Stepper_Dual_Stop();
    App_Stepper_Use_Stage1_Pwm_Step_Pin();
    elog_i("RUN", "stage1 run dir=%u steps=%u freq=%u lim=%d",
           dir, steps, freq_hz, App_Stepper_Stage1_IsLimitHit());
    BSP_Stepper_Run(&App_Stepper_X, dir, steps, freq_hz);
}

void App_Stepper_Stage2_Run(uint8_t dir, uint32_t steps, uint32_t freq_hz)
{
    App_Stepper_Enable_Timer_Irq();
    App_Stepper_Dual_Stop();
    App_Stepper_Use_Stage2_Pwm_Step_Pin();
    elog_i("RUN", "stage2 run dir=%u steps=%u freq=%u lim=%d",
           dir, steps, freq_hz, App_Stepper_Stage2_IsLimitHit());
    BSP_Stepper_Run(&App_Stepper_Y, dir, steps, freq_hz);
}

bool App_Stepper_Dual_Run(uint8_t stage1_dir, uint32_t stage1_steps,
                          uint8_t stage2_dir, uint32_t stage2_steps,
                          uint32_t master_freq_hz)
{
    uint32_t master_steps = (stage1_steps > stage2_steps) ?
                            stage1_steps : stage2_steps;

    if ((master_steps == 0u) || (master_freq_hz == 0u) ||
        (master_freq_hz > (UINT32_MAX / 2u))) {
        return false;
    }

    App_Stepper_Enable_Timer_Irq();
    App_Stepper_Dual_Stop();
    BSP_Stepper_Stop(&App_Stepper_X);
    BSP_Stepper_Stop(&App_Stepper_Y);
    DL_Timer_clearInterruptStatus(STEPPER_X_PWM_INST,
                                  STEPPER_X_PWM_INT_FLAG);
    DL_TimerA_clearInterruptStatus(STEPPER_Y_PWM_INST,
                                   STEPPER_Y_PWM_INT_FLAG);
    NVIC_ClearPendingIRQ(STEPPER_X_PWM_IRQn);
    NVIC_ClearPendingIRQ(STEPPER_Y_PWM_IRQn);
    App_Stepper_Use_Gpio_Step_Pins();

    HW_Gpio_Write(App_Stepper_X.dir_pin.port, App_Stepper_X.dir_pin.pin,
                  stage1_dir ? 1u : 0u);
    HW_Gpio_Write(App_Stepper_Y.dir_pin.port, App_Stepper_Y.dir_pin.pin,
                  stage2_dir ? 1u : 0u);

    App_Stepper_X.step_count = 0u;
    App_Stepper_X.target_steps = stage1_steps;
    App_Stepper_X.current_dir = stage1_dir ? 1u : 0u;
    App_Stepper_X.running = (stage1_steps != 0u);
    App_Stepper_Y.step_count = 0u;
    App_Stepper_Y.target_steps = stage2_steps;
    App_Stepper_Y.current_dir = stage2_dir ? 1u : 0u;
    App_Stepper_Y.running = (stage2_steps != 0u);

    s_dda.current_block =
        (app_stepper_dual_block_t){0};
    s_dda.current_block.stage1_dir = stage1_dir;
    s_dda.current_block.stage2_dir = stage2_dir;
    s_dda.current_block.stage1_steps = stage1_steps;
    s_dda.current_block.stage2_steps = stage2_steps;
    s_dda.current_block.master_freq_hz =
        master_freq_hz;
    s_dda.master_steps = master_steps;
    s_dda.master_index = 0u;
    s_dda.dda_denominator =
        master_steps << APP_STEPPER_AMASS_MAX_LEVEL;
    s_dda.dda_event_count = master_steps;
    s_dda.dda_event_index = 0u;
    s_dda.amass_level = 0u;
    s_dda.stage1_steps =
        stage1_steps << APP_STEPPER_AMASS_MAX_LEVEL;
    s_dda.stage2_steps =
        stage2_steps << APP_STEPPER_AMASS_MAX_LEVEL;
    s_dda.stage1_error = s_dda.dda_denominator / 2u;
    s_dda.stage2_error = s_dda.dda_denominator / 2u;
    s_dda.high_mask = 0u;
    s_dda.pulse_high = false;
    s_dda.stage1_position_sign = 0;
    s_dda.stage2_position_sign = 0;
    s_dda.nominal_master_freq_hz = master_freq_hz;
    s_dda.current_master_freq_hz = master_freq_hz;
    s_dda.exit_master_freq_hz = master_freq_hz;
    s_dda.active = true;
    s_dual_queue_mode = false;
    s_dual_current_freq_hz = master_freq_hz * 2u;

    HW_PWM_SetFreq(STEPPER_X_PWM_INST, master_freq_hz * 2u);
    DL_Timer_clearInterruptStatus(STEPPER_X_PWM_INST,
                                  STEPPER_X_PWM_INT_FLAG);
    NVIC_ClearPendingIRQ(STEPPER_X_PWM_IRQn);
    DL_Timer_startCounter(STEPPER_X_PWM_INST);

    elog_i("DDA", "dual start s1=%u d1=%u s2=%u d2=%u master=%u freq=%u irq=%u",
           stage1_steps, stage1_dir, stage2_steps, stage2_dir,
           master_steps, master_freq_hz, master_freq_hz * 2u);
    return true;
}

bool App_Stepper_Dual_Queue_Block(
    const app_stepper_dual_block_t *block)
{
    app_stepper_dual_block_t planned_block;
    const app_stepper_dual_block_t *previous_block = NULL;
    uint32_t next_head;
    uint32_t irq_state;
    uint32_t master_steps;
    bool start_required;

    if (block == NULL) {
        return false;
    }
    planned_block = *block;
    master_steps = (block->stage1_steps > block->stage2_steps) ?
                   block->stage1_steps : block->stage2_steps;
    if ((master_steps == 0u) ||
        (block->master_freq_hz == 0u) ||
        (block->master_freq_hz > (UINT32_MAX / 2u)) ||
        ((block->stage1_steps != 0u) &&
         (block->stage1_position_sign != -1) &&
         (block->stage1_position_sign != 1)) ||
        ((block->stage2_steps != 0u) &&
         (block->stage2_position_sign != -1) &&
         (block->stage2_position_sign != 1))) {
        return false;
    }

    irq_state = __get_PRIMASK();
    __disable_irq();
    next_head = App_Stepper_Dual_Queue_Next(
        s_dual_queue_head);
    if (next_head == s_dual_queue_tail) {
        if (irq_state == 0u) {
            __enable_irq();
        }
        return false;
    }

    if (s_dual_queue_head != s_dual_queue_tail) {
        previous_block =
            &s_dual_queue[
                App_Stepper_Dual_Queue_Previous(
                    s_dual_queue_head)];
    } else if (s_dda.active) {
        previous_block = &s_dda.current_block;
    }

    planned_block.max_entry_freq_hz =
        (previous_block != NULL) ?
        App_Stepper_Dual_Junction_Freq(
            previous_block, &planned_block) :
        APP_STEPPER_QUEUE_START_FREQ_HZ;
    planned_block.planned_entry_freq_hz =
        APP_STEPPER_QUEUE_START_FREQ_HZ;
    planned_block.planned_exit_freq_hz =
        APP_STEPPER_QUEUE_START_FREQ_HZ;
    s_dual_queue[s_dual_queue_head] = planned_block;
    s_dual_queue_head = next_head;
    App_Stepper_Dual_Replan_Queue_Locked();
    start_required = !s_dda.active;
    if (start_required) {
        App_Stepper_Enable_Timer_Irq();
        App_Stepper_Use_Gpio_Step_Pins();
        (void)App_Stepper_Dual_Load_Queued_Block();
    }
    if (irq_state == 0u) {
        __enable_irq();
    }
    return true;
}

uint32_t App_Stepper_Dual_Queue_Count(void)
{
    uint32_t head = s_dual_queue_head;
    uint32_t tail = s_dual_queue_tail;

    if (head >= tail) {
        return head - tail;
    }
    return APP_STEPPER_DUAL_QUEUE_CAPACITY -
           (tail - head);
}

uint32_t App_Stepper_Dual_Queue_Free(void)
{
    return (APP_STEPPER_DUAL_QUEUE_CAPACITY - 1u) -
           App_Stepper_Dual_Queue_Count();
}

uint32_t App_Stepper_Dual_Queue_Completed(void)
{
    return s_dual_queue_completed;
}

void App_Stepper_Dual_Queue_Set_Position(int32_t stage1_steps,
                                         int32_t stage2_steps)
{
    uint32_t irq_state = __get_PRIMASK();

    __disable_irq();
    if (!s_dda.active) {
        s_dual_stage1_position_steps = stage1_steps;
        s_dual_stage2_position_steps = stage2_steps;
        s_dual_queue_completed = 0u;
    }
    if (irq_state == 0u) {
        __enable_irq();
    }
}

void App_Stepper_Dual_Queue_Get_Position(int32_t *stage1_steps,
                                         int32_t *stage2_steps)
{
    uint32_t irq_state = __get_PRIMASK();

    __disable_irq();
    if (stage1_steps != NULL) {
        *stage1_steps = s_dual_stage1_position_steps;
    }
    if (stage2_steps != NULL) {
        *stage2_steps = s_dual_stage2_position_steps;
    }
    if (irq_state == 0u) {
        __enable_irq();
    }
}

void App_Stepper_Dual_Queue_Clear(void)
{
    App_Stepper_Dual_Stop();
}

bool App_Stepper_Dual_Queue_IsBusy(void)
{
    return s_dda.active ||
           (s_dual_queue_head != s_dual_queue_tail);
}

void App_Stepper_Dual_Stop(void)
{
    /*
     * Legacy homing calls this before every independent one-pulse move.
     * When the DDA queue is idle, touching the shared timer or both running
     * flags here would make the two homing axes cancel each other.
     */
    if (!s_dda.active &&
        !s_dual_queue_mode &&
        (s_dual_queue_head == s_dual_queue_tail)) {
        return;
    }

    DL_Timer_stopCounter(STEPPER_X_PWM_INST);
    DL_GPIO_clearPins(GPIOA, STEPPER_X_STEP_PIN | STEPPER_Y_STEP_PIN);
    s_dda.high_mask = 0u;
    s_dda.pulse_high = false;
    s_dda.active = false;
    s_dda.stage1_position_sign = 0;
    s_dda.stage2_position_sign = 0;
    s_dda.nominal_master_freq_hz = 0u;
    s_dda.current_master_freq_hz = 0u;
    s_dda.exit_master_freq_hz = 0u;
    s_dda.dda_denominator = 0u;
    s_dda.dda_event_count = 0u;
    s_dda.dda_event_index = 0u;
    s_dda.amass_level = 0u;
    s_dual_queue_head = 0u;
    s_dual_queue_tail = 0u;
    s_dual_queue_mode = false;
    s_dual_current_freq_hz = 0u;
    App_Stepper_X.running = false;
    App_Stepper_Y.running = false;
}

bool App_Stepper_Dual_IsRunning(void)
{
    return s_dda.active;
}

void App_Stepper_Stage1_Stop(void)
{
    if (s_dda.active) {
        App_Stepper_Dual_Stop();
        return;
    }
    BSP_Stepper_Stop(&App_Stepper_X);
}

void App_Stepper_Stage2_Stop(void)
{
    if (s_dda.active) {
        App_Stepper_Dual_Stop();
        return;
    }
    BSP_Stepper_Stop(&App_Stepper_Y);
}

bool App_Stepper_Stage1_IsLimitHit(void)
{
    return HW_Stage1_Limit_Hit();
}

bool App_Stepper_Stage2_IsLimitHit(void)
{
    return HW_Stage2_Limit_Hit();
}

uint32_t App_Stepper_Stage1_Total_Pulses(void)
{
    return s_tima1_irq_seen;
}

uint32_t App_Stepper_Stage2_Total_Pulses(void)
{
    return s_tima0_irq_seen;
}

void App_Stepper_Zero_All(void)
{
    App_Stepper_Zero_All_At_Freq(300u);
}

void App_Stepper_Zero_All_At_Freq(uint32_t freq_hz)
{
    s_zero_freq_hz = (freq_hz == 0u) ? 1u : freq_hz;
    s_zero_state = 1u;
    s_zero_both_since_ms = 0u;
    s_zero_both_pending = false;

    if (App_Stepper_Stage1_IsLimitHit()) {
        BSP_Stepper_Stop(&App_Stepper_X);
        App_Stepper_X.step_count = 0u;
    }
    if (App_Stepper_Stage2_IsLimitHit()) {
        BSP_Stepper_Stop(&App_Stepper_Y);
        App_Stepper_Y.step_count = 0u;
    }
}

bool App_Stepper_IsZeroing(void)
{
    return (s_zero_state != 0u);
}

void App_Stepper_Cancel_Zeroing(void)
{
    s_zero_state = 0u;
    s_zero_both_since_ms = 0u;
    s_zero_both_pending = false;
    App_Stepper_Stage1_Stop();
    App_Stepper_Stage2_Stop();
}

void App_Stepper_Task(void)
{
    bool stage1_limit;
    bool stage2_limit;

    if (App_Stepper_Stage2_IsLimitHit() &&
        BSP_Stepper_IsRunning(&App_Stepper_Y) &&
        (App_Stepper_Y.current_dir == LIMIT_STAGE2_HOME_DIR)) {
        elog_w("HOME", "stage2 limit stop dir=%u home_dir=%u zero_state=%u",
               App_Stepper_Y.current_dir,
               LIMIT_STAGE2_HOME_DIR,
               s_zero_state);
        App_Stepper_Stage2_Stop();
        App_Stepper_Y.step_count = 0u;
    }

    if (App_Stepper_Stage1_IsLimitHit() &&
        BSP_Stepper_IsRunning(&App_Stepper_X) &&
        (App_Stepper_X.current_dir == LIMIT_STAGE1_HOME_DIR)) {
        elog_w("HOME", "stage1 limit stop dir=%u home_dir=%u zero_state=%u",
               App_Stepper_X.current_dir,
               LIMIT_STAGE1_HOME_DIR,
               s_zero_state);
        App_Stepper_Stage1_Stop();
        App_Stepper_X.step_count = 0u;
    }

    if (s_zero_state == 0u) {
        return;
    }

    stage1_limit = App_Stepper_Stage1_IsLimitHit();
    stage2_limit = App_Stepper_Stage2_IsLimitHit();
    if (stage1_limit && stage2_limit) {
        if (!BSP_Stepper_IsRunning(&App_Stepper_X) &&
            !BSP_Stepper_IsRunning(&App_Stepper_Y)) {
            if (!s_zero_both_pending) {
                s_zero_both_pending = true;
                s_zero_both_since_ms = s_sys_tick;
                elog_i("HOME", "both limits active; confirming stable=%ums",
                       APP_STEPPER_HOME_LIMIT_STABLE_MS);
            } else if ((uint32_t)(s_sys_tick - s_zero_both_since_ms) >=
                       APP_STEPPER_HOME_LIMIT_STABLE_MS) {
                App_Stepper_X.step_count = 0u;
                App_Stepper_Y.step_count = 0u;
                s_zero_state = 0u;
                s_zero_both_pending = false;
                elog_i("HOME", "both limits stable; zero complete");
            }
        }
        return;
    }

    s_zero_both_pending = false;
    if (!BSP_Stepper_IsRunning(&App_Stepper_X) && !stage1_limit) {
        App_Stepper_Stage1_Run(LIMIT_STAGE1_HOME_DIR, 1u, s_zero_freq_hz);
    }
    if (!BSP_Stepper_IsRunning(&App_Stepper_Y) && !stage2_limit) {
        App_Stepper_Stage2_Run(LIMIT_STAGE2_HOME_DIR, 1u, s_zero_freq_hz);
    }
}
