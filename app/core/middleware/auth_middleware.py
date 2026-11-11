#!/usr/bin/env python3

from flask import session, redirect, url_for, url_for
from functools import wraps


def auth(originalFunction):
    @wraps(originalFunction)
    def function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("app_controller.login"))
        return originalFunction(*args, **kwargs)

    return function


def guest(originalFunction):
    @wraps(originalFunction)
    def function(*args, **kwargs):
        if "user_id" in session:
            return redirect(url_for("app_controller.dashboard"))
        return originalFunction(*args, **kwargs)

    return function
