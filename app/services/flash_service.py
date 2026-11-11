#!/usr/bin/env python3

from flask import session


class FlashService:
    @staticmethod
    def has(name: str):
        return name in session

    @staticmethod
    def set(name: str, value):
        session[name] = value

    @staticmethod
    def get(name: str, default=None):
        return session.pop(name, default)
