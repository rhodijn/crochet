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
from app.core.middleware.auth_middleware import auth, guest
from app.entities.auth.user_entity import UserEntity
from app.enums.auth.user_role import UserRole
from app.services.auth_service import AuthService
from app.core.translation.i18n import t
from app.services.flash_service import FlashService

app_controller: Blueprint = Blueprint("app_controller", __name__)
config: Settings = Settings()
auth_service: AuthService = AuthService()
flash_service: FlashService = FlashService()

type TemplateResponse = str | tuple[str, int]


@app_controller.get("/")
def dashboard() -> str:
    return render_template("pages/home/index.html")
