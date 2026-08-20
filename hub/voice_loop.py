# -*- coding: utf-8 -*-
"""
语音闭环（voice_loop.py）— Phase 2 Hub 侧完整实现

流程：语音输入 → VAD 静音检测 → 本地 ASR 转写 → ReAct Agent(M3) 回复
      → TTS 合成 → 语音播放，实现免按键语音对话闭环。

两种输入源（CLI 选择）：
    mic    电脑麦克风（sounddevice）—— 不依赖硬件，本地即可完整测试
    serial ESP32 串口音频流（serial_bridge 接 vad/audio 事件）—— 板子到货用

用法：
    hub/.venv/Scripts/python.exe voice_loop.py mic
    hub/.venv/Scripts/python.exe voice_loop.py serial --port COM3

说明：
    - 说话即触发（能量超过 VAD_ENERGY），静音 SILENCE_MS 自动结束
    - 回复通过系统喇叭播放；串口模式下同时下发 play 到机器人喇叭
    - 退出：Ctrl+C
"""
import argparse
import base64
import io
import sys
import tempfile
import time
import wave
from typing import Optional

import numpy as np

from agent import SYSTEM_PROMPT, run_agent
from asr import local_transcribe
from minimax_client import MiniMaxClient
from mcp_tools import McpManager
from settings import resolve_api_key

# ---- 音频参数（与固件 config.h 一致）----
SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_MS = 100                    # 采集块时长
BLOCK = SAMPLE_RATE * BLOCK_MS // 1000  # 每块样本数（1600）

# ---- VAD 参数（按环境调参）----
VAD_ENERGY = 800.0                # 说话起始能量阈值（int16 RMS）
SILENCE_MS = 800                  # 静音结束判定


