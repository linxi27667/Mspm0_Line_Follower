#ifndef __MY_EASYLOG_H__
#define __MY_EASYLOG_H__

#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include "SEGGER_RTT.h"

/* ========== 用户配置 ========== */

/* 编译期关闭所有日志（电赛正式比赛设为 0，零代码零开销） */
#ifndef MYLOG_ENABLED
#define MYLOG_ENABLED  1
#endif

/* 单条日志最大字节数（栈缓冲），覆盖 99% 场景 */
#ifndef MYLOG_BUF_SIZE
#define MYLOG_BUF_SIZE  160
#endif

/* 默认级别：VERBOSE = 全开 */
#ifndef MYLOG_DEFAULT_LEVEL
#define MYLOG_DEFAULT_LEVEL  LOG_LVL_VERBOSE
#endif

/* 默认开彩色 */
#ifndef MYLOG_DEFAULT_COLOR
#define MYLOG_DEFAULT_COLOR  1
#endif

/* ========== 级别枚举 ========== */

typedef enum {
    LOG_LVL_ASSERT  = 0,
    LOG_LVL_ERROR   = 1,
    LOG_LVL_WARN    = 2,
    LOG_LVL_INFO    = 3,
    LOG_LVL_DEBUG   = 4,
    LOG_LVL_VERBOSE = 5,
} log_level_t;

/* ========== 配色方案（电赛优化版） ========== */
/* 采用 SEGGER RTT 内置 ANSI，各终端兼容性好       */

/* 级别颜色 */
#define _MYLOG_CLR_A    "\033[1;35m"   /* assert  · 亮品红 — 致命断言 */
#define _MYLOG_CLR_E    "\033[1;31m"   /* error   · 亮红   — 严重错误 */
#define _MYLOG_CLR_W    "\033[1;33m"   /* warn    · 亮黄   — 警告提醒 */
#define _MYLOG_CLR_I    "\033[37m"     /* info    · 白色   — 运行信息 */
#define _MYLOG_CLR_D    "\033[32m"     /* debug   · 绿色   — 调试正确 */
#define _MYLOG_CLR_V    "\033[2;36m"   /* verbose · 暗青   — 细节流水 */
#define _MYLOG_RST      "\033[0m"      /* 复位     */

/* 装饰符号 */
#define _MYLOG_SEP_L    "["
#define _MYLOG_SEP_M    "]"
#define _MYLOG_SEP_R    ""

/* ========== API ========== */

void my_log_init(void);
void my_log_set_level(log_level_t level);
void my_log_set_color(bool enable);

#if MYLOG_ENABLED

void my_log_write(log_level_t level, const char *tag, const char *fmt, ...);

#define log_a(tag, fmt, ...)  my_log_write(LOG_LVL_ASSERT,   tag, fmt, ##__VA_ARGS__)
#define log_e(tag, fmt, ...)  my_log_write(LOG_LVL_ERROR,    tag, fmt, ##__VA_ARGS__)
#define log_w(tag, fmt, ...)  my_log_write(LOG_LVL_WARN,     tag, fmt, ##__VA_ARGS__)
#define log_i(tag, fmt, ...)  my_log_write(LOG_LVL_INFO,     tag, fmt, ##__VA_ARGS__)
#define log_d(tag, fmt, ...)  my_log_write(LOG_LVL_DEBUG,    tag, fmt, ##__VA_ARGS__)
#define log_v(tag, fmt, ...)  my_log_write(LOG_LVL_VERBOSE,  tag, fmt, ##__VA_ARGS__)

#else

/* 关闭 → 编译器直接优化掉，零开销 */
#define log_a(tag, fmt, ...)  ((void)0)
#define log_e(tag, fmt, ...)  ((void)0)
#define log_w(tag, fmt, ...)  ((void)0)
#define log_i(tag, fmt, ...)  ((void)0)
#define log_d(tag, fmt, ...)  ((void)0)
#define log_v(tag, fmt, ...)  ((void)0)

#endif /* MYLOG_ENABLED */

#endif /* __MY_EASYLOG_H__ */
