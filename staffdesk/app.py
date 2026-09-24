from __future__ import annotations

import json
import math
import os
from collections import Counter
from pathlib import Path

import networkx as nx
import streamlit as st

from demo import demo_pdf
from graph_view import evidence_graph, graph_figure, select_graph_view
from sample_policies import FILENAME, sample_policy_pdf
from knowledge import KnowledgeBase
from models import ModelError, Ollama
from workflow import PolicyWorkflow


DEFAULT_MODEL = os.environ.get("STAFFDESK_MODEL", "qwen3.5:4b")
EMBEDDING_MODEL = "nomic-embed-text:v1.5"
DATA_ROOT = Path(os.environ.get("STAFFDESK_DATA_DIR", str(Path(__file__).resolve().parent / "data"))).expanduser().resolve()
GRADES = ["All", "Primary", "Middle", "Secondary"]
MAX_PDF_BYTES = 25 * 1024 * 1024


@st.cache_resource(show_spinner=False)
def knowledge_base(root: str):
    return KnowledgeBase(Path(root), Ollama(model=DEFAULT_MODEL, embedding_model=EMBEDDING_MODEL))


def reset_session():
    st.session_state.messages = []
    st.session_state.results = []
    st.session_state.analytics = []
    st.session_state.pop("question", None)
    st.session_state.pop("upload_feedback", None)


def similarity(value):
    try:
        number = float(value)
        return f"{number:.3f}" if math.isfinite(number) else "Not available"
    except (TypeError, ValueError):
        return "Not available"


def original_download(kb, document_id, filename, key):
    if not document_id:
        st.caption("Original PDF unavailable: this evidence has no document identifier.")
        return
    try:
        data = kb.pdf_bytes(document_id)
        st.download_button("Download original PDF", data, file_name=Path(filename).name,
                           mime="application/pdf", key=key, on_click="ignore")
    except Exception:
        st.warning("Original PDF could not be read. Check the workspace files or restore a backup.")


def show_sources(kb, sources, prefix):
    for index, source in enumerate(sources, 1):
        tag = source.get("citation", index)
        name = source.get("source", "Policy PDF")
        page = source.get("page", "Unknown")
        with st.expander(f"[{tag}] {name} | Page {page}"):
            st.caption(f"Source [{tag}] · Page {page} · Grade: {source.get('grade_band', 'All')}")
            st.caption(f"Heuristic similarity: {similarity(source.get('score'))} — not a probability of correctness.")
            st.text(source.get("quote") or source.get("text") or "No snippet provided.")
            original_download(kb, source.get("document_id"), name, f"{prefix}_source_{index}")


def show_result(kb, result, prefix):
    if result.get("sensitive"):
        st.warning("Sensitive policy topic. Verify the original PDF and involve the designated school lead; this is not professional advice.")
    st.text(result.get("answer", "No answer returned. Please try again."))
    disposition = "Abstained" if result.get("abstained") else "Evidence returned"
    st.caption(f"{disposition} · {result.get('category', 'Policy')} · Heuristic retrieval similarity: {similarity(result.get('confidence'))}")
    show_sources(kb, result.get("sources", []), prefix)
    with st.expander("Retrieved context and answer graph"):
        candidates = result.get("retrieved_context", [])
        st.caption("These are retrieval candidates, not automatically approved answers. Only cited excerpts support the answer above.")
        if candidates:
            cited = {source["id"] for source in result.get("sources", [])}
            for position, candidate in enumerate(candidates, 1):
                st.caption(f"Candidate {position} | {candidate['source']} | Page {candidate['page']} | "
                           f"Cosine {similarity(candidate.get('score'))} | Keyword score {similarity(candidate.get('lexical_score'))} | "
                           f"{'Cited' if candidate['id'] in cited else 'Not cited'} | {candidate.get('extraction_kind', 'native')}")
                st.text(candidate["text"])
            view = evidence_graph(kb.graph(), chunks=candidates, compact=True)
            st.plotly_chart(graph_figure(view), width="stretch", key=f"{prefix}_context_graph")
            st.caption("This graph contains only the retrieved PDF pages and their evidence-linked topics, not unrelated documents.")
        else:
            st.info("No usable PDF context was retrieved for this answer.")
    with st.expander("Inspect this response's workflow"): 
        trace_table(result.get("trace", []))


