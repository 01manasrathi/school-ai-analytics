import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import networkx as nx
from pypdf import PdfWriter
from reportlab.pdfgen import canvas

if __package__:
    from . import knowledge
    from .graph_view import graph_figure
else:
    import knowledge
    from graph_view import graph_figure


class FakeModels:
    embedding_model = "fake-embed:v1"
    model = "fake-chat:v1"

    def __init__(self):
        self.digest = "sha256:fake-embedding-v1"
        self.calls = []
        self.response = '{"triples": []}'
        self.visual = "Students follow safety rules."

    def model_digest(self, model):
        self.calls.append(("digest", model))
        return self.digest

    def embed(self, texts, query=False):
        self.calls.append(("embed", query))
        vectors = []
        for text in texts:
            vector = [0.01] * 16
            for token in text.lower().split():
                slot = hashlib.sha256(token.encode()).digest()[0] % 16
                vector[slot] += 1.0
            vectors.append(vector)
        return vectors

    def chat(self, messages, schema=None, images=None):
        self.calls.append(("chat", bool(images)))
        return self.visual if images else self.response


def make_pdf(*pages):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, invariant=1)
    for page in pages:
        text = pdf.beginText(45, 780)
        for line in page.splitlines():
            text.textLine(line)
        pdf.drawText(text)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.llm = FakeModels()
        self.kb = knowledge.KnowledgeBase(self.root, self.llm)

    def tearDown(self):
        self.kb.close()
        self.temporary.cleanup()

    def test_constructor_is_offline_and_client_shared(self):
        self.assertEqual(self.llm.calls, [])
        other = knowledge.KnowledgeBase(self.root, self.llm)
        try:
            self.assertIs(other._client, self.kb._client)
            other.close()
            self.assertEqual(self.kb.documents(), [])
        finally:
            other.close()

    def test_ingestion_dedup_and_grade_are_separate(self):
        data = make_pdf("Students must record attendance.", "Teachers assign homework.")
        first = self.kb.ingest("policy.pdf", data, grade_band="6–8")
        duplicate = self.kb.ingest("renamed.pdf", data, grade_band="6–8")
        different_grade = self.kb.ingest("policy.pdf", data, grade_band="9–12")
        self.assertFalse(first["deduplicated"])
        self.assertTrue(duplicate["deduplicated"])
        self.assertEqual(first["id"], duplicate["id"])
        self.assertNotEqual(first["id"], different_grade["id"])
        self.assertEqual(len(self.kb.documents()), 2)
        self.assertEqual(self.kb.pdf_bytes(first["id"]), data)
        self.assertEqual(len(list((self.root / "pdfs").glob("*.pdf"))), 1)
        self.assertEqual(first["pages"], 2)
        self.assertEqual({c["page"] for c in self.kb.chunks()}, {1, 2})

    def test_duplicate_enrichment_warns_without_changing_existing_index(self):
        data = make_pdf("Teachers record attendance.")
        first = self.kb.ingest("policy.pdf", data)
        original_documents = self.kb.documents()
        original_chunks = self.kb.chunks()
        for options, labels in (
            ({"vision": True}, ["visual extraction"]),
            ({"extract_relations": True}, ["relationship extraction"]),
            ({"vision": True, "extract_relations": True},
             ["visual extraction", "relationship extraction"]),
        ):
            with self.subTest(options=options), patch.object(self.kb, "_extract") as extract, \
                    patch.object(self.llm, "embed") as embed:
                duplicate = self.kb.ingest("renamed.pdf", data, **options)
                self.assertTrue(duplicate["deduplicated"])
                self.assertEqual(duplicate["id"], first["id"])
                self.assertFalse(duplicate["vision"])
                self.assertFalse(duplicate["extract_relations"])
                warning = duplicate["warnings"][-1]
                for phrase in ["original extraction options", "was not applied", "separate new workspace", *labels]:
                    self.assertIn(phrase, warning)
                extract.assert_not_called()
                embed.assert_not_called()
                self.assertEqual(self.kb.documents(), original_documents)
                self.assertEqual(self.kb.chunks(), original_chunks)
                self.assertEqual(self.kb.pdf_bytes(first["id"]), data)
        ordinary_duplicate = self.kb.ingest("policy.pdf", data)
        self.assertEqual(ordinary_duplicate["warnings"], first["warnings"])

    def test_persistence_and_search_grade_filter(self):
        self.kb.ingest("lower.pdf", make_pdf("Students submit homework."), grade_band="6–8")
        self.kb.ingest("upper.pdf", make_pdf("Teachers record exam assessment."), grade_band="9–12")
        self.kb.ingest("shared.pdf", make_pdf("All students follow safety rules."))
        self.kb.close()
        self.kb = knowledge.KnowledgeBase(self.root, self.llm)
        lower = self.kb.search("homework", grade_band="6–8")
        self.assertTrue(lower)
        self.assertEqual({c["grade_band"] for c in lower}, {"6–8", "All"})
        self.assertTrue(all(-1 <= c["score"] <= 1 for c in lower))
        self.assertEqual(len(self.kb.search("students", limit=10)), 3)
        self.assertEqual({c["grade_band"] for c in self.kb.search("students", grade_band="unknown")}, {"All"})
        self.assertEqual(self.kb.search(" "), [])
        self.assertEqual(self.kb.stats()["documents"], 3)
        self.assertTrue(any(call == ("embed", True) for call in self.llm.calls))

    def test_corrupt_non_pdf_and_empty_rejected(self):
        for data in (b"not a PDF", b"%PDF-1.7\ncorrupt"):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    self.kb.ingest("bad.pdf", data)
        buffer = io.BytesIO()
        PdfWriter().write(buffer)
        with self.assertRaisesRegex(ValueError, "no pages|no extractable text"):
            self.kb.ingest("empty.pdf", buffer.getvalue())
        with self.assertRaisesRegex(ValueError, "no extractable text"):
            self.kb.ingest("blank.pdf", make_pdf(""))
        self.assertEqual(self.kb.documents(), [])
        self.assertFalse((self.root / "manifest.json").exists())

    def test_scanned_or_blank_page_warning_and_page_faithfulness(self):
        result = self.kb.ingest("mixed.pdf", make_pdf("", "Teachers track attendance."))
        self.assertTrue(any("Page 1" in warning for warning in result["warnings"]))
        self.assertEqual({c["page"] for c in self.kb.chunks()}, {2})
        graph = self.kb.graph()
        self.assertEqual(sum(d["kind"] == "page" for _, d in graph.nodes(data=True)), 2)

    def test_limits(self):
        with self.assertRaisesRegex(ValueError, "25 MB"):
            self.kb.ingest("huge.pdf", b"%PDF-" + b"x" * knowledge.MAX_PDF_BYTES)
        with self.assertRaisesRegex(ValueError, "150-page"):
            self.kb.ingest("long.pdf", make_pdf(*(["Text"] * 151)))
        self.assertEqual(self.kb.documents(), [])

    def test_model_digest_mismatch_keeps_data(self):
        original = self.kb.ingest("policy.pdf", make_pdf("Attendance policy."))
        self.llm.digest = "sha256:changed"
        with self.assertRaisesRegex(ValueError, "new workspace"):
            self.kb.search("attendance")
        with self.assertRaisesRegex(ValueError, "new workspace"):
            self.kb.ingest("another.pdf", make_pdf("Different policy."))
        self.assertEqual(self.kb.documents()[0]["id"], original["id"])
        other = FakeModels()
        other.embedding_model = "different-model"
        with self.assertRaisesRegex(ValueError, "new workspace"):
            knowledge.KnowledgeBase(self.root, other)
        self.assertEqual(self.kb.stats()["documents"], 1)

    def test_failed_vector_publication_rolls_back(self):
        first = self.kb.ingest("first.pdf", make_pdf("Attendance matters."))
        original_upsert = self.kb._client.upsert

        def fail_after_upsert(*args, **kwargs):
            original_upsert(*args, **kwargs)
            raise RuntimeError("Simulated interrupted publication")

        with patch.object(self.kb._client, "upsert", side_effect=fail_after_upsert):
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                self.kb.ingest("second.pdf", make_pdf("Homework matters."))
        self.assertEqual([d["id"] for d in self.kb.documents()], [first["id"]])
        self.assertEqual({c["document_id"] for c in self.kb.search("homework")}, {first["id"]})
        self.assertEqual(len(list((self.root / "chunks").glob("*.json"))), 1)
        self.assertEqual(self.kb._client.count(knowledge.COLLECTION, exact=True).count, first["chunks"])

    def test_failed_manifest_commit_does_not_publish(self):
        original = knowledge._atomic_json

        def fail_manifest(path, value):
            if Path(path).name == "manifest.json":
                raise OSError("Simulated manifest failure")
            return original(path, value)

        data = make_pdf("Students attend school.")
        with patch.object(knowledge, "_atomic_json", side_effect=fail_manifest), \
                patch.object(self.kb._client, "delete_collection") as delete_collection:
            with self.assertRaisesRegex(OSError, "manifest failure"):
                self.kb.ingest("policy.pdf", data)
            delete_collection.assert_not_called()
        self.assertEqual(self.kb.documents(), [])
        self.assertFalse((self.root / "manifest.json").exists())
        self.assertTrue(self.kb._client.collection_exists(knowledge.COLLECTION))
        self.assertEqual(self.kb._client.count(knowledge.COLLECTION, exact=True).count, 0)
        self.assertEqual(list((self.root / "chunks").glob("*.json")), [])
        self.assertEqual(list((self.root / "pdfs").glob("*.pdf")), [])
        successful = self.kb.ingest("policy.pdf", data)
        self.assertFalse(successful["deduplicated"])
        self.assertEqual(self.kb._client.count(knowledge.COLLECTION, exact=True).count, successful["chunks"])
        self.kb.close()
        self.kb = knowledge.KnowledgeBase(self.root, self.llm)
        self.assertEqual([d["id"] for d in self.kb.documents()], [successful["id"]])
        self.assertEqual(self.kb.pdf_bytes(successful["id"]), data)
        self.assertEqual({c["document_id"] for c in self.kb.search("school")}, {successful["id"]})

    def test_retained_empty_collection_dimension_mismatch_is_actionable(self):
        original = knowledge._atomic_json

        def fail_manifest(path, value):
            if Path(path).name == "manifest.json":
                raise OSError("Simulated manifest failure")
            return original(path, value)

        data = make_pdf("Teachers record attendance.")
        with patch.object(knowledge, "_atomic_json", side_effect=fail_manifest):
            with self.assertRaises(OSError):
                self.kb.ingest("policy.pdf", data)
        self.kb.close()
        self.kb = knowledge.KnowledgeBase(self.root, self.llm)
        self.assertEqual(self.kb._client.count(knowledge.COLLECTION, exact=True).count, 0)
        with patch.object(self.llm, "embed", side_effect=lambda texts, query=False: [[1.0] * 8 for _ in texts]):
            with self.assertRaisesRegex(ValueError, "incompatible dimensions.*new workspace"):
                self.kb.ingest("policy.pdf", data)
        self.assertEqual(self.kb.documents(), [])
        self.assertFalse((self.root / "manifest.json").exists())
        self.assertEqual(self.kb._client.count(knowledge.COLLECTION, exact=True).count, 0)
        successful = self.kb.ingest("policy.pdf", data)
        self.assertEqual(self.kb.pdf_bytes(successful["id"]), data)

    def test_file_rollback_failure_is_reported(self):
        original_json = knowledge._atomic_json
        original_unlink = Path.unlink

        def fail_manifest(path, value):
            if Path(path).name == "manifest.json":
                raise OSError("Simulated manifest failure")
            return original_json(path, value)

        def fail_chunk_cleanup(path, *args, **kwargs):
            if path.parent == self.root / "chunks":
                raise PermissionError("Simulated file cleanup failure")
            return original_unlink(path, *args, **kwargs)

        with patch.object(knowledge, "_atomic_json", side_effect=fail_manifest), \
                patch.object(Path, "unlink", new=fail_chunk_cleanup):
            with self.assertRaisesRegex(RuntimeError, "File rollback.*file cleanup failure") as caught:
                self.kb.ingest("policy.pdf", make_pdf("Teachers record attendance."))
        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertEqual(self.kb.documents(), [])
        self.assertEqual(self.kb._client.count(knowledge.COLLECTION, exact=True).count, 0)
        self.assertEqual(list((self.root / "pdfs").glob("*.pdf")), [])

    def test_manifest_filters_unpublished_points_even_if_rollback_fails(self):
        first = self.kb.ingest("first.pdf", make_pdf("Attendance matters."))
        original = knowledge._atomic_json

        def fail_manifest(path, value):
            if Path(path).name == "manifest.json":
                raise OSError("Simulated manifest failure")
            return original(path, value)

        with patch.object(knowledge, "_atomic_json", side_effect=fail_manifest), \
                patch.object(self.kb._client, "delete", side_effect=RuntimeError("rollback failed")):
            with self.assertRaisesRegex(RuntimeError, "cleanup was incomplete.*rollback failed") as caught:
                self.kb.ingest("second.pdf", make_pdf("Homework matters."))
        self.assertIsInstance(caught.exception.__cause__, OSError)
        hits = self.kb.search("homework", limit=20)
        self.assertEqual({hit["document_id"] for hit in hits}, {first["id"]})
        self.assertEqual(len(self.kb.chunks()), first["chunks"])

    def test_embedding_failure_preserves_state(self):
        with patch.object(self.llm, "embed", return_value=[[0.0] * 16]):
            with self.assertRaisesRegex(ValueError, "zero vector"):
                self.kb.ingest("policy.pdf", make_pdf("Students learn."))
        self.assertEqual(self.kb.documents(), [])
        self.assertFalse((self.root / "manifest.json").exists())

    def test_verified_triples_and_mentions_distinguished(self):
        evidence = "Teachers notify parents about attendance."
        self.llm.response = json.dumps({"triples": [
            {"subject": "Teachers", "relation": "notify", "object": "parents", "evidence": evidence},
            {"subject": "Teachers", "relation": "punish", "object": "students", "evidence": evidence},
            {"subject": "Teachers", "relation": "notify", "object": "parents", "evidence": "Invented quote."},
        ]})
        self.kb.ingest("policy.pdf", make_pdf(evidence), extract_relations=True)
        graph = self.kb.graph()
        assertions = [d for _, _, d in graph.edges(data=True) if d["kind"] == "llm_assertion"]
        self.assertEqual(len(assertions), 1)
        self.assertEqual(assertions[0]["evidence"], evidence)
        self.assertEqual(self.kb.stats()["relations"], 1)
        self.assertTrue(any(d["kind"] == "mentions" for _, _, d in graph.edges(data=True)))
        for _, _, data in graph.edges(data=True):
            self.assertTrue(all(k in data for k in ("source", "page", "evidence")))
        self.assertEqual(len(self.kb.chunks()[0]["triples"]), 1)

    def test_vision_blank_pdf_extracts_and_marks_text(self):
        result = self.kb.ingest("scan.pdf", make_pdf(""), vision=True)
        self.assertTrue(any("model-generated" in w for w in result["warnings"]))
        self.assertEqual(self.kb.chunks()[0]["extraction_kind"], "vision")
        self.assertIn(("chat", True), self.llm.calls)

    def test_vision_preserves_native_text_and_labels_mixed_pages(self):
        native = "Teachers must record attendance before nine."
        self.llm.visual = "Diagram: office receives attendance records."
        for pages in ((native,), (native, "")):
            with self.subTest(page_count=len(pages)):
                result = self.kb.ingest("mixed.pdf", make_pdf(*pages), vision=True)
                chunks = [c for c in self.kb.chunks() if c["document_id"] == result["id"]]
                native_chunk = next(c for c in chunks if c["page"] == 1)
                self.assertEqual(native_chunk["extraction_kind"], "native+vision")
                self.assertEqual(native_chunk["text"], native +
                                 "\n\n[Vision transcription: verify against original]\n" + self.llm.visual)
                self.assertTrue(any("model-generated" in warning for warning in result["warnings"]))
                if len(pages) == 2:
                    scanned_chunk = next(c for c in chunks if c["page"] == 2)
                    self.assertEqual(scanned_chunk["extraction_kind"], "vision")
                    self.assertEqual(scanned_chunk["text"], self.llm.visual)

    def test_filename_safe_and_graph_html_escaped(self):
        result = self.kb.ingest("../../\\<script>evil</script>\x00.pdf", make_pdf("Students & teachers."))
        self.assertNotIn("/", result["name"])
        self.assertNotIn("\\", result["name"])
        self.assertNotIn("\x00", result["name"])
        self.assertNotIn("<", result["name"])
        graph = self.kb.graph()
        graph.add_node("unsafe", kind="entity", label='<script>alert("x")</script>')
        graph.add_edge("unsafe", next(iter(graph)), kind="llm_assertion", relation="<b>unsafe</b>",
                       source="<img src=x>", page=1, evidence="<script>bad</script>")
        figure = graph_figure(graph, focus="<script>")
        encoded = figure.to_json()
        decoded = json.dumps(json.loads(encoded), ensure_ascii=False)
        self.assertNotIn("<script>", decoded)
        self.assertNotIn("<img src=x>", decoded)
        self.assertIn("&lt;script&gt;", decoded)
        self.assertEqual(self.kb.pdf_bytes(result["id"])[:5], b"%PDF-")

    def test_graph_empty_cap_and_determinism(self):
        self.assertTrue(graph_figure(nx.MultiDiGraph()).layout.annotations)
        graph = nx.MultiDiGraph()
        for number in range(200):
            graph.add_node(str(number), kind="entity", label=f"Entity {number}")
            if number:
                graph.add_edge(str(number - 1), str(number), kind="mentions", evidence="test")
        first = graph_figure(graph, max_nodes=12)
        second = graph_figure(graph, max_nodes=12)
        self.assertEqual(first.to_json(), second.to_json())
        nodes = sum(len(trace.x) for trace in first.data if trace.mode == "markers+text")
        self.assertLessEqual(nodes, 12)

    def test_chunk_overlap_and_page_boundaries(self):
        first = " ".join(["Attendance policy applies to students."] * 60)
        result = self.kb.ingest("long.pdf", make_pdf(first, "Second page homework policy."))
        chunks = self.kb.chunks()
        self.assertGreater(result["chunks"], 2)
        self.assertTrue(all(len(c["text"]) <= 900 for c in chunks))
        self.assertTrue(all("Second page" not in c["text"] for c in chunks if c["page"] == 1))
        native_chunks = list(knowledge._page_chunks("word " * 500))
        self.assertTrue(native_chunks[0][-100:] in native_chunks[1][:160])


if __name__ == "__main__":
    unittest.main()
