#!/usr/bin/env python3

from ldap3 import Server, Connection, ALL
from ldap3.core.exceptions import LDAPException
from app.config.settings import Settings
from app.entities.auth.user_entity import UserEntity
from flask import session
from app.enums.auth.user_role import UserRole


class AuthService:

    @staticmethod
    def is_logged_in() -> bool:
        return "user_id" in session

    @staticmethod
    def is_guest() -> bool:
        return "user_id" not in session

    @staticmethod
    def is_admin() -> bool:
        return "role" in session and UserRole.ADMIN == session["role"]

    @staticmethod
    def authenticate_local(user_cn: str, password: str, email_suffix: str = "@zhaw.ch"):
        email = f"{user_cn}{email_suffix}"

        if not email in Settings().LDAP_ADMINS:
            return None

        if not password == Settings().LDAP_ADMIN_LOCAL_PASSWORD:
            return None

        return UserEntity().from_dict(
            {
                "uid": user_cn,
                "givenName": "Administrator",
                "sn": "Administrator",
                "displayName": "Administrator",
                "mail": email,
            }
        )

    @staticmethod
    def authenticate(
        user_cn: str,
        password: str,
        attributes=["uid", "givenName", "sn", "displayName", "mail"],
    ) -> UserEntity | None:
        serverAddress = Settings().LDAP_SERVER_ADDRESS
        user_cn = user_cn
        base_dn = Settings().LDAP_BASE_DN
        user_dn = f"cn={user_cn},{base_dn}"

        ldapServer = Server(serverAddress, get_info=ALL)

        try:
            connection = Connection(
                ldapServer, user=user_dn, password=password, auto_bind=True
            )

            result = {}

            if attributes:
                connection.search(
                    search_base=base_dn,
                    search_filter=f"(cn={user_cn})",
                    attributes=attributes,
                )
                if connection.entries:
                    entry = connection.entries[0]
                    for attr in attributes:
                        result[attr] = entry[attr].value

            connection.unbind()
            return UserEntity().from_dict(result) if attributes else {}

        except LDAPException:
            return None
