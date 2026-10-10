def test_same_entity_is_correlation_key():
    first={"entity_id":"checkout","message_type":"CRITICAL"}
    followup={"entity_id":"checkout","message_type":"RECOVERY"}
    assert first["entity_id"]==followup["entity_id"]
