"""embeddings_client endpoint/auth resolution — relay vs Azure (offline, no network)."""

from __future__ import annotations

import pytest

from persome.writer import embeddings_client as ec


@pytest.mark.parametrize(
    "base, want_url, want_header",
    [
        # relay: append /embeddings, JWT in x-api-key
        (
            "https://persome-web.vercel.app/api/llm",
            "https://persome-web.vercel.app/api/llm/embeddings",
            "x-api-key",
        ),
        ("https://web/api/llm/", "https://web/api/llm/embeddings", "x-api-key"),
        # Azure OpenAI: full route used verbatim, key in api-key
        (
            "https://persome-resource.cognitiveservices.azure.com/openai/deployments/text-embedding-3-large/embeddings?api-version=2023-05-15",
            "https://persome-resource.cognitiveservices.azure.com/openai/deployments/text-embedding-3-large/embeddings?api-version=2023-05-15",
            "api-key",
        ),
        # a plain full /embeddings URL (non-Azure) keeps x-api-key
        ("https://host/v1/embeddings", "https://host/v1/embeddings", "x-api-key"),
    ],
)
def test_resolve_endpoint(monkeypatch, base, want_url, want_header):
    monkeypatch.setattr(ec, "provider_base_url", lambda _p: base)
    url, header = ec._resolve_endpoint()
    assert url == want_url
    assert header == want_header


def test_resolve_endpoint_unconfigured(monkeypatch):
    monkeypatch.setattr(ec, "provider_base_url", lambda _p: None)
    assert ec._resolve_endpoint() is None


class _FakeResp:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


def test_embed_batch_skips_empty_inputs(monkeypatch):
    """Strict OpenAI/Azure endpoints reject empty strings in a batch; empty
    entries must be dropped (→ None) and only non-empty inputs posted."""
    posted: list[list[str]] = []

    def fake_post(endpoint, *, content, headers):
        body = __import__("json").loads(content)
        inputs = body["input"]
        assert all(s.strip() for s in inputs), f"empty string leaked to endpoint: {inputs!r}"
        posted.append(inputs)
        return _FakeResp(
            {"data": [{"index": i, "embedding": [float(i)]} for i in range(len(inputs))]}
        )

    monkeypatch.setattr(ec, "provider_api_key", lambda _p: "k")
    monkeypatch.setattr(
        ec, "_resolve_endpoint", lambda: ("https://host/v1/embeddings", "x-api-key")
    )
    monkeypatch.setattr(
        ec, "_http_client", lambda: type("C", (), {"post": staticmethod(fake_post)})()
    )

    out = ec.embed_batch(["alpha", "", "  ", "beta"])
    # positions 1 (empty) and 2 (whitespace-only) → None; 0 and 3 embedded
    assert out[0] is not None and out[3] is not None
    assert out[1] is None and out[2] is None
    # only the two non-empty inputs reached the endpoint, in order
    assert posted == [["alpha", "beta"]]


def test_embed_batch_all_empty_returns_none_without_posting(monkeypatch):
    def fail_post(*a, **k):
        raise AssertionError("must not POST an all-empty batch")

    monkeypatch.setattr(ec, "provider_api_key", lambda _p: "k")
    monkeypatch.setattr(
        ec, "_resolve_endpoint", lambda: ("https://host/v1/embeddings", "x-api-key")
    )
    monkeypatch.setattr(
        ec, "_http_client", lambda: type("C", (), {"post": staticmethod(fail_post)})()
    )
    assert ec.embed_batch(["", "   "]) == [None, None]
