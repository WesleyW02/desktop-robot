# -*- coding: utf-8 -*-
"""
技能：send_workbuddy —— 打开 WorkBuddy 并发送消息

给 WorkBuddy 发消息 = 激活窗口 → 输入内容 → 回车发送。
WorkBuddy 未打开时自动启动（路径在 config.yaml → apps.workbuddy.path）。
"""
from typing import Dict


def skill_meta() -> dict:
    return {
        "name": "send_workbuddy",
        "description": (
            "打开 WorkBuddy（若未运行）并把指定消息发送给它（在输入框输入并回车）。"
            "适合让 WorkBuddy 执行任务、提问或转交信息。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "要发送给 WorkBuddy 的消息内容（用第一人称表述，如「帮我总结今天的待办」）",
                }
            },
            "required": ["message"],
        },
        "danger": "high",  # 会真的发送消息，执行前确认
    }


def run(args: dict) -> str:
    msg = (args.get("message") or "").strip()
    if not msg:
        return "错误：消息内容为空"

    from tools.type_to_app import type_to_app

    # type_to_app 内部：激活窗口（找不到则先启动应用）→ 剪贴板粘贴 → 回车
    return type_to_app("workbuddy", msg, press_enter=True)
