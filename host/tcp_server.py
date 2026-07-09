"""
tcp_server.py — TCP server 线程

监听 8888 端口，接收 ESP-01S（或模拟器）的 TCP 连接，
按行解析遥测 JSON，通过回调派发到上层；提供 send() 下发参数/指令。

设计要点：
  - 独立线程跑 accept/recv 循环，不阻塞 Flask 主线程
  - 单连接模式（ESP-01S CIPMUX=0），新连接到达时关闭旧连接
  - 按行分割（小车遥测以 \\n 结尾），跨包重组
  - send() 加锁，避免多线程同时写 socket
"""
import socket
import threading
import logging
import json

from protocol import parse_telemetry

logger = logging.getLogger("tcp_server")


class TcpServer:
    """TCP server，单连接模式

    Args:
        port: 监听端口（默认 8888，与 app_esp01s_cfg.h ESP01S_SERVER_PORT 一致）
        on_telemetry: 收到遥测帧的回调，签名 (telemetry_dict) -> None
        on_connect: 客户端连接回调，签名 (addr_tuple) -> None
        on_disconnect: 客户端断开回调，签名 () -> None
        on_log: 收到 elog 日志行（非遥测）的回调，签名 (line_str) -> None
    """

    def __init__(self, port=8888, on_telemetry=None, on_connect=None, on_disconnect=None, on_log=None):
        self.port = port
        self.on_telemetry = on_telemetry
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.on_log = on_log
        self._sock = None
        self._client = None
        self._client_addr = None
        self._lock = threading.Lock()
        self._running = False
        self._frame_count = 0  # 收到的遥测帧总数（诊断用）

    # ----------------------------------------------------------
    # 启动 / 停止
    # ----------------------------------------------------------

    def start(self):
        """启动 TCP server（非阻塞，立即返回）"""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", self.port))
        self._sock.listen(1)
        self._sock.settimeout(0.5)  # 超时使 _accept_loop 能响应 _running=False
        self._running = True
        threading.Thread(target=self._accept_loop, daemon=True, name="tcp-accept").start()
        logger.info("TCP server listening on :%d", self.port)

    def stop(self):
        """停止 TCP server"""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._close_client()

    # ----------------------------------------------------------
    # 下发数据
    # ----------------------------------------------------------

    def send(self, json_str: str) -> bool:
        """下发 JSON 到小车

        Args:
            json_str: JSON 字符串（如 '{"set":{"KP":6.0}}'）
        Returns:
            True=发送成功, False=无连接或发送失败
        """
        with self._lock:
            if not self._client:
                logger.warning("send failed: no client connected")
                return False
            try:
                self._client.sendall(json_str.encode("utf-8"))
                logger.debug("send: %s", json_str)
                return True
            except OSError as e:
                logger.error("send failed: %s", e)
                self._close_client()
                if self.on_disconnect:
                    self.on_disconnect()
                return False

    # ----------------------------------------------------------
    # 状态查询
    # ----------------------------------------------------------

    def is_connected(self) -> bool:
        """是否有客户端连接"""
        return self._client is not None

    def get_client_addr(self):
        """获取已连接客户端地址，无连接返回 None"""
        return self._client_addr

    def get_frame_count(self) -> int:
        """获取收到的遥测帧总数"""
        return self._frame_count

    # ----------------------------------------------------------
    # 内部循环
    # ----------------------------------------------------------

    def _accept_loop(self):
        """接受连接循环（独立线程）"""
        while self._running:
            try:
                conn, addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            logger.info("client connected: %s:%d", addr[0], addr[1])
            with self._lock:
                # 关闭旧连接（单连接模式）
                if self._client:
                    try:
                        self._client.close()
                    except OSError:
                        pass
                    if self.on_disconnect:
                        self.on_disconnect()
                self._client = conn
                self._client_addr = addr

            if self.on_connect:
                self.on_connect(addr)

            threading.Thread(
                target=self._recv_loop, args=(conn,),
                daemon=True, name=f"tcp-recv-{addr[1]}"
            ).start()

    def _recv_loop(self, conn):
        """接收循环（每个客户端一个线程）"""
        buf = b""
        while self._running:
            try:
                data = conn.recv(1024)
            except OSError:
                break

            if not data:
                # 客户端关闭连接
                logger.info("client disconnected")
                break

            buf += data
            # 按行分割（小车遥测和 elog 日志均以 \n 结尾）
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line_str = line.decode("utf-8", errors="ignore").rstrip("\r")
                if not line_str:
                    continue

                # 按 "t" 字段区分帧类型：tele=遥测，log=elog 透传日志
                # 兼容旧固件：无 "t" 字段时尝试 parse_telemetry，失败则当 log
                try:
                    obj = json.loads(line_str)
                    frame_type = obj.get("t")
                except (json.JSONDecodeError, ValueError):
                    obj = None
                    frame_type = None

                if frame_type == "tele":
                    self._frame_count += 1
                    if self.on_telemetry:
                        try:
                            self.on_telemetry(obj)
                        except Exception as e:
                            logger.error("on_telemetry callback error: %s", e)
                elif frame_type == "log":
                    # elog 透传日志：{"t":"log","msg":"..."}
                    if self.on_log:
                        try:
                            self.on_log(obj.get("msg", ""))
                        except Exception as e:
                            logger.error("on_log callback error: %s", e)
                else:
                    # 兼容旧固件裸文本 / 无 t 字段的 JSON
                    tele = parse_telemetry(line_str)
                    if tele:
                        self._frame_count += 1
                        if self.on_telemetry:
                            try:
                                self.on_telemetry(tele)
                            except Exception as e:
                                logger.error("on_telemetry callback error: %s", e)
                    elif self.on_log:
                        try:
                            self.on_log(line_str)
                        except Exception as e:
                            logger.error("on_log callback error: %s", e)

        # 接收循环退出，清理连接
        with self._lock:
            if conn is self._client:
                self._close_client()
                if self.on_disconnect:
                    self.on_disconnect()

    def _close_client(self):
        """关闭当前客户端连接（需在 _lock 内调用）"""
        if self._client:
            try:
                self._client.close()
            except OSError:
                pass
            self._client = None
            self._client_addr = None
