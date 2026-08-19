# -*- coding: utf-8 -*-
"""
Agent 工具注册表

集中维护：
- TOOLS：OpenAI function calling schema（喂给 M3）
- TOOL_FUNCS：name → 可调用函数
- DANGER：name → 危险级别（low / medium / high），agent.py 据此决定是否弹确认

新增工具三步：
1. 在 tools/ 下新建模块实现函数
2. 在此 import 并注册到 TOOL_FUNCS / TOOLS / DANGER
"""
from .launch_app import launch_app
from .shell import run_shell
from .scheduler import schedule_reminder
from .type_to_app import type_to_app

# 函数注册表：name → fn(**kwargs) -> str
TOOL_FUNCS = {
    "launch_app": launch_app,
    "type_to_app": type_to_app,
    "shell": run_shell,
    "scheduler": schedule_reminder,
}

# 危险级别：
#   low    = 无副作用（如定时提醒）
#   medium = 有副作用但可控（如启动白名单应用）
#   high   = 直接影响系统（如模拟输入、执行命令）→ 必须用户确认
DANGER = {
    "launch_app": "medium",
    "type_to_app": "high",
    "shell": "high",
    "scheduler": "low",
}

# OpenAI function calling schema（M3 兼容）
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "launch_app",
            "description": "启动白名单中的应用（记事本、计算器、浏览器等）。应用必须已登记在 config.yaml 的 apps 段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "白名单中的应用 key，如 notepad / calculator / chrome / explorer",
                    }
                },
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_to_app",
            "description": "向白名单应用的窗口输入文本（激活窗口后粘贴，支持中文）。若应用未打开会先启动。",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "白名单中的应用 key，如 notepad",
                    },
                    "text": {
                        "type": "string",
                        "description": "要输入的文本内容",
                    },
                    "press_enter": {
                        "type": "boolean",
                        "description": "输入后是否按回车（默认 false）",
                    },
                },
                "required": ["app_name", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "执行白名单中的命令（只读为主，如 git status / git log / dir / tasklist）。仅允许 config.yaml 的 commands 白名单前缀。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的命令，必须是白名单前缀，如 dir、git status",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scheduler",
            "description": "设置定时提醒（一次性），到点后电脑会提示。适合会议提醒、待办提醒等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "number",
                        "description": "多少秒后提醒",
                    },
                    "message": {
                        "type": "string",
                        "description": "提醒内容",
                    },
                },
                "required": ["seconds", "message"],
            },
        },
    },
]


def tool_names() -> str:
    """返回可用工具名列表（供提示词/调试）。"""
    return "、".join(TOOL_FUNCS.keys())
