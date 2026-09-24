# StaffDesk: local PDF school-policy assistant

Independent application; never import or modify School Management or Student Analytics data.
This is a fresh local implementation of the policy-assistant workflow demonstrated by
https://github.com/ramlapoonawala/StaffDesk-LangGraph, not a copy of its notebook or private handbook.

## Setup and run (PowerShell, from this folder)

```powershell
.\setup.ps1
.\start.ps1
```

Setup creates `.venv`, installs `requirements.txt`, and pulls `qwen3.5:4b` and
`nomic-embed-text:v1.5` into the existing Ollama installation. No global pip changes,
Node.js, Docker, paid model, cloud account, or standalone database server is needed.
Open http://127.0.0.1:8503. The app is loopback-only and has no authentication; do not expose
it to the public internet or use a public share tunnel with school documents.

## Required APIs and models

Only Ollama's loopback HTTP API is used:
- `GET /api/tags`: installed local models and digests.
- `POST /api/show`: model capabilities.
- `POST /api/embed`: local document/query embeddings.
- `POST /api/chat`: local classification, query rewrite, cited answers, optional PDF vision
  extraction, and optional structured relationship extraction.

No API keys are required. No Groq, OpenAI, Notion, Google Drive, WeatherAPI, Semantic Scholar,
Hugging Face token, or LangSmith account is needed. Those upstream integrations are deliberately
excluded: answers must come only from uploaded PDFs, not web or external service enrichment.
LangGraph packages include a LangSmith library transitively, but tracing is disabled.
Installation/model downloads need internet; document processing does not.

Qwen3.5 4B is a recent Apache-2.0 chat/vision model selected for the available 32 GB system RAM
and 4 GB NVIDIA T500. It is not claimed to be the world's best model. Larger models may improve
answers but can be much slower and require more memory. Nomic Embed Text v1.5 is a lightweight
Apache-2.0 embedding model. Model licenses are separate from Ollama's license. Model tags may
change upstream; embedding identity is checked against the stored index. Use a new data folder
when changing embedding models rather than mixing incompatible embeddings.

## Workflow

1. Upload school PDFs in the PDF Library and assign All, Primary, Middle, or Secondary scope.
2. Validate the file, extract text by physical PDF page, and split into overlapping page-local
   chunks. Titles/printed page labels can differ from physical page numbers used in citations.
3. Optionally render scanned pages and diagrams with PDFium and read them with the local vision
   model. Vision transcription is model-generated and must be checked against the original.
4. Embed chunks locally and persist vectors/payloads with Qdrant local mode. Qdrant owns its
   on-disk storage format; unlike the other apps, this project intentionally uses a vector store,
   not CSV-only storage. Original PDF files and JSON metadata remain local under `data/`.
5. Build a NetworkX knowledge graph linking documents, pages, chunks, and mentioned entities.
   Optional semantic relationships include an exact supporting excerpt and page provenance.
   Mention edges are not factual policy assertions. Extracted relationships require human review.
6. LangGraph orchestrates triage, retrieval, a bounded low-confidence rewrite/retry, response,
   and citation validation. Grade scope is preserved through retrieval. New-teacher responses
   request more explanation; experienced-teacher responses request brevity.
7. Answers expose retrieved PDF sources and page numbers, an execution trace, and heuristic
   retrieval similarity. Low-evidence queries abstain. Invalid generated responses also abstain;
   retrieved passages remain available in a separate context panel and are never substituted
   for a verified policy answer. Citation matching tolerates whitespace/line-wrap differences,
   never changed words or numbers.
8. Explore the interactive Plotly graph, relation evidence, and local graph export.

Citation checks verify source membership and verbatim evidence, not complete semantic entailment.
Review important HR/safeguarding decisions against the actual handbook and school leadership.
PDF text is treated as untrusted evidence, never as executable instructions. No shell execution,
external actions, or arbitrary code tools are exposed to the model.

## Controlled 10-page policy test

`Maple_Grove_School_Sample_Policies_10_Pages.pdf` is a deterministic, fictional handbook with
exactly ten text-readable pages. Its sibling `.questions.json` contains 12 questions, expected
facts and physical PDF page numbers. `sample_policies.py` generates both without overwriting
existing files; use `--output NEW_FILENAME.pdf` when regenerating for comparison.

From this directory:
```powershell
.\start.ps1 -SamplePolicies
```
This indexes only the ten-page sample in the separate `sample_test_data/` workspace, then starts
Streamlit on port 8503. The old `data/` PDFs and index are never deleted or rewritten. Stop the
existing StaffDesk server first if port 8503 is already occupied. Alternatively, use the
**Index 10-page sample only** button in PDF Library; it adds the sample and selects it for chat,
while preserving other documents. **PDF to answer from** must show the sample, not All indexed PDFs.

Verify the persisted index before starting the server (one process owns each Qdrant directory):
```powershell
.\.venv\Scripts\python.exe verify_sample.py
.\.venv\Scripts\python.exe verify_sample.py --chat
```
The first command tests real embeddings/retrieval for all cases plus graph construction and
index reopening. `--chat` also runs real Ollama responses and validates expected facts/citations;
`--case 3 --case 4` selects individual cases. Detailed reports are written under the sample
workspace with unique names. These reports contain only fictional sample text.

PDF Library now displays total versus searchable pages, missing pages, text chunk counts and
Qdrant vector counts. A font-metadata error (`KeyError: bbox`) in the original PyPDF extractor
was reproduced on an existing upload; the PDFium native-text fallback recovers text without
LLM transcription. This improves NEW ingestion, not already-published incomplete indexes.
Re-uploading identical bytes still deduplicates; use a new workspace to re-extract old documents
without overwriting their published data. Blank pages remain visibly unindexed.

Retrieval combines cosine similarity and local BM25 keyword ranking via reciprocal-rank fusion.
Document and grade filters apply before retrieval and are rechecked by the workflow. Similarity
is not a calibrated probability. The graph is a provenance visualization, not a separate source
of facts: queries still retrieve actual PDF chunks. **Retrieved context and answer graph** shows
candidate passages and their page-linked topics for each response. **Policy overview** hides chunk
nodes, **Full chunk provenance** shows them, and **Last answer context** excludes unrelated pages.
The graph also detects literal named-role `reports to` statements; these are distinct from
optional LLM-extracted assertions. Changing the selected chat PDF clears stale conversation context.

## Older three-page demo

In PDF Library, choose **Index fictional demo PDF**. The three-page document is generated in memory
by `demo.py` and goes through the same PDF extraction and embedding pipeline as real uploads.
It is never presented as a real school's policy. Try:
- How soon must teachers return marked assignments?
- Who approves planned leave, and how early must it be requested?
- Who should staff contact about safeguarding concerns?
- What is the school's cafeteria menu? (Not provided; should abstain.)

Do not mix fictional demonstration policies with real school policies in a live workspace.
Use `STAFFDESK_DATA_DIR` to select a separate data folder and restart the app. The default is
`staffdesk/data`, independent of the launch working directory. One Streamlit process owns one
Qdrant local directory; a second process must use a different directory.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
```

Unit tests use fake model responses and temporary datasets. Live model verification must be
run separately; a passing fake-model test does not demonstrate actual model quality.
`models.py` uses HTTP directly to avoid requiring the old global Ollama Python client.
Keep model calls bounded and serialized to avoid exhausting local GPU memory.
Do not log PDF text or user conversations to external services. Browser chat/analytics are session-local.
Data is not encrypted at rest; use OS permissions/disk encryption for real school material.
