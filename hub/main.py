# -*- coding: utf-8 -*-
"""
桌面机器人 · 电脑端 Agent Hub 入口（Phase 0 先行版 · 文本交互）

功能：键盘输入 → MiniMax M3 对话 → TTS 合成 → 电脑播放语音
      验证「本地 Agent ↔ MiniMax」联通，不依赖任何硬件。

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

from minimax_client import MiniMaxClient
from settings import resolve_api_key

# 桌宠人设（系统提示词，可按喜好调整）
SYSTEM_PROMPT = (
    "你是一个名为「小萌」的桌面机器人助手，外形是白色+薄荷绿的可爱胶囊机器人。"
    "你说话简短亲切，喜欢用可爱的语气，偶尔加一点拟声词。"
    "你运行在用户的电脑上，未来可以帮他操作电脑、提醒日程。"
    "回答控制在 2-3 句话以内。"
)


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
    print("  小萌已上线（Phase 0 文本交互）")
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
            # 1) M3 对话
            result = mm.timed_chat(messages)
            reply = result["text"]
            messages.append(mm.asst_msg(reply))
            print(f"\n小萌: {reply}  （{result['elapsed_ms']}ms）")

            # 2) TTS 合成 + 播放
            print("  [语音] 合成中...")
            audio = mm.synthesize(reply)
            play_wav_bytes(audio)
        except Exception as e:
            print(f"[错误] {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