def trace_table(trace):
    if trace:
        st.dataframe([{key: str(row.get(key, "")) for key in ("node", "status", "details")} for row in trace],
                     hide_index=True, width="stretch")
    else:
        st.caption("No workflow trace yet.")


def index_pdf(kb, filename, content, grade, vision, relations):
    if len(content) > MAX_PDF_BYTES:
        return "error", f"{filename}: exceeds 25 MB. Split or compress this PDF before uploading."
    if not filename.lower().endswith(".pdf") or not content.startswith(b"%PDF-"):
        return "error", f"{filename}: only valid PDF files are accepted."
    try:
        with st.spinner(f"Indexing {filename}. Local extraction and embedding can take several minutes..."):
            result = kb.ingest(filename, content, grade_band=grade, vision=vision, extract_relations=relations)
        if result.get("deduplicated"):
            message = f"Already indexed: {filename}. The same PDF and grade band were not added twice; existing extraction settings are unchanged."
        else:
            message = f"Indexed {filename}: {result.get('pages', 0)} pages, {result.get('chunks', 0)} evidence chunks."
        warnings = result.get("warnings", [])
        return "success", message + ("\nWarnings: " + "; ".join(map(str, warnings)) if warnings else "")
    except ModelError as exc:
        return "error", f"{filename}: {exc} Start Ollama and check the required local models."
    except ValueError as exc:
        return "error", f"{filename}: {exc}"
    except Exception:
        return "error", f"{filename}: indexing failed. Check local model availability, PDF validity and workspace permissions. No exception content is logged by this interface."


def ask_tab(kb, llm, documents, ready, grade, teacher):
    st.subheader("Your policies. Answers with receipts.")
    st.markdown("Ask a practical staff question. StaffDesk uses **only indexed PDFs**, not the web or general model knowledge. Every answer needs verifiable page evidence.")
    lookup = {doc["id"]: doc for doc in documents}
    options = [""] + list(lookup)
    preferred = next((i for i, key in enumerate(options) if key and lookup[key]["name"] == FILENAME), len(options) - 1)
    selected = st.selectbox("PDF to answer from", options, index=preferred,
                            format_func=lambda key: f"{lookup[key]['name']} ({lookup[key]['grade_band']})" if key else "All indexed PDFs",
                            key="answer_document", on_change=reset_session)
    document_ids = [selected] if selected else None
    if selected:
        st.caption("Search is restricted to this PDF. Changing the PDF clears the old conversation, but keeps the stored documents.")
        for warning in lookup[selected].get("warnings", []):
            st.warning(str(warning))
    elif len(documents) > 1:
        st.warning("You are searching several PDFs. Select a single PDF for controlled testing to avoid mixing policies.")
    if not documents:
        st.info("Start in PDF Library: upload a school policy PDF or explicitly index the fictional demo. Nothing is loaded automatically.")
    elif not ready:
        st.info("Your PDF library remains available offline. Start Ollama and install the selected models to ask questions.")
    if not st.session_state.messages:
        st.caption("Try a question supported by your own PDFs, such as: What is the absence reporting procedure? Which induction steps apply to new staff?")
    for index, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                show_result(kb, message["result"], f"chat_{index}")
            else:
                st.text(message["content"])
    with st.form("ask_form", clear_on_submit=True):
        question = st.text_area("Your question", key="question", placeholder="Ask about a policy, process or staff responsibility...", max_chars=4000, height=100)
        submitted = st.form_submit_button("Ask StaffDesk", type="primary", disabled=not documents or not ready)
    st.caption("Similarity is a retrieval heuristic, not calibrated confidence or a guarantee. Always check the original policy and its effective date.")
    if submitted:
        if not question.strip():
            st.warning("Enter a question before asking StaffDesk.")
            return
        history = [{"role": item["role"], "content": item["content"]} for item in st.session_state.messages]
        try:
            with st.spinner("Checking scope, retrieving PDF evidence and validating citations..."):
                result = PolicyWorkflow(kb, llm).run(question.strip(), grade_band=grade, teacher_type=teacher, history=history, document_ids=document_ids)
            st.session_state.messages.extend([
                {"role": "user", "content": question.strip()},
                {"role": "assistant", "content": result.get("answer", ""), "result": result},
            ])
            st.session_state.results.append(result)
            st.session_state.analytics.append({"category": result.get("category", "Policy"),
                                               "sensitive": bool(result.get("sensitive")),
                                               "abstained": bool(result.get("abstained"))})
            st.rerun()
        except ModelError as exc:
            st.error(f"Local model unavailable: {exc} No answer was generated. Start Ollama and retry.")
        except Exception:
            st.error("The local workflow could not complete. No answer was generated. Check Ollama, the selected models and workspace integrity, then retry.")


