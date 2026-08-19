from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Protocol

from app.business_routing.models import BusinessRequest, RequestContext, RouteResult
from app.errors import AppError


class BusinessHandler(Protocol):
    def handle(self, request: BusinessRequest, context: RequestContext) -> RouteResult: ...


@dataclass(frozen=True)
class DispatchEvent:
    """Observability data emitted after a dispatch attempt."""

    request: BusinessRequest
    context: RequestContext
    elapsed_ms: float
    result: RouteResult | None = None
    error: BaseException | None = None


DispatchHook = Callable[[DispatchEvent], None]


class BusinessRouter:
    """Registry-based dispatcher; adding a department module does not change channels."""

    def __init__(
        self,
        *,
        default_handler: BusinessHandler | None = None,
        hooks: tuple[DispatchHook, ...] = (),
    ) -> None:
        self._handlers: dict[str, BusinessHandler] = {}
        self._default_handler = default_handler
        self._hooks = hooks

    def register(self, intent: str, handler: BusinessHandler) -> None:
        if intent in self._handlers:
            raise ValueError(f"handler already registered: {intent}")
        self._handlers[intent] = handler

    def unregister(self, intent: str) -> bool:
        """Remove a handler and return whether a registration was removed."""
        return self._handlers.pop(intent, None) is not None

    def registered_intents(self) -> tuple[str, ...]:
        """Return registered intent names in stable order for logs and diagnostics."""
        return tuple(sorted(self._handlers))

    def can_route(self, request: BusinessRequest) -> bool:
        return request.intent in self._handlers or self._default_handler is not None

    def dispatch(self, request: BusinessRequest, context: RequestContext) -> RouteResult:
        """Dispatch a request and run optional observability hooks.

        Callers must catch :class:`AppError` for unsupported intents. Handler
        exceptions are also re-raised after hooks receive the failure event.
        """
        started = perf_counter()
        handler = self._handlers.get(request.intent) or self._default_handler
        result: RouteResult | None = None
        error: BaseException | None = None
        try:
            if handler is None:
                raise AppError(
                    "BUSINESS_INTENT_UNSUPPORTED",
                    "暂不支持该业务请求",
                    status_code=422,
                )
            result = handler.handle(request, context)
            return result
        except Exception as exc:
            error = exc
            raise
        finally:
            if self._hooks:
                event = DispatchEvent(
                    request=request,
                    context=context,
                    elapsed_ms=round((perf_counter() - started) * 1000, 3),
                    result=result,
                    error=error,
                )
                for hook in self._hooks:
                    hook(event)
