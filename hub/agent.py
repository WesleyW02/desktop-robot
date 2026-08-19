# -*- coding: utf-8 -*-
"""
Agent 核心：ReAct 框架（Phase 3 v2）
====================================

架构：对话与行动【分流】，行动采用【先规划后执行】的 ReAct 循环。

    ┌─ 分流轮：带完整工具问 M3
    │    ├─ 无工具调用 ──────────────► 直接对话（返回文本，一轮结束）
    │    └─ 有工具调用 ──► 行动模式：
    │          ① 规划轮（Planner）：只暴露 submit_plan 协议工具，
    │             M3 必须先生成 JSON 执行计划（步骤数组）
    │          ② 执行轮（Executor / ReAct）：注入计划上下文，
    │             每步 思考(Reason) → 行动(Act) → 观察(Observe)，
    │             循环直至 M3 判断计划完成并直接给出最终答复
    └─ 对话与行为是两套独立逻辑：对话不规划、行动必规划

运行（文本版，控制电脑）：
    hub/.venv/Scripts/python.exe agent.py
    例：输入 "你好"（直接对话）/ "打开记事本写一句话"（规划+执行）

安全：所有工具执行前按危险级别确认（见 confirm.py 与 tools.DANGER）。
"""
import json
from typing import List, Optional

from confirm import confirm_if
from mcp_tools import MCP_PREFIX, McpManager
from minimax_client import MiniMaxClient
from skills import get_danger as skill_danger, run_skill, skill_names
from tools import DANGER, TOOL_FUNCS, TOOLS as BASE_TOOLS

# 桌宠人设（对话与行动共用的人设基底）
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

# 规划阶段提示词：要求 M3 先产出结构化计划（只允许调用 submit_plan）
PLAN_PROMPT = (
    "你需要调用工具来完成用户的请求。行动之前，先制定一个执行计划。"
    "现在你必须调用 submit_plan 工具提交计划（这是本轮唯一允许的工具）："
    "plan_steps 参数是 JSON 数组，每个元素包含："
    "step（序号）、task（步骤做什么）、tool（预期工具名，可省略）、args（预期参数，可省略）。"
    "要求：计划 3-5 步以内、按执行顺序排列、覆盖用户请求的全部要点。"
    "只提交计划，不要执行其他任何操作。"
)

# 执行阶段提示词：按计划 ReAct 逐步执行
EXEC_PROMPT = (
    "执行计划已经确认。请按计划逐步推进，直到全部完成："
    "1. 每一步先思考（用 <think> 说明当前状态和下一步该做什么），再调用工具；"
    "2. 观察工具返回结果，判断该步是否成功，失败则尝试合理修正或如实说明；"
    "3. 计划全部完成后，直接输出最终答复（不要调用工具）。"
    "4. 不要重复提交计划，不要执行与计划无关的操作。"
)

MAX_TOOL_ITER = 8  # 单轮对话最大工具调用轮次（执行阶段）


# =====================================================================
# 内部协议工具：submit_plan（仅规划阶段暴露）
# =====================================================================
def _submit_plan(plan_steps: str) -> str:
    """【内部协议】接收 M3 提交的 JSON 执行计划，校验后确认。"""
    try:
        steps = json.loads(plan_steps)
        if isinstance(steps, list) and steps:
            return f"计划已接收，共 {len(steps)} 步，可以开始执行"
        return "错误：计划格式不正确，应为非空 JSON 数组"
    except json.JSONDecodeError:
        return "错误：plan_steps 不是合法 JSON"


PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_plan",
        "description": (
            "【内部协议】当需要调用工具完成任务时，必须先调用本工具提交执行计划。"
            "plan_steps 为 JSON 数组字符串，每项含 step/task/tool/args。"
            "提交后等待执行指令，不要重复提交。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plan_steps": {
                    "type": "string",
                    "description": "JSON 数组格式的执行计划，如 [{\"step\":1,\"task\":\"打开记事本\",\"tool\":\"launch_app\",\"args\":{\"app_name\":\"notepad\"}}]",
                }
            },
            "required": ["plan_steps"],
        },
    },
}


# =====================================================================
# 工具执行（带安全确认）
# =====================================================================
def execute_tool(name: str, args: dict, mm=None, mcp: Optional[McpManager] = None) -> str:
    """执行单个工具（内置 / 技能 / MCP，带安全确认），返回结果字符串。"""
    if name == "submit_plan":
        return _submit_plan(args.get("plan_steps", ""))

    # 技能（hub/skills/ 下注册的自定义技能，按技能自身危险级确认）
    if name in skill_names():
        desc = f"执行技能「{name}」参数 {json.dumps(args, ensure_ascii=False)}"
        if not confirm_if(skill_danger(name), desc, mm=mm):
            return f"用户拒绝了操作：{name}"
        return run_skill(name, args)

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


