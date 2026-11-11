#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any


class BaseEntity:
    DATE_FIELDS = {"created_at"}
    TIME_FIELDS = {"start_time", "end_time"}

    ignored_empty_fields: set[str] = set()

    @property
    def is_empty(self) -> bool:
        if not is_dataclass(self):
            return False

        for field in fields(self):
            if field.name in self.ignored_empty_fields:
                continue

            value = getattr(self, field.name)

            if self.has_value(value):
                return False

        return True

    def has_value(self, value: Any) -> bool:
        if value is None:
            return False

        if isinstance(value, str):
            return value.strip() != ""

        if isinstance(value, (list, tuple, set, dict)):
            return len(value) > 0

        return True
