# -*- coding: utf-8 -*-
"""
MCP 工具动态加载层（mcp_tools.py）

从 config.yaml 的 mcp.servers 段读取 MCP 服务器配置，后台连接并动态
拉取工具，转成 OpenAI function calling schema 供 Agent 使用；工具调用
通过 call_tool 转发给对应服务器。连接常驻后台线程（portal 模式）。

配置示例（config.yaml）：
    mcp:
      servers:
        test_server:
          command: "D:\\path\\to\\python.exe"
          args: ["-u", "hub/test_mcp_server.py"]
          env: {"PYTHONIOENCODING": "utf-8"}
        remote_server:
          url: "http://localhost:8080/mcp"

工具命名：mcp_<服务器名>_<工具名>，避免与内置工具冲突。

用法（agent.py 集成）：
    manager = McpManager()
    manager.wait_ready(timeout=8)          # 后台连接 + 等待工具就绪
    TOOLS_ALL = BASE_TOOLS + manager.get_schemas()
    ...
    result = manager.call("mcp_test_get_time", {})
"""
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional

import anyio

from settings import get

MCP_PREFIX = "mcp_"

logger = logging.getLogger("mcp_tools")


def _safe(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z_]", "_", name)


def _tool_key(server: str, tool: str) -> str:
    return f"{MCP_PREFIX}{_safe(server)}_{_safe(tool)}"


class McpManager:
    """管理多个 MCP 服务器的连接与工具调用。"""

    def __init__(self, servers_cfg: Optional[dict] = None):
        self.servers_cfg = (
            servers_cfg if servers_cfg is not None
            else (get("mcp", {}).get("servers", {}) or {})
        )
        # 每个服务器一个独立 portal（独立 event loop 线程），
        # 避免多 stdio 服务器在单 portal 下并发握手冲突（Windows 实测）。
        self._portals: Dict[str, Any] = {}  # server_name -> BlockingPortal
        self._tool_map: Dict[str, Dict] = {}  # mcp_工具名 -> {schema, server, tool, session}
        self._ready = threading.Event()
        self._lock = threading.Lock()

    # ---------------- 生命周期 ----------------
    def is_configured(self) -> bool:
        return bool(self.servers_cfg)

    def start(self) -> None:
        """后台连接所有配置的服务器（非阻塞，每服务器独立线程+portal）。

        各服务器错开启动（2s 间隔），规避 Windows 下多个 stdio 子进程
        并发创建管道的冲突（实测并发握手会卡死第二个）。
        """
        if not self.servers_cfg:
            return
        for idx, (name, cfg) in enumerate(self.servers_cfg.items()):
            threading.Thread(
                target=self._connect_one, args=(name, cfg), daemon=True,
                name=f"mcp-{name}",
            ).start()
            time.sleep(2.0)  # 错开子进程启动

    def wait_ready(self, timeout: float = 8.0) -> bool:
        """连接所有服务器并等待工具就绪。"""
        if not self.is_configured():
            return False
        self.start()
        return self._ready.wait(timeout)

    def _connect_one(self, name: str, cfg: dict) -> None:
        """单个服务器：独立 portal 中建立连接并保持。"""
        import traceback
        try:
            # 注意：anyio 4.x 的 start_blocking_portal 是同步 context manager
            portal_cm = anyio.from_thread.start_blocking_portal()
            portal = portal_cm.__enter__()
            with self._lock:
                self._portals[name] = portal
            if "url" in cfg:
                portal.call(self._hold_sse, name, cfg["url"])
            else:
                portal.call(self._hold_stdio, name, cfg)
        except Exception:
            logger.error("MCP 服务器 [%s] 连接失败:\n%s", name, traceback.format_exc())

    async def _hold_stdio(self, name: str, cfg: dict) -> None:
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client

        env = dict(cfg.get("env") or {})
        env.setdefault("PYTHONIOENCODING", "utf-8")  # 防 Windows 编码问题
        params = StdioServerParameters(
            command=cfg.get("command", "python"),
            args=cfg.get("args", []),
            env=env,
        )
        async with stdio_client(params) as (read, write):
            await self._hold_session(name, read, write)

    async def _hold_sse(self, name: str, url: str) -> None:
        from mcp.client.sse import sse_client

        async with sse_client(url) as (read, write):
            await self._hold_session(name, read, write)

    async def _hold_session(self, name: str, read, write) -> None:
        """握手 + 拉取工具 + 注册，然后常驻保持连接。"""
        from mcp import ClientSession

        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            with self._lock:
                for t in tools.tools:
                    key = _tool_key(name, t.name)
                    # 兼容新旧版 SDK 字段命名（input_schema / inputSchema）
                    input_schema = (
                        getattr(t, "input_schema", None)
                        or getattr(t, "inputSchema", None)
                        or {"type": "object", "properties": {}}
                    )
                    schema = {
                        "type": "function",
                        "function": {
                            "name": key,
                            "description": f"[MCP:{name}] {t.description or t.name}",
                            "parameters": input_schema,
                        },
                    }
                    self._tool_map[key] = {
                        "schema": schema, "server": name, "tool": t.name, "session": session,
                    }
            self._ready.set()
            logger.info("MCP 服务器 [%s] 就绪，注册 %d 个工具", name, len(tools.tools))
            # 保持连接直到进程退出（等待一个永不触发的 Event）
            await anyio.Event().wait()

    # ---------------- Agent 使用 ----------------
    def get_schemas(self) -> List[Dict]:
        with self._lock:
            return [v["schema"] for v in self._tool_map.values()]

    def tool_names(self) -> List[str]:
        with self._lock:
            return list(self._tool_map.keys())

    def call(self, tool_name: str, args: dict) -> str:
        """调用 MCP 工具（按注册名），返回文本结果。"""
        with self._lock:
            meta = self._tool_map.get(tool_name)
            portal = self._portals.get(meta["server"]) if meta else None
        if meta is None or portal is None:
            return f"错误：未知 MCP 工具 {tool_name}"

        try:
            result = portal.call(meta["session"].call_tool, meta["tool"], args or {})
        except Exception as e:
            return f"错误：MCP 工具调用失败 {e}"

        texts = []
        for block in (getattr(result, "content", None) or []):
            if getattr(block, "type", None) == "text":
                texts.append(getattr(block, "text", ""))
        text = "\n".join(t for t in texts if t)
        return text or "(无返回内容)"


if __name__ == "__main__":
    # 自测：python mcp_tools.py
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    mgr = McpManager()
    if not mgr.wait_ready(timeout=10):
        print("❌ 无 MCP 服务器就绪（检查 config.yaml 的 mcp.servers）")
    else:
        print("✅ 就绪，工具:", mgr.tool_names())
        for name in mgr.tool_names():
            print(f"  {name} → {mgr.call(name, {})}")