# =====================================================================
# ReAct 三阶段
# =====================================================================
def _parse_args(raw: str) -> dict:
    try:
        args = json.loads(raw or "{}")
        return args if isinstance(args, dict) else {}
    except json.JSONDecodeError:
        return {}


def _chat_once(mm: MiniMaxClient, working: list, tools: list):
    """单次 M3 调用，返回 (message, tool_calls)。"""
    resp = mm.chat(working, tools=tools)
    msg = resp.choices[0].message
    return msg, getattr(msg, "tool_calls", None)


def _planner(mm: MiniMaxClient, working: list, tools: list) -> Optional[list]:
    """规划阶段：M3 必须调 submit_plan 提交 JSON 计划，返回步骤列表。

    失败（未提交计划 / 计划非法）返回 None，由调用方降级处理。
    """
    plan_tools = [PLAN_TOOL]  # 规划轮只暴露协议工具，强制先规划
    msg, tool_calls = _chat_once(mm, working, plan_tools)

    if not tool_calls:
        return None
    for tc in tool_calls:
        if tc.function.name == "submit_plan":
            args = _parse_args(tc.function.arguments)
            raw = args.get("plan_steps", "")
            try:
                steps = json.loads(raw)
                if isinstance(steps, list) and steps:
                    return steps
            except (json.JSONDecodeError, TypeError):
                pass
    return None


def _format_plan(steps: list) -> str:
    """把计划步骤列表格式化为可读文本（注入执行上下文用）。"""
    lines = []
    for i, s in enumerate(steps, 1):
        task = s.get("task", "") if isinstance(s, dict) else str(s)
        tool = s.get("tool") if isinstance(s, dict) else None
        lines.append(f"{i}. {task}" + (f"（工具：{tool}）" if tool else ""))
    return "\n".join(lines)


def _executor(mm: MiniMaxClient, working: list, tools: list,
              plan_text: str, max_iter: int,
              mcp: Optional[McpManager] = None) -> str:
    """执行阶段（ReAct）：注入计划 → 每步 思考/行动/观察 → 直到 M3 直接答复。

    返回最终文本。working 为本轮会话副本，不污染主对话历史。
    """
    working.append(mm.user_msg(f"{EXEC_PROMPT}\n\n执行计划：\n{plan_text}"))

    for _ in range(max_iter):
        msg, tool_calls = _chat_once(mm, working, tools)

        # M3 不再调用工具 → 计划完成，输出最终答复
        if not tool_calls:
            return (msg.content or "").strip()

        # 显式展示思考内容（如有）
        if msg.content and msg.content.strip():
            print(f"  🤔 {msg.content.strip()[:200]}")

        working.append(msg.model_dump())
        for tc in tool_calls:
            name = tc.function.name
            args = _parse_args(tc.function.arguments)
            result = execute_tool(name, args, mm=mm, mcp=mcp)
            print(f"  ⚡ 行动: {name}({json.dumps(args, ensure_ascii=False)})")
            print(f"  👀 观察: {result[:300]}")
            working.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    return "（已达最大执行轮次，计划可能未全部完成）"


def run_agent(mm: MiniMaxClient, messages: list,
              mcp: Optional[McpManager] = None,
              max_iter: int = MAX_TOOL_ITER) -> str:
    """ReAct 主入口：分流（对话 / 行动）→ 行动则规划 + 执行。

    messages: 跨轮次对话历史（调用方持有，函数内只读不污染）。
    """
    # 完整工具表 = 内置 + 技能 + MCP 动态工具（不含协议工具 submit_plan）
    from skills import get_schemas as get_skill_schemas

    tools = list(BASE_TOOLS) + get_skill_schemas()
    if mcp is not None:
        tools += mcp.get_schemas()

    # ---------- ① 分流轮：直接对话 还是 需要行动 ----------
    msg, tool_calls = _chat_once(mm, messages, tools)
    if not tool_calls:
        # 纯对话：直接回复，不规划
        return (msg.content or "").strip()

    # ---------- ② 行动模式：先规划 ----------
    working = list(messages)
    steps = _planner(mm, working, tools)
    if not steps:
        # 规划失败（M3 未按要求提交计划）→ 降级：直接 ReAct 执行，不注入计划
        return _executor(mm, working, tools, plan_text="（未生成结构化计划，请自行合理行动）",
                         max_iter=max_iter, mcp=mcp)

    plan_text = _format_plan(steps)
    print(f"\n📋 执行计划：\n{plan_text}")

    # ---------- ③ 执行阶段（ReAct） ----------
    return _executor(mm, working, tools, plan_text, max_iter=max_iter, mcp=mcp)


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
    print("  小萌 Agent 模式（ReAct · 先规划后执行 · 对话/行动分流）")
    print("  试试：你好 / 打开记事本写一句话 / 列出当前目录文件 / 现在几点")
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