def library_tab(kb, documents, ingestion_ready):
    st.subheader("The evidence behind every answer")
    st.markdown("Original PDFs and their index are stored locally. **Do not upload personal or sensitive records unless you are authorized to store them on this device.**")
    left, right = st.columns([1.5, 1], gap="large")
    with left:
        uploads = st.file_uploader("Upload policy PDFs", type=["pdf"], accept_multiple_files=True, help="PDF only. Maximum 25 MB per file, enforced before indexing.")
        upload_grade = st.selectbox("PDF grade band", GRADES, key="upload_grade")
        vision = st.checkbox("Read scanned pages and diagrams with local vision", key="vision")
        st.caption(f"Vision uses the fixed ingestion model ({DEFAULT_MODEL}), is slower, and may misread diagrams. Verify transcriptions against the original.")
        relations = st.checkbox("Extract semantic relationships", key="relations")
        st.caption("Optional and slow: local model extraction links assertions to verbatim page evidence. A linked quote is not proof that a relationship is correct. Structural and keyword links work without it.")
        if st.button("Index uploaded PDFs", type="primary", disabled=not uploads or not ingestion_ready):
            st.session_state.upload_feedback = [index_pdf(kb, item.name, item.getvalue(), upload_grade, vision, relations) for item in uploads]
            st.rerun()
    with right:
        with st.container(border=True):
            st.markdown("#### 10-page school-policy test PDF")
            st.caption("Fictional Maple Grove School policies: ten readable pages with attendance, leave, assessment, safety, privacy and trips. Use this PDF alone for testing.")
            sample = sample_policy_pdf()
            st.download_button("Download 10-page sample policies", sample, file_name=FILENAME, mime="application/pdf", on_click="ignore")
            if st.button("Index 10-page sample only", disabled=not ingestion_ready):
                feedback = index_pdf(kb, FILENAME, sample, "All", False, False)
                st.session_state.upload_feedback = [feedback]
                if feedback[0] == "success":
                    match = next((d for d in kb.documents() if d["name"] == FILENAME), None)
                    if match:
                        st.session_state.pending_document = match["id"]
                st.rerun()
            st.caption("Indexes native text, without vision rewriting. Selects this document for chat; existing PDFs remain untouched. Topic and role graph links are generated without a model call.")
        with st.container(border=True):
            st.markdown("#### Explore without school data")
            st.write("The fictional demo is a clearly labeled sample policy, not guidance for any real school. It is never added automatically.")
            if st.button("Index fictional demo PDF", disabled=not ingestion_ready):
                try:
                    feedback = index_pdf(kb, "StaffDesk-FICTIONAL-demo.pdf", demo_pdf(), upload_grade, vision, relations)
                    st.session_state.upload_feedback = [feedback]
                    st.rerun()
                except Exception:
                    st.error("The fictional demo could not be created. You can still upload a policy PDF.")
            st.caption("Uses the same extraction, embedding and storage pipeline as uploaded PDFs.")
    if not ingestion_ready:
        st.warning(f"Indexing needs Ollama with {DEFAULT_MODEL} and {EMBEDDING_MODEL} installed locally. Library browsing and downloads do not need Ollama.")
    for status, message in st.session_state.get("upload_feedback", []):
        getattr(st, status)(message)
    st.divider()
    st.markdown("#### Indexed library")
    if not documents:
        st.info("No PDFs indexed yet. Blank or unreadable PDFs cannot provide policy evidence.")
        return
    st.dataframe([{key: doc.get(key, "") for key in ("name", "pages", "chunks", "grade_band")} for doc in documents], hide_index=True, width="stretch")
    coverage = list(kb.coverage())
    if coverage:
        st.markdown("#### Extraction and vector coverage")
        st.dataframe(coverage, hide_index=True, width="stretch")
        for row in coverage:
            if row["missing_pages"] or not row["vectors_match"]:
                st.warning(f"{row['name']}: searchable pages {row['indexed_pages']}/{row['total_pages']}; "
                           f"missing pages {row['missing_pages']}; text chunks {row['text_chunks']}, vectors {row['vector_chunks']}. "
                           "This PDF is incomplete. Do not assume answers cover the entire document. Use the new sample PDF for a clean test.")
    lookup = {doc["id"]: doc for doc in documents}
    selected = st.selectbox("Inspect a PDF", list(lookup), format_func=lambda value: f"{lookup[value]['name']} · {lookup[value].get('grade_band', 'All')}")
    doc = lookup[selected]
    original_download(kb, selected, doc["name"], "library_original")
    for warning in doc.get("warnings", []):
        st.warning(str(warning))
    chunks = [chunk for chunk in kb.chunks() if chunk.get("document_id") == selected]
    if chunks:
        position = st.selectbox("Evidence chunk", range(len(chunks)), format_func=lambda value: f"Chunk {value + 1} · Page {chunks[value].get('page', '?')}")
        chunk = chunks[position]
        st.caption(f"{doc['name']} · Page {chunk.get('page', '?')} · {chunk.get('extraction_kind', 'PDF text')}")
        st.text(chunk.get("text", ""))
        if chunk.get("triples"):
            with st.expander("Evidence-linked assertions in this chunk"):
                st.dataframe(chunk["triples"], hide_index=True, width="stretch")


