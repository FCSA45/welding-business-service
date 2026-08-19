from __future__ import annotations

from typing import Any, Callable


class OutputTemplateRegistry:
    def __init__(self) -> None:
        self._templates: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, template: Callable[..., Any]) -> None:
        if name in self._templates:
            raise ValueError(f"output template already registered: {name}")
        self._templates[name] = template

    def contains(self, name: str) -> bool:
        """Return whether a template is registered without invoking it."""
        return name in self._templates

    def render(self, name: str, *args, **kwargs):
        try:
            template = self._templates[name]
        except KeyError as exc:
            raise ValueError(f"unknown output template: {name}") from exc
        return template(*args, **kwargs)
