from shared.security import hash_password, verify_password

def test_password_hash_verification():
    encoded=hash_password("a-long-test-password")
    assert verify_password("a-long-test-password",encoded)
    assert not verify_password("wrong-password",encoded)

def test_password_hash_rejects_too_short_password():
    import pytest
    with pytest.raises(ValueError):
        hash_password("short")


def test_signed_token_contains_valid_claims_and_rejects_tampering():
    import pytest
    from shared.security import create_token, decode_token
    token = create_token("admin@example.com", "admin", ttl=300, organization_id=1)
    claims = decode_token(token)
    assert claims["sub"] == "admin@example.com"
    assert claims["role"] == "admin"
    header, payload, signature = token.split(".")
    with pytest.raises(ValueError):
        decode_token(f"{header}.{payload}.{signature[:-2]}xx")
