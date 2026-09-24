# StaffDesk — Complete Process Documentation

A detailed explanation of how the StaffDesk school-policy assistant works end to end:
every component, every data flow, every safety decision, and how to run and test it.

StaffDesk is an independent project inside `school ai\staffdesk`. It does not share
code, data, or ports with the School Management System (`frontend/` + `backend/`) or
the Student Analytics app (`student_analytics/`).

---

## 1. What the application does

StaffDesk answers staff questions **only from uploaded school PDFs**. It never uses
general knowledge, never calls cloud services, and never requires API keys.

Given a question like *"What time does the school day start?"*, the system:

1. Validates and bounds the input.
2. Classifies the question (triage) and detects sensitive/safeguarding topics.
3. Retrieves the most relevant PDF passages from a local vector database.
4. Measures retrieval confidence and retries once with a rewritten query if weak.
5. Generates an answer that **must quote the PDF verbatim**.
6. Verifies every citation against the retrieved text — word for word.
7. Publishes the answer only if grounding succeeds; otherwise abstains.
8. Shows the exact sources, page numbers, workflow trace, and an evidence graph.

**APIs required: none.** The only network calls are to the local Ollama HTTP server
at `http://127.0.0.1:11434` (loopback only — remote hosts are rejected by code).

---

## 2. Technology choices and why

| Concern | Choice | Reason |
|---|---|---|
| Chat / vision model | `qwen3.5:4b` via Ollama | Recent, tool-capable, fits the 4 GB VRAM / 32 GB RAM machine |
| Embedding model | `nomic-embed-text:v1.5` via Ollama | Open, local, 768-dim vectors, strong retrieval quality |
| Vector database | Qdrant **local mode** | Embedded in Python — no server, no Docker, no account, no API key |
| Workflow orchestration | LangGraph | Explicit nodes, conditional edges, retry loops, typed state |
| Knowledge graph | NetworkX + Plotly | Local, free, interactive HTML visualization |
| Web UI | Streamlit | Python-only, consistent with the other apps in this workspace |
| PDF text | `pypdf` + `pypdfium2` fallback | `pypdf` fails on some font metadata; PDFium recovers text natively |
| Scanned-page reading | Local vision via `qwen3.5:4b` | Optional transcription of image-only pages, still fully local |

The reference project (`StaffDesk-LangGraph` notebook) used Groq, FAISS,
HuggingFace embeddings, Gradio, and optional Notion/Drive/weather/search APIs.
Every one of those was replaced with a local equivalent; the external integrations
were intentionally **not** carried over, because answers must come from PDFs only.

---

## 3. File map

```text
staffdesk/
  app.py               Streamlit UI: PDF library, chat, sources, trace, graph
  models.py            Local-only Ollama client (chat, vision, embed) + model checks
  knowledge.py         PDF ingestion, chunking, Qdrant indexing, BM25 hybrid search,
                       manifest persistence, graph data, coverage reporting
  workflow.py          LangGraph state machine: validate -> scope -> triage ->
                       retrieve -> confidence gate -> rewrite/retry -> respond ->
                       citation grounding -> finalize
  graph_view.py        Plotly rendering of the NetworkX graph (escaped, deterministic)
  demo.py              Builds the small 3-page fictional demo PDF
  sample_policies.py   Builds the 10-page controlled test PDF + questions JSON
  verify_sample.py     Standalone verification: indexes the 10-page PDF, runs all
                       12 test questions, checks pages/facts/citations, writes report
  start.ps1            Launches Streamlit on 127.0.0.1:8503 (option -SamplePolicies)
  setup.ps1            Creates .venv, installs requirements, pulls Ollama models
  requirements.txt     Pinned dependencies
  test_*.py            105 unit/integration tests
  tests/fixtures/      Generated test PDFs
  data/                Default workspace: uploaded PDFs, manifest, Qdrant storage
  sample_test_data/    Isolated workspace for the 10-page sample verification
```

---

## 4. Data flow — PDF ingestion

When a PDF is uploaded (or the demo/sample button is pressed), `knowledge.py` runs
the ingestion pipeline:

