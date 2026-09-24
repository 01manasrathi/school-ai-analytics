import unittest
from unittest.mock import Mock, patch

import requests

from models import ModelError, Ollama


class ModelTests(unittest.TestCase):
    def test_remote_hosts_rejected(self):
        for host in ["https://example.com", "http://example.com", "http://127.0.0.1/path", "http://u:p@localhost:11434"]:
            with self.subTest(host=host), self.assertRaises(ValueError):
                Ollama(host=host)

    def test_cloud_models_filtered(self):
        client = Ollama()
        with patch.object(client, "_request", return_value={"models": [
            {"name": "local:4b", "digest": "one"},
            {"name": "bad:cloud"},
            {"name": "remote:8b", "remote_host": "https://example.com"},
        ]}):
            self.assertEqual([m["name"] for m in client.available_models()], ["local:4b"])
            with self.assertRaises(ModelError):
                client.model_digest("bad:cloud")

    def test_embedding_prefixes(self):
        client = Ollama()
        with patch.object(client, "_verify_local"), patch.object(client, "_request", return_value={"embeddings": [[1.0, 0.0]]}) as call:
            self.assertEqual(client.embed(["handbook"]), [[1.0, 0.0]])
            self.assertEqual(call.call_args.args[2]["input"], ["search_document: handbook"])
            client.embed(["question"], query=True)
            self.assertEqual(call.call_args.args[2]["input"], ["search_query: question"])

    def test_bad_embeddings_fail_closed(self):
        client = Ollama()
        for vectors in [[], [[]], [[float("nan")]], [[float("inf")]]]:
            with self.subTest(vectors=vectors), patch.object(client, "_verify_local"), patch.object(client, "_request", return_value={"embeddings": vectors}), self.assertRaises(ModelError):
                client.embed(["text"])

    def test_vision_requires_vision_capability(self):
        client = Ollama()
        with patch.object(client, "_verify_local", return_value=("digest", ["completion"])), self.assertRaises(ModelError):
            client.chat([{"role": "user", "content": "Read the PDF"}], images=["image"])

    def test_thinking_disabled_and_schema_sent(self):
        client = Ollama()
        schema = {"type": "object"}
        with patch.object(client, "_verify_local", return_value=("digest", ["completion", "thinking"])), patch.object(client, "_request", return_value={"message": {"content": "{}"}}) as call:
            self.assertEqual(client.chat([{"role": "user", "content": "Classify"}], schema), "{}")
            self.assertFalse(call.call_args.args[2]["think"])
            self.assertEqual(call.call_args.args[2]["format"], schema)

    def test_redirects_and_timeouts_handled(self):
        client = Ollama()
        response = Mock(status_code=302)
        with patch.object(client.session, "request", return_value=response) as call, self.assertRaises(ModelError):
            client.available_models()
        self.assertFalse(call.call_args.kwargs["allow_redirects"])
        self.assertFalse(client.session.trust_env)
        with patch.object(client.session, "request", side_effect=requests.Timeout), self.assertRaisesRegex(ModelError, "timed out"):
            client.available_models()


if __name__ == "__main__":
    unittest.main()
