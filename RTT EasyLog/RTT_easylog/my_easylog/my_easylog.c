#include "my_easylog.h"
#include <stdio.h>
#include <stdarg.h>

/* ---------- 静态状态 ---------- */

static log_level_t g_log_level = MYLOG_DEFAULT_LEVEL;
static bool        g_color     = MYLOG_DEFAULT_COLOR;

static const char * const s_level_str[] = {
    [LOG_LVL_ASSERT]   = "A",
    [LOG_LVL_ERROR]    = "E",
    [LOG_LVL_WARN]     = "W",
    [LOG_LVL_INFO]     = "I",
    [LOG_LVL_DEBUG]    = "D",
    [LOG_LVL_VERBOSE]  = "V",
};

static const char * const s_level_clr[] = {
    [LOG_LVL_ASSERT]   = _MYLOG_CLR_A,
    [LOG_LVL_ERROR]    = _MYLOG_CLR_E,
    [LOG_LVL_WARN]     = _MYLOG_CLR_W,
    [LOG_LVL_INFO]     = _MYLOG_CLR_I,
    [LOG_LVL_DEBUG]    = _MYLOG_CLR_D,
    [LOG_LVL_VERBOSE]  = _MYLOG_CLR_V,
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

void my_log_write(log_level_t level, const char *tag, const char *fmt, ...)
{
    /* 级别过滤 — 最早退出，零浪费 */
    if (level > g_log_level) {
        return;
    }

    char buf[MYLOG_BUF_SIZE];
    int  n = 0;

    /* 颜色前缀 — 整行一个颜色 */
    if (g_color) {
        n += snprintf(buf + n, sizeof(buf) - n,
                    "%s%s%s%s ",
                    s_level_clr[level],
                    _MYLOG_SEP_L,
                    s_level_str[level],
                    _MYLOG_SEP_M);
    } else {
        n += snprintf(buf + n, sizeof(buf) - n,
                    "%s%s%s ",
                    _MYLOG_SEP_L,
                    s_level_str[level],
                    _MYLOG_SEP_M);
    }

    /* tag */
    n += snprintf(buf + n, sizeof(buf) - n, "%s: ", tag);

    /* 用户格式 — 用 vsnprintf 防止溢出 */
    va_list args;
    va_start(args, fmt);
    n += vsnprintf(buf + n, sizeof(buf) - n, fmt, args);
    va_end(args);

    /* 行尾 + 颜色复位 */
    if (g_color) {
        n += snprintf(buf + n, sizeof(buf) - n, "%s\r\n", _MYLOG_RST);
    } else {
        buf[n++] = '\r';
        buf[n++] = '\n';
    }

    /* 直接推送到 RTT — 非阻塞，RTT 内部有自己的 ring buffer */
    SEGGER_RTT_Write(0, buf, (unsigned)n);
}

#endif /* MYLOG_ENABLED */
