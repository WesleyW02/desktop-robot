# -*- coding: utf-8 -*-
"""
工具：白名单命令执行（shell）

命令必须匹配 config.yaml 中 commands 白名单的【前缀】，
默认只建议放只读命令（git status / git log / dir / tasklist 等），
写操作命令（del / rm / git push 等）应加入白名单前慎重评估。
"""
import os
import subprocess
import sys

# 兼容直接运行（python tools/shell.py）：把 hub/ 加入搜索路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from settings import get

MAX_OUTPUT = 2000  # 回填给模型的最大输出字符数


def run_shell(command: str) -> str:
    """执行白名单命令（前缀匹配），返回输出前 MAX_OUTPUT 字符。"""
    allowlist = get("commands", []) or []
    cmd = command.strip()

    if not cmd:
        return "错误：命令为空"
    if not any(cmd.startswith(c) for c in allowlist):
        return f"错误：命令不在白名单中。白名单前缀：{allowlist}"

    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=15, encoding="gbk", errors="replace",
        )
        out = (r.stdout or "") + (r.stderr or "")
        out = out.strip()
        if not out:
            return "(无输出)"
        return out[:MAX_OUTPUT] + ("…(已截断)" if len(out) > MAX_OUTPUT else "")
    except subprocess.TimeoutExpired:
        return "错误：命令执行超时（>15s）"
    except Exception as e:
        return f"执行失败：{e}"


if __name__ == "__main__":
    # 自测：python -m tools.shell "dir"
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dir"
    print(run_shell(cmd))
