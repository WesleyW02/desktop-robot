# -*- coding: utf-8 -*-
"""
本地语音转写（ASR）— faster-whisper 封装
=========================================

背景：MiniMax Token Plan 平台未提供 ASR 接口（实测 /v1/asr、
/audio/transcriptions 等端点全部 404），语音闭环的"声音→文字"
环节改用本地 faster-whisper 实现：免费、离线、隐私好，
RTX 5070 等 NVIDIA 显卡可切换 GPU 加速（需 ctranslate2 CUDA 版）。

用法：
    from asr import local_transcribe
    text = local_transcribe(wav_bytes)          # 默认 small 模型 / CPU
    text = local_transcribe(wav_bytes, model="base", device="cuda")

模型：首次调用自动从 HuggingFace 下载（国内默认走 hf-mirror.com 镜像）。
      tiny ~75MB / base ~145MB / small ~460MB（推荐，中文够用）/ medium ~1.5GB
      也可下载到本地目录 hub/models/faster-whisper-small/ 直接加载（推荐，
      可避免 huggingface_hub 缓存清理被沙箱拦截，且不重复下载）。

依赖：pip install faster-whisper
"""
import io
import os
import threading
from pathlib import Path
from typing import Optional

# 国内下载模型走镜像（可改为官方源：设置 HF_ENDPOINT=https://huggingface.co）
if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

DEFAULT_MODEL = "small"        # 中文推荐 small；追求更快可换 base
DEFAULT_DEVICE = "cpu"         # 显卡加速改 "cuda"（需 ctranslate2 CUDA 版）
DEFAULT_LANGUAGE = "zh"        # 中文

# 本地模型目录（优先使用；不存在则退回 HuggingFace 下载）
LOCAL_MODEL_DIR = Path(__file__).resolve().parent / "models" / "faster-whisper-small"

_model = None
_model_lock = threading.Lock()


def _resolve_model_path(model: str) -> str:
    """本地目录存在则用本地，否则用模型名（走 HF 下载）。"""
    if model == DEFAULT_MODEL and LOCAL_MODEL_DIR.exists():
        return str(LOCAL_MODEL_DIR)
    return model


def _get_model(model: str, device: str):
    """懒加载模型（进程内只加载一次，多线程安全）。"""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from faster_whisper import WhisperModel
                path = _resolve_model_path(model)
                src = "本地目录" if Path(path).exists() else "HuggingFace"
                print(f"[asr] 加载本地模型 {model}（{src}，device={device}）...")
                _model = WhisperModel(path, device=device, compute_type="int8")
    return _model


def local_transcribe(audio_bytes: bytes,
                     model: str = DEFAULT_MODEL,
                     device: str = DEFAULT_DEVICE,
                     language: str = DEFAULT_LANGUAGE) -> str:
    """语音转写：传入 WAV/PCM 字节，返回识别文本。

    参数：
        audio_bytes: WAV 音频字节（16kHz/16bit/mono 最佳，其他采样率亦可）
        model:       tiny / base / small / medium / large-v3
        device:      cpu / cuda（cuda 需 ctranslate2 CUDA 版 + NVIDIA 驱动）
        language:    zh / en / auto（auto 自动检测）
    返回：
        识别出的文本（可能为空字符串）
    """
    whisper = _get_model(model, device)

    # 内存字节 → 文件对象（faster-whisper 用 PyAV 解码，支持 WAV/MP3 等）
    audio_file = io.BytesIO(audio_bytes)
    segments, info = whisper.transcribe(
        audio_file,
        language=None if language == "auto" else language,
        beam_size=5,
        vad_filter=True,      # 过滤静音段，提升准确率
    )
    texts = [seg.text.strip() for seg in segments if seg.text.strip()]
    return "".join(texts)


def model_status() -> str:
    """返回当前 ASR 模型加载状态（调试用）。"""
    if _model is None:
        return f"未加载（下次转写时加载 {DEFAULT_MODEL}，约 {_model_size_mb(DEFAULT_MODEL)}MB）"
    return f"已加载: {_model.model} / device={_model.device}"


def _model_size_mb(name: str) -> str:
    return {"tiny": "75", "base": "145", "small": "460", "medium": "1500",
            "large-v3": "2900"}.get(name, "?")


if __name__ == "__main__":
    # 自测：python asr.py xxx.wav
    import sys
    if len(sys.argv) < 2:
        print("用法: python asr.py <audio.wav> [model] [device]")
        sys.exit(1)
    with open(sys.argv[1], "rb") as f:
        data = f.read()
    m = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MODEL
    d = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_DEVICE
    print(f"转写中（model={m}, device={d}）...")
    print("结果:", local_transcribe(data, model=m, device=d))
