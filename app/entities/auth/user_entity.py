from __future__ import annotations

from typing import Any
from dataclasses import dataclass
from app.entities.base_entity import BaseEntity


@dataclass
class UserEntity(BaseEntity):
    user_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None
    email: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> UserEntity | None:
        if not data:
            return None

        return cls(
            user_name=data.get("user_name"),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            display_name=data.get("display_name"),
            email=data.get("email"),
        )
