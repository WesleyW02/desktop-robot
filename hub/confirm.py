# -*- coding: utf-8 -*-
"""
安全确认机制（confirm.py）

危险操作分级 + 执行前确认：
- low    ：无副作用，直接执行
- medium ：有副作用但可控（白名单应用），直接执行（或可配置确认）
- high   ：直接影响系统（模拟输入 / 执行命令），必须用户确认

确认方式（Phase 3 文本版）：
- 控制台输入 y / yes 确认，n / no 拒绝
- 若传入 mm（MiniMax 客户端），先 TTS 播报询问（让用户"听"到问题）

Phase 2 语音闭环后，可在此接入语音确认（用户说"可以"即放行）。
"""
import re
import sys
import threading

# 是否开启确认（调试时可设 False 跳过；生产保持 True）
CONFIRM_ENABLED = True


def _say(mm, text: str) -> None:
    """可选：用 MiniMax TTS 播报询问（后台线程，不阻塞）。"""
    if mm is None:
        return
    def _run():
        try:
            mm.synthesize(text)  # 播放交给调用方/播放器
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def _parse_answer(ans: str, default: bool) -> bool:
    """宽松解析确认输入。

    放行：输入以 y/yes/是/确定 开头或结尾，或整句包含独立的确认词；
    拒绝：输入以 n/no/否/不 开头或结尾，或包含否定词；
    无法识别 → 默认拒绝（安全优先）。
    """
    a = (ans or "").strip().lower()
    if not a:
        return default

    if a.startswith(("y", "yes", "是", "确", "放行", "可以", "好的")):
        return True
    if a.startswith(("n", "no", "否", "拒", "不要", "不行", "不可以")):
        return False
    if a.endswith(("y", "yes", "是", "确定", "放行")):
        return True
    if a.endswith(("n", "no", "否", "拒绝")):
        return False

    # 整句包含确认词 / 否定词（\b 保证 y/n 是独立词，避免误匹配）
    if re.search(r"\b(?:yes|y)\b", a) or "是" in a or "确定" in a:
        return True
    if re.search(r"\b(?:no|n)\b", a) or "拒绝" in a or "不要" in a or "不行" in a:
        return False
    return default  # 无法识别 → 用默认值（默认拒绝）


def confirm(question: str, mm=None, default: bool = False) -> bool:
    """向用户确认一个动作，返回是否放行。

    mm 非空时先 TTS 播报；随后控制台等待输入。
    输入 y/是/确定（或包含这些词）放行；n/否/不要 拒绝；空回车用默认值。
    """
    if not CONFIRM_ENABLED:
        return True

    _say(mm, question)
    prompt = f"\n⚠️ 安全确认：{question}\n  输入 y 放行 / n 拒绝 [{'Y/n' if default else 'y/N'}]: "
    try:
        ans = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("\n（未确认，已拒绝）")
        return False
    return _parse_answer(ans, default)


def confirm_if(level: str, desc: str, mm=None) -> bool:
    """按危险级别决定是否确认。

    规则：
      low / medium → 直接放行（medium 已由白名单约束）
      high         → 弹确认
    """
    if level == "high":
        return confirm(f"{desc}？", mm=mm)
    return True


if __name__ == "__main__":
    # 自测：python confirm.py
    print("放行" if confirm_if("high", "执行模拟输入测试") else "拒绝")
