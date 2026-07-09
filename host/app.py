"""
app.py — Flask + SocketIO 上位机主程序

启动流程：
  1. 加载配置
  2. 创建调参引擎（本地规则或 GLM）
  3. 启动 TCP server 线程（监听 8888，接收小车遥测）
  4. 启动 Flask + SocketIO Web 服务（端口 5000）

Web 路由：
  GET  /           主界面
  SocketIO 事件:
    connect          浏览器连接
    telemetry        推送遥测帧到所有浏览器
    client_status    推送小车连接状态
    ai_result        推送 AI 分析结果
    send_cmd         前端发指令（start/stop/...）
    send_params      前端发参数
    ai_analyze       前端请求 AI 分析
"""
import argparse
import logging
import threading
import time
from collections import deque
from pathlib import Path
import sys
import webbrowser

from flask import Flask, render_template, request
from flask_socketio import SocketIO

from config import Config
from protocol import PARAMS, build_set, build_cmd, clamp
from tcp_server import TcpServer
from tuning_engine import get_engine


def _resource_root() -> Path:
    """返回资源根目录（开发态=当前脚本目录，冻结打包态=_MEIPASS）。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def _resource_path(*parts: str) -> str:
    """兼容源码/打包态返回资源路径。"""
    candidates = [
        _resource_root() / Path(*parts),
        _resource_root() / "host" / Path(*parts),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return str(candidates[0])

# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("host")

# ============================================================
# Flask 应用
# ============================================================
app = Flask(
    __name__,
    template_folder=_resource_path("templates"),
    static_folder=_resource_path("static"),
    static_url_path="/static",
)
app.config["SECRET_KEY"] = "tuning-secret"


socketio = SocketIO(app, cors_allowed_origins="*", async_mode=None)

# ============================================================
# 全局状态
# ============================================================
config = Config.load()
engine = get_engine(config)

# 遥测历史（线程安全的双端队列，固定长度）
telemetry_history = deque(maxlen=config.TELEMETRY_WINDOW)

# 当前参数（运行时可改，前端展示+下发给小车）
current_params = {k: v["default"] for k, v in PARAMS.items()}

# 小车连接状态
client_connected = False
client_addr = None

# 日志缓冲（前端展示最近 200 条）
log_buffer = deque(maxlen=200)

# 小车/ESP-01S 日志缓冲（新打开的浏览器也能看到最近日志）
car_log_buffer = deque(maxlen=500)

# 线程锁
state_lock = threading.Lock()


def add_log(level: str, msg: str):
    """添加日志到缓冲（前端通过 SocketIO 推送）"""
    entry = {"time": time.strftime("%H:%M:%S"), "level": level, "msg": msg}
    log_buffer.append(entry)
    socketio.emit("log", entry, namespace="/")
    logger.log(getattr(logging, level.upper(), logging.INFO), msg)


def parse_car_log_line(line: str) -> dict:
    """解析 EasyLogger 行，给前端提供结构化字段用于上色。"""
    import re
    clean = re.sub(r"(?:\x1b)?\[[0-9;]*m", "", line).strip()
    match = re.match(r"^(?P<lvl>[VDIWEA])/(?P<tag>\S+)\s+\[(?P<mcu>\d+)\]\s*(?P<msg>.*)$", clean)
    if not match:
        return {
            "line": clean,
            "level": "INFO",
            "tag": "",
            "mcu_time": "",
            "msg": clean,
        }

    level_map = {
        "V": "TRACE",
        "D": "DEBUG",
        "I": "INFO",
        "W": "WARNING",
        "E": "ERROR",
        "A": "ASSERT",
    }
    return {
        "line": clean,
        "level": level_map.get(match.group("lvl"), "INFO"),
        "tag": match.group("tag"),
        "mcu_time": match.group("mcu"),
        "msg": match.group("msg"),
    }


# ============================================================
# TCP server 回调
# ============================================================

def on_telemetry(tele: dict):
    """收到遥测帧"""
    with state_lock:
        telemetry_history.append(tele)
        frame_no = len(telemetry_history)
        # 同步当前参数（小车端 kp/kd 可能因其他方式改变）
        if "kp" in tele:
            current_params["KP"] = tele["kp"]
        if "kd" in tele:
            current_params["KD"] = tele["kd"]
    if frame_no <= 10 or frame_no % 20 == 0:
        logger.info("telemetry #%d: st=%s le=%s kp=%s kd=%s",
                    frame_no, tele.get("st"), tele.get("le"),
                    tele.get("kp"), tele.get("kd"))
    # 推送到所有浏览器客户端
    socketio.emit("telemetry", tele, namespace="/")


def on_connect(addr):
    """小车连接"""
    global client_connected, client_addr
    with state_lock:
        client_connected = True
        client_addr = addr
    add_log("INFO", f"小车连接: {addr[0]}:{addr[1]}")
    socketio.emit("client_status", {"connected": True, "addr": f"{addr[0]}:{addr[1]}"})


def on_disconnect():
    """小车断开"""
    global client_connected, client_addr
    with state_lock:
        client_connected = False
        client_addr = None
    add_log("WARNING", "小车断开连接")
    socketio.emit("client_status", {"connected": False, "addr": ""})


def on_car_log(line: str):
    """收到小车 elog 透传日志行（裸文本，非遥测 JSON）

    固件 elog_port_output 同时写 RTT 和 ESP 环形缓冲，
    主循环 elog_port_esp_flush 通过 TCP 发到这里。
    """
    parsed = parse_car_log_line(line)
    entry = {"time": time.strftime("%H:%M:%S"), **parsed}
    car_log_buffer.append(entry)
    logger.info("car: %s", parsed["line"])
    socketio.emit("car_log", entry)


# ============================================================
# 创建 TCP server
# ============================================================
tcp = TcpServer(
    port=config.TCP_PORT,
    on_telemetry=on_telemetry,
    on_connect=on_connect,
    on_disconnect=on_disconnect,
    on_log=on_car_log,
)


# ============================================================
# Web 路由
# ============================================================

@app.route("/")
def index():
    return render_template(
        "index.html",
        params=PARAMS,
        current=current_params,
        config=config.as_dict(),
    )


# ============================================================
# SocketIO 事件
# ============================================================

@socketio.on("connect")
def ws_connect():
    """浏览器连接，推送当前状态"""
    sid = request.sid
    socketio.emit("client_status", {
        "connected": client_connected,
        "addr": f"{client_addr[0]}:{client_addr[1]}" if client_addr else "",
    }, room=sid)
    socketio.emit("params_update", current_params, room=sid)
    # 推送历史日志
    for entry in list(log_buffer)[-20:]:
        socketio.emit("log", entry, room=sid)
    for entry in list(car_log_buffer)[-200:]:
        socketio.emit("car_log", entry, room=sid)


@socketio.on("send_cmd")
def ws_send_cmd(data):
    """前端发指令：data = {"cmd": "start"}"""
    cmd = data.get("cmd", "")
    try:
        json_str = build_cmd(cmd)
        if tcp.send(json_str):
            add_log("INFO", f"指令已发送: {cmd}")
        else:
            add_log("ERROR", f"指令发送失败（小车未连接）: {cmd}")
    except ValueError as e:
        add_log("ERROR", f"非法指令: {e}")


@socketio.on("send_params")
def ws_send_params(data):
    """前端发参数：data = {"KP": 6.0, "KD": 1.5}"""
    if not data:
        return
    try:
        json_str = build_set(data)
        # 更新当前参数
        with state_lock:
            for k, v in data.items():
                if k in PARAMS:
                    current_params[k] = clamp(k, v)
        if tcp.send(json_str):
            add_log("INFO", f"参数已发送: {data}")
            socketio.emit("params_update", current_params)
        else:
            add_log("ERROR", f"参数发送失败（小车未连接）: {data}")
    except Exception as e:
        add_log("ERROR", f"参数发送异常: {e}")


@socketio.on("ai_analyze")
def ws_ai_analyze():
    """前端请求 AI 分析"""
    with state_lock:
        if not telemetry_history:
            socketio.emit("ai_result", {"error": "无遥测数据"})
            return
        history = list(telemetry_history)[-config.AI_ANALYZE_FRAMES:]
        params_copy = current_params.copy()

    add_log("INFO", f"AI 分析中（{len(history)} 帧，引擎: {type(engine).__name__}）...")
    try:
        suggestion = engine.analyze(history, params_copy)
        socketio.emit("ai_result", suggestion)
        add_log("INFO", f"AI 建议: {suggestion.get('params', {})} "
                        f"置信度: {suggestion.get('confidence', 0):.2f}")
    except Exception as e:
        add_log("ERROR", f"AI 分析失败: {e}")
        socketio.emit("ai_result", {"error": str(e)})


@socketio.on("get_status")
def ws_get_status():
    """前端查询状态"""
    socketio.emit("status", {
        "client_connected": client_connected,
        "client_addr": f"{client_addr[0]}:{client_addr[1]}" if client_addr else "",
        "frame_count": tcp.get_frame_count(),
        "history_len": len(telemetry_history),
        "engine": type(engine).__name__,
        "auto_tuning": auto_tuner.active,
        "auto_tuning_rounds": auto_tuner.rounds,
    })


# ============================================================
# 自动调参闭环模式
# ============================================================

class AutoTuner:
    """自动调参闭环：每 interval 秒自动分析+下发，达到停止条件自动停止

    停止条件：
      1. AI 置信度 < min_confidence（说明已无需调整）
      2. 连续 max_rounds 轮参数变化 < convergence_delta（参数收敛）
      3. 达到 max_rounds 上限
      4. 用户手动停止
    """

    def __init__(self):
        self.active = False
        self.thread = None
        self.rounds = 0
        self.interval = 5.0            # 每轮间隔（秒）
        self.min_confidence = 0.4      # 低于此置信度自动停止
        self.max_rounds = 10           # 最多迭代轮数
        self.convergence_delta = 0.05  # 参数变化幅度小于此值视为收敛
        self.history_snapshots = []    # 每轮参数快照（前端可视化）

    def start(self, interval=None, max_rounds=None):
        if self.active:
            return False, "自动调参已在运行"
        self.active = True
        self.rounds = 0
        self.history_snapshots = []
        if interval: self.interval = interval
        if max_rounds: self.max_rounds = max_rounds
        self.thread = threading.Thread(target=self._loop, daemon=True, name="auto-tuner")
        self.thread.start()
        return True, f"自动调参启动（间隔{self.interval}s，最多{self.max_rounds}轮）"

    def stop(self):
        if not self.active:
            return False, "自动调参未运行"
        self.active = False
        return True, "自动调参已停止"

    def _loop(self):
        add_log("INFO", f"[AUTO] 自动调参启动（间隔{self.interval}s）")
        socketio.emit("auto_tuning_status", {"active": True, "rounds": 0})

        while self.active and self.rounds < self.max_rounds:
            self.rounds += 1
            # 1. 分析
            with state_lock:
                if len(telemetry_history) < 20:
                    add_log("WARNING", f"[AUTO] 第{self.rounds}轮: 数据不足，等待...")
                    socketio.emit("auto_tuning_status", {
                        "active": True, "rounds": self.rounds, "status": "waiting_data"
                    })
                    time.sleep(self.interval)
                    continue
                history = list(telemetry_history)[-config.AI_ANALYZE_FRAMES:]
                params_before = current_params.copy()

            try:
                suggestion = engine.analyze(history, params_before)
            except Exception as e:
                add_log("ERROR", f"[AUTO] 第{self.rounds}轮分析失败: {e}")
                time.sleep(self.interval)
                continue

            params_suggested = suggestion.get("params", {})
            confidence = suggestion.get("confidence", 0)

            # 记录快照
            snapshot = {
                "round": self.rounds,
                "params_before": params_before.copy(),
                "params_suggested": params_suggested.copy(),
                "confidence": confidence,
                "reason": suggestion.get("reason", ""),
            }
            self.history_snapshots.append(snapshot)
            socketio.emit("auto_tuning_round", snapshot)

            # 2. 停止条件检查
            if not params_suggested:
                add_log("INFO", f"[AUTO] 第{self.rounds}轮: 无需调整，自动停止")
                add_log("INFO", f"[AUTO] 原因: {suggestion.get('reason','')}")
                break

            if confidence < self.min_confidence:
                add_log("INFO", f"[AUTO] 第{self.rounds}轮: 置信度{confidence:.2f}<{self.min_confidence}，自动停止")
                break

            # 3. 下发参数
            json_str = build_set(params_suggested)
            with state_lock:
                for k, v in params_suggested.items():
                    if k in PARAMS:
                        current_params[k] = clamp(k, v)
            if tcp.send(json_str):
                add_log("INFO", f"[AUTO] 第{self.rounds}轮: 下发 {params_suggested} (置信度{confidence:.2f})")
                socketio.emit("params_update", current_params)
            else:
                add_log("ERROR", f"[AUTO] 第{self.rounds}轮: 下发失败（小车未连接），停止")
                break

            # 4. 收敛检测
            if self.rounds > 1 and self.history_snapshots:
                prev = self.history_snapshots[-2]["params_suggested"] if len(self.history_snapshots) >= 2 else {}
                # 计算参数变化幅度
                all_keys = set(prev.keys()) | set(params_suggested.keys())
                if all_keys:
                    max_delta = max(
                        abs(params_suggested.get(k, 0) - prev.get(k, 0))
                        for k in all_keys
                    )
                    if max_delta < self.convergence_delta:
                        add_log("INFO", f"[AUTO] 第{self.rounds}轮: 参数变化{max_delta:.3f}<{self.convergence_delta}，收敛停止")
                        break

            # 5. 等待下一轮（让新参数生效并收集遥测）
            socketio.emit("auto_tuning_status", {
                "active": True, "rounds": self.rounds, "status": "waiting_next"
            })
            # 分段 sleep 以便快速响应 stop
            slept = 0
            while self.active and slept < self.interval:
                time.sleep(0.5)
                slept += 0.5

        self.active = False
        add_log("INFO", f"[AUTO] 自动调参结束（共{self.rounds}轮）")
        socketio.emit("auto_tuning_status", {
            "active": False, "rounds": self.rounds,
            "snapshots": self.history_snapshots,
        })


auto_tuner = AutoTuner()


@socketio.on("auto_tuning_start")
def ws_auto_tuning_start(data):
    """启动自动调参：data = {"interval": 5.0, "max_rounds": 10}"""
    if not client_connected:
        add_log("ERROR", "[AUTO] 小车未连接，无法启动自动调参")
        return
    interval = data.get("interval", 5.0) if data else 5.0
    max_rounds = data.get("max_rounds", 10) if data else 10
    ok, msg = auto_tuner.start(interval=interval, max_rounds=max_rounds)
    add_log("INFO" if ok else "WARNING", msg)


@socketio.on("auto_tuning_stop")
def ws_auto_tuning_stop():
    """停止自动调参"""
    ok, msg = auto_tuner.stop()
    add_log("INFO" if ok else "WARNING", msg)


# ============================================================
# 主入口
# ============================================================


def run_host(no_browser: bool = False, web_port: int | None = None):
    """启动上位机主循环（给 exe 入口复用）。"""
    if web_port is not None:
        config.WEB_PORT = web_port

    tcp.start()
    add_log("INFO", f"TCP server 监听 :{config.TCP_PORT}")
    add_log("INFO", f"调参引擎: {type(engine).__name__}")

    url = f"http://localhost:{config.WEB_PORT}"
    print(f"\n[HOST] 上位机已启动")
    print(f"[HOST] TCP server 监听端口: {config.TCP_PORT}")
    print(f"[HOST] Web 界面: {url}")
    print(f"[HOST] 调参引擎: {type(engine).__name__}")
    print(f"[HOST] 按 Ctrl+C 退出\n")

    if not no_browser:
        threading.Thread(
            target=lambda: (time.sleep(1.0), webbrowser.open(url)),
            daemon=True,
        ).start()

    try:
        socketio.run(
            app, host="0.0.0.0", port=config.WEB_PORT,
            debug=False, allow_unsafe_werkzeug=True,
        )
    except KeyboardInterrupt:
        print("\n[HOST] 正在停止...")
    finally:
        tcp.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Track Car 上位机")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    parser.add_argument("--web-port", type=int, default=config.WEB_PORT, help="Web 端口")
    args = parser.parse_args()
    run_host(no_browser=args.no_browser, web_port=args.web_port)
