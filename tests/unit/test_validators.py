
import importlib.util
from pathlib import Path
import pytest
from fastapi import HTTPException
from shared.event_schemas import AlertPayload

SPEC=importlib.util.spec_from_file_location("alert_validators", Path(__file__).parents[2]/"services/alert-routing/app/validators.py")
MODULE=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)

def test_valid_critical_payload():
    result=MODULE.validate_payload({"message_type":"CRITICAL","entity_id":"api-1","state_message":"failed"})
    assert result["message_type"]=="CRITICAL" and result["entity_id"]=="api-1"

def test_invalid_type_rejected():
    with pytest.raises(HTTPException): MODULE.validate_payload({"message_type":"NOPE","entity_id":"x"})

def test_text_annotation_limit():
    with pytest.raises(HTTPException): MODULE.validate_payload({"message_type":"INFO","entity_id":"x","vo_annotate.s.note":"x"*1125})

def test_missing_entity_id_is_generated_for_single_event():
    result = MODULE.validate_payload({"message_type": "CRITICAL"})
    assert result["entity_id"]
    assert len(result["entity_id"]) <= 256

def test_blank_entity_id_rejected():
    with pytest.raises(HTTPException):
        MODULE.validate_payload({"message_type": "CRITICAL", "entity_id": "   "})

def test_url_annotation_must_be_http_url():
    with pytest.raises(HTTPException):
        MODULE.validate_payload({"message_type": "INFO", "entity_id": "x", "vo_annotate.u.Runbook": "javascript:alert(1)"})

def test_note_annotation_at_limit_is_allowed():
    result = MODULE.validate_payload({"message_type": "INFO", "entity_id": "x", "vo_annotate.s.Note": "x" * 1124})
    assert len(result["vo_annotate.s.Note"]) == 1124

def test_lowercase_message_type_is_normalized():
    result = MODULE.validate_payload({"message_type": "critical", "entity_id": "svc-1"})
    assert result["message_type"] == "CRITICAL"


def test_url_annotation_rejects_missing_host():
    with pytest.raises(HTTPException):
        MODULE.validate_payload({"message_type": "INFO", "entity_id": "x", "vo_annotate.u.Runbook": "https://"})


def test_url_annotation_accepts_https_url():
    result = MODULE.validate_payload({"message_type": "INFO", "entity_id": "x", "vo_annotate.u.Runbook": "https://example.com/runbook"})
    assert result["vo_annotate.u.Runbook"] == "https://example.com/runbook"
