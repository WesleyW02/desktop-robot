# -*- coding: utf-8 -*-
"""
工具：激活窗口 + 模拟输入（type_to_app）

流程：激活目标应用窗口（pygetwindow）→ 剪贴板粘贴文本（支持中文）→ 可选回车。
窗口标题关键词在 config.yaml 的 apps.<key>.window_title 配置。
"""
import time

import pyautogui
import pygetwindow as gw
import pyperclip

from settings import get


def _find_window(title_kw):
    """按标题关键词查找可见窗口（支持字符串或关键词列表，任一匹配）。

    取第一个匹配且非空的窗口。关键词列表用于兼容中英文系统标题
    （如 notepad 的 window_title 可配 ["记事本", "Notepad"]）。
    """
    keywords = [title_kw] if isinstance(title_kw, str) else list(title_kw or [])
    try:
        wins = [w for w in gw.getAllWindows()
                if w.title and any(k.lower() in w.title.lower() for k in keywords)]
    except Exception:
        return None
    return wins[0] if wins else None


def activate_window(title_kw: str) -> bool:
    """激活匹配标题的窗口；找不到返回 False。"""
    w = _find_window(title_kw)
    if w is None:
        return False
    try:
        w.activate()
        return True
    except Exception:
        # 部分窗口 activate 受限，用最小化/恢复兜底
        try:
            w.minimize()
            w.restore()
            w.activate()
            return True
        except Exception:
            return False


def type_to_app(app_name: str, text: str, press_enter: bool = False) -> str:
    """向白名单应用的窗口输入文本（中文走剪贴板粘贴）。

    若窗口未打开则先尝试启动它，再等待窗口出现。
    """
    apps = get("apps", {}) or {}
    info = apps.get(app_name)
    if not info:
        names = "、".join(apps.keys()) if apps else "(空)"
        return f"错误：应用「{app_name}」不在白名单中，可选：{names}"

    title_kw = info.get("window_title") or info.get("name") or app_name
    display = info.get("name", app_name)

    if not activate_window(title_kw):
        # 窗口未开 → 尝试启动
        from tools.launch_app import launch_app
        launch_app(app_name)
        time.sleep(1.5)
        if not activate_window(title_kw):
            kws = title_kw if isinstance(title_kw, list) else [title_kw]
            return f"错误：无法找到或激活「{display}」的窗口（关键词：{'/'.join(kws)}）"

    time.sleep(0.3)
    try:
        # 中文等非 ASCII 必须走剪贴板
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        if press_enter:
            time.sleep(0.2)
            pyautogui.press("enter")
        return f"已向「{display}」输入内容"
    except Exception as e:
        return f"向「{display}」输入失败：{e}"


if __name__ == "__main__":
    # 自测：python -m tools.type_to_app notepad "你好世界"
    import sys
    app = sys.argv[1] if len(sys.argv) > 1 else "notepad"
    text = sys.argv[2] if len(sys.argv) > 2 else "你好，我是小萌"
    print(type_to_app(app, text))
