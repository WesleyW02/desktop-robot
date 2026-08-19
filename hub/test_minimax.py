# -*- coding: utf-8 -*-
"""
MiniMax 联通测试脚本（Phase 0）

验证三件事：
  1. API Key 是否有效
  2. M3 对话接口是否可用
  3. TTS 合成接口是否可用（生成 test_tts.wav 并尝试播放）
  4. ASR 转写接口（可选，需要音频文件参数）

用法：
    配置 API Key（二选一）：
      A. 编辑项目根目录 config.yaml → minimax.api_key
      B. 环境变量：set MINIMAX_API_KEY=sk-xxx
    python test_minimax.py                 # 跑 1-3
    python test_minimax.py --asr audio.wav # 加跑 ASR

通过标准：全部打印 ✅
"""
import argparse
import os
import sys

from minimax_client import MiniMaxClient
from settings import resolve_api_key

OK = "✅"
FAIL = "❌"


def test_chat(mm: MiniMaxClient) -> None:
    print("\n[1/3] M3 对话接口")
    try:
        result = mm.timed_chat([mm.sys_msg("你是测试助手，简短回答"), mm.user_msg("说一句你好")])
        print(f"  {OK} 返回: {result['text']}")
        print(f"  {OK} 模型: {result['model']}，耗时 {result['elapsed_ms']}ms")
    except Exception as e:
        print(f"  {FAIL} 对话失败: {e}")
        print("  可能原因：Key 无效 / 模型名不对 / 套餐无此模型权限")
        sys.exit(1)


def test_tts(mm: MiniMaxClient) -> None:
    print("\n[2/3] TTS 语音合成接口")
    try:
        audio = mm.synthesize("你好呀，我是小萌，很高兴见到你")
        out = "test_tts.wav"
        with open(out, "wb") as f:
            f.write(audio)
        print(f"  {OK} 合成成功: {len(audio)} 字节 → {out}")
        # 尝试播放（Windows winsound）
        try:
            import winsound
            winsound.PlaySound(out, winsound.SND_FILENAME)
            print(f"  {OK} 已播放（应能听到声音）")
        except Exception:
            print("  （未播放：非 Windows 或无声卡，可手动打开 test_tts.wav 试听）")
    except Exception as e:
        print(f"  {FAIL} TTS 失败: {e}")
        print("  提示：Token Plan 走原生端点 /v1/t2a_v2，检查模型名（speech-2.8-hd）与音色 voice_id")


def test_asr(mm: MiniMaxClient, audio_path: str) -> None:
    print("\n[3/3] ASR 语音转写（Token Plan 无云端 ASR，改测本地 faster-whisper）")
    try:
        from asr import local_transcribe
    except ImportError:
        print(f"  {FAIL} 本地 ASR 未就绪（hub/asr.py 不存在）")
        print("     说明：Token Plan 平台未提供 ASR 接口（实测全 404），")
        print("           语音闭环的转写改用本地 faster-whisper（免费/离线/隐私好，RTX 5070 可 GPU 加速）")
        return
    try:
        with open(audio_path, "rb") as f:
            audio = f.read()
        text = local_transcribe(audio)
        print(f"  {OK} 本地转写结果: {text}")
    except Exception as e:
        print(f"  {FAIL} 本地 ASR 失败: {e}")


def main() -> int:
    if not resolve_api_key():
        print("[错误] 未找到 MiniMax API Key，请二选一配置：")
        print("  A. 编辑项目根目录 config.yaml → minimax.api_key 字段")
        print("  B. 设置环境变量：PowerShell 用 $env:MINIMAX_API_KEY=\"sk-xxx\"")
        return 1

    mm = MiniMaxClient()
    print("MiniMax 联通测试开始")
    print(f"  base_url: {mm.base_url}")
    print(f"  chat模型: {mm.model_chat} | tts: {mm.model_tts} | asr: {mm.model_asr}")

    test_chat(mm)
    test_tts(mm)

    parser = argparse.ArgumentParser()
    parser.add_argument("--asr", metavar="AUDIO_FILE", help="指定 WAV 音频文件以测试 ASR")
    args, _ = parser.parse_known_args()
    if args.asr:
        test_asr(mm, args.asr)
    else:
        print("\n[3/3] ASR 跳过（无音频文件，可用 --asr xxx.wav 指定，将走本地 faster-whisper）")

    print("\n全部测试完成。1-2 全部 ✅ 说明 Agent ↔ MiniMax 联通成功；ASR 走本地方案。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