### 4.1 Validation

- Filename is sanitized (no path traversal).
- Size limit: **25 MB**. Page limit: **150 pages**.
- Encrypted PDFs are rejected.
- Document identity = SHA-256 of the file bytes. Identical re-uploads are
  deduplicated — the same document is never indexed twice.

### 4.2 Text extraction (per page)

1. `pypdf` extracts native text.
2. If `pypdf` raises a font-metadata error (a real bug observed on an uploaded PDF:
   `KeyError: bbox`) or returns empty text, **`pypdfium2`** is used as a native-text
   fallback — no LLM involved.
3. If the page is still empty (scanned/image-only), and the user enabled
   *visual extraction*, the page is rendered to an image and `qwen3.5:4b`
   transcribes it locally.
4. Each page records its `extraction_kind`: `native`, `pdfium`, `vision`, or
   `native+vision`.
5. Pages that yield no text are recorded as **missing pages** — visible in the
   PDF Library coverage panel, never silently dropped.

### 4.3 Chunking

Each page's text is split into overlapping chunks:

```text
chunk size : ~900 characters
overlap    : ~150 characters
scope      : page-local (a chunk never spans pages)
```

Every chunk stores metadata: `chunk_id`, `document_id`, `source` filename,
`page`, `grade_band`, `extraction_kind`, `text`, and optional relationships.

### 4.4 Embedding and indexing

- Chunks are embedded with `nomic-embed-text:v1.5` (768-dim) through Ollama's
  `POST /api/embed`.
- Vectors are upserted into a **local Qdrant collection** stored under the
  workspace's `data/` directory. Qdrant local mode uses a file lock — exactly one
  process may own a workspace at a time.
- The embedding model digest and dimension are recorded in the manifest; if the
  model changes, the app warns instead of silently mixing incompatible vectors.

### 4.5 Atomic persistence

- `documents.json` manifest is written via temp-file + atomic rename.
- A `filelock` guard prevents concurrent writers.
- On failure mid-ingestion, partial state is rolled back — a half-indexed
  document is never published.

---

## 5. Data flow — hybrid retrieval

`KnowledgeBase.search(...)` combines two rankings:

1. **Cosine similarity** — Qdrant dense-vector search.
2. **BM25 keyword ranking** — computed locally over chunk text.

The two rankings are fused with **reciprocal-rank fusion** (RRF). This fixes the
failure mode where pure vector search misses exact-policy terms (e.g. "POL-02",
"8:45 AM") and where pure keyword search misses paraphrases.

Filters are applied **before** retrieval and **rechecked** in the workflow:

- `document_id` — the "PDF to answer from" selector restricts search to one PDF,
  so chunks from other PDFs can never contaminate an answer.
- `grade_band` — All / Primary / Middle / Secondary. A model rewrite that tries to
  drop the scope cannot widen it; the filter is re-applied in code.

Retrieved scores are **heuristics, not probabilities**. The UI labels them as such.

---

## 6. Data flow — the LangGraph workflow

`workflow.py` compiles a typed `StateGraph`. One `PolicyWorkflow.run(...)` call
returns:

```text
answer, sources, trace, category, sensitive, confidence, abstained,
retrieved_context
```

### Node-by-node

1. **validate** — bounds the question length, trims history to recent
   user/assistant turns, marks all history as untrusted context (never evidence).
2. **scope** — preserves the selected grade band and teacher type
   (New vs Existing). Detects follow-up questions and adds only the last relevant
   user turn as context.
3. **triage** — asks the local model to classify the question (Policy,
   Safeguarding-sensitive, Out-of-scope, etc.). If the model is unavailable or
   returns malformed output, a deterministic keyword fallback classifies instead —
   the workflow never crashes on model failure.
4. **retrieve** — hybrid search as in §5, within document + grade filters.
5. **confidence check** — if the fused retrieval is weak, the edge routes to a
   **rewrite** node: the model rephrases the question once, retrieval re-runs, and
   the better result set wins. At most **one** retry — bounded by construction.
