import streamlit as st
from utils import api_post, require_role, sidebar_user_info

st.set_page_config(page_title="AI Assistant - School AI", page_icon="🤖", layout="wide")
require_role("admin", "teacher")
sidebar_user_info()

st.title("🤖 AI Assistant (Agentic Workflow)")
st.caption(
    "Powered by a local, open-source **Llama 3.1 (8B)** model running via **Ollama** — "
    "no cloud APIs, no cost. The assistant can call tools to query live student, attendance "
    "and marks data before answering."
)

if "chat_messages" not in st.session_state:
    st.session_state["chat_messages"] = []

with st.expander("💡 Try asking..."):
    st.markdown(
        """
        - "How many students are at risk of falling behind?"
        - "What's Riya Sharma's attendance percentage?"
        - "Show me the performance summary for class C1."
        - "Generate a report card for student ST0001."
        - "What is the attendance trend over the last 30 days?"
        """
    )

for msg in st.session_state["chat_messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("tool_calls"):
            with st.expander("🔧 Tool calls made by the agent"):
                for tc in msg["tool_calls"]:
                    st.code(f"{tc['tool']}({tc['arguments']}) ->\n{tc['result']}", language="json")

prompt = st.chat_input("Ask about students, attendance, marks, or request a report...")
if prompt:
    st.session_state["chat_messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state["chat_messages"][:-1]
    ]

    with st.chat_message("assistant"):
        with st.spinner("Thinking... (local LLM, may take a few seconds)"):
            result = api_post("/ai/chat", json={"message": prompt, "history": history})
        if result:
            st.markdown(result["reply"])
            if result.get("tool_calls"):
                with st.expander("🔧 Tool calls made by the agent"):
                    for tc in result["tool_calls"]:
                        st.code(f"{tc['tool']}({tc['arguments']}) ->\n{tc['result']}", language="json")
            st.session_state["chat_messages"].append({
                "role": "assistant", "content": result["reply"], "tool_calls": result.get("tool_calls", []),
            })

if st.session_state["chat_messages"] and st.button("Clear conversation"):
    st.session_state["chat_messages"] = []
    st.rerun()
