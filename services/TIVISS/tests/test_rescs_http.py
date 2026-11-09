import io
import json
import urllib.error

import pytest

from tiviss.integrations.rescs_http import RescsClientError, RescsHttpClient


class _FakeResponse:
    def __init__(self, payload, *, status=200):
        self._payload = payload
        self.status = status

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _install(monkeypatch, handler):
    calls = []

    def fake_urlopen(request, *, timeout=None):
        calls.append(request)
        return handler(request)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return calls


def _client(**overrides):
    params = {"base_url": "http://x:8000", "api_key": "k" * 16}
    params.update(overrides)
    return RescsHttpClient(**params)


def test_constructor_validation():
    with pytest.raises(RescsClientError):
        RescsHttpClient(base_url="  ", api_key="k")
    with pytest.raises(RescsClientError):
        RescsHttpClient(base_url="http://x", api_key="")
    with pytest.raises(RescsClientError):
        RescsHttpClient(base_url="http://x", api_key="k", timeout_s=0)


def test_namespace_guard():
    client = _client()
    with pytest.raises(RescsClientError, match="outside"):
        client.list_records(namespace="asis.memory")
    permissive = _client(allow_foreign_namespaces=True)
    assert permissive._check_namespace("asis.memory") == "asis.memory"


def test_create_record_request_shape(monkeypatch):
    def handler(request):
        assert request.get_method() == "POST"
        assert request.full_url == "http://x:8000/api/v1/records"
        assert request.get_header("X-api-key") == "k" * 16
        body = json.loads(request.data.decode("utf-8"))
        assert body["namespace"] == "tiviss.memory"
        assert body["owner"] == "tiviss"
        return _FakeResponse({"id": "r-1", **body})

    calls = _install(monkeypatch, handler)
    result = _client().create_record(
        namespace="tiviss.memory", key="k", value={"a": 1}
    )
    assert result["id"] == "r-1"
    assert len(calls) == 1


def test_get_update_delete(monkeypatch):
    seen = []

    def handler(request):
        seen.append((request.get_method(), request.full_url))
        if request.get_method() == "DELETE":
            return _FakeResponse({}, status=200)
        return _FakeResponse({"id": "r-1"})

    _install(monkeypatch, handler)
    client = _client()
    assert client.get_record("r-1")["id"] == "r-1"
    assert client.update_record("r-1", {"value": {}}, if_match='"e"')["id"] == "r-1"
    assert client.delete_record("r-1") == {}
    methods = [method for method, _ in seen]
    assert methods == ["GET", "PATCH", "DELETE"]
    assert "if_match" in seen[1][1]


def test_list_and_search_query_params(monkeypatch):
    urls = []

    def handler(request):
        urls.append(request.full_url)
        return _FakeResponse({"items": [], "total": 0})

    _install(monkeypatch, handler)
    client = _client()
    client.list_records(namespace="tiviss.memory", limit=5, key_prefix="a")
    client.search_records("hello world", namespace="tiviss.memory")
    assert "namespace=tiviss.memory" in urls[0]
    assert "key_prefix=a" in urls[0]
    assert "query=hello+world" in urls[1]


def test_http_error_mapping(monkeypatch):
    def handler(request):
        body = json.dumps(
            {"error": {"code": "NOT_FOUND", "message": "gone"}}
        ).encode("utf-8")
        raise urllib.error.HTTPError(
            request.full_url, 404, "Not Found", {}, io.BytesIO(body)
        )

    _install(monkeypatch, handler)
    with pytest.raises(RescsClientError) as excinfo:
        _client().get_record("missing")
    assert excinfo.value.code == "NOT_FOUND"
    assert excinfo.value.status == 404


def test_api_key_never_in_url_or_body(monkeypatch):
    captured = {}

    def handler(request):
        captured["url"] = request.full_url
        captured["body"] = (request.data or b"").decode("utf-8")
        return _FakeResponse({"id": "r-1"})

    _install(monkeypatch, handler)
    _client(api_key="supersecretkey").create_record(
        namespace="tiviss.memory", key="k", value={}
    )
    assert "supersecretkey" not in captured["url"]
    assert "supersecretkey" not in captured["body"]