6. **respond** — the model is instructed to answer *only* by quoting the retrieved
   chunks verbatim, emitting citation IDs that must match real chunk IDs. PDF text
   is wrapped as untrusted data, not instructions — prompt injection inside a PDF
   cannot redirect the system.
7. **citation grounding** — deterministic code verification:
   - Every citation ID must exist among retrieved chunks.
   - The claim text must equal the concatenation of the exact verbatim quotes
     (whitespace/line-wrap tolerant; word or number changes fail).
   - Unsupported paraphrase, invented citation, or model-unavailable output →
     the response is **not published**. The system abstains with a clear message,
     and the retrieved passages remain visible in a separate *Retrieved context*
     panel — never presented as a verified answer.
8. **finalize** — attaches the trace, category, sensitivity flag, confidence
   heuristic, and source list (one-based citation numbers, document, page, quote).

### Sensitive topics

Safeguarding-flagged questions (e.g. abuse disclosure procedures) are answered
only from PDF text and additionally carry a human-review notice. The system never
invents reporting contacts, phone numbers, or policies.

### Teacher type

`New` teachers get slightly more procedural detail and a lower floor for
extractive detail; `Existing` teachers get the concise version. The selection is
carried through state and shown in the trace.

### Tracing

`LANGSMITH_TRACING=false` and `LANGCHAIN_TRACING_V2=false` are set in
`start.ps1` — nothing leaves the machine.

---

## 7. Knowledge graph

### 7.1 What the graph contains

Built in `knowledge.py`, rendered in `graph_view.py`:

- **Document nodes** — one per indexed PDF.
- **Page nodes** — one per extracted page, linked to their document.
- **Chunk nodes** — provenance links from chunks to pages (hidden in the
  *Policy overview* mode, shown in *Full chunk provenance*).
- **Concept nodes** — policy topics/categories extracted from text (e.g.
  attendance, safeguarding), linked to the pages that mention them.
- **Relationship edges**:
  - `mentions` — deterministic, from extracted text.
  - `reports to` — literal named-role statements detected in PDF text (e.g.
    "The Attendance Officer reports to the Principal").
  - model-generated assertions — optional, visually distinct, and **never** used
    as independent policy evidence. Only real PDF chunks ground answers.

### 7.2 Rendering modes in the UI

- **Policy overview** — documents, pages, concepts, relationships.
- **Full chunk provenance** — adds chunk nodes.
- **Last answer context** — after a question, the graph filters to the retrieved
  pages and their topics so you can *see* where the answer came from.
- **Focus search** — type a term to highlight matching nodes.

All labels and relation text are HTML-escaped before entering Plotly output;
layout is deterministic for testability.

---

## 8. Security and privacy properties

- PDFs never leave the machine; Ollama host is restricted to `127.0.0.1` —
  remote/cloud endpoints and redirects are rejected in code.
- Cloud-only Ollama models (e.g. `-cloud` tags) are filtered out of model lists.
- Filenames sanitized; sizes/pages bounded; encrypted PDFs rejected.
- PDF text and chat history are treated as untrusted data in prompts.
- Atomic writes + file locks; no half-published index.
- Provider error payloads are normalized — no secrets or raw internals surface in
  the UI.
- Citations are verified verbatim; unsupported output fails closed (abstain).
- Retrieved similarity is displayed as a heuristic, not a probability.
- The app never fabricates contacts, policies, or safeguarding procedures.

---

## 9. The 10-page controlled test PDF

`Maple_Grove_School_Sample_Policies_10_Pages.pdf` is a **fictional** handbook
generated by `sample_policies.py` — deterministic, text-readable, exactly ten
pages. Its sibling `*.questions.json` holds **12 test questions** with expected
facts and physical page numbers, covering:

school hours, attendance and absence reporting, assessment and marking,
staff leave, safeguarding reporting, behaviour and inclusion, health and
medication, digital/device safety, parent communication and complaints,
and educational visits.

Because every expected answer and its page are known, this PDF turns "does the
chatbot work?" into a checkable test rather than a vibe.

