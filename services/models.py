"""MongoDB collection names and lightweight document wrappers."""

from __future__ import annotations

from typing import Any


class Document:
    """Attribute-access wrapper for MongoDB documents returned to services."""

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = dict(data)

    def __getattr__(self, name: str) -> Any:
        if name in self._data:
            return self._data[name]
        raise AttributeError(name)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


def as_document(data: dict[str, Any] | None) -> Document | None:
    return Document(data) if data else None
