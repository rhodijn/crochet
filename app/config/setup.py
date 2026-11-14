#!/usr/bin/env python3

import logging

from flask import Flask, app

from app.config.settings import Settings
from app.core.translation.i18n import t, lang
from app.controllers.app_controller import app_controller
from app.controllers.skkg_controller import skkg_controller
from app.controllers.crochet_controller import crochet_controller
from app.controllers.model3d_controller import model3d_controller
from app.services.flash_service import FlashService

config = Settings()


class Setup:

    @staticmethod
    def register_controllers(app: Flask) -> None:
        app.register_blueprint(app_controller)
        app.register_blueprint(skkg_controller)
        app.register_blueprint(crochet_controller)
        app.register_blueprint(model3d_controller)

    @staticmethod
    def set_flask_secret_key(app: Flask) -> None:
        app.secret_key = config.FLASK_SECRET_KEY

    @staticmethod
    def set_jinja_config(app: Flask) -> None:
        app.jinja_env.globals.update(
            config=config, t=t, lang=lang, flash=FlashService()
        )

    @staticmethod
    def set_logging_config() -> None:
        logging.basicConfig(
            level=config.APP_LOG_LEVEL,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
