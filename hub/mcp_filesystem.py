# -*- coding: utf-8 -*-
"""
真实 MCP 文件系统服务器（mcp SDK lowlevel · 标准 stdio 协议）

供 McpManager 动态加载（config.yaml → mcp.servers.filesystem），
提供真实文件工具：list_dir / read_file / search_text / get_file_info。
全部【只读】，路径限制在 ROOT 目录内。

运行：
    python -u mcp_filesystem.py
"""
import os
import time as _t
from typing import Any, List

import anyio
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import (CallToolRequestParams, CallToolResult, ListToolsResult,
                       TextContent, Tool)

# 允许访问的根目录
ROOT = os.path.abspath(os.path.expanduser("D:/"))

TOOLS = [
    Tool(
        name="list_dir",
        description="列出目录下的文件与子目录（名称+类型+大小）",
        inputSchema={"type": "object", "properties": {"path": {"type": "string", "description": "目录路径，默认 ."}}},
    ),
    Tool(
        name="read_file",
        description="读取文本文件内容（UTF-8，截断到 max_chars）",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件绝对路径"},
                "max_chars": {"type": "number", "description": "最多读取字符数，默认 4000"},
            },
            "required": ["path"],
        },
    ),
    Tool(
        name="search_text",
        description="在目录内递归搜索包含关键词的文本文件（.md/.txt/.py/.yaml/.json/.ino/.cpp/.h/.html），返回前 10 个匹配",
        inputSchema={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词"},
                "path": {"type": "string", "description": "起始目录，默认 ."},
            },
            "required": ["keyword"],
        },
    ),
    Tool(
        name="get_file_info",
        description="获取文件/目录基本信息（大小、修改时间）",
        inputSchema={"type": "object", "properties": {"path": {"type": "string", "description": "绝对路径"}}, "required": ["path"]},
    ),
]


def _safe(path: str) -> str:
    p = os.path.abspath(os.path.expanduser(path or "."))
    if not p.startswith(ROOT):
        raise ValueError(f"路径 {p} 超出允许根目录 {ROOT}")
    return p


def _handle(name: str, args: dict) -> str:
    if name == "list_dir":
        p = _safe(args.get("path", "."))
        if not os.path.isdir(p):
            return f"错误：{p} 不是目录"
        lines = []
        for item in sorted(os.listdir(p)):
            full = os.path.join(p, item)
            if os.path.isdir(full):
                lines.append(f"[目录] {item}/")
            else:
                lines.append(f"[文件] {item} ({os.path.getsize(full)}B)")
        return "\n".join(lines) if lines else "(空目录)"

    if name == "read_file":
        p = _safe(args["path"])
        if not os.path.isfile(p):
            return f"错误：{p} 不是文件"
        max_chars = int(args.get("max_chars", 4000))
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                text = f.read(max_chars)
        except OSError as e:
            return f"错误：{e}"
        return text + ("\n…(已截断)" if len(text) >= max_chars else "")

    if name == "search_text":
        root = _safe(args.get("path", "."))
        keyword = args.get("keyword", "")
        if not os.path.isdir(root):
            return f"错误：{root} 不是目录"
        hits = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if not d.startswith((".", "$", "node_modules", ".venv", "__pycache__", "build"))]
            for fn in filenames:
                if not fn.endswith((".md", ".txt", ".py", ".yaml", ".json", ".ino", ".cpp", ".h", ".html")):
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    with open(full, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(200000)
                except OSError:
                    continue
                if keyword in content:
                    hits.append(f"{full}（{len(content)}B）")
                    if len(hits) >= 10:
                        break
            if len(hits) >= 10:
                break
        return "\n".join(hits) if hits else f"未在 {root} 下找到包含「{keyword}」的文本"

    if name == "get_file_info":
        p = _safe(args["path"])
        if not os.path.exists(p):
            return f"错误：{p} 不存在"
        st = os.stat(p)
        kind = "目录" if os.path.isdir(p) else "文件"
        mtime = _t.strftime("%Y-%m-%d %H:%M", _t.localtime(st.st_mtime))
        return f"{kind}: {p}\n大小: {st.st_size} 字节\n修改时间: {mtime}"

    return f"错误：未知工具 {name}"


async def _on_list_tools(ctx, params) -> ListToolsResult:
    return ListToolsResult(tools=TOOLS)


async def _on_call_tool(ctx, params: CallToolRequestParams) -> CallToolResult:
    try:
        text = _handle(params.name, dict(params.arguments or {}))
    except ValueError as e:
        text = f"错误：{e}"
    except Exception as e:
        text = f"错误：工具执行异常 {e}"
    return CallToolResult(content=[TextContent(type="text", text=text)])


app = Server("filesystem", on_list_tools=_on_list_tools, on_call_tool=_on_call_tool)


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    anyio.run(main)
