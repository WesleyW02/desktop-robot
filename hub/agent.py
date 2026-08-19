# -*- coding: utf-8 -*-
"""
Agent 核心：M3 对话 + 工具调用循环（Phase 3）

流程：
    M3 返回 tool_calls → 解析 → 安全确认 → 执行工具 → 结果回填 → 再问 M3
    循环直至 M3 不再调用工具，输出最终回答。

运行（文本版，控制电脑）：
    hub/.venv/Scripts/python.exe agent.py
    例：输入 "打开记事本" / "列出当前目录文件" / "5分钟后提醒我开会"

安全：所有工具执行前按危险级别确认（见 confirm.py 与 tools.DANGER）。
"""
import json
from typing import Optional

from confirm import confirm_if
from mcp_tools import MCP_PREFIX, McpManager
from minimax_client import MiniMaxClient
from tools import DANGER, TOOL_FUNCS, TOOLS as BASE_TOOLS

# 桌宠人设（含工具使用说明）
SYSTEM_PROMPT = (
    "你是一个名为「小萌」的桌面机器人助手，外形是白色+薄荷绿的可爱胶囊机器人。"
    "你可以使用工具帮用户操作电脑。"
    "规则："
    "1. 用户请求操作电脑时（打开应用、输入内容、执行命令、设置提醒），调用对应工具；"
    "2. 工具执行结果以「工具: 结果」形式返回给你，你需要据此向用户汇报；"
    "3. 若工具结果以「错误」开头，如实告知用户原因；"
    "4. 仅使用提供的工具，不要编造其他工具；"
    "5. 回答控制在 2-3 句话以内，语气亲切可爱，偶尔加拟声词。"
)

MAX_TOOL_ITER = 5  # 单轮对话最多工具调用轮次


def execute_tool(name: str, args: dict, mm=None, mcp: Optional[McpManager] = None) -> str:
    """执行单个工具（内置或 MCP，带安全确认），返回结果字符串。"""
    # MCP 动态工具：mcp_<服务器>_<工具>
    if name.startswith(MCP_PREFIX):
        if mcp is None:
            return f"错误：MCP 工具 {name} 不可用（未连接 MCP 服务器）"
        desc = f"调用 MCP 工具「{name}」参数 {json.dumps(args, ensure_ascii=False)}"
        if not confirm_if("medium", desc, mm=mm):
            return f"用户拒绝了操作：{name}"
        return mcp.call(name, args)

    if name not in TOOL_FUNCS:
        return f"错误：未知工具 {name}"

    desc = f"调用工具「{name}」参数 {json.dumps(args, ensure_ascii=False)}"
    if not confirm_if(DANGER.get(name, "medium"), desc, mm=mm):
        return f"用户拒绝了操作：{name}"

    fn = TOOL_FUNCS[name]
    try:
        return fn(**args)
    except TypeError as e:
        return f"错误：工具参数不正确 {e}"
    except Exception as e:
        return f"错误：工具执行异常 {e}"


def run_agent(mm: MiniMaxClient, messages: list,
              mcp: Optional[McpManager] = None,
              max_iter: int = MAX_TOOL_ITER) -> str:
    """M3 工具调用主循环：直到 M3 不再调用工具，返回最终文本。

    mcp: 可选 McpManager，其动态工具会合并进工具列表。
    """
    # 内置工具 + MCP 动态工具
    tools = list(BASE_TOOLS)
    if mcp is not None:
        tools += mcp.get_schemas()

    for _ in range(max_iter):
        resp = mm.chat(messages, tools=tools)
        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)

        if not tool_calls:
            return (msg.content or "").strip()

        # 追加 assistant 消息（含 tool_calls），回填工具结果
        messages.append(msg.model_dump())
        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
                if not isinstance(args, dict):
                    args = {}
            except json.JSONDecodeError:
                args = {}
            result = execute_tool(name, args, mm=mm, mcp=mcp)
            print(f"\n  [工具] {name}({json.dumps(args, ensure_ascii=False)})")
            print(f"  [结果] {result}")
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    return "（已达最大工具调用轮次，操作未全部完成）"


def main() -> int:
    if not __import__("settings", fromlist=["resolve_api_key"]).resolve_api_key():
        print("[错误] 未找到 MiniMax API Key，请在 config.yaml 的 minimax.api_key 填写或设置环境变量 MINIMAX_API_KEY")
        return 1

    mm = MiniMaxClient()
    messages = [mm.sys_msg(SYSTEM_PROMPT)]

    # 启动 MCP 服务器（后台连接，动态注册工具）
    mcp = McpManager()
    if mcp.is_configured():
        if mcp.wait_ready(timeout=8):
            print(f"  [MCP] 已连接 {len(mcp.servers_cfg)} 个服务器，工具: {'、'.join(mcp.tool_names())}")
        else:
            print("  [MCP] 连接超时（检查 config.yaml 的 mcp.servers 配置）")
    else:
        print("  [MCP] 未配置服务器（config.yaml → mcp.servers）")

    print("=" * 50)
    print("  小萌 Agent 模式（Phase 3 · 可控制电脑 + MCP 扩展）")
    print("  试试：打开记事本 / 列出当前目录文件 / 现在几点 / 5分钟后提醒我喝水")
    print("  退出：exit")
    print("=" * 50)

    while True:
        try:
            user_input = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见 ~")
            break
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "退出"):
            print("小萌: 拜拜，记得想我哦~")
            break

        messages.append(mm.user_msg(user_input))
        try:
            reply = run_agent(mm, messages, mcp=mcp)
            print(f"\n小萌: {reply}")
            messages.append(mm.asst_msg(reply))
        except Exception as e:
            print(f"\n[错误] {e}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
