from dataclasses import dataclass
from time import perf_counter, sleep

import httpx

from app.config import Settings
from app.errors import AppError
from app.ai.token_budget import fit_prompt


@dataclass(frozen=True)
class ModelGatewayConfig:
    enabled: bool
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int
    prompt_token_budget: int = 6000
    completion_token_budget: int = 1000
    retry_max_attempts: int = 2

    @classmethod
    def from_settings(cls, settings: Settings) -> "ModelGatewayConfig":
        return cls(
            enabled=bool(getattr(settings, "model_enabled", False)),
            base_url=settings.model_base_url.rstrip("/"),
            api_key=settings.model_api_key,
            model=settings.model_name,
            timeout_seconds=settings.model_timeout_seconds,
            prompt_token_budget=settings.model_prompt_token_budget,
            completion_token_budget=settings.model_completion_token_budget,
            retry_max_attempts=settings.model_retry_max_attempts,
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.enabled and self.base_url and self.api_key and self.model)


@dataclass(frozen=True)
class ModelCompletion:
    content: str
    model: str
    duration_ms: int
    prompt_tokens: int
    completion_tokens: int


class ModelGateway:
    def __init__(self, config: ModelGatewayConfig) -> None:
        self.config = config

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> str:
        return self.complete_with_metadata(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        ).content

    def complete_with_metadata(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> ModelCompletion:
        if not self.config.is_configured:
            raise AppError(
                "MODEL_NOT_CONFIGURED",
                "统一大模型尚未配置",
                status_code=503,
            )

        started_at = perf_counter()
        budgeted = fit_prompt(system_prompt, user_prompt, self.config.prompt_token_budget)
        payload = None
        content = None
        usage = {}
        last_error: Exception | None = None
        for attempt in range(self.config.retry_max_attempts):
            try:
                response = httpx.post(
                    f"{self.config.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.config.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.config.model,
                        "messages": [
                            {"role": "system", "content": budgeted.system_prompt},
                            {"role": "user", "content": budgeted.user_prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": self.config.completion_token_budget,
                    },
                    timeout=self.config.timeout_seconds,
                    trust_env=False,
                )
                response.raise_for_status()
                payload = response.json()
                content = payload["choices"][0]["message"]["content"]
                usage = payload.get("usage") or {}
                break
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
                last_error = exc
                retryable = not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code in {
                    408, 409, 425, 429, 500, 502, 503, 504,
                }
                if not retryable or attempt + 1 >= self.config.retry_max_attempts:
                    break
                sleep(0.25 * (attempt + 1))
        if payload is None:
            raise AppError(
                "MODEL_REQUEST_FAILED", "统一大模型调用失败", status_code=502
            ) from last_error

        if not isinstance(content, str) or not content.strip():
            raise AppError(
                "MODEL_EMPTY_RESPONSE",
                "统一大模型返回了空内容",
                status_code=502,
            )
        return ModelCompletion(
            content=content.strip(),
            model=str(payload.get("model") or self.config.model),
            duration_ms=max(0, round((perf_counter() - started_at) * 1000)),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
        )
