# -*- coding: utf-8 -*-
"""
MiniMax API 客户端：ASR（语音转写）/ M3（对话+工具）/ TTS（语音合成）三接口封装。

使用 OpenAI 兼容协议（openai SDK + 自定义 base_url），
模型名/端点按你的 Token Plan 平台实际情况调整（见 config.yaml）。

用法：
    from minimax_client import MiniMaxClient
    mm = MiniMaxClient()                     # 自动读 config.yaml / 环境变量 MINIMAX_API_KEY
    reply = mm.chat([mm.user_msg("你好")])
    audio = mm.synthesize("你好呀")
    text  = mm.transcribe(audio_bytes)

配置来源（优先级从高到低）：
    1. 构造函数显式传入（api_key / base_url / model_*）
    2. 环境变量 MINIMAX_API_KEY
    3. 项目根目录 config.yaml（见 settings.py）
    4. 内置默认值 DEFAULT_*
"""
import time
from typing import List, Dict, Optional, Any

import requests

from openai import OpenAI

from settings import load_config, resolve_api_key

DEFAULT_BASE_URL = "https://api.minimaxi.com/v1"

# 模型名默认值（如平台有出入，在 config.yaml 里覆盖）
DEFAULT_MODEL_CHAT = "MiniMax-M3"
DEFAULT_MODEL_TTS  = "speech-2.8-hd"
DEFAULT_MODEL_ASR  = "minimax-asr-01"
DEFAULT_TTS_VOICE  = "female-shaonv"


def _decode_audio(resp_json: dict) -> bytes:
    """从 t2a_v2 响应中提取并解码音频字节（兼容 hex / base64 / 二进制）。

    Token Plan 的 t2a_v2 默认返回 {"data": {"audio": "<hex字符串>"}}，
    需 hex 解码后才能得到可播放的 wav/mp3 字节。
    """
    data = resp_json.get("data", resp_json) if isinstance(resp_json, dict) else {}
    audio = data.get("audio", "")
    if isinstance(audio, str):
        s = audio.strip()
        # 1) hex（最常见）
        try:
            return bytes.fromhex(s)
        except ValueError:
            pass
        # 2) base64
        try:
            import base64
            return base64.b64decode(s)
        except Exception:
            pass
        raise ValueError(
            f"无法解码 TTS 音频：audio 字段既不是 hex 也不是 base64（前 100 字符：{s[:100]!r}）"
        )
    if isinstance(audio, (bytes, bytearray)):
        return bytes(audio)
    raise ValueError(f"TTS 响应缺少可用的 audio 字段：{str(resp_json)[:200]}")


