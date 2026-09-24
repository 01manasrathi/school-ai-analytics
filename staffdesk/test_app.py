from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import networkx as nx
import plotly.graph_objects as go
import streamlit as st
from streamlit.testing.v1 import AppTest
from graph_view import evidence_graph, select_graph_view


APP = Path(__file__).resolve().with_name("app.py")
PDF = b"%PDF-1.4\nfictional test fixture"


class FakeModelError(RuntimeError):
    pass


class StaffDeskAppTests(unittest.TestCase):
    def setUp(self):
        st.cache_resource.clear()
        st.cache_data.clear()
        self.documents = []
        self.chunks = []
        self.kb = MagicMock()
        self.kb.documents.side_effect = lambda: list(self.documents)
        self.kb.chunks.side_effect = lambda: list(self.chunks)
        self.kb.stats.side_effect = lambda: {"documents": len(self.documents), "pages": len(self.documents),
                                            "chunks": len(self.chunks), "entities": 0, "relations": 0}
        self.kb.graph.side_effect = self.make_graph
        self.kb.pdf_bytes.return_value = PDF
        self.kb.ingest.side_effect = self.ingest
        self.kb_factory = MagicMock(return_value=self.kb)
        self.created_models = []
        self.offline = False
        self.model_rows = [{"name": "qwen3.5:4b"}, {"name": "nomic-embed-text:v1.5"}, {"name": "local-other:4b"},
                           {"name": "remote:cloud"}, {"name": "remote-model", "remote_host": "cloud.invalid"}]
        self.model_factory = MagicMock(side_effect=self.make_model)
        self.result = {"answer": "Fictional staff must report absence before 07:30. [1]", "category": "Attendance",
                       "sensitive": False, "abstained": False, "confidence": 0.78,
                       "sources": [{"id": "c1", "document_id": "d1", "source": "fictional.pdf", "page": 1,
                                    "quote": "Fictional staff must report absence before 07:30.", "score": 0.78, "citation": 1}],
                       "trace": [{"node": "validate", "status": "ok", "details": "Scope checked"},
                                 {"node": "retrieve", "status": "ok", "details": "Found page evidence"}]}
        self.workflow = MagicMock()
        self.workflow.run.return_value = self.result
        self.workflow_factory = MagicMock(return_value=self.workflow)
        self.figure = MagicMock(return_value=go.Figure(go.Scatter(x=[0, 1], y=[0, 1])))
        modules = {}
        for name, attrs in {
            "models": {"Ollama": self.model_factory, "ModelError": FakeModelError},
            "knowledge": {"KnowledgeBase": self.kb_factory},
            "workflow": {"PolicyWorkflow": self.workflow_factory},
            "graph_view": {"graph_figure": self.figure, "evidence_graph": evidence_graph, "select_graph_view": select_graph_view},
            "demo": {"demo_pdf": MagicMock(return_value=PDF)},
        }.items():
            module = ModuleType(name)
            module.__dict__.update(attrs)
            modules[name] = module
        self.original_modules = {name: sys.modules.get(name) for name in modules}
        sys.modules.update(modules)
        self.env_patch = patch.dict(os.environ, {"STAFFDESK_MODEL": "qwen3.5:4b", "STAFFDESK_DATA_DIR": str(APP.parent / "data")})
        self.env_patch.start()

    def tearDown(self):
        st.cache_resource.clear()
        st.cache_data.clear()
        self.env_patch.stop()
        for name, original in self.original_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

    def make_model(self, model, embedding_model):
        instance = MagicMock()
        instance.model = model
        instance.embedding_model = embedding_model
        instance.available_models.side_effect = lambda: self.available_models()
        self.created_models.append(instance)
        return instance

    def available_models(self):
        if self.offline:
            raise FakeModelError("Ollama is not running")
        return self.model_rows

    def ingest(self, filename, content, grade_band="All", vision=False, extract_relations=False, progress=None):
        if self.documents:
            return dict(self.documents[0], deduplicated=True)
        doc = {"id": "d1", "name": filename, "pages": 1, "chunks": 1, "grade_band": grade_band, "warnings": []}
        self.documents.append(doc)
        self.chunks.append({"id": "c1", "text": "Fictional staff must report absence before 07:30.",
                            "document_id": "d1", "source": filename, "page": 1, "grade_band": grade_band})
        return dict(doc, deduplicated=False)

    def make_graph(self):
        graph = nx.MultiDiGraph()
        if self.documents:
            graph.add_node("doc", label=self.documents[0]["name"], kind="document")
            graph.add_node("absence", label="Absence", kind="entity")
            graph.add_edge("doc", "absence", relation="keyword mention", kind="mentions", source="fictional.pdf", page=1,
                           document_id="d1", evidence="report absence")
        return graph

    def render(self):
        app = AppTest.from_file(str(APP), default_timeout=90).run()
        self.assertEqual(len(app.exception), 0, [item.message for item in app.exception])
        return app

    def button(self, app, label):
        return next(item for item in app.button if item.label == label)

    def selectbox(self, app, label):
        return next(item for item in app.selectbox if item.label == label)

    def load_helpers(self):
        spec = importlib.util.spec_from_file_location("staffdesk_ui_helpers", APP)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_initial_render_has_four_tabs_and_empty_guidance(self):
        app = self.render()
        self.assertEqual([tab.label for tab in app.tabs], ["Ask StaffDesk", "PDF Library", "Knowledge Graph", "Workflow & Insights"])
        self.assertTrue(self.button(app, "Ask StaffDesk").disabled)
        self.assertTrue(any("No PDFs indexed" in message.value for message in app.info))
        self.assertTrue(any("not for public sharing" in message.value for message in app.warning))
        self.assertEqual(self.selectbox(app, "PDF grade band").options, ["All", "Primary", "Middle", "Secondary"])
        self.assertEqual(len(app.checkbox), 2)
        self.kb.ingest.assert_not_called()
        self.workflow.run.assert_not_called()

    def test_missing_ollama_is_actionable_and_library_still_renders(self):
        self.offline = True
        self.ingest("fictional.pdf", PDF)
        app = self.render()
        self.assertTrue(self.button(app, "Ask StaffDesk").disabled)
        self.assertTrue(self.button(app, "Index fictional demo PDF").disabled)
        self.assertTrue(any("ollama serve" in code.value for code in app.code))
        self.assertTrue(any("Local models unavailable" in warning.value for warning in app.warning))
        self.kb.pdf_bytes.assert_called_with("d1")
        self.assertEqual(len(app.tabs), 4)
        self.workflow.run.assert_not_called()

    def test_missing_embedding_model_disables_indexing_and_questions(self):
        self.model_rows = [{"name": "qwen3.5:4b"}]
        self.ingest("fictional.pdf", PDF)
        app = self.render()
        self.assertTrue(self.button(app, "Ask StaffDesk").disabled)
        self.assertTrue(self.button(app, "Index fictional demo PDF").disabled)

    def test_model_selection_reuses_one_fixed_knowledge_base(self):
        self.ingest("fictional.pdf", PDF)
        app = self.render()
        selector = self.selectbox(app, "Local chat model")
        self.assertNotIn("remote:cloud", selector.options)
        self.assertNotIn("remote-model", selector.options)
        selector.select("local-other:4b").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(self.kb_factory.call_count, 1)
        root, ingestion_model = self.kb_factory.call_args.args
        self.assertEqual(root, (APP.parent / "data").resolve())
        self.assertEqual(ingestion_model.model, "qwen3.5:4b")
        self.assertEqual(ingestion_model.embedding_model, "nomic-embed-text:v1.5")
        self.assertEqual(self.created_models[-1].model, "local-other:4b")
        self.render()
        self.assertEqual(self.kb_factory.call_count, 1)
        self.kb.close.assert_not_called()

    def test_blank_question_does_not_run_workflow(self):
        self.ingest("fictional.pdf", PDF)
        app = self.render()
        app.text_area[0].input("   ")
        self.button(app, "Ask StaffDesk").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("Enter a question" in item.value for item in app.warning))
        self.workflow.run.assert_not_called()

    def test_answer_sources_trace_history_and_grade_scope(self):
        self.ingest("fictional.pdf", PDF)
        app = self.render()
        self.selectbox(app, "Answer grade band").select("Primary").run()
        self.selectbox(app, "Teacher context").select("New").run()
        app.text_area[0].input("When should staff report absence?")
        self.button(app, "Ask StaffDesk").click().run()
        self.assertEqual(len(app.exception), 0, [e.message for e in app.exception])
        self.workflow.run.assert_called_once_with("When should staff report absence?", grade_band="Primary", teacher_type="New", history=[], document_ids=["d1"])
        self.assertEqual(len(app.session_state["messages"]), 2)
        self.assertEqual(len(app.session_state["results"]), 1)
        self.assertEqual(app.session_state["analytics"][0]["category"], "Attendance")
        self.assertTrue(any("[1] fictional.pdf | Page 1" == item.label for item in app.expander))
        self.assertTrue(any("not a probability" in item.value for item in app.caption))
        self.assertTrue(any("Fictional staff must" in item.value for item in app.text))
        app.text_area[0].input("Does that apply to new staff?")
        self.button(app, "Ask StaffDesk").click().run()
        self.assertEqual(len(self.workflow.run.call_args.kwargs["history"]), 2)
        self.assertEqual(len(app.session_state["results"]), 2)

    def test_new_chat_clears_session_not_documents(self):
        self.ingest("fictional.pdf", PDF)
        app = self.render()
        app.text_area[0].input("What is the procedure?")
        self.button(app, "Ask StaffDesk").click().run()
        self.button(app, "New chat / clear session").click().run()
        self.assertEqual(len(app.exception), 0)
        for key in ("messages", "results", "analytics"):
            self.assertEqual(app.session_state[key], [])
        self.assertEqual(len(self.documents), 1)
        self.assertEqual(self.kb_factory.call_count, 1)
        self.kb.close.assert_not_called()

    def test_demo_uses_ingestion_pipeline_settings_and_dedup_feedback(self):
        app = self.render()
        self.selectbox(app, "PDF grade band").select("Middle").run()
        app.checkbox[0].check().run()
        app.checkbox[1].check().run()
        self.button(app, "Index fictional demo PDF").click().run()
        self.assertEqual(len(app.exception), 0, [e.message for e in app.exception])
        self.kb.ingest.assert_called_once_with("StaffDesk-FICTIONAL-demo.pdf", PDF, grade_band="Middle", vision=True, extract_relations=True)
        self.assertTrue(any("Indexed StaffDesk" in message.value for message in app.success))
        self.button(app, "Index fictional demo PDF").click().run()
        self.assertTrue(any("Already indexed" in message.value for message in app.success))
        self.assertEqual(len(self.documents), 1)

    def test_failed_workflow_never_adds_a_fake_answer(self):
        self.ingest("fictional.pdf", PDF)
        self.workflow.run.side_effect = FakeModelError("Local service unavailable")
        app = self.render()
        app.text_area[0].input("What should I do?")
        self.button(app, "Ask StaffDesk").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("No answer was generated" in item.value for item in app.error))
        self.assertEqual(app.session_state["messages"], [])

    def test_sensitive_abstention_is_visible_and_counted(self):
        self.ingest("fictional.pdf", PDF)
        self.result.update(sensitive=True, abstained=True, sources=[], answer="Insufficient PDF evidence.")
        app = self.render()
        app.text_area[0].input("What safeguarding policy applies?")
        self.button(app, "Ask StaffDesk").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("Sensitive policy topic" in item.value for item in app.warning))
        metrics = {item.label: item.value for item in app.metric}
        self.assertEqual(metrics["Abstentions"], "1")
        self.assertEqual(metrics["Sensitive topics"], "1")

    def test_graph_focus_handles_no_matches_and_restores_view(self):
        self.ingest("fictional.pdf", PDF)
        app = self.render()
        self.assertGreater(self.figure.call_count, 0)
        app.text_input[0].input("nonexistent-node").run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("No matching nodes" in item.value for item in app.info))
        app.text_input[0].input("absence").run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn("absence", self.figure.call_args.args[0])
        self.assertEqual(self.figure.call_args.kwargs["max_nodes"], 120)

    def test_pdf_size_type_validation_and_failures(self):
        helpers = self.load_helpers()
        status, message = helpers.index_pdf(self.kb, "large.pdf", b"%PDF-" + b"x" * helpers.MAX_PDF_BYTES, "All", False, False)
        self.assertEqual(status, "error")
        self.assertIn("25 MB", message)
        status, message = helpers.index_pdf(self.kb, "not.pdf", b"not a PDF", "All", False, False)
        self.assertEqual(status, "error")
        self.kb.ingest.assert_not_called()
        self.kb.ingest.side_effect = ValueError("PDF has no extractable text")
        status, message = helpers.index_pdf(self.kb, "blank.pdf", PDF, "All", False, False)
        self.assertEqual(status, "error")
        self.assertIn("no extractable text", message)
        self.kb.ingest.side_effect = RuntimeError("PRIVATE DOCUMENT CONTENT")
        status, message = helpers.index_pdf(self.kb, "broken.pdf", PDF, "All", False, False)
        self.assertEqual(status, "error")
        self.assertNotIn("PRIVATE DOCUMENT CONTENT", message)

    def test_sample_button_indexes_native_text_and_selects_only_sample(self):
        app = self.render()
        self.button(app, "Index 10-page sample only").click().run()
        self.assertEqual(len(app.exception), 0, [e.message for e in app.exception])
        call = self.kb.ingest.call_args
        self.assertEqual(call.args[0], "Maple_Grove_School_Sample_Policies_10_Pages.pdf")
        self.assertEqual(call.kwargs, {"grade_band": "All", "vision": False, "extract_relations": False})
        self.assertEqual(app.session_state["answer_document"], "d1")
        self.assertEqual(app.session_state["messages"], [])

    def test_pdf_switch_clears_previous_context_and_scopes_next_question(self):
        self.ingest("first.pdf", PDF)
        self.documents.append({"id": "d2", "name": "second.pdf", "pages": 1, "chunks": 1, "grade_band": "All", "warnings": []})
        app = self.render()
        app.text_area[0].input("What is the procedure?")
        self.button(app, "Ask StaffDesk").click().run()
        self.assertEqual(self.workflow.run.call_args.kwargs["document_ids"], ["d2"])
        self.selectbox(app, "PDF to answer from").select("d1").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["messages"], [])
        app.text_area[0].input("What is the procedure?")
        self.button(app, "Ask StaffDesk").click().run()
        self.assertEqual(self.workflow.run.call_args.kwargs["document_ids"], ["d1"])
        self.assertEqual(self.workflow.run.call_args.kwargs["history"], [])

    def test_retrieved_context_is_visible_even_when_answer_abstains(self):
        self.ingest("fictional.pdf", PDF)
        self.result.update(abstained=True, sources=[], retrieved_context=[dict(self.chunks[0], score=0.62, lexical_score=2.1)])
        app = self.render()
        app.text_area[0].input("What does the PDF say?")
        self.button(app, "Ask StaffDesk").click().run()
        self.assertEqual(len(app.exception), 0, [e.message for e in app.exception])
        self.assertTrue(any(item.label == "Retrieved context and answer graph" for item in app.expander))
        self.assertTrue(any("Candidate 1" in item.value and "Not cited" in item.value for item in app.caption))

    def test_workspace_failure_is_actionable(self):
        self.kb_factory.side_effect = RuntimeError("Qdrant lock is held")
        app = self.render()
        self.assertTrue(any("one StaffDesk server" in item.value for item in app.error))
        self.workflow.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
