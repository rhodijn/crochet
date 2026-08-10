import logging

from flask import Flask

from app.config.settings import Settings
from app.services.auth_service import AuthService
from app.core.translation.i18n import t, lang

config = Settings()


class Setup:

    @staticmethod
    def register_controllers(app: Flask) -> None:
        app.register_blueprint()

    @staticmethod
    def set_flask_secret_key(app: Flask) -> None:
        app.secret_key = config.FLASK_SECRET_KEY

    @staticmethod
    def set_jinja_config(app: Flask) -> None:
        app.jinja_env.globals.update(config=config, auth=AuthService(), t=t, lang=lang)

    @staticmethod
    def set_logging_config() -> None:
        logging.basicConfig(
            level=config.LOG_LEVEL,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