class MiniMaxClient:
    """MiniMax 客户端：统一封装对话 / 转写 / 合成三个能力。"""

    def __init__(self,
                 api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 model_chat: Optional[str] = None,
                 model_tts: Optional[str] = None,
                 model_asr: Optional[str] = None,
                 tts_voice: Optional[str] = None) -> None:
        # 从 config.yaml 读取 minimax 段（无则用默认值）
        cfg = load_config().get("minimax", {})

        self.api_key = api_key or resolve_api_key()
        if not self.api_key:
            raise ValueError(
                "缺少 MiniMax API Key：请在项目根目录 config.yaml 的 "
                "minimax.api_key 字段填写，或设置环境变量 "
                f"{cfg.get('api_key_env') or 'MINIMAX_API_KEY'}。"
            )
        self.base_url = base_url or cfg.get("base_url") or DEFAULT_BASE_URL
        self.model_chat = model_chat or cfg.get("model_chat") or DEFAULT_MODEL_CHAT
        self.model_tts = model_tts or cfg.get("model_tts") or DEFAULT_MODEL_TTS
        self.model_asr = model_asr or cfg.get("model_asr") or DEFAULT_MODEL_ASR
        self.tts_voice = tts_voice or cfg.get("tts_voice") or DEFAULT_TTS_VOICE
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    # ------------------------------------------------------------------
    # 消息构造工具
    # ------------------------------------------------------------------
    @staticmethod
    def sys_msg(content: str) -> Dict[str, str]:
        return {"role": "system", "content": content}

    @staticmethod
    def user_msg(content: str) -> Dict[str, str]:
        return {"role": "user", "content": content}

    @staticmethod
    def asst_msg(content: str) -> Dict[str, str]:
        return {"role": "assistant", "content": content}

    # ------------------------------------------------------------------
    # 对话（M3，支持工具调用）
    # ------------------------------------------------------------------
    def chat(self,
             messages: List[Dict[str, str]],
             tools: Optional[List[Dict]] = None,
             temperature: float = 0.7,
             max_tokens: Optional[int] = None) -> Any:
        """调用 M3 对话接口。

        messages: [{"role":"system"|"user"|"assistant","content":...}, ...]
        tools:    OpenAI 格式的工具定义列表（function calling）
        返回 openai ChatCompletion 对象，回复文本取 resp.choices[0].message.content
        """
        kwargs = {
            "model": self.model_chat,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        return self.client.chat.completions.create(**kwargs)

    # ------------------------------------------------------------------
    # 语音转写（ASR）— ⚠️ Token Plan 当前不支持！
    #
    # 实测（2026-08）：api.minimaxi.com/v1 下 /asr、/audio/transcriptions、
    # /audio/transcribe、/stt、/speech_recognition 全部 404（路由不存在），
    # 官方文档亦无 ASR 页面。Token Plan 语音能力仅 TTS（t2a_v2）。
    #
    # 语音闭环的转写方案改为【本地 ASR】（见 hub/asr.py，faster-whisper 封装）：
    #   from asr import local_transcribe
    #   text = local_transcribe(audio_bytes)
    # 本方法保留仅为将来 Token Plan 开放 ASR 后的兼容占位。
    # ------------------------------------------------------------------
    def transcribe(self,
                   audio_bytes: bytes,
                   filename: str = "record.wav",
                   language: str = "zh") -> str:
        raise NotImplementedError(
            "Token Plan 平台未提供 ASR 接口（/v1/asr、/v1/audio/transcriptions 均 404）。\n"
            "请改用本地 ASR：from asr import local_transcribe; text = local_transcribe(audio_bytes)"
        )

    # ------------------------------------------------------------------
    # 语音合成（TTS）— Token Plan 原生端点 POST /v1/t2a_v2
    # 注意：Token Plan 平台不支持 OpenAI 兼容的 /audio/speech（404），
    #       必须用官方原生端点；响应中 data.audio 为 hex 编码，需解码。
    # ------------------------------------------------------------------
    def synthesize(self,
                   text: str,
                   voice: Optional[str] = None,
                   response_format: str = "wav",
                   sample_rate: int = 24000) -> bytes:
        """语音合成：返回音频字节（默认 wav，可直接播放/下发）。"""
        url = f"{self.base_url}/t2a_v2"
        payload = {
            "model": self.model_tts,
            "text": text,
            "stream": False,
            "voice_setting": {
                "voice_id": voice or self.tts_voice,
                "speed": 1.0,
                "vol": 1.0,
                "pitch": 0,
            },
            "audio_setting": {
                "sample_rate": sample_rate,
                "bitrate": 128000,
                "format": response_format,
                "channel": 1,
            },
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            return _decode_audio(resp.json())
        except Exception as e:
            raise RuntimeError(
                f"TTS 调用失败：{e}\n"
                f"提示：Token Plan 使用原生端点 /v1/t2a_v2，检查模型名（speech-2.8-hd）"
                f"与音色 voice_id（如 female-shaonv / male-qn-qingse）是否有效。"
            )

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    def timed_chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """对话并返回耗时（用于联通测试/诊断）。"""
        t0 = time.time()
        resp = self.chat(messages, **kwargs)
        return {
            "text": resp.choices[0].message.content or "",
            "elapsed_ms": int((time.time() - t0) * 1000),
            "model": resp.model,
        }
