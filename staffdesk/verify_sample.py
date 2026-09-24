from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from graph_view import evidence_graph, graph_figure
from knowledge import KnowledgeBase
from models import Ollama
from sample_policies import CASES, FILENAME, sample_policy_pdf
from workflow import PolicyWorkflow


def prepare(root):
    kb = KnowledgeBase(root, Ollama())
    try:
        if any(d["name"] != FILENAME for d in kb.documents()):
            raise ValueError("The sample workspace contains another PDF. Choose a new workspace; nothing was deleted.")
        doc = kb.ingest(FILENAME, sample_policy_pdf(), grade_band="All", vision=False, extract_relations=False)
        coverage = kb.coverage()[0]
        assert coverage["total_pages"] == coverage["indexed_pages"] == 10, coverage
        assert coverage["vectors_match"] and coverage["vector_chunks"] > 10, coverage
        print("Coverage:", json.dumps(coverage), flush=True)
        return doc
    finally:
        kb.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parent / "sample_test_data")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--chat", action="store_true")
    parser.add_argument("--case", type=int, action="append")
    args = parser.parse_args()
    start = time.monotonic()
    doc = prepare(args.workspace)
    if args.prepare_only:
        return
    kb = KnowledgeBase(args.workspace, Ollama())
    results = []
    try:
        flow = PolicyWorkflow(kb, kb.llm)
        for index, case in enumerate(CASES, 1):
            if args.case and index not in args.case:
                continue
            hits = kb.search(case["question"], document_ids=[doc["id"]])
            row = dict(case, case=index, retrieved_pages=[h["page"] for h in hits],
                       retrieval_pass=case["page"] is None or case["page"] in [h["page"] for h in hits[:3]])
            if args.chat:
                answer = flow.run(case["question"], document_ids=[doc["id"]])
                row["response"] = answer
                if case["page"]:
                    normalized = " ".join(answer["answer"].split()).casefold()
                    row["answer_pass"] = (not answer["abstained"] and all(s.casefold() in normalized for s in case["expected"])
                                          and case["page"] in [s["page"] for s in answer["sources"]])
                else:
                    row["answer_pass"] = answer["abstained"] or any(phrase in answer["answer"].casefold()
                        for phrase in ("does not specify", "does not define", "does not set", "contains no", "cannot be answered"))
            results.append(row)
            print(json.dumps(row, ensure_ascii=True), flush=True)
        graph = evidence_graph(kb.graph(), document_ids=[doc["id"]], compact=True)
        assert len(graph) > 20 and kb.stats()["relations"] > 0
        assert graph_figure(graph).data
        rows = [{key: value for key, value in row.items() if key != "response"} for row in results]
        print("Summary:", json.dumps(rows, indent=2), flush=True)
        report = {"elapsed_seconds": round(time.monotonic() - start, 1), "stats": kb.stats(), "results": results}
        report_path = args.workspace / f"verification-{time.time_ns()}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Detailed verification:", report_path, flush=True)
        if not all(row["retrieval_pass"] and row.get("answer_pass", True) for row in results):
            raise AssertionError("Some sample checks failed; see the detailed verification above.")
        print("Sample verification passed.", flush=True)
    finally:
        kb.close()


if __name__ == "__main__":
    main()
