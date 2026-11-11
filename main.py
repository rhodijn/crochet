#!/usr/bin/env python3

from app.config.settings import Settings
from app.config.setup import Setup
from flask import Flask, session

config = Settings()


app = Flask(
    __name__, static_folder="resources/static", template_folder="resources/views"
)


# Set Default Language
@app.before_request
def set_default_lang() -> None:
    if "lang" not in session:
        session["lang"] = config.TRANSLATION_DEFAULT_LANG


Setup.set_logging_config()
Setup.set_jinja_config(app)
Setup.set_flask_secret_key(app)
Setup.register_controllers(app)


if __name__ == "__main__":
    app.run(host=config.APP_HOST, port=config.APP_PORT, debug=config.APP_DEBUG)
