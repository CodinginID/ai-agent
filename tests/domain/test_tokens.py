from app.domain.tokens import generate_device_token, hash_device_token, verify_device_token


def test_hash_device_token_does_not_return_raw_token() -> None:
    token = "worker-secret"

    token_hash = hash_device_token(token)

    assert token_hash != token
    assert verify_device_token(token, token_hash) is True


def test_verify_device_token_rejects_wrong_token() -> None:
    token_hash = hash_device_token("worker-secret")

    assert verify_device_token("other-secret", token_hash) is False


def test_generate_device_token_returns_non_empty_secret() -> None:
    token = generate_device_token()

    assert len(token) >= 32
