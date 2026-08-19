# -*- coding: utf-8 -*-
"""
工具：定时任务 / 主动提醒（scheduler）

基础版：一次性延时提醒。到点后打印并（可选）回调播报函数。
Phase 2 语音闭环接入后，可把 notify 钩子接到 TTS 播报。
"""
import threading
import time
from datetime import datetime

_reminders: list = []
_lock = threading.Lock()


def _format_eta(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)} 秒"
    if seconds < 3600:
        return f"{seconds / 60:.1f} 分钟"
    return f"{seconds / 3600:.1f} 小时"


def schedule_reminder(seconds: float, message: str,
                      notify=None) -> str:
    """设置 seconds 秒后提醒，返回确认描述。

    notify: 可选回调 notify(text)，到点触发（可接 TTS）。
    """
    seconds = max(1.0, float(seconds))
    eta = _format_eta(seconds)
    due = datetime.now().strftime("%H:%M:%S")

    def _fire():
        time.sleep(seconds)
        line = f"⏰ 提醒：{message}"
        print(line)
        if notify:
            try:
                notify(message)
            except Exception:
                pass

    threading.Thread(target=_fire, daemon=True).start()
    with _lock:
        _reminders.append({"message": message, "eta_seconds": seconds, "due": due})
    return f"已设置 {eta} 后提醒：{message}"


def list_reminders() -> str:
    """列出当前挂起的提醒（调试用）。"""
    with _lock:
        if not _reminders:
            return "当前无挂起提醒"
        lines = [f"{i + 1}. {r['message']}（{r['eta_seconds']:.0f} 秒后）"
                 for i, r in enumerate(_reminders)]
        return "\n".join(lines)


if __name__ == "__main__":
    # 自测：python -m tools.scheduler
    print(schedule_reminder(3, "测试提醒"))
    time.sleep(4)
    print("done")
