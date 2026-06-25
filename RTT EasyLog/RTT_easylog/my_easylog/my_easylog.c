#include "my_easylog.h"
#include "bsp_common.h"
#include <stdio.h>
#include <stdarg.h>

/* ---------- 静态状态 ---------- */

static log_level_t g_log_level = MYLOG_DEFAULT_LEVEL;
static bool        g_color     = MYLOG_DEFAULT_COLOR;

/* IWAE 四级标签 */
static const char * const s_level_str[] = {
    [LOG_LVL_ASSERT]  = "A",
    [LOG_LVL_ERROR]   = "E",
    [LOG_LVL_WARN]    = "W",
    [LOG_LVL_INFO]    = "I",
};

static const char * const s_level_clr[] = {
    [LOG_LVL_ASSERT]  = _MYLOG_CLR_A,
    [LOG_LVL_ERROR]   = _MYLOG_CLR_E,
    [LOG_LVL_WARN]    = _MYLOG_CLR_W,
    [LOG_LVL_INFO]    = _MYLOG_CLR_I,
};

/* ---------- 公共 API ---------- */

void my_log_init(void)
{
    g_log_level = MYLOG_DEFAULT_LEVEL;
    g_color     = MYLOG_DEFAULT_COLOR;
}

void my_log_set_level(log_level_t level)
{
    g_log_level = level;
}

void my_log_set_color(bool enable)
{
    g_color = enable;
}

/* ---------- 核心输出 ---------- */

#if MYLOG_ENABLED

/* systick_ms 通过 bsp_common.h 的 extern 声明访问 */

void my_log_write(log_level_t level, const char *tag, const char *fmt, ...)
{
    if (level > g_log_level) {
        return;
    }

    char buf[MYLOG_BUF_SIZE];
    int  n = 0;

    /* 简洁格式: \x1B[2;32m[I TAG]\x1B[0m message\r\n
     * - 颜色只包裹级别+TAG头部，message保持默认色，便于阅读
     * - 去掉 tick 时间戳（调试时可单独打印，常规运行无需）
     * - 去掉重复的 [[TAG]] 结构 */
    if (g_color) {
        n += snprintf(buf + n, sizeof(buf) - n,
                    "%s[%s %s]\x1B[0m ",
                    s_level_clr[level],
                    s_level_str[level], tag);
    } else {
        n += snprintf(buf + n, sizeof(buf) - n,
                    "[%s %s] ",
                    s_level_str[level], tag);
    }

    /* 用户格式 */
    va_list args;
    va_start(args, fmt);
    n += vsnprintf(buf + n, sizeof(buf) - n, fmt, args);
    va_end(args);

    /* 行尾 */
    buf[n++] = '\r';
    buf[n++] = '\n';

    SEGGER_RTT_Write(0, buf, (unsigned)n);
}

#endif /* MYLOG_ENABLED */
