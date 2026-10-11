from types import SimpleNamespace

import pytest

from oracle_brain.holistic_runtime import OpenAIEmbedding, OpenAIModel
from oracle_brain.ingest.originals import OpenAIVisualReader, OriginalView
from oracle_brain.provider_policy import ProcessingRequest
from oracle_brain.provider_transport import transport_options


def request(provider: str, endpoint: str, *, fallback: bool = False) -> ProcessingRequest:
    return ProcessingRequest(provider=provider, account="test", endpoint=endpoint,
                             data_classes=frozenset({"synthetic"}), purpose="test",
                             terms_hash="a" * 64, fallback=fallback)


def test_transport_allowlist_rejects_unknown_endpoint_provider_and_fallback():
    with pytest.raises(PermissionError):
        transport_options(request("openai", "https://evil.example/v1"), "gpt-4o", operation="chat")
    with pytest.raises(PermissionError):
        transport_options(request("other", "https://api.openai.com/v1"), "gpt-4o", operation="chat")
    with pytest.raises(PermissionError):
        transport_options(request("openrouter", "https://openrouter.ai/api/v1", fallback=True),
                          "openai/gpt-4o", operation="chat")


def test_openrouter_requires_openai_model_without_variant_and_returns_fixed_options():
    req = request("openrouter", "https://openrouter.ai/api/v1")
    with pytest.raises(PermissionError):
        transport_options(req, "anthropic/claude", operation="chat")
    with pytest.raises(PermissionError):
        transport_options(req, "openai/gpt-4o:free", operation="embedding")
    assert transport_options(req, "openai/gpt-4o", operation="chat") == {
        "extra_body": {"provider": {"only": ["openai"], "allow_fallbacks": False,
                                      "require_parameters": True, "data_collection": "deny"}}
    }


class FakeClient:
    def __init__(self):
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.chat_create))
        self.embeddings = SimpleNamespace(create=self.embed_create)

    def chat_create(self, **kwargs):
        self.calls.append(("chat", kwargs))
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop",
                                                         message=SimpleNamespace(content='{"pages":[]}'))])

    def embed_create(self, **kwargs):
        self.calls.append(("embedding", kwargs))
        return SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[0.1]) for _ in kwargs["input"]])


def test_router_options_reach_reader_chat_and_embedding_but_openai_stays_unchanged():
    router = request("openrouter", "https://openrouter.ai/api/v1")
    options = transport_options(router, "openai/gpt-4o", operation="chat")
    client = FakeClient()
    OpenAIVisualReader(client, "openai/gpt-4o", options)("read", [OriginalView(1, "full", b"x", 1, 1)])
    OpenAIModel("openai/gpt-4o", client, options).invoke("prompt")
    OpenAIEmbedding("openai/text-embedding-3-small", client, 1,
                    transport_options(request("openrouter", "https://openrouter.ai/api/v1"),
                                      "openai/text-embedding-3-small", operation="embedding"))\
        .embed_documents(["text"])
    for operation, kwargs in client.calls:
        assert kwargs["extra_body"]["provider"] == {
            "only": ["openai"], "allow_fallbacks": False,
            "require_parameters": True, "data_collection": "deny",
        }
        if operation == "chat":
            assert kwargs["max_tokens"] in {10000, 24000}
            assert "max_completion_tokens" not in kwargs

    direct = FakeClient()
    direct_options = transport_options(request("openai", "https://api.openai.com/v1"),
                                       "gpt-4o", operation="chat")
    OpenAIModel("gpt-4o", direct, direct_options).invoke("prompt")
    assert "extra_body" not in direct.calls[0][1]
    assert direct.calls[0][1]["max_completion_tokens"] == 10000
    assert "max_tokens" not in direct.calls[0][1]
    direct_reader = FakeClient()
    OpenAIVisualReader(direct_reader, "gpt-4o")("read", [OriginalView(1, "full", b"x", 1, 1)])
    assert direct_reader.calls[0][1]["max_completion_tokens"] == 24000
    assert "max_tokens" not in direct_reader.calls[0][1]
