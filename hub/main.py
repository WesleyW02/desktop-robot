# -*- coding: utf-8 -*-
"""
桌面机器人 · 电脑端 Agent Hub 入口（Phase 3 · 文本交互 + 工具调用）

功能：键盘输入 → M3 对话（可调用工具控制电脑）→ TTS 合成 → 电脑播放语音
      验证「本地 Agent ↔ MiniMax 联通」与工具调用链路，不依赖任何硬件。

运行：
    配置 API Key（二选一）：
      A. 编辑项目根目录 config.yaml → minimax.api_key
      B. 环境变量：set MINIMAX_API_KEY=sk-xxx
    python main.py

退出：输入 exit / quit
"""
import os
import sys
import tempfile
import winsound  # Windows 内置音频播放（纯 WAV）

from agent import SYSTEM_PROMPT, run_agent
from minimax_client import MiniMaxClient
from settings import resolve_api_key


def play_wav_bytes(data: bytes) -> None:
    """把 WAV 字节写入临时文件并播放（Windows winsound）。"""
    fd, path = tempfile.mkstemp(suffix=".wav")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        winsound.PlaySound(path, winsound.SND_FILENAME)
    finally:
        if os.path.exists(path):
            os.remove(path)


def main() -> int:
    if not resolve_api_key():
        print("[错误] 未找到 MiniMax API Key，请二选一配置：")
        print("  A. 编辑项目根目录 config.yaml → minimax.api_key 字段")
        print("  B. 设置环境变量：PowerShell 用 $env:MINIMAX_API_KEY=\"sk-xxx\"")
        return 1

    mm = MiniMaxClient()
    messages = [mm.sys_msg(SYSTEM_PROMPT)]
    print("=" * 50)
    print("  小萌已上线（Phase 3 · 文本交互 + 工具调用）")
    print("  试试：打开记事本 / 列出当前目录文件 / 5分钟后提醒我喝水")
    print("  输入内容按回车对话，exit 退出")
    print("=" * 50)

    while True:
        try:
            user_input = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见 ~")
            break
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "退出"):
            print("小萌: 拜拜，记得想我哦~")
            break

        messages.append(mm.user_msg(user_input))
        try:
            # 1) M3 对话 + 工具调用循环
            reply = run_agent(mm, messages)
            messages.append(mm.asst_msg(reply))
            print(f"\n小萌: {reply}")

            # 2) TTS 合成 + 播放
            print("  [语音] 合成中...")
            audio = mm.synthesize(reply)
            play_wav_bytes(audio)
        except Exception as e:
            print(f"[错误] {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
