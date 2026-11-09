import pytest

from tiviss.models import MockProvider, ModelResponse, ProviderError


def test_provider_available_by_default():
    provider = MockProvider()
    assert provider.available() is True


def test_provider_identity():
    provider = MockProvider()
    assert provider.provider_id == "mock.local"
    assert provider.model_id == "tiviss-mock-1"


def test_provider_info():
    provider = MockProvider()
    info = provider.info()
    assert info.provider_id == "mock.local"
    assert info.model_id == "tiviss-mock-1"
    assert info.available is True
    assert info.version == "0.1.0"


def test_mock_generation_is_deterministic():
    provider = MockProvider()
    first = provider.generate("hello world")
    second = provider.generate("hello world")
    assert first.content == second.content == "ack(tiviss-mock-1): hello world"
    assert isinstance(first, ModelResponse)


def test_mock_generation_respects_wordlimit_context():
    provider = MockProvider()
    response = provider.generate("one two three four", context={"wordlimit": 2})
    assert response.content == "ack(tiviss-mock-1): one two"


def test_provider_failure_mode():
    provider = MockProvider(failure_mode=True)
    assert provider.available() is False
    with pytest.raises(ProviderError):
        provider.generate("hello")


def test_provider_failure_after_configure():
    provider = MockProvider()
    provider.configure({"failure_mode": True})
    with pytest.raises(ProviderError):
        provider.generate("hello")
    provider.configure({"failure_mode": False})
    assert provider.generate("x").content == "ack(tiviss-mock-1): x"


def test_provider_empty_content_failure():
    provider = MockProvider()
    with pytest.raises(ProviderError):
        provider.generate("   ")


def test_provider_model_change_via_configure():
    provider = MockProvider()
    provider.configure({"model_id": "model-b", "prefix": "ok"})
    assert provider.model_id == "model-b"
    assert provider.generate("hi").content == "ok(model-b): hi"
