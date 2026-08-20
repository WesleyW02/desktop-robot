# -*- coding: utf-8 -*-
"""
串口桥（serial_bridge.py）— Phase 1 电脑端 ↔ 机器人通信

职责：
    1. 串口连接管理（pyserial，921600，端口从 config.yaml → serial.port 读取）
    2. 协议 v2.0 收发：下行指令自动带 seq；上行 JSON 解析；seq 匹配等待 ack
    3. 命令行测试工具：发指令验证机器人（板子到货后直接联调用）

用法（板子到货后）：
    python serial_bridge.py ping                 # 心跳测试（看 pong）
    python serial_bridge.py face happy           # 表情
    python serial_bridge.py text "你好"          # 屏幕文字
    python serial_bridge.py servo 1 90           # 舵机 1（摇头）
    python serial_bridge.py move forward 60      # 移动
    python serial_bridge.py mode sleep           # 模式切换
    python serial_bridge.py reboot               # 重启
    python serial_bridge.py boot                 # 上电握手（回 hello_ack）后持续监听
    python serial_bridge.py monitor              # 只监听上行消息
    通用参数：--port COM5 覆盖端口；--no-wait 发送后不等 ack

协议：docs/protocol.md v2.0（JSON 行 · seq · ack/err/心跳/握手）
"""
import argparse
import json
import sys
import threading
import time
from typing import Optional

import serial  # pyserial

from settings import get

# 命令 → (type, 参数说明, 是否等待 ack)
CMD_DEFS = {
    "ping":   ("ping",   "心跳测试（响应为 pong，无需 ack）", False),
    "face":   ("face",   "<expr> 表情：happy/sad/idle/sleep/surprise/thinking", True),
    "text":   ("text",   "<文字> 屏幕显示文字", True),
    "servo":  ("servo",  "<ch 1摇头|2点头> <angle 度>", True),
    "move":   ("move",   "<forward|back|left|right|stop> [speed 0-100]", True),
    "mode":   ("mode",   "<listen|sleep> 工作模式", True),
    "locate": ("locate", "<start|stop> 敲击定位", True),
    "reboot": ("reboot", "重启机器人", True),
}


