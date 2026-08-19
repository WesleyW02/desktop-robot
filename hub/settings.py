# -*- coding: utf-8 -*-
"""
全局配置加载器（settings.py）

从项目根目录的 config.yaml 统一读取配置，并合并环境变量兜底。

加载优先级（从高到低）：
    1. 环境变量（如 MINIMAX_API_KEY）
    2. config.yaml（项目根目录优先，其次 hub/ 目录）
    3. 代码内置默认值（见 _DEFAULTS）

用法：
    from settings import load_config, get, resolve_api_key

    cfg = load_config()                     # 全量配置
    port = get("serial.port", "COM3")       # 按 a.b.c 路径取值
    key  = resolve_api_key()                # API Key（环境变量 > config.yaml）
"""
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# 项目根目录 = 本文件所在目录的上一级（桌面机器人/）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# config.yaml 候选位置（按优先级）
CONFIG_CANDIDATES = [
    PROJECT_ROOT / "config.yaml",                          # 项目根目录（推荐）
    Path(__file__).resolve().parent / "config.yaml",       # hub/ 目录（兼容）
]

_DEFAULTS: Dict[str, Any] = {
    "minimax": {
        "api_key": "",
        "api_key_env": "MINIMAX_API_KEY",
        "base_url": "https://api.minimaxi.com/v1",
        "model_chat": "MiniMax-M3",
        "model_tts": "speech-2.8-hd",
        "model_asr": "minimax-asr-01",
        "tts_voice": "female-shaonv",
    },
    "serial": {
        "port": "COM3",
        "baudrate": 921600,
    },
    "apps": {},
    "commands": [],
}

_cache: Optional[Dict[str, Any]] = None


def _find_config() -> Optional[Path]:
    """返回实际存在的 config.yaml 路径（无则 None）。"""
    for p in CONFIG_CANDIDATES:
        if p.exists():
            return p
    return None


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并字典：override 覆盖 base（子字典按 key 合并）。"""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config() -> Dict[str, Any]:
    """读取并缓存全局配置（config.yaml 不存在时返回默认值）。"""
    global _cache
    if _cache is not None:
        return _cache

    data: Dict[str, Any] = {}
    cfg_path = _find_config()
    if cfg_path is not None:
        with open(cfg_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
            if isinstance(loaded, dict):
                data = loaded

    _cache = _deep_merge(_DEFAULTS, data)
    _cache["_config_path"] = str(cfg_path) if cfg_path else None
    return _cache


def reload() -> None:
    """清空缓存，强制下次重新读取（改配置后调用）。"""
    global _cache
    _cache = None


def get(key_path: str, default: Any = None) -> Any:
    """按 'a.b.c' 路径取值，缺失返回 default。"""
    cur: Any = load_config()
    for part in key_path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def resolve_api_key() -> Optional[str]:
    """API Key 解析：环境变量 > config.yaml 的 api_key 字段。

    返回 None 表示未配置（调用方给出友好提示）。
    """
    env_name = get("minimax.api_key_env", "MINIMAX_API_KEY") or "MINIMAX_API_KEY"
    val = os.environ.get(env_name) or os.environ.get("MINIMAX_API_KEY")
    if val and val.strip():
        return val.strip()

    val = get("minimax.api_key", "")
    if val and val.strip():
        return val.strip()
    return None


def config_path() -> Optional[str]:
    """返回实际生效的 config.yaml 路径（未找到返回 None）。"""
    return get("_config_path", None)
