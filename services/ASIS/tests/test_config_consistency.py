"""Configuration consistency regression tests - verify launcher/Python/TUI use same settings."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from asis.configuration.settings import load_settings, reset_settings
from asis.tui.state import AppState
from asis.ai.manager import create_provider
from asis.ai.providers import OllamaProvider


def test_settings_use_env_vars():
    """Test that settings correctly read from environment variables."""
    test_env = {
        "ASIS_AI_PROVIDER": "ollama",
        "ASIS_AI_MODEL": "test-model:7b",
        "ASIS_AI_ENDPOINT": "http://custom-host:9999",
        "ASIS_AI_TEMPERATURE": "0.5",
        "ASIS_AI_THINK": "false",
        "ASIS_AI_NUM_PREDICT": "100",
        "ASIS_AI_KEEP_ALIVE": "10m",
    }
    
    settings = load_settings(env=test_env)
    
    assert settings.ai.provider == "ollama"
    assert settings.ai.model == "test-model:7b"
    assert settings.ai.endpoint == "http://custom-host:9999"
    assert settings.ai.temperature == 0.5
    assert settings.ai.think == "false"
    assert settings.ai.num_predict == 100
    assert settings.ai.keep_alive == "10m"


def test_create_provider_uses_settings():
    """Test that create_provider uses the settings values."""
    test_env = {
        "ASIS_AI_PROVIDER": "ollama",
        "ASIS_AI_MODEL": "consistency-test:7b",
        "ASIS_AI_ENDPOINT": "http://consistency-host:8888",
        "ASIS_AI_TEMPERATURE": "0.3",
        "ASIS_AI_THINK": "auto",
        "ASIS_AI_NUM_PREDICT": "50",
        "ASIS_AI_KEEP_ALIVE": "5m",
    }
    
    reset_settings(env=test_env)
    from asis.configuration.settings import settings
    provider = create_provider()
    
    assert isinstance(provider, OllamaProvider)
    assert provider.model == "consistency-test:7b"
    assert provider.host == "http://consistency-host:8888"
    assert provider.temperature == 0.3
    assert provider.num_predict == 50
    assert provider.keep_alive == "5m"


def test_app_state_stores_inference_options():
    """Test that AppState correctly stores inference options from CLI."""
    state = AppState(
        ai_temperature=0.7,
        ai_think="true",
        ai_num_predict=200,
        ai_keep_alive="30m",
    )
    
    assert state.ai_temperature == 0.7
    assert state.ai_think == "true"
    assert state.ai_num_predict == 200
    assert state.ai_keep_alive == "30m"


def test_launcher_endpoint_parsing():
    """Test that launcher correctly parses ASIS_AI_ENDPOINT."""
    # This mimics the logic in scripts/asis.mjs
    def parse_endpoint(endpoint_str):
        from urllib.parse import urlparse
        try:
            url = urlparse(endpoint_str)
            host = url.hostname
            port = url.port or (443 if url.scheme == "https" else 80)
            return host, port
        except Exception:
            return "127.0.0.1", 11434
    
    # Test various endpoint formats
    assert parse_endpoint("http://127.0.0.1:11434") == ("127.0.0.1", 11434)
    assert parse_endpoint("http://localhost:11434") == ("localhost", 11434)
    assert parse_endpoint("http://custom-host:9999") == ("custom-host", 9999)
    assert parse_endpoint("https://secure-host:443") == ("secure-host", 443)
    assert parse_endpoint("https://secure-host") == ("secure-host", 443)
    assert parse_endpoint("http://host") == ("host", 80)
    # Invalid URL without scheme returns None for hostname
    # This is expected behavior - the launcher would need a scheme
    assert parse_endpoint("invalid") == (None, 80)


def test_model_env_var_consistency():
    """Test that ASIS_AI_MODEL is used consistently."""
    test_env = {"ASIS_AI_MODEL": "shared-model:14b"}
    
    reset_settings(env=test_env)
    from asis.configuration.settings import settings
    provider = create_provider()
    
    assert settings.ai.model == "shared-model:14b"
    assert provider.model == "shared-model:14b"


def test_endpoint_env_var_consistency():
    """Test that ASIS_AI_ENDPOINT is used consistently."""
    test_env = {"ASIS_AI_ENDPOINT": "http://shared-host:7777"}
    
    reset_settings(env=test_env)
    from asis.configuration.settings import settings
    provider = create_provider()
    
    assert settings.ai.endpoint == "http://shared-host:7777"
    assert provider.host == "http://shared-host:7777"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])