class SerialBridge:
    """串口桥：协议 v2.0 收发 + seq 匹配回执。"""

    def __init__(self, port: Optional[str] = None, baudrate: Optional[int] = None,
                 on_message=None):
        cfg = get("serial", {}) or {}
        self.port = port or cfg.get("port") or "COM3"
        self.baudrate = baudrate or cfg.get("baudrate") or 921600
        self.ser: Optional[serial.Serial] = None
        self._seq = 0
        self._tx_lock = threading.Lock()
        self._ack_events: dict = {}    # seq -> threading.Event
        self._ack_results: dict = {}   # seq -> ack dict
        self._rx_thread: Optional[threading.Thread] = None
        self._running = False
        # 消息回调（voice_loop 等使用）：返回 True 表示已消费（不再打印）
        self.on_message = on_message

    # ---------------- 连接管理 ----------------
    def open(self) -> "SerialBridge":
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=0.1)
        except serial.SerialException as e:
            raise RuntimeError(
                f"无法打开串口 {self.port}：{e}\n"
                f"  提示：设备管理器中查看实际 COM 口，用 --port 指定，"
                f"或修改 config.yaml → serial.port"
            )
        self._running = True
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True, name="serial-rx")
        self._rx_thread.start()
        return self

    def close(self) -> None:
        self._running = False
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

    # ---------------- 发送 ----------------
    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFFFF
        return self._seq

    def send(self, type_: str, payload: Optional[dict] = None,
             wait_ack: bool = True, timeout: float = 5.0,
             seq: Optional[int] = None) -> Optional[dict]:
        """发送一条下行指令，返回匹配的 ack（wait_ack=True 时）。

        返回：ack 字典（含 ok/for/seq/err）或 None（超时/不等待）。
        """
        if self.ser is None:
            raise RuntimeError("串口未打开")
        seq = seq if seq is not None else self._next_seq()
        doc = {"type": type_, "seq": seq}
        if payload:
            doc.update(payload)
        line = json.dumps(doc, ensure_ascii=False)

        with self._tx_lock:
            self.ser.write((line + "\n").encode("utf-8"))
        print(f"[tx] {line}")

        if not wait_ack:
            return None
        ev = threading.Event()
        self._ack_events[seq] = ev
        ev.wait(timeout)
        result = self._ack_results.pop(seq, None)
        self._ack_events.pop(seq, None)
        return result

    # ---------------- 接收 ----------------
    def _rx_loop(self) -> None:
        buf = ""
        while self._running and self.ser is not None:
            try:
                data = self.ser.read(4096)
            except Exception:
                break
            if not data:
                continue
            buf += data.decode("utf-8", errors="replace")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if line:
                    self._handle_line(line)

    def _handle_line(self, line: str) -> None:
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            print(f"[rx][bad_json] {line[:80]}")
            return
        # 业务回调优先（voice_loop 收音频流等）；返回 True 表示已消费
        if self.on_message is not None:
            try:
                if self.on_message(msg):
                    return
            except Exception as e:
                print(f"[rx][callback_err] {e}")
        t = msg.get("type")
        seq = msg.get("seq")

        if t == "ack":
            if seq in self._ack_events:
                self._ack_results[seq] = msg
                self._ack_events[seq].set()
            else:
                print(f"[rx][ack] {msg.get('for')} seq={seq} ok={msg.get('ok')}"
                      + (f" err={msg.get('err')}" if not msg.get("ok") else ""))
        elif t == "err":
            print(f"[rx][err] code={msg.get('code')} msg={msg.get('msg')}")
        elif t == "hello":
            caps = ",".join(msg.get("capabilities") or [])
            print(f"[rx][hello] fw={msg.get('fw')} proto={msg.get('proto_version')} caps={caps}")
        elif t == "pong":
            print(f"[rx][pong] seq={seq} uptime={msg.get('uptime')}s")
        elif t == "telemetry":
            fall = msg.get("fall")
            extra = f" ⚠️ FALL={fall}" if fall else ""
            print(f"[rx][telemetry] bat={msg.get('bat')}V free={msg.get('free')}{extra}")
        elif t == "vad":
            print(f"[rx][vad] {msg.get('state')}")
        elif t == "knock":
            print(f"[rx][knock] angle={msg.get('angle')}°")
        else:
            print(f"[rx][{t}] {line[:120]}")

    # ---------------- 指令封装 ----------------
    def cmd_boot(self) -> None:
        """上电握手：回复机器人的 hello（协议 v2.0）。"""
        self.send("hello_ack", {
            "proto_version": "2.0",
            "mode": "listen",
            "capabilities": ["asr", "tts", "mcp"],
        }, wait_ack=False)

    def cmd_ping(self) -> None:
        self.send("ping", wait_ack=False)  # 响应 pong 由后台线程打印

    def cmd_face(self, expr: str) -> Optional[dict]:
        return self.send("face", {"expr": expr})

    def cmd_text(self, text: str) -> Optional[dict]:
        return self.send("text", {"text": text})

    def cmd_servo(self, ch: int, angle: int) -> Optional[dict]:
        return self.send("servo", {"ch": ch, "angle": angle})

    def cmd_move(self, cmd: str, speed: int = 60) -> Optional[dict]:
        return self.send("move", {"cmd": cmd, "speed": speed})

    def cmd_mode(self, mode: str) -> Optional[dict]:
        return self.send("mode", {"mode": mode})

    def cmd_locate(self, cmd: str) -> Optional[dict]:
        return self.send("locate", {"cmd": cmd})

    def cmd_reboot(self) -> Optional[dict]:
        return self.send("reboot")


