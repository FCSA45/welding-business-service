from types import SimpleNamespace

from app.ai.gateway import ModelGatewayConfig


def test_model_gateway_is_disabled_by_default():
    settings = SimpleNamespace(
        model_enabled=False,
        model_base_url="https://example.test/v1",
        model_api_key="key",
        model_name="model",
        model_timeout_seconds=20,
        model_prompt_token_budget=6000,
        model_completion_token_budget=1000,
        model_retry_max_attempts=2,
    )

    config = ModelGatewayConfig.from_settings(settings)

    assert config.enabled is False
    assert config.is_configured is False
