import json

import pytest

from tiviss.configuration import TIVISSConfig
from tiviss.identity import Ownership
from tiviss.memory.interface import MemoryRecord
from tiviss.memory.local import LocalMemory
from tiviss.state_io import (
    EXPORT_VERSION,
    StateImportError,
    export_state,
    import_state,
)


def _parts():
    config = TIVISSConfig.load(
        {
            "agent": {"name": "t", "owner_id": "kishir", "agent_id": "a-1"},
            "permissions": {"allow": ["conversation.generate"]},
        }
    )
    identity = config.build_identity()
    ownership = Ownership.create("kishir")
    memory = LocalMemory()
    memory.store(
        MemoryRecord(
            key="fact", content="likes tea", metadata={"session_token": "s3cr3t"}
        )
    )
    return config, identity, ownership, memory


def test_export_roundtrip():
    config, identity, ownership, memory = _parts()
    records = memory.search("").records
    doc = export_state(
        identity=identity,
        ownership=ownership,
        model={"provider_id": "mock", "model_id": "m"},
        permissions={"allow": ["conversation.generate"], "deny": []},
        memory_records=records,
        counters={"requests_handled": 3},
    )
    assert doc["tiviss_export"] is True
    assert doc["version"] == EXPORT_VERSION
    assert doc["integrity"]
    # Secret metadata dropped + recorded.
    assert doc["dropped_secrets"] == ["memory.fact.session_token"]
    assert doc["payload"]["memory_records"][0]["metadata"] == {}
    raw = json.dumps(doc)
    restored = import_state(json.loads(raw))
    assert restored.agent_id == "a-1"
    assert restored.identity.owner_id == "kishir"
    assert restored.ownership.owner_id == "kishir"
    assert len(restored.memory_records) == 1
    assert restored.counters == {"requests_handled": 3}


def test_export_drops_identity_meta_secrets():
    from tiviss.identity import AgentIdentity

    identity = AgentIdentity.create(
        name="t", version="1", owner_id="k", meta={"api_key": "K", "nick": "t"}
    )
    ownership = Ownership.create("k")
    doc = export_state(
        identity=identity,
        ownership=ownership,
        model={},
        permissions={},
        memory_records=[],
    )
    assert doc["payload"]["identity"]["meta"] == {"nick": "t"}
    assert "identity.meta.api_key" in doc["dropped_secrets"]
    assert import_state(doc).identity.meta == {"nick": "t"}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("tiviss_export"),
        lambda d: d.update(version=999),
        lambda d: d["payload"].pop("identity"),
        lambda d: d.update(integrity="0" * 64),
        lambda d: d["payload"]["counters"].update({"x": "not-an-int"}),
    ],
)
def test_import_rejects_invalid(mutate):
    config, identity, ownership, memory = _parts()
    doc = export_state(
        identity=identity,
        ownership=ownership,
        model={},
        permissions={},
        memory_records=[],
    )
    mutate(doc)
    with pytest.raises(StateImportError):
        import_state(doc)


def test_import_rejects_non_mapping():
    with pytest.raises(StateImportError):
        import_state(["not", "a", "mapping"])


def test_export_scrubs_model_config_secrets():
    """Test that model configuration section is scrubbed for secrets."""
    from tiviss.identity import AgentIdentity, Ownership
    
    identity = AgentIdentity.create(name="t", version="1", owner_id="k")
    ownership = Ownership.create("k")
    
    # Model config with api_key
    model_config = {
        "provider_id": "ollama",
        "model_id": "llama3",
        "api_key": "secret-key-123",
        "endpoint": "http://localhost:11434",
        "nested": {"api_key": "nested-secret", "safe": "value"},
        "list_of_mappings": [
            {"api_key": "list-secret-1", "data": "ok"},
            {"token": "list-secret-2", "info": "fine"}
        ]
    }
    
    doc = export_state(
        identity=identity,
        ownership=ownership,
        model=model_config,
        permissions={},
        memory_records=[],
    )
    
    # Check model section is scrubbed
    model_payload = doc["payload"]["model"]
    assert "api_key" not in model_payload
    assert model_payload["provider_id"] == "ollama"
    assert model_payload["model_id"] == "llama3"
    assert model_payload["endpoint"] == "http://localhost:11434"
    
    # Check nested mapping scrubbed
    assert "api_key" not in model_payload["nested"]
    assert model_payload["nested"]["safe"] == "value"
    
    # Check list of mappings scrubbed
    assert "api_key" not in model_payload["list_of_mappings"][0]
    assert model_payload["list_of_mappings"][0]["data"] == "ok"
    assert "token" not in model_payload["list_of_mappings"][1]
    assert model_payload["list_of_mappings"][1]["info"] == "fine"
    
    # Check dropped secrets recorded
    dropped = doc["dropped_secrets"]
    assert "model.api_key" in dropped
    assert "model.nested.api_key" in dropped
    assert "model.list_of_mappings[0].api_key" in dropped
    assert "model.list_of_mappings[1].token" in dropped


def test_export_scrubs_mappings_within_lists():
    """Test that mappings within lists are recursively scrubbed."""
    from tiviss.identity import AgentIdentity, Ownership
    from tiviss.memory.interface import MemoryRecord
    from tiviss.memory.local import LocalMemory
    
    identity = AgentIdentity.create(name="t", version="1", owner_id="k")
    ownership = Ownership.create("k")
    memory = LocalMemory()
    
    # Memory record with list of mappings containing secrets
    memory.store(MemoryRecord(
        key="test",
        content="content",
        metadata={
            "tags": [
                {"name": "tag1", "api_key": "secret-in-list"},
                {"name": "tag2", "password": "another-secret"}
            ],
            "safe_field": "value"
        }
    ))
    
    records = memory.search("").records
    doc = export_state(
        identity=identity,
        ownership=ownership,
        model={},
        permissions={},
        memory_records=records,
    )
    
    # Check memory record metadata is scrubbed
    mem_metadata = doc["payload"]["memory_records"][0]["metadata"]
    assert "tags" in mem_metadata
    assert len(mem_metadata["tags"]) == 2
    assert "api_key" not in mem_metadata["tags"][0]
    assert mem_metadata["tags"][0]["name"] == "tag1"
    assert "password" not in mem_metadata["tags"][1]
    assert mem_metadata["tags"][1]["name"] == "tag2"
    assert mem_metadata["safe_field"] == "value"
    
    # Check dropped secrets
    dropped = doc["dropped_secrets"]
    assert "memory.test.tags[0].api_key" in dropped
    assert "memory.test.tags[1].password" in dropped


def test_no_api_key_sentinel_in_serialized_output():
    """Assert no sentinel api_key appears in serialized JSON output."""
    from tiviss.identity import AgentIdentity, Ownership
    import json
    
    identity = AgentIdentity.create(
        name="t", version="1", owner_id="k", 
        meta={"api_key": "should-not-appear", "normal": "data"}
    )
    ownership = Ownership.create("k")
    
    doc = export_state(
        identity=identity,
        ownership=ownership,
        model={"api_key": "model-secret", "provider": "test"},
        permissions={},
        memory_records=[],
    )
    
    # Serialize to JSON
    json_str = json.dumps(doc)
    
    # The literal string "api_key" should not appear as a key in the JSON
    # (it should be dropped and only appear in dropped_secrets list)
    assert '"api_key":' not in json_str
    # But the dropped_secrets should contain the paths
    assert "identity.meta.api_key" in doc["dropped_secrets"]
    assert "model.api_key" in doc["dropped_secrets"]
