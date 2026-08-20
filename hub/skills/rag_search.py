# -*- coding: utf-8 -*-
"""
技能：rag_search —— 本地知识库检索（RAG）

在项目文档库中检索与问题相关的片段，让 Agent 基于文档内容回答。
知识库：docs/、README.md、方案书等（config.yaml → rag.docs_dir）。
"""
from typing import Dict


def skill_meta() -> dict:
    return {
        "name": "rag_search",
        "description": (
            "在本地知识库（项目文档库）中检索与用户问题相关的文档片段（RAG）。"
            "当问题涉及项目设计、协议、配置、开发计划等文档内容时使用，"
            "基于检索结果回答问题比凭空猜测更准确。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "要检索的问题或关键词，如「通信协议 v2.0 有哪些新特性」",
                }
            },
            "required": ["query"],
        },
        "danger": "low",  # 只读检索，无副作用
    }


def run(args: Dict[str, str]) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        return "错误：检索内容为空"

    from rag import get_index
    return get_index().query(query)