def graph_tab(kb):
    st.subheader("Follow the evidence")
    st.write("Explore document, page, chunk and entity connections. Keyword mentions are not policy assertions; extracted relationships require human review.")
    graph = kb.graph()
    docs = {d["id"]: d for d in kb.documents()}
    selected = st.selectbox("Graph PDF", [""] + list(docs), format_func=lambda key: docs[key]["name"] if key else "All indexed PDFs")
    mode = st.selectbox("Graph detail", ["Policy overview", "Full chunk provenance", "Last answer context"])
    candidates = st.session_state.results[-1].get("retrieved_context", []) if st.session_state.results else []
    if mode == "Last answer context":
        candidates = [c for c in candidates if not selected or c["document_id"] == selected]
    graph = evidence_graph(graph, chunks=candidates if mode == "Last answer context" else None,
                           document_ids=[selected] if selected else None, compact=mode != "Full chunk provenance")
    controls = st.columns([2, 1])
    focus = controls[0].text_input("Focus on a node or phrase", placeholder="For example: Principal, attendance or a PDF name")
    cap = controls[1].slider("Maximum visible nodes", min_value=20, max_value=250, value=120, step=10)
    if graph.number_of_nodes() == 0:
        st.info("The graph is empty. Index a PDF or ask a question to create evidence connections for this view.")
        return
    visible = select_graph_view(graph, focus, cap)
    st.caption(f"Showing {visible.number_of_nodes()} of {graph.number_of_nodes()} nodes. Matching nodes are selected before the display cap. Overview connects pages directly to mentioned roles and topics.")
    if visible.number_of_nodes():
        figure = graph_figure(visible, max_nodes=cap)
        st.plotly_chart(figure, width="stretch", config={"displaylogo": False, "scrollZoom": True})
        st.markdown("#### Nodes and entities")
        st.dataframe([{"id": str(node), "label": str(attrs.get("label", node)), "kind": attrs.get("kind", "entity")} for node, attrs in visible.nodes(data=True)], hide_index=True, width="stretch")
        st.markdown("#### Relationships and page evidence")
        edges = [{"from": str(visible.nodes[u].get("label", u)), "relationship": attrs.get("relation", attrs.get("kind", "linked")),
                  "to": str(visible.nodes[v].get("label", v)), "kind": attrs.get("kind", ""),
                  "source": attrs.get("source", ""), "page": str(attrs.get("page", "")),
                  "evidence": attrs.get("evidence", ""), "document_id": attrs.get("document_id", "")}
                 for u, v, attrs in visible.edges(data=True)]
        if edges:
            st.dataframe(edges, hide_index=True, width="stretch")
        else:
            st.caption("No relationships in this view.")
    else:
        st.info("No matching nodes. Try a broader phrase or clear the focus.")
    st.download_button("Download complete graph JSON", json.dumps(nx.node_link_data(graph), ensure_ascii=False, indent=2, default=str),
                       file_name="staffdesk-knowledge-graph.json", mime="application/json", on_click="ignore")
    st.caption("Export includes local evidence snippets. Handle it with the same care as the original PDFs. Charts render locally without a CDN.")


