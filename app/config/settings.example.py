#!/usr/bin/env python3

import os
import logging


class Settings:
    APP_NAME: str = "<APP_NAME>"
    APP_HOST: str = os.getenv("APP_HOST", "<PRODUCTION_DOMAIN_URL>")  # required
    APP_DEBUG: str = os.getenv("APP_DEBUG", False)  # required default
    APP_PORT: int = 80 # required
    APP_LOG_LEVEL: str = logging.INFO
    APP_PUBLIC_DIR: str = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "public"
    )  # required
    APP_SECURE_UPLOAD_DIR: str = os.path.join(
        os.path.dirname(__file__), "..", "..", "secure-uploads"
    )  # required
    LDAP_ADMINS: list[str] = [
        "abdl@zhaw.ch",
        "zolo@zhaw.ch",
        "ghou@zhaw.ch",
        "popa@zhaw.ch",
        "hamn@zhaw.ch",
    ]
    LDAP_ADMIN_LOCAL_PASSWORD: str = os.getenv("LDAP_ADMIN_LOCAL_PASSWORD")  # required
    LDAP_SERVER_ADDRESS: str = os.getenv("LDAP_SERVER_ADDRESS", "")  # required
    LDAP_BIND_DN: str = os.getenv("LDAP_BIN_DN", "")  # required
    LDAP_BIND_USER: str = os.getenv("LDAP_BIND_USER", "")  # required
    LDAP_BIND_PASSWORD: str = os.getenv("LDAP_BIND_PASSWORD", "")  # required
    LDAP_BASE_DN: str = os.getenv("LDAP_BASE_DN", "")  # required
    DATABASE_HOST: str = os.getenv("DATABASE_HOST", "localhost")  # required
    DATABASE_USER: str = os.getenv("DATABASE_USER", "root")  # required
    DATABASE_PASSWORD: str = os.getenv("DATABASE_PASSWORD", "")  # required default
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "")  # required
    TRANSLATION_DEFAULT_LANG: str = os.getenv(
        "TRANSLATION_DEFAULT_LANG", "de"
    )  # required
    FLASK_SECRET_KEY: str = "" # required
