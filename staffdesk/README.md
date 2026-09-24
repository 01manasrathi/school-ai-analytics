# StaffDesk — Local PDF policy assistant

A private, evidence-first chatbot for school staff policies. It answers questions
**only from uploaded PDFs**, quotes them verbatim, cites the page, and shows an
interactive knowledge graph.

## Main file for Streamlit

```text
staffdesk/app.py
```

Use this path as the **Main file path** in Streamlit Community Cloud.
The `requirements.txt` next to it (`staffdesk/requirements.txt`) is detected
automatically.

## Important: Ollama is required

StaffDesk is built around **local** AI. It needs [Ollama](https://ollama.com/)
running on the same machine at `http://127.0.0.1:11434` with:

- `qwen3.5:4b` (chat + optional vision for scanned pages)
- `nomic-embed-text:v1.5` (embeddings)

Install them with:

```powershell
ollama pull qwen3.5:4b
ollama pull nomic-embed-text:v1.5
```

## Can this run on Streamlit Community Cloud?

**Not as-is.** Streamlit Community Cloud does not provide Ollama, cannot download
multi-gigabyte models, and has no GPU. The app will start, but every feature that
needs a model will show "Local models unavailable."

To host StaffDesk on the internet you need a server that can run Ollama, for
example:

- A VPS/VM with a GPU (RunPod, Vast.ai, AWS, Azure, etc.) and run Ollama there.
- A container platform that lets you bundle the Ollama binary and models (Render,
  Fly.io, Railway GPU tier).
- A self-hosted machine exposed behind a VPN or reverse proxy with authentication.

If you are OK with using a cloud LLM (OpenAI, Groq, Anthropic, etc.), StaffDesk
would need a separate branch that swaps `models.py` for a cloud client. That
contradicts the original design goal of keeping all PDF processing local and
API-key-free.

## Run locally (recommended)

```powershell
cd staffdesk
.\setup.ps1       # creates .venv, installs deps, pulls models
.\start.ps1       # opens http://127.0.0.1:8503
```

## What works without Ollama?

Only the UI shell. PDF indexing and answering require the local models.

## Files of interest

- `app.py` — Streamlit UI (the entry point)
- `models.py` — Ollama client (chat, embeddings, model checks)
- `knowledge.py` — PDF extraction, chunking, Qdrant vectors, graph builder
- `workflow.py` — LangGraph agent (validate → scope → triage → retrieve → respond → ground → finalize)
- `graph_view.py` — Plotly graph renderer
- `LEARN_STAFFDESK.md` — 11,000-word beginner's guide to every concept
- `PROCESS.md` — technical process documentation
- `AGENTS.md` — developer/agent quick-reference

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
.\.venv\Scripts\python.exe verify_sample.py --chat
```
