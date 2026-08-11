"""Provider configuration that must survive deployment environment drift."""

from api.llm.groq_provider import sdk_base_url


def test_groq_sdk_base_url_uses_the_api_origin() -> None:
    assert sdk_base_url("https://api.groq.com") == "https://api.groq.com"


def test_groq_sdk_base_url_normalises_the_legacy_rest_suffix() -> None:
    assert (
        sdk_base_url("https://api.groq.com/openai/v1/")
        == "https://api.groq.com"
    )
