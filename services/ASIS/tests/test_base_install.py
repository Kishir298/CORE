"""Base-install robustness: mock/offline CLI must not require `requests`.

Simulates a minimal base install (no `ai` extra) by blocking the
`requests` import in a subprocess. No model is loaded, no network is
touched, no local inference runs — safe on low-RAM machines.
"""

from __future__ import annotations

import subprocess
import sys

_BLOCKER = (
    "import sys\n"
    "class _Blocker:\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name == 'requests' or name.startswith('requests.'):\n"
    "            raise ImportError('No module named requests (simulated base install)')\n"  # noqa: E501
    "sys.meta_path.insert(0, _Blocker())\n"
)


def _run(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _BLOCKER + code],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_mock_cli_imports_without_requests():
    proc = _run(
        "import asis.cli.main\n"
        "import asis.app.assistant\n"
        "import asis.ai.providers as p\n"
        "assert 'asis.ai.providers.ollama' not in sys.modules, 'ollama eagerly imported'\n"  # noqa: E501
        "print('base-import-ok')\n"
    )
    assert proc.returncode == 0, proc.stderr
    assert "base-import-ok" in proc.stdout


def test_mock_provider_constructs_without_requests():
    proc = _run(
        "from asis.ai.manager import create_provider\n"
        "provider = create_provider('mock')\n"
        "assert provider.name == 'mock'\n"
        "print('mock-provider-ok')\n"
    )
    assert proc.returncode == 0, proc.stderr
    assert "mock-provider-ok" in proc.stdout


def test_ollama_without_requests_fails_with_hint():
    # The provider module imports lazily (base installs have no `requests`);
    # construction succeeds and the first HTTP use raises a clear hint.
    proc = _run(
        "from asis.ai.manager import create_provider\n"
        "from asis.ai.models import AIMessage, MessageRole\n"
        "provider = create_provider('ollama')\n"
        "assert provider.available() is False\n"
        "try:\n"
        "    provider.chat([AIMessage(role=MessageRole.USER, content='hi')])\n"
        "except Exception as exc:\n"
        "    assert 'requests' in str(exc), str(exc)\n"
        "    print('ollama-hint-ok')\n"
        "else:\n"
        "    raise AssertionError('expected requests hint without requests')\n"
    )
    assert proc.returncode == 0, proc.stderr
    assert "ollama-hint-ok" in proc.stdout


def test_ollama_attribute_still_available_with_requests():
    from asis.ai import OllamaProvider as via_package
    from asis.ai.providers import OllamaProvider as via_providers

    assert via_package is via_providers
    assert via_package.__name__ == "OllamaProvider"
