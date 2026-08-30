"""Agentic workflow: a ReAct-style tool-calling loop backed by a local
Ollama model (llama3.1:8b by default).

The model is given a set of "tools" (Python functions over the school's
CSV data) via Ollama's tool-calling chat API. It decides which tools to
call, we execute them locally, feed results back, and repeat until the
model produces a final natural-language answer. This is a small,
dependency-light agent loop (no LangChain needed) that keeps everything
open-source and fully local.
"""
from __future__ import annotations

import ollama

from .. import config
from . import tools

SYSTEM_PROMPT = """You are the School AI Assistant, an analytics copilot for a school's \
administration and teachers. You have access to tools that query the school's live data \
(students, attendance, marks, classes). Always use tools to fetch real data before answering \
questions about specific students, classes, attendance or performance — never invent numbers.

Guidelines:
- Be concise and clear. Use bullet points or short tables in plain text when listing multiple items.
- When asked about a named student, first resolve their student_id with get_student_info.
- When identifying "at-risk" students, use get_at_risk_students.
- If a user asks for a report/PDF for a student, call generate_student_report_card and tell them \
where the file was saved.
- If a question is unrelated to school data (e.g. general knowledge), answer directly without tools.
- Never fabricate data that should come from a tool.
"""

MAX_TOOL_ITERATIONS = 6


def _client() -> ollama.Client:
    return ollama.Client(host=config.OLLAMA_HOST)


def chat(message: str, history: list[dict] | None = None) -> dict:
    """Run one agentic turn. Returns {"reply": str, "tool_calls": [...]}."""
    client = _client()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": message})

    tool_trace = []

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.chat(
            model=config.OLLAMA_MODEL,
            messages=messages,
            tools=tools.TOOL_SCHEMAS,
        )
        msg = response["message"]
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            return {"reply": msg.get("content", ""), "tool_calls": tool_trace}

        messages.append({"role": "assistant", "content": msg.get("content", ""), "tool_calls": tool_calls})

        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = tc["function"].get("arguments") or {}
            result = tools.call_tool(fn_name, fn_args)
            tool_trace.append({"tool": fn_name, "arguments": fn_args, "result": result})
            messages.append({"role": "tool", "content": result, "name": fn_name})

    # If we exhausted iterations, ask the model to summarize with what it has.
    final = client.chat(model=config.OLLAMA_MODEL, messages=messages)
    return {"reply": final["message"].get("content", ""), "tool_calls": tool_trace}
