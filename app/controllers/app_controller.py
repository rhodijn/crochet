#!/usr/bin/env python3

from flask import (
    Blueprint,
    Response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from app.config.settings import Settings
from app.core.translation.i18n import t
from app.services.flash_service import FlashService

app_controller: Blueprint = Blueprint("app_controller", __name__)
config: Settings = Settings()
flash_service: FlashService = FlashService()

type TemplateResponse = str | tuple[str, int]


@app_controller.get("/")
def dashboard() -> str:
    return render_template("pages/home/index.html")
