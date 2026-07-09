"""
protocol.py — 调参协议常量与 JSON 解析/组包

协议规范（与固件 app_tuning.c 对齐）：
  下行（PC → 小车）：
    {"set":{"KP":2.5,"KI":0.0,"KD":1.0,"GDAMP":0.15,"VBASE":40,"VSTR":50,"VCUR":30,"RATHR":2.5}}
    {"cmd":"start|stop|whitecal|blackcal|reconnect"}
  上行 100Hz（小车 → PC，以 \\n 结尾）：
    {"t":"tele","adc":[8值],"gz":0.12,"el":1024,"er":980,"le":0.3,"po":45,"st":"LF","kp":5.0,"kd":1.0}

参数钳位范围（与固件 track.c setter 一致）：
  GDAMP  0~1
  VBASE/VSTR/VCUR  0~100
  RATHR  0.5~10
  KP/KI/KD 无固件钳位（上位机侧建议范围 0~50/0~5/0~20）
"""
import json

# ============================================================
# 参数定义（min/max/default 与固件 track.c setter 钳位一致）
# ============================================================
PARAMS = {
    "KP":    {"min": 0.0, "max": 50.0, "default": 5.0,  "desc": "循迹比例增益",      "step": 0.1},
    "KI":    {"min": 0.0, "max": 5.0,  "default": 0.0,  "desc": "循迹积分增益",      "step": 0.05},
    "KD":    {"min": 0.0, "max": 20.0, "default": 1.0,  "desc": "循迹微分增益",      "step": 0.1},
    "GDAMP": {"min": 0.0, "max": 1.0,  "default": 0.15, "desc": "陀螺仪阻尼系数",    "step": 0.01},
    "VBASE": {"min": 0,   "max": 100,  "default": 40,   "desc": "基础速度",          "step": 1},
    "VSTR":  {"min": 0,   "max": 100,  "default": 50,   "desc": "直道速度",          "step": 1},
    "VCUR":  {"min": 0,   "max": 100,  "default": 30,   "desc": "弯道速度",          "step": 1},
    "RATHR": {"min": 0.5, "max": 10.0, "default": 2.5,  "desc": "直角弯检测阈值",    "step": 0.1},
}

# 状态枚举 → 全名映射（与 track.h track_state_t 对齐）
STATE_MAP = {
    "ID": "IDLE",
    "LF": "LINE_FOLLOW",
    "RA": "RIGHT_ANGLE",
    "LL": "LINE_LOST",
    "SL": "START_LINE",
    "CR": "CROSS",
    "FN": "FINISHED",
}

# 指令白名单（防止前端注入非法指令）
VALID_CMDS = {"start", "stop", "whitecal", "blackcal", "reconnect"}


# ============================================================
# 工具函数
# ============================================================

def clamp(name: str, value):
    """钳位到参数合法范围

    Args:
        name: 参数名（如 "KP"）
        value: 输入值（str/float/int）
    Returns:
        钳位后的 float
    """
    if name not in PARAMS:
        raise ValueError(f"unknown param: {name}")
    p = PARAMS[name]
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = p["default"]
    return max(p["min"], min(p["max"], v))


def parse_telemetry(line: str):
    """解析上行遥测 JSON（一行一帧）

    Args:
        line: 一行 JSON 字符串
    Returns:
        dict: 解析后的遥测字典，失败返回 None
    """
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    # 校验必需字段
    if obj.get("t") != "tele":
        return None
    required = ["adc", "gz", "el", "er", "le", "po", "st", "kp", "kd"]
    if not all(k in obj for k in required):
        return None
    return obj


def build_set(params: dict) -> str:
    """组下行 set JSON

    Args:
        params: 参数字典，如 {"KP": 6.0, "KD": 1.5}
    Returns:
        JSON 字符串，如 {"set":{"KP":6.0,"KD":1.5}}
    """
    # 钳位 + 过滤非法字段
    clean = {}
    for k, v in params.items():
        if k in PARAMS:
            clean[k] = clamp(k, v)
    return json.dumps({"set": clean}, separators=(",", ":"))


def build_cmd(cmd: str) -> str:
    """组下行 cmd JSON

    Args:
        cmd: 指令名，如 "start"
    Returns:
        JSON 字符串，如 {"cmd":"start"}
    Raises:
        ValueError: 非法指令
    """
    if cmd not in VALID_CMDS:
        raise ValueError(f"invalid cmd: {cmd}")
    return json.dumps({"cmd": cmd}, separators=(",", ":"))


def state_full_name(abbr: str) -> str:
    """状态缩写转全名（如 LF → LINE_FOLLOW）"""
    return STATE_MAP.get(abbr, "UNKNOWN")
