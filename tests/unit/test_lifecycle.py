from shared.event_schemas import AlertPayload

def test_lifecycle_message_types_are_limited():
    for message_type in ["CRITICAL","WARNING","ACKNOWLEDGEMENT","INFO","RECOVERY"]:
        payload=AlertPayload(message_type=message_type,entity_id="entity-1")
        assert payload.message_type==message_type

def test_unknown_lifecycle_type_fails():
    import pytest
    with pytest.raises(Exception): AlertPayload(message_type="UNKNOWN",entity_id="entity-1")
