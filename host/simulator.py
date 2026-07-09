"""
simulator.py — 小车遥测模拟器

模拟 MSPM0 循迹小车端行为，连接上位机 TCP server，发送 100Hz 遥测 JSON，
接收并响应下行参数/指令。

用途：固件烧录前验证上位机逻辑闭环（波形/AI/参数下发）。

运行：
  python simulator.py [host] [port]
  默认 host=127.0.0.1, port=8888
"""
import socket
import sys
import time
import json
import math
import threading
import random

# 默认参数（与 protocol.PARAMS 一致）
DEFAULT_PARAMS = {
    "KP": 5.0,
    "KI": 0.0,
    "KD": 1.0,
    "GDAMP": 0.15,
    "VBASE": 40,
    "VSTR": 50,
    "VCUR": 30,
    "RATHR": 2.5,
}

# 模拟场景：正弦误差 + 噪声 + 偶尔丢线
SCENE_PERIOD = 20.0  # 20 秒一个完整误差周期


def simulate(host="127.0.0.1", port=8888):
    """启动模拟器"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((host, port))
    except ConnectionRefusedError:
        print(f"[SIM] 无法连接 {host}:{port}，请先启动上位机 (python app.py)")
        return

    print(f"[SIM] 已连接上位机 {host}:{port}")
    print(f"[SIM] 开始发送 100Hz 遥测，按 Ctrl+C 退出")

    # 共享参数（接收线程修改，发送线程读取）
    params = dict(DEFAULT_PARAMS)
    params_lock = threading.Lock()
    running = {"alive": True}

    # 当前状态（模拟状态机）
    state = {"current": "LF"}

    def recv_loop():
        """接收线程：解析下行参数/指令

        用 JSONDecoder.raw_decode 处理嵌套 JSON (如 {"set":{"KP":7.5}}),
        不能简单按 } 分割 (嵌套对象会断开)。
        """
        buf = b""
        decoder = json.JSONDecoder()
        while running["alive"]:
            try:
                data = sock.recv(256)
            except OSError:
                break
            if not data:
                break
            buf += data
            # 尝试从 buf 开头解析完整 JSON 对象（可能多个连在一起）
            while buf:
                try:
                    text = buf.decode("utf-8")
                    stripped = text.lstrip()
                    if not stripped:
                        buf = b""
                        break
                    obj, end = decoder.raw_decode(stripped)
                    consumed = len(text) - len(stripped) + end
                    buf = buf[consumed:]
                except json.JSONDecodeError:
                    # 数据不完整，等下次 recv
                    break
                except UnicodeDecodeError:
                    buf = b""
                    break

                msg = obj
                if "set" in msg:
                    with params_lock:
                        params.update(msg["set"])
                    print(f"[SIM] 收到参数: {msg['set']} → 当前: {params}")
                elif "cmd" in msg:
                    cmd = msg["cmd"]
                    print(f"[SIM] 收到指令: {cmd}")
                    if cmd == "start":
                        state["current"] = "LF"
                    elif cmd == "stop":
                        state["current"] = "ID"
                    elif cmd == "whitecal":
                        print("[SIM] 模拟白色校准完成")
                    elif cmd == "blackcal":
                        print("[SIM] 模拟黑色校准完成")
                    elif cmd == "reconnect":
                        print("[SIM] 模拟重连")

    threading.Thread(target=recv_loop, daemon=True, name="sim-recv").start()

    # 发送遥测（100Hz）
    t = 0.0
    frame_count = 0

    # 场景循环：每 20 秒一个完整循环
    #   0-5s   直道（小误差 + 陀螺抖动）
    #   5-10s  弯道（大误差正弦）
    #   10-13s 直角弯（误差突到极值）
    #   13-15s 丢线（全白）
    #   15-20s 恢复循迹
    SCENE_CYCLE = 20.0
    prev_error = 0.0  # 用于 PID 微分（跨帧保持）

    try:
        while running["alive"]:
            with params_lock:
                p = dict(params)

            scene_t = t % SCENE_CYCLE

            # 场景调度
            if scene_t < 5.0:
                # 直道：小误差 + 陀螺抖动
                error = 0.3 * math.sin(t * 2.0) + random.gauss(0, 0.15)
                gyro = 1.5 * math.sin(t * 5.0) + random.gauss(0, 0.3)  # 陀螺抖动明显
                st = "LF"
            elif scene_t < 10.0:
                # 弯道：大误差正弦
                error = 2.8 * math.sin((scene_t - 5.0) * 1.2) + random.gauss(0, 0.2)
                gyro = 0.5 * math.cos((scene_t - 5.0) * 1.2) + random.gauss(0, 0.2)
                st = "LF"
                # 弯道丢线概率
                if abs(error) > 3.0 and random.random() < 0.08:
                    st = "LL"
            elif scene_t < 13.0:
                # 直角弯：误差突到极值
                if scene_t < 11.0:
                    error = 3.2 + random.gauss(0, 0.1)
                    st = "RA"
                    gyro = 5.0  # 直角弯角速度大
                else:
                    error = -0.5 + random.gauss(0, 0.1)
                    st = "LF"
                    gyro = random.gauss(0, 0.2)
            elif scene_t < 15.0:
                # 丢线：全白
                error = 0.0
                gyro = 0.3 + random.gauss(0, 0.1)
                st = "LL"
            else:
                # 恢复循迹
                error = 0.5 * math.sin(t * 1.5) + random.gauss(0, 0.15)
                gyro = 0.2 * math.sin(t * 1.5) + random.gauss(0, 0.2)
                st = "LF"

            # PID 转向输出（用当前 KP/KD）
            turn = p["KP"] * error + p["KD"] * (error - prev_error) * 10  # 10=微分增益
            prev_error = error

            # 编码器：基础速度 + 转向差速
            base = p["VBASE"]
            left_speed = int(base - turn * 0.5)
            right_speed = int(base + turn * 0.5)

            # 灰度 ADC：模拟 8 路，中间通道随误差变化
            adc = []
            for i in range(8):
                pos = i - 3.5
                dist = abs(pos - error)
                base_adc = 2000 - int(1500 * math.exp(-dist * 0.5))
                base_adc += random.randint(-50, 50)
                adc.append(max(0, min(4095, base_adc)))

            # 丢线时全白
            if st == "LL":
                adc = [random.randint(80, 120) for _ in range(8)]

            tele = {
                "t": "tele",
                "adc": adc,
                "gz": round(gyro, 2),
                "el": left_speed,
                "er": right_speed,
                "le": round(error, 2),
                "po": round(turn, 2),
                "st": st,
                "kp": p["KP"],
                "kd": p["KD"],
            }

            try:
                sock.sendall((json.dumps(tele) + "\n").encode("utf-8"))
            except OSError:
                print("[SIM] 连接断开")
                break

            frame_count += 1
            if frame_count % 100 == 0:
                print(f"[SIM] 已发送 {frame_count} 帧, t={t:.1f}s, error={error:.2f}, st={st}")

            # 模拟 elog 透传日志：每 50 帧（0.5 秒）发一行 JSON 封装日志
            # 固件 elog_port_esp_flush 把 elog 输出封装为 {"t":"log","msg":"..."}\n
            if frame_count % 50 == 0:
                # 模拟 elog 格式：[时间戳] I/标签 日志内容
                msg = f"[{int(t*1000)}] I/track State:{st} Error:{error:.2f} KP:{p['KP']:.1f} KD:{p['KD']:.1f}"
                log_frame = json.dumps({"t": "log", "msg": msg}, separators=(",", ":")) + "\n"
                try:
                    sock.sendall(log_frame.encode("utf-8"))
                except OSError:
                    pass

            t += 0.01
            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n[SIM] 退出")
    finally:
        running["alive"] = False
        sock.close()


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8888
    simulate(host, port)
