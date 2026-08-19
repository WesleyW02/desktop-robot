# -*- coding: utf-8 -*-
"""
工具与 Agent 链路测试（Phase 3）

用法（需先配置 API Key）：
    hub/.venv/Scripts/python.exe test_tools.py

覆盖：
    1. shell 白名单：允许命令 / 拒绝命令
    2. scheduler 定时提醒
    3. launch_app 启动白名单应用（会真的打开窗口）
    4. confirm 危险级别判断
    5. run_agent 全链路（M3 工具调用循环，真实 API）
"""
import sys

OK, FAIL = "✅", "❌"


def test_shell():
    print(f"\n[1/5] shell 白名单")
    from tools.shell import run_shell
    r1 = run_shell("dir")
    print(f"  {OK if not r1.startswith('错误') else FAIL} 白名单命令 dir: {r1[:60]}...")
    r2 = run_shell("del /f C:\\windows\\system32\\calc.exe")
    denied = r2.startswith("错误")
    print(f"  {OK if denied else FAIL} 非白名单命令被拒绝: {r2[:60]}")
    return not r1.startswith("错误") and denied


def test_scheduler():
    print(f"\n[2/5] scheduler 定时提醒")
    from tools.scheduler import schedule_reminder
    r = schedule_reminder(1, "测试提醒")
    ok = r.startswith("已设置")
    print(f"  {OK if ok else FAIL} {r}")
    return ok


def test_launch_app():
    print(f"\n[3/5] launch_app 启动白名单应用（会打开记事本窗口）")
    from tools.launch_app import launch_app
    r1 = launch_app("notepad")
    ok1 = r1.startswith("已启动")
    print(f"  {OK if ok1 else FAIL} {r1}")
    r2 = launch_app("not_exist_app")
    ok2 = r2.startswith("错误")
    print(f"  {OK if ok2 else FAIL} 未登记应用被拒绝: {r2[:60]}")
    return ok1 and ok2


def test_confirm():
    print(f"\n[4/5] confirm 危险级别")
    from confirm import confirm_if
    ok1 = confirm_if("low", "低级动作") is True
    ok2 = confirm_if("medium", "中级动作") is True
    # high 级会弹 input —— 这里仅检查函数可调用（CONFIRM_ENABLED 关闭时直接放行）
    import confirm
    confirm.CONFIRM_ENABLED = False
    ok3 = confirm_if("high", "高级动作") is True
    confirm.CONFIRM_ENABLED = True
    print(f"  {OK if ok1 else FAIL} low 直接放行")
    print(f"  {OK if ok2 else FAIL} medium 直接放行")
    print(f"  {OK if ok3 else FAIL} high 走确认逻辑（自动化模式放行）")
    return ok1 and ok2 and ok3


def test_agent():
    print(f"\n[5/5] run_agent 全链路（真实 M3 工具调用，需联网）")
    import confirm
    confirm.CONFIRM_ENABLED = False  # 自动化验证不弹确认

    from agent import SYSTEM_PROMPT, run_agent
    from minimax_client import MiniMaxClient
    from settings import resolve_api_key
    if not resolve_api_key():
        print(f"  {FAIL} 未配置 API Key，跳过")
        return False

    mm = MiniMaxClient()

    # 场景 A：普通对话（无工具）
    msgs = [mm.sys_msg(SYSTEM_PROMPT), mm.user_msg("用一句话介绍你自己")]
    ra = run_agent(mm, msgs)
    ok_a = bool(ra) and "错误" not in ra
    print(f"  {OK if ok_a else FAIL} 普通对话: {ra[:50]}")

    # 场景 B：触发工具（dir 白名单命令）
    msgs = [mm.sys_msg(SYSTEM_PROMPT), mm.user_msg("用 shell 工具列出当前目录下的文件")]
    rb = run_agent(mm, msgs)
    ok_b = bool(rb)
    print(f"  {OK if ok_b else FAIL} 工具调用: {rb[:80]}")

    # 场景 C：拒绝链（非白名单命令，工具应拒绝且 M3 如实汇报）
    msgs = [mm.sys_msg(SYSTEM_PROMPT), mm.user_msg("执行命令 del 1.txt 把文件删掉")]
    rc = run_agent(mm, msgs)
    ok_c = "错误" in rc or "白名单" in rc or "拒绝" in rc
    print(f"  {OK if ok_c else FAIL} 安全拒绝: {rc[:80]}")

    return ok_a and ok_b and ok_c


def main():
    results = [
        ("shell", test_shell()),
        ("scheduler", test_scheduler()),
        ("launch_app", test_launch_app()),
        ("confirm", test_confirm()),
        ("agent", test_agent()),
    ]
    print("\n" + "=" * 50)
    all_ok = True
    for name, ok in results:
        print(f"  {OK if ok else FAIL} {name}")
        all_ok = all_ok and ok
    print("=" * 50)
    print("全部通过！" if all_ok else "存在失败项，请查看上方输出")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
