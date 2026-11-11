#!/usr/bin/env python3

from flask import has_request_context, session

from app.config.settings import Settings
from resources.translations.de import translations as de
from resources.translations.en import translations as en

translations = {
    "de": de,
    "en": en,
}


def lang() -> str:
    if has_request_context():
        return session.get(
            "lang",
            Settings().TRANSLATION_DEFAULT_LANG,
        )

    return Settings().TRANSLATION_DEFAULT_LANG


def t(key: str, **kwargs) -> str:
    language = lang()

    text = translations.get(
        language,
        translations[Settings().TRANSLATION_DEFAULT_LANG],
    ).get(
        key,
        key,
    )

    return text.format(**kwargs)
