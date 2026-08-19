# -*- coding: utf-8 -*-
"""
技能系统（skills）

给 Agent 加技能 = 在 hub/skills/ 下新建一个模块，定义两个函数：

    def skill_meta() -> dict:
        \"\"\"技能元数据（转成 OpenAI function schema）\"\"\"
        return {
            "name": "技能名（小写下划线）",
            "description": "一句话说明技能做什么、何时用",
            "parameters": {"type": "object", "properties": {...}, "required": [...]},
            "danger": "medium",   # 可选：low / medium / high（默认 medium）
        }

    def run(args: dict) -> str:
        \"\"\"技能执行体：接收参数字典，返回结果文本。\"\"\"
        ...

写完保存即可，Agent 下次启动自动注册（无需改 agent.py）。

当前技能：
    send_workbuddy   打开 WorkBuddy 并发送消息
"""
import importlib
import pkgutil
from typing import Dict, List, Optional

_SKILLS: Dict[str, dict] = {}


def _discover() -> None:
    """扫描 skills/ 包下所有模块，收集 skill_meta + run。"""
    for m in pkgutil.iter_modules(__path__):
        if m.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"{__name__}.{m.name}")
        except Exception as e:
            print(f"[skills] 加载 {m.name} 失败: {e}")
            continue
        meta_fn = getattr(mod, "skill_meta", None)
        run_fn = getattr(mod, "run", None)
        if not callable(meta_fn) or not callable(run_fn):
            print(f"[skills] 跳过 {m.name}（缺少 skill_meta() 或 run()）")
            continue
        try:
            meta = meta_fn()
        except Exception as e:
            print(f"[skills] {m.name}.skill_meta() 异常: {e}")
            continue
        if not isinstance(meta, dict) or "name" not in meta:
            print(f"[skills] 跳过 {m.name}（skill_meta 缺少 name）")
            continue
        meta.setdefault("danger", "medium")
        _SKILLS[meta["name"]] = {"meta": meta, "run": run_fn}
        print(f"[skills] 已注册: {meta['name']}")


_discover()


def get_schemas() -> List[Dict]:
    """技能 → OpenAI function calling schema 列表。"""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": f"[技能] {v['meta']['description']}",
                "parameters": v["meta"].get("parameters", {"type": "object", "properties": {}}),
            },
        }
        for name, v in _SKILLS.items()
    ]


def skill_names() -> List[str]:
    return list(_SKILLS.keys())


def get_danger(name: str) -> str:
    return _SKILLS.get(name, {}).get("meta", {}).get("danger", "medium")


def run_skill(name: str, args: dict) -> str:
    """执行技能，返回结果文本。"""
    entry = _SKILLS.get(name)
    if entry is None:
        return f"错误：未知技能 {name}"
    try:
        return entry["run"](args or {})
    except Exception as e:
        return f"错误：技能 {name} 执行异常 {e}"


if __name__ == "__main__":
    # 自测：python -m skills
    print("已注册技能:", skill_names())