def insights_tab():
    st.subheader("A workflow you can inspect")
    st.markdown("**Validate scope → Triage → Retrieve PDF evidence → Respond or abstain → Finalize**")
    st.caption("Weak retrieval triggers at most one query rewrite and retry. Sensitive topics require human review. No PDF evidence means no policy answer.")
    steps = st.columns(3)
    for column, title, body in zip(steps, ["01 / Scope & route", "02 / Find & verify", "03 / Cite & review"],
                                   ["Validate the question, classify its category and retain the selected grade scope.",
                                    "Retrieve indexed chunks. Retry once if evidence is weak; do not invent missing policy.",
                                    "Validate verbatim citations, flag sensitive topics and show the workflow trace."]):
        with column.container(border=True):
            st.markdown(f"#### {title}")
            st.write(body)
    st.markdown("#### Session insights")
    events = st.session_state.analytics
    metrics = st.columns(3)
    metrics[0].metric("Questions processed", len(events))
    metrics[1].metric("Abstentions", sum(row["abstained"] for row in events))
    metrics[2].metric("Sensitive topics", sum(row["sensitive"] for row in events))
    st.caption("Conversation, traces and category analytics stay in this Streamlit session only. StaffDesk does not persist chat or analytics logs by default. New chat clears all three, not the PDF library.")
    if events:
        counts = Counter(row["category"] for row in events)
        st.bar_chart(dict(Category=list(counts), Questions=list(counts.values())), x="Category", y="Questions", color="#0f766e")
    results = st.session_state.results
    if results:
        selected = st.selectbox("Inspect a response trace", range(len(results)), index=len(results) - 1,
                                format_func=lambda value: f"Response {value + 1} · {results[value].get('category', 'Policy')}")
        trace_table(results[selected].get("trace", []))
    else:
        st.info("Ask your first PDF-backed question to see a real execution trace and category breakdown.")


