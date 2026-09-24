from __future__ import annotations

import math
import os
import threading
from urllib.parse import urlparse

import requests

DEFAULT_MODEL = "qwen3.5:4b"
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text:v1.5"
_MODEL_LOCK = threading.RLock()


class ModelError(RuntimeError):
    pass


class Ollama:
    def __init__(self, model=DEFAULT_MODEL, embedding_model=DEFAULT_EMBEDDING_MODEL, host=None, timeout=300):
        self.model = model
        self.embedding_model = embedding_model
        self.host = (host or os.environ.get("STAFFDESK_OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
        parsed = urlparse(self.host)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password:
            raise ValueError("StaffDesk only permits a loopback HTTP Ollama service; remote hosts are disabled.")
        if parsed.path or parsed.query or parsed.fragment:
            raise ValueError("Ollama host must not contain a path, query, or fragment.")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.trust_env = False
        self._verified = {}

    def _request(self, method, path, body=None, timeout=None):
        try:
            response = self.session.request(method, self.host + path, json=body, timeout=(5, timeout or self.timeout), allow_redirects=False)
            if 300 <= response.status_code < 400:
                raise ModelError("Ollama redirects are disabled to keep PDF data local.")
            response.raise_for_status()
            result = response.json()
            if result.get("error"):
                raise ModelError("Ollama could not complete this request. Check installed models and available memory.")
            return result
        except requests.Timeout as exc:
            raise ModelError("Local model timed out. Retry with a shorter PDF/query or a smaller installed model.") from exc
        except requests.RequestException as exc:
            raise ModelError("Cannot complete the local Ollama request. Start Ollama and install the selected models using setup.ps1.") from exc
        except ValueError as exc:
            raise ModelError("Ollama returned an invalid response.") from exc

    def available_models(self):
        rows = self._request("GET", "/api/tags", timeout=30).get("models", [])
        return [row for row in rows if not row.get("remote_host") and not row.get("remote_model") and ":cloud" not in row.get("name", "")]

    def model_digest(self, model):
        for row in self.available_models():
            if row.get("name") == model or row.get("model") == model:
                return row["digest"]
        raise ModelError(f"Local model {model!r} is missing. Install it with ollama pull {model}.")

    def _verify_local(self, model):
        if model not in self._verified:
            digest = self.model_digest(model)
            details = self._request("POST", "/api/show", {"model": model}, timeout=30)
            if details.get("remote_model") or details.get("remote_host") or ":cloud" in model:
                raise ModelError("Cloud models are disabled. Select a locally installed model.")
            self._verified[model] = (digest, details.get("capabilities", []))
        return self._verified[model]

    def chat(self, messages, schema=None, images=None):
        with _MODEL_LOCK:
            _, capabilities = self._verify_local(self.model)
            if images and "vision" not in capabilities:
                raise ModelError("Scanned PDF/diagram extraction needs a vision model such as qwen3.5:4b.")
            clean = [dict(message) for message in messages]
            if images:
                clean[-1]["images"] = images
            body = {
                "model": self.model,
                "messages": clean,
                "stream": False,
                "keep_alive": "5m",
                "options": {"temperature": 0.1, "num_ctx": 8192, "num_predict": 1800},
            }
            if "thinking" in capabilities:
                body["think"] = False
            if schema:
                body["format"] = schema
            result = self._request("POST", "/api/chat", body)
            text = result.get("message", {}).get("content", "").strip()
            if not text:
                raise ModelError("Local model returned no text. Try the request again.")
            return text

    def embed(self, texts, query=False):
        if not texts:
            return []
        prefix = "search_query: " if query else "search_document: "
        with _MODEL_LOCK:
            self._verify_local(self.embedding_model)
            result = []
            for start in range(0, len(texts), 16):
                batch = texts[start:start + 16]
                response = self._request("POST", "/api/embed", {
                    "model": self.embedding_model,
                    "input": [prefix + text for text in batch],
                    "truncate": False,
                    "keep_alive": "5m",
                })
                vectors = response.get("embeddings", [])
                if len(vectors) != len(batch) or any(not v or not all(math.isfinite(float(x)) for x in v) for v in vectors):
                    raise ModelError("Embedding model returned incomplete or invalid vectors.")
                result.extend(vectors)
            if len({len(vector) for vector in result}) != 1:
                raise ModelError("Embedding dimensions were inconsistent.")
            return result