**Important**: the earlier real-world PDF you uploaded had a `pypdf` font bug —
5 of 6 pages extracted no text, so retrieval looked "wrong" though the vector DB
was fine. The PDFium fallback (§4.2) fixes that for new uploads, and the PDF
Library coverage panel now shows searchable vs missing pages so the failure is
visible instead of silent.

---

## 10. Running the application

```powershell
cd "C:\Users\mrathi\Desktop\school ai\staffdesk"

# one-time setup: venv + pinned deps + ollama model pulls
.\setup.ps1

# normal start  ->  http://127.0.0.1:8503
.\start.ps1

# start in the isolated 10-page sample workspace
.\start.ps1 -SamplePolicies
```

In the UI:

1. **PDF Library** (sidebar) — upload a PDF, or press
   *Index 10-page sample only* / *Index fictional demo PDF*.
   Check the coverage line: `indexed pages`, `missing pages`, chunks, vectors.
2. **PDF to answer from** — select the sample PDF (not "All indexed PDFs") to
   guarantee answers come from it alone.
3. Pick grade band and teacher type, ask a question.
4. Expand the answer's **sources**, **workflow trace**, **Retrieved context**,
   and **answer graph** to inspect exactly what the system used.
5. Open the **Knowledge graph** tab for the full visualization.

Only run one StaffDesk server per workspace — Qdrant local storage is locked.

---

## 11. Verification

### Automated tests (105 tests)

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
```

Coverage includes: model filtering, embed prefixes, timeout/redirect handling,
PDF limits, persistence, document isolation, deduplication, grade filtering,
chunk boundaries, scanned/blank pages, vision extraction, verified relations,
graph escaping and determinism, workflow compilation, triage fallback, retry
behaviour, citation validation, exact-quote grounding, safeguarding, history
injection, grade-scope invariance, teacher-type behaviour, and Streamlit
rendering/interaction via AppTest.

### Real end-to-end verification (uses actual Ollama)

```powershell
.\.venv\Scripts\python.exe verify_sample.py          # retrieval + graph + reopen
.\.venv\Scripts\python.exe verify_sample.py --chat   # + real generated answers
.\.venv\Scripts\python.exe verify_sample.py --chat --case 3 --case 4
```

The script indexes the 10-page PDF in `sample_test_data/`, runs all 12 questions,
checks retrieved pages and expected facts, validates citations, rebuilds the
graph, reopens the index, and writes a timestamped report.

**Practical note**: `qwen3.5:4b` on this machine runs at 100% CPU and takes
~30–60 s per generation while warming. If a `--chat` case reports "model
unavailable / failed citation checks" while retrieval passed, that is a cold
model or timeout — wait for `ollama ps` to show the model idle and retry, or run
fewer cases at once. Retrieval-side results (pages, facts, hybrid ranking) are
unaffected by chat-model latency.

---

## 12. Failure modes and what you will see

| Situation | Behaviour |
|---|---|
| PDF page has no extractable text | Listed under *missing pages* in coverage; other pages still indexed |
| Question not covered by PDFs | Low-confidence branch → one rewrite retry → abstain message, sources still inspectable |
| Model answer fails verbatim check | Abstention notice; retrieved context panel shows candidates; no fake answer published |
| Ollama not running | Setup guidance shown; deterministic fallbacks keep UI functional where safe |
| Same PDF uploaded twice | Deduplicated by content hash — no double indexing |
| Safeguarding question | PDF-grounded answer + human-review notice; never invented contacts |
| User picks a different PDF | Conversation context is cleared so stale evidence cannot leak across documents |

---

## 13. What was deliberately left out

- No Groq / OpenAI / any cloud LLM.
- No weather, web-search, Semantic Scholar, Notion, or Google Drive integrations
  (present in the reference notebook, incompatible with "PDFs only").
- No Docker, no database server, no hosted vector DB, no API keys.
- No LangSmith/cloud tracing.

---

*StaffDesk answers only what your PDFs say — and proves it with quotes, pages,
a visible trace, and a graph you can inspect.*
