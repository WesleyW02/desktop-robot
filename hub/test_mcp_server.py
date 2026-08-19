#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
极简 MCP 测试服务器（stdio 协议）

用于验证 Agent 的 MCP 动态加载链路，暴露两个工具：
    get_time  获取当前时间
    list_dir  列出目录内容

以 MCP stdio 服务器方式启动（由 mcp_tools.py 拉起）：
    python -u test_mcp_server.py

协议：stdin/stdout 上的 JSON-RPC 2.0（\n 分隔）。
真实使用时，把它替换为任意 MCP 服务器（如 mcp-server-filesystem、
GitHub MCP、数据库 MCP 等），只需改 config.yaml 的 mcp.servers 配置。
"""
import json
import os
import sys
from datetime import datetime

TOOLS = {
    "get_time": {
        "description": "获取当前日期和时间",
        "params": {},
    },
    "list_dir": {
        "description": "列出指定目录下的文件与子目录名",
        "params": {"path": {"type": "string", "description": "目录路径，默认当前目录"}},
    },
}


def handle_tool(name: str, args: dict) -> str:
    if name == "get_time":
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if name == "list_dir":
        path = args.get("path", ".")
        try:
            items = os.listdir(path)
        except OSError as e:
            return f"错误：{e}"
        return "\n".join(items)[:1000] or "(空目录)"
    return f"错误：未知工具 {name}"


def respond(msg_id, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}) + "\n")
    sys.stdout.flush()


def respond_error(msg_id, code, message):
    sys.stdout.write(json.dumps(
        {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
    ) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method")
        msg_id = msg.get("id")

        if method == "initialize":
            respond(msg_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "test-mcp-server", "version": "0.1.0"},
            })
        elif method == "notifications/initialized":
            pass  # 通知无响应
        elif method == "tools/list":
            tools = [
                {
                    "name": n,
                    "description": t["description"],
                    "inputSchema": {"type": "object", "properties": t["params"]},
                }
                for n, t in TOOLS.items()
            ]
            respond(msg_id, {"tools": tools})
        elif method == "tools/call":
            name = msg["params"]["name"]
            args = msg["params"].get("arguments", {}) or {}
            text = handle_tool(name, args)
            respond(msg_id, {"content": [{"type": "text", "text": text}], "isError": False})
        else:
            respond_error(msg_id, -32601, f"未知方法: {method}")


if __name__ == "__main__":
    main()
