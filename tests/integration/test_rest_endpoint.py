from shared.event_schemas import AlertPayload

def test_rest_payload_fields():
    payload=AlertPayload.model_validate({"message_type":"CRITICAL","entity_id":"svc-42","entity_display_name":"Service 42","state_message":"timeout"})
    assert payload.entity_id=="svc-42" and payload.state_message=="timeout"