def pcm16_to_wav(pcm: bytes, rate: int = SAMPLE_RATE, channels: int = CHANNELS) -> bytes:
    """PCM16 裸数据 → WAV 字节（供 ASR 解码）。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def play_wav_bytes(data: bytes) -> None:
    """播放 WAV 字节（Windows winsound）。"""
    import os
    import winsound
    fd, path = tempfile.mkstemp(suffix=".wav")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        winsound.PlaySound(path, winsound.SND_FILENAME)
    finally:
        if os.path.exists(path):
            os.remove(path)


class VoiceLoop:
    """语音闭环核心：处理一段语音（PCM）→ 文字 → 回复 → 语音。"""

    def __init__(self, energy: float = VAD_ENERGY, silence_ms: int = SILENCE_MS):
        self.mm = MiniMaxClient()
        self.mcp = McpManager()
        self.mcp.wait_ready(timeout=8)
        self.messages = [self.mm.sys_msg(SYSTEM_PROMPT)]
        self._busy = False
        self.energy = energy        # VAD 能量阈值
        self.silence_ms = silence_ms  # 静音结束判定
        # 串口模式回调桥（由 serial 模式设置）
        self.on_reply = None   # callable(reply_text) -> 可选下发机器人

    # ---------- 语音 → 处理 ----------
    def process_audio(self, pcm: bytes) -> str:
        """处理一段 PCM 语音：ASR → Agent → TTS 播放，返回小萌回复。"""
        wav = pcm16_to_wav(pcm)
        text = local_transcribe(wav)
        text = text.strip()
        if not text:
            return ""
        return self.process_text(text)

    def process_text(self, text: str) -> str:
        """处理一句文字：Agent 对话 → TTS 播放，返回小萌回复。"""
        print(f"\n[你] {text}")
        self._busy = True
        try:
            self.messages.append(self.mm.user_msg(text))
            reply = run_agent(self.mm, self.messages, mcp=self.mcp)
            print(f"[小萌] {reply}")
            self.messages.append(self.mm.asst_msg(reply))

            # TTS 合成并播放（本地喇叭）
            print("  [语音] 合成中...")
            audio = self.mm.synthesize(reply)
            play_wav_bytes(audio)

            # 串口模式：同时下发机器人喇叭播放（板子到货）
            if self.on_reply is not None:
                try:
                    self.on_reply(audio)
                except Exception as e:
                    print(f"  [serial] 下发播放失败: {e}")
            return reply
        finally:
            self._busy = False

    # ---------- mic 模式：电脑麦克风 ----------
    def run_mic(self) -> None:
        import sounddevice as sd

        print(f"🎤 麦克风模式（阈值 {self.energy:.0f}，静音 {self.silence_ms}ms 自动结束）")
        print("   说话即可对话，Ctrl+C 退出")

        state = {"capturing": False, "silence": 0, "buf": []}

        def callback(indata, frames, time_info, status):
            block = indata[:, 0]
            energy = float(np.sqrt(np.mean(np.square(block))))
            if state["capturing"]:
                state["buf"].append(block.copy())
                state["silence"] = state["silence"] + BLOCK_MS if energy < self.energy else 0
            elif energy > self.energy and not self._busy:
                state["capturing"] = True
                state["silence"] = 0
                state["buf"] = [block.copy()]

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, blocksize=BLOCK,
                            callback=callback):
            while True:
                if state["capturing"] and state["silence"] > self.silence_ms:
                    state["capturing"] = False
                    pcm = np.concatenate(state["buf"]).astype(np.int16).tobytes()
                    state["buf"] = []
                    self.process_audio(pcm)
                time.sleep(0.05)

    # ---------- serial 模式：ESP32 音频流 ----------
    def run_serial(self, port: Optional[str] = None) -> None:
        from serial_bridge import SerialBridge

        # 收到 vad/audio 事件 → 攒 PCM；vad end → 处理
        audio = {"buf": [], "pts": -1}

        def on_message(msg: dict) -> bool:
            t = msg.get("type")
            if t == "vad":
                if msg.get("state") == "start":
                    audio["buf"] = []
                    audio["pts"] = -1
                elif msg.get("state") == "end" and audio["buf"] and not self._busy:
                    pcm = b"".join(audio["buf"])
                    audio["buf"] = []
                    self.process_audio(pcm)
                return True
            if t == "audio":
                audio["buf"].append(base64.b64decode(msg.get("data", "")))
                return True
            return False  # 其他消息走默认打印

        self.on_reply = lambda wav: self._serial_play(bridge, wav)

        print(f"🔌 串口模式 {port or '(config.yaml)'} @ 921600 ...")
        bridge = SerialBridge(port=port, on_message=on_message)
        try:
            bridge.open()
            print("   已连接，等待机器人语音（vad/audio）...")
            bridge.cmd_boot()
            while True:
                time.sleep(1)
        except RuntimeError as e:
            print(f"[错误] {e}")
        finally:
            bridge.close()

    @staticmethod
    def _serial_play(bridge, wav: bytes) -> None:
        """把 TTS 音频下发机器人喇叭播放（协议 v2.0 play）。"""
        b64 = base64.b64encode(wav).decode("ascii")
        bridge.send("play", {"fmt": "wav_16k", "len": len(wav), "data": b64},
                    wait_ack=True, timeout=10.0)


def main() -> int:
    if not resolve_api_key():
        print("[错误] 未找到 MiniMax API Key，请配置 config.yaml 或环境变量 MINIMAX_API_KEY")
        return 1

    parser = argparse.ArgumentParser(description="桌面机器人 · 语音闭环（Phase 2）")
    parser.add_argument("mode", nargs="?", default="mic", choices=["mic", "serial"],
                        help="mic=电脑麦克风 / serial=ESP32 串口")
    parser.add_argument("--port", "-p", help="串口模式：指定 COM 口（默认读 config.yaml）")
    parser.add_argument("--energy", type=float, default=VAD_ENERGY, help="VAD 能量阈值")
    args = parser.parse_args()

    loop = VoiceLoop(energy=args.energy)
    try:
        if args.mode == "serial":
            loop.run_serial(args.port)
        else:
            loop.run_mic()
    except KeyboardInterrupt:
        print("\n👋 再见 ~")
    return 0


if __name__ == "__main__":
    sys.exit(main())
