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

/* 默认级别：INFO = IWAE 四级全开 */
#ifndef MYLOG_DEFAULT_LEVEL
#define MYLOG_DEFAULT_LEVEL  LOG_LVL_INFO
#endif

/* 默认开彩色 */
#ifndef MYLOG_DEFAULT_COLOR
#define MYLOG_DEFAULT_COLOR  1
#endif

/* ========== IWAE 四级枚举 ========== */

typedef enum {
    LOG_LVL_ASSERT  = 0,
    LOG_LVL_ERROR   = 1,
    LOG_LVL_WARN    = 2,
    LOG_LVL_INFO    = 3,
} log_level_t;

/* ========== 配色方案（参照 LOG.h，使用 \x1B[2;3Xm dim 风格，J-Link RTT Viewer 兼容） ========== */

#define _MYLOG_CLR_A    "\x1B[2;35m"   /* assert  · 品红 */
#define _MYLOG_CLR_E    "\x1B[2;31m"   /* error   · 红色 */
#define _MYLOG_CLR_W    "\x1B[2;33m"   /* warn    · 黄色 */
#define _MYLOG_CLR_I    "\x1B[2;32m"   /* info    · 绿色 */
#define _MYLOG_RST      "\x1B[0m"      /* 复位    */

/* ========== API ========== */

void my_log_init(void);
void my_log_set_level(log_level_t level);
void my_log_set_color(bool enable);

#if MYLOG_ENABLED

void my_log_write(log_level_t level, const char *tag, const char *fmt, ...);

#define elog_a(tag, fmt, ...)  my_log_write(LOG_LVL_ASSERT,  tag, fmt, ##__VA_ARGS__)
#define elog_e(tag, fmt, ...)  my_log_write(LOG_LVL_ERROR,   tag, fmt, ##__VA_ARGS__)
#define elog_w(tag, fmt, ...)  my_log_write(LOG_LVL_WARN,    tag, fmt, ##__VA_ARGS__)
#define elog_i(tag, fmt, ...)  my_log_write(LOG_LVL_INFO,    tag, fmt, ##__VA_ARGS__)

#else

#define elog_a(tag, fmt, ...)  ((void)0)
#define elog_e(tag, fmt, ...)  ((void)0)
#define elog_w(tag, fmt, ...)  ((void)0)
#define elog_i(tag, fmt, ...)  ((void)0)

#endif /* MYLOG_ENABLED */

#endif /* __MY_EASYLOG_H__ */
