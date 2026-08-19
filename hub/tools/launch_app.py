# -*- coding: utf-8 -*-
"""
工具：启动白名单应用（launch_app）

应用列表在项目根目录 config.yaml 的 apps 段登记，格式：
    apps:
      notepad:
        name: 记事本
        path: notepad.exe
        window_title: 记事本

仅能启动白名单中登记的应用（语音/Agent 无法启动任意程序）。
"""
import os
import subprocess
import sys

# 兼容直接运行（python tools/launch_app.py）：把 hub/ 加入搜索路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from settings import get


def launch_app(app_name: str) -> str:
    """启动白名单应用，返回执行结果描述。"""
    apps = get("apps", {}) or {}
    info = apps.get(app_name)
    if not info:
        names = "、".join(apps.keys()) if apps else "(空)"
        return f"错误：应用「{app_name}」不在白名单中，可选：{names}"

    path = info.get("path", "")
    display = info.get("name", app_name)
    if not path:
        return f"错误：应用「{display}」未配置 path"

    try:
        # 列表形式启动，避免 shell=True 的命令注入风险
        subprocess.Popen([path], shell=False)
        return f"已启动「{display}」"
    except FileNotFoundError:
        # 兼容系统命令（如 notepad.exe）走 shell
        try:
            subprocess.Popen(path, shell=True)
            return f"已启动「{display}」"
        except Exception as e:
            return f"启动「{display}」失败：{e}"
    except Exception as e:
        return f"启动「{display}」失败：{e}"


if __name__ == "__main__":
    # 自测：python -m tools.launch_app notepad
    import sys
    print(launch_app(sys.argv[1] if len(sys.argv) > 1 else "notepad"))
