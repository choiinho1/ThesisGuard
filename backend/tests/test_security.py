from thesisguard_backend.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_access_token_roundtrip() -> None:
    token = create_access_token(subject="11111111-1111-1111-1111-111111111111")
    assert decode_access_token(token) == "11111111-1111-1111-1111-111111111111"


def test_access_token_rejects_garbage() -> None:
    assert decode_access_token("not-a-real-token") is None