# =====================================================================
# 命令行
# =====================================================================
def _print_ack(result: Optional[dict]) -> bool:
    if result is None:
        print("  ⏱ 等待 ack 超时（机器人未响应？检查波特率/连接）")
        return False
    ok = bool(result.get("ok"))
    tail = f" err={result.get('err')}" if not ok else ""
    print(f"  {'✅' if ok else '❌'} ack for={result.get('for')} seq={result.get('seq')} ok={ok}{tail}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description="桌面机器人 · 串口桥（协议 v2.0）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="命令示例：\n"
               "  python serial_bridge.py ping\n"
               "  python serial_bridge.py face happy\n"
               "  python serial_bridge.py text \"你好\"\n"
               "  python serial_bridge.py servo 1 90\n"
               "  python serial_bridge.py move forward 60\n"
               "  python serial_bridge.py boot\n"
               "  python serial_bridge.py monitor",
    )
    parser.add_argument("command", help="ping/face/text/servo/move/mode/locate/reboot/boot/monitor")
    parser.add_argument("args", nargs="*", help="命令参数")
    parser.add_argument("--port", "-p", help="串口（默认读 config.yaml）")
    parser.add_argument("--no-wait", action="store_true", help="发送后不等待 ack")
    args = parser.parse_args()

    cmd = args.command
    if cmd not in CMD_DEFS and cmd not in ("boot", "monitor"):
        print(f"[错误] 未知命令 {cmd}，可用：{'/'.join(list(CMD_DEFS) + ['boot', 'monitor'])}")
        return 1

    bridge = SerialBridge(port=args.port)
    try:
        bridge.open()
    except RuntimeError as e:
        print(f"[错误] {e}")
        return 1
    print(f"[serial] {bridge.port} @ {bridge.baudrate} 已连接")

    try:
        if cmd == "monitor":
            print("  [monitor] 持续监听上行消息，Ctrl+C 退出")
            while True:
                time.sleep(1)
        elif cmd == "boot":
            bridge.cmd_boot()
            print("  [boot] hello_ack 已发送，持续监听上行消息，Ctrl+C 退出")
            while True:
                time.sleep(1)
        elif cmd == "ping":
            bridge.cmd_ping()
            print("  [ping] 已发送，等待 pong（自动打印）...")
            time.sleep(3)
        else:
            wait = not args.no_wait
            type_, _, default_ack = CMD_DEFS[cmd]
            if cmd == "face":
                if not args.args:
                    print("[错误] 缺少表情参数：face <happy|sad|idle|sleep|surprise|thinking>")
                    return 1
                result = bridge.cmd_face(args.args[0]) if wait else bridge.send("face", {"expr": args.args[0]}, wait_ack=False)
            elif cmd == "text":
                result = bridge.cmd_text(" ".join(args.args)) if wait else bridge.send("text", {"text": " ".join(args.args)}, wait_ack=False)
            elif cmd == "servo":
                if len(args.args) < 2:
                    print("[错误] 缺少参数：servo <ch> <angle>")
                    return 1
                result = bridge.cmd_servo(int(args.args[0]), int(args.args[1])) if wait else bridge.send("servo", {"ch": int(args.args[0]), "angle": int(args.args[1])}, wait_ack=False)
            elif cmd == "move":
                speed = int(args.args[1]) if len(args.args) > 1 else 60
                result = bridge.cmd_move(args.args[0], speed) if wait else bridge.send("move", {"cmd": args.args[0], "speed": speed}, wait_ack=False)
            elif cmd == "mode":
                result = bridge.cmd_mode(args.args[0]) if wait else bridge.send("mode", {"mode": args.args[0]}, wait_ack=False)
            elif cmd == "locate":
                result = bridge.cmd_locate(args.args[0]) if wait else bridge.send("locate", {"cmd": args.args[0]}, wait_ack=False)
            else:  # reboot
                result = bridge.cmd_reboot() if wait else bridge.send("reboot", wait_ack=False)

            if result is not None:
                ok = _print_ack(result)
                return 0 if ok else 2
    except KeyboardInterrupt:
        print("\n已中断")
    finally:
        bridge.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
