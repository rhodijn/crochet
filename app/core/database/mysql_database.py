import pymysql
from pymysql.cursors import DictCursor
from threading import Lock
from app.config.settings import Settings
from contextlib import contextmanager


class MysqlDatabase:
    instance = None
    lock = Lock()

    def __init__(self):
        config = Settings()
        self.host = config.DATABASE_HOST
        self.user = config.DATABASE_USER
        self.password = config.DATABASE_PASSWORD
        self.database = config.DATABASE_NAME
        self.cursorclass = DictCursor
        self.autocommit = True

    @classmethod
    def get_instance(cls):
        if cls.instance is None:
            with cls.lock:
                if cls.instance is None:
                    cls.instance = cls()
        return cls.instance

    def get_connection(self):
        return pymysql.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database,
            cursorclass=self.cursorclass,
            autocommit=self.autocommit,
        )

    def commit(self):
        return None

    @contextmanager
    def cursor(self):
        connection = self.get_connection()

        try:
            with connection.cursor() as cursor:
                yield cursor
        finally:
            connection.close()
