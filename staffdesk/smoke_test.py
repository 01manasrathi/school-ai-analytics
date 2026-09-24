from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from demo import demo_pdf, diagram_pdf
from graph_view import graph_figure
from knowledge import KnowledgeBase
from models import Ollama
from workflow import PolicyWorkflow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vision", action="store_true")
    parser.add_argument("--relations", action="store_true")
    args = parser.parse_args()
    llm = Ollama()
    print("Local chat model:", llm.model, llm.model_digest(llm.model), flush=True)
    print("Local embedding model:", llm.embedding_model, llm.model_digest(llm.embedding_model), flush=True)
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="staffdesk-verification-") as temporary:
        kb = KnowledgeBase(Path(temporary), llm)
        try:
            pdf = demo_pdf()
            result = kb.ingest("FICTIONAL-demo-handbook.pdf", pdf, extract_relations=args.relations)
            assert result["pages"] == 3 and result["chunks"] >= 3, result
            assert kb.ingest("duplicate.pdf", pdf)["deduplicated"]
            assert kb.pdf_bytes(result["id"]) == pdf
            hits = kb.search("How soon must teachers return marked assignments?")
            assert hits and any("7 school days" in hit["text"] for hit in hits), hits
            print("PDF ingestion, persistent vectors, deduplication and retrieval passed.", flush=True)
            workflow = PolicyWorkflow(kb, llm)
            answer = workflow.run("How soon must teachers return marked assignments?")
            print(json.dumps(answer, indent=2, ensure_ascii=True), flush=True)
            assert not answer["abstained"] and "7 school days" in answer["answer"] and answer["sources"], answer
            assert any(t["node"] == "respond" and t["status"] == "ok" for t in answer["trace"]), "Live model did not produce a validated answer."
            irrelevant = workflow.run("What is the cafeteria menu for tomorrow?")
            assert irrelevant["abstained"], irrelevant
            print("Grounded answer and out-of-document abstention passed.", flush=True)
            figure = graph_figure(kb.graph())
            assert figure.data
            assert len(figure.to_json()) > 1000
            if args.relations:
                assert kb.stats()["relations"] > 0, "No evidence-validated semantic relationships extracted."
            if args.vision:
                visual = kb.ingest("FICTIONAL-demo-diagram.pdf", diagram_pdf(), vision=True, extract_relations=args.relations)
                print("Vision warnings:", visual["warnings"], flush=True)
                visual_chunks = [c for c in kb.chunks() if c["document_id"] == visual["id"]]
                assert any("vision" in c["extraction_kind"] and "Principal" in c["text"] for c in visual_chunks)
                print("PDF diagram vision extraction passed.", flush=True)
            print("Graph stats:", kb.stats(), flush=True)
        finally:
            kb.close()
        reopened = KnowledgeBase(Path(temporary), llm)
        try:
            assert reopened.documents() and reopened.search("marked assignments")
            print("Index reopened successfully.", flush=True)
        finally:
            reopened.close()
    print(f"Live verification passed in {time.monotonic() - start:.1f} seconds.", flush=True)


if __name__ == "__main__":
    main()