def main():
    st.set_page_config(page_title="StaffDesk | Local policy intelligence", layout="wide", initial_sidebar_state="expanded")
    st.markdown("""<style>
    .stApp {background: #f5f7fb; color: #14283f;}
    [data-testid="stSidebar"] {background: #eaf0f5;}
    .block-container {padding-top: 2.3rem; max-width: 1450px;}
    h1, h2, h3 {letter-spacing: -0.035em; color: #132d46;}
    [data-testid="stMetric"] {background: white; padding: 16px 20px; border: 1px solid #dce5ec; border-radius: 12px;}
    [data-testid="stMetricLabel"] {color: #486076;}
    [data-testid="stMetricValue"] {color: #0f766e;}
    [data-testid="stChatMessage"] {background: white; border: 1px solid #dce5ec; border-radius: 12px;}
    [data-testid="stText"] {white-space: pre-wrap; overflow-wrap: anywhere; font-family: inherit;}
    .stTabs [data-baseweb="tab-list"] {gap: 22px; border-bottom: 1px solid #dce5ec;}
    .stTabs [data-baseweb="tab"] {font-weight: 600; padding-bottom: 14px;}
    .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {background: #0f766e; border-color: #0f766e;}
    </style>""", unsafe_allow_html=True)
    for key in ("messages", "results", "analytics"):
        if key not in st.session_state:
            st.session_state[key] = []
    st.caption("STAFFDESK / LOCAL POLICY WORKSPACE")
    st.title("Clarity for the school day.")
    st.write("A private, evidence-first desk for staff policies, procedures and institutional knowledge.")
    with st.sidebar:
        st.header("StaffDesk")
        st.caption("LOCAL MODELS · PDF EVIDENCE")
        st.warning("Loopback use only. No authentication: not for public sharing or untrusted networks.")
        grade = st.selectbox("Answer grade band", GRADES, key="answer_grade")
        teacher = st.selectbox("Teacher context", ["Existing", "New"], key="teacher_type")
        st.caption("Grade scopes retrieval. Teacher context changes presentation, never policy facts.")
        installed = []
        discovery_error = False
        try:
            probe = Ollama(model=DEFAULT_MODEL, embedding_model=EMBEDDING_MODEL)
            rows = probe.available_models()
            installed = sorted({row if isinstance(row, str) else row.get("name", row.get("model", "")) for row in rows
                                if isinstance(row, str) or not row.get("remote_host") and not row.get("remote_model")})
            installed = [name for name in installed if name and ":cloud" not in name]
        except Exception:
            discovery_error = True
        options = list(dict.fromkeys([DEFAULT_MODEL] + [name for name in installed if name != EMBEDDING_MODEL]))
        selected_model = st.selectbox("Local chat model", options, key="chat_model")
        st.caption(f"Fixed embeddings: {EMBEDDING_MODEL}. Ingestion uses {DEFAULT_MODEL}; changing chat models never opens another index.")
        ready = not discovery_error and selected_model in installed and EMBEDDING_MODEL in installed
        ingestion_ready = not discovery_error and DEFAULT_MODEL in installed and EMBEDDING_MODEL in installed
        if ready:
            st.success("Local Ollama ready")
        else:
            st.warning("Local models unavailable")
        with st.expander("Local setup & connection", expanded=not ready):
            st.write("Start Ollama, then install the required models. No cloud model or API key is used.")
            st.code(f"ollama serve\nollama pull {DEFAULT_MODEL}\nollama pull {EMBEDDING_MODEL}", language="powershell")
            st.caption("Model downloads need internet once; inference then stays on this machine. Select only models installed locally.")
            st.code("streamlit run app.py --server.address 127.0.0.1 --server.port 8503 --browser.gatherUsageStats false", language="powershell")
        st.button("Refresh local models", key="refresh_models")
        st.divider()
        st.button("New chat / clear session", on_click=reset_session, width="stretch")
        st.caption("Clears session conversation, traces and analytics. Stored PDFs are preserved.")
    try:
        kb = knowledge_base(str(DATA_ROOT))
        documents = kb.documents()
        stats = kb.stats()
    except Exception as exc:
        st.error("The local PDF workspace could not be opened. Run only one StaffDesk server per workspace; check permissions or restore a damaged index.")
        if isinstance(exc, (ValueError, ModelError)):
            st.text(str(exc))
        st.caption(f"Workspace: {DATA_ROOT}")
        st.stop()
    if "pending_document" in st.session_state:
        pending = st.session_state.pop("pending_document")
        feedback = st.session_state.get("upload_feedback", [])
        reset_session()
        st.session_state.answer_document = pending
        st.session_state.upload_feedback = feedback
    for column, name, label in zip(st.columns(5), ["documents", "pages", "chunks", "entities", "relations"],
                                   ["Policy PDFs", "PDF pages (check coverage)", "Evidence chunks", "Entities", "Extracted relations"]):
        column.metric(label, stats.get(name, 0))
    st.write("")
    ask, library, graph, insights = st.tabs(["Ask StaffDesk", "PDF Library", "Knowledge Graph", "Workflow & Insights"])
    with ask:
        llm = Ollama(model=selected_model, embedding_model=EMBEDDING_MODEL) if ready else None
        ask_tab(kb, llm, documents, ready, grade, teacher)
    with library:
        library_tab(kb, documents, ingestion_ready)
    with graph:
        graph_tab(kb)
    with insights:
        insights_tab()
    st.divider()
    st.caption("LOCAL BY DESIGN · No cloud inference · No automatic demo data · PDF evidence, not institutional authority")


if __name__ == "__main__":
    main()
