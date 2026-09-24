import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import networkx as nx
from pypdf import PdfReader

import knowledge
from graph_view import evidence_graph, graph_figure, select_graph_view
from sample_policies import CASES, sample_policy_pdf
from test_knowledge import FakeModels, make_pdf
from test_workflow import FakeKB, FakeLLM, PolicyWorkflow, chunk, response


class PDFContextTests(unittest.TestCase):
    def test_fixture_has_ten_readable_pages_with_expected_facts(self):
        reader = PdfReader(io.BytesIO(sample_policy_pdf()))
        self.assertEqual(len(reader.pages), 10)
        for case in CASES:
            if case["page"]:
                text = reader.pages[case["page"] - 1].extract_text()
                for phrase in case["expected"]:
                    self.assertIn(phrase, text)
        self.assertEqual(sample_policy_pdf(), sample_policy_pdf())

    def test_pdfium_recovers_native_text_after_font_parser_failure(self):
        reader = MagicMock()
        reader.is_encrypted = False
        broken_page = MagicMock()
        broken_page.extract_text.side_effect = KeyError("bbox")
        reader.pages = [broken_page]
        with tempfile.TemporaryDirectory() as root:
            kb = knowledge.KnowledgeBase(Path(root), FakeModels())
            try:
                with patch.object(knowledge, "PdfReader", return_value=reader):
                    doc = kb.ingest("font-problem.pdf", make_pdf("Parents report absence by 8:45 AM."))
                self.assertIn("8:45 AM", kb.chunks()[0]["text"])
                self.assertEqual(kb.chunks()[0]["extraction_kind"], "pdfium")
                self.assertEqual(kb.coverage()[0]["indexed_pages"], 1)
            finally:
                kb.close()

    def test_document_filter_excludes_other_pdf_even_with_identical_vectors(self):
        with tempfile.TemporaryDirectory() as root:
            model = FakeModels()
            model.embed = lambda texts, query=False: [[1.0, 0.0] for _ in texts]
            kb = knowledge.KnowledgeBase(Path(root), model)
            try:
                old = kb.ingest("old.pdf", make_pdf("Planned leave needs 99 days notice."))
                selected = kb.ingest("selected.pdf", make_pdf("Planned leave needs 5 school days notice."))
                hits = kb.search("planned leave", document_ids=[selected["id"]])
                self.assertEqual({c["document_id"] for c in hits}, {selected["id"]})
                self.assertEqual(kb.search("leave", document_ids=[]), [])
                self.assertEqual(kb.search("leave", document_ids=["unknown"]), [])
                self.assertEqual(len(kb.documents()), 2)
                self.assertEqual(kb.coverage()[0]["vector_chunks"], 1)
                self.assertNotEqual(old["id"], selected["id"])
            finally:
                kb.close()

    def test_hybrid_rank_resolves_dense_ties_with_specific_policy_terms(self):
        with tempfile.TemporaryDirectory() as root:
            model = FakeModels()
            model.embed = lambda texts, query=False: [[1.0, 0.0] for _ in texts]
            kb = knowledge.KnowledgeBase(Path(root), model)
            try:
                kb.ingest("policies.pdf", make_pdf("Teachers mark assignments promptly.", "The evacuation assembly point is the north sports field."))
                hits = kb.search("evacuation assembly point", limit=2)
                self.assertEqual(hits[0]["page"], 2)
                self.assertGreater(hits[0]["lexical_score"], 0)
            finally:
                kb.close()

    def test_graph_nonmatching_focus_is_empty_not_unrelated_overview(self):
        graph = nx.MultiDiGraph()
        graph.add_node("d", kind="document", label="handbook.pdf")
        self.assertFalse(graph_figure(graph, focus="nonexistent-topic").data)

    def test_invalid_answer_is_not_presented_as_successful_policy_answer(self):
        result = PolicyWorkflow(FakeKB(), FakeLLM(respond="malformed")).run("When is the cafeteria open?")
        self.assertTrue(result["abstained"])
        self.assertFalse(result["sources"])
        self.assertNotIn(chunk()["text"], result["answer"])
        self.assertEqual(result["retrieved_context"][0]["text"], chunk()["text"])

    def test_sensitive_flag_uses_cited_evidence_not_unrelated_candidate(self):
        result = PolicyWorkflow(FakeKB([[chunk(), chunk("s", "Safeguarding concerns go to the lead.", score=0.5)]]), FakeLLM()).run("When are assessment records due?")
        self.assertFalse(result["sensitive"])

    def test_context_graph_keeps_only_retrieved_page_provenance(self):
        with tempfile.TemporaryDirectory() as root:
            kb = knowledge.KnowledgeBase(Path(root), FakeModels())
            try:
                first = kb.ingest("first.pdf", make_pdf("The HR Coordinator reports to the Principal.", "The School Nurse reports to the Principal."))
                kb.ingest("other.pdf", make_pdf("The IT Coordinator reports to the Principal."))
                selected = [c for c in kb.chunks() if c["document_id"] == first["id"] and c["page"] == 1]
                graph = evidence_graph(kb.graph(), chunks=selected, compact=True)
                self.assertTrue(graph.number_of_edges())
                self.assertTrue(all(e["source"] == "first.pdf" and e["page"] == 1 for _, _, e in graph.edges(data=True)))
                self.assertTrue(any(e["kind"] == "explicit_relation" for _, _, e in graph.edges(data=True)))
                self.assertFalse(any(a["kind"] == "chunk" for _, a in graph.nodes(data=True)))
            finally:
                kb.close()

    def test_graph_focus_survives_cap_and_searches_full_chunk_text(self):
        graph = nx.MultiDiGraph()
        for i in range(100):
            graph.add_node(str(i), kind="page", label=f"Page {i}")
        graph.add_node("important", kind="entity", label="Attendance Officer")
        graph.add_node("chunk", kind="chunk", label="Truncated introduction", text="Late paragraph refers to medication consent.")
        graph.add_edge("99", "important", kind="mentions")
        self.assertIn("important", select_graph_view(graph, "Attendance Officer", 2))
        self.assertIn("chunk", select_graph_view(graph, "medication", 2))

    def test_pdf_line_wrapping_does_not_invalidate_exact_words(self):
        text = "Teachers return marked assignments within 7 school days\nof submission."
        quote = text.replace("\n", " ")
        result = PolicyWorkflow(FakeKB([[chunk(text=text)]]), FakeLLM(respond=response(quote))).run("When are assignments returned?")
        self.assertFalse(result["abstained"])
        self.assertEqual(result["sources"][0]["quote"], text)

    def test_workflow_preserves_selected_document_even_on_retry(self):
        class ScopedKB:
            def __init__(self):
                self.calls = []
            def search(self, query, grade_band="All", limit=6, document_ids=None):
                self.calls.append(document_ids)
                return [dict(chunk(score=0.1), document_id="wrong")]
        kb = ScopedKB()
        result = PolicyWorkflow(kb, FakeLLM()).run("What is the policy?", document_ids=["selected"])
        self.assertTrue(result["abstained"])
        self.assertEqual(kb.calls, [["selected"], ["selected"]])
        self.assertEqual(result["retrieved_context"], [])


if __name__ == "__main__":
    unittest.main()
