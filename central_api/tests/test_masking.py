from central_api.masking import mask_pii


def test_mask_openai_key():
    text = "Set OPENAI_API_KEY=sk-proj-abc123XYZdef456ghi789JKL012mno345PQR678stu901VWX"
    masked = mask_pii(text)
    assert "sk-proj-" not in masked
    assert "[REDACTED:api_key]" in masked


def test_mask_aws_access_key():
    text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE is my key"
    masked = mask_pii(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in masked
    assert "[REDACTED:aws_key]" in masked


def test_mask_github_token():
    text = "token ghp_abcdef1234567890abcdef1234567890abcd"
    masked = mask_pii(text)
    assert "ghp_" not in masked
    assert "[REDACTED:github_token]" in masked


def test_mask_email():
    text = "Contact alice@example.com for details"
    masked = mask_pii(text)
    assert "alice@example.com" not in masked
    assert "[REDACTED:email]" in masked


def test_mask_bearer_token_in_url():
    text = "curl https://api.example.com/data?token=eyJhbGciOiJIUzI1NiJ9.very-long-jwt-value-here"
    masked = mask_pii(text)
    assert "eyJhbGciOiJIUzI1NiJ9" not in masked
    assert "[REDACTED:token]" in masked


def test_preserves_non_pii():
    text = "Call stripe.Charge.create(amount=100) to charge the customer"
    masked = mask_pii(text)
    assert masked == text


def test_mask_is_idempotent():
    text = "alice@example.com and sk-proj-abc123XYZdef456ghi789JKL012mno345PQR678stu901VWX"
    once = mask_pii(text)
    twice = mask_pii(once)
    assert once == twice
