import pymysql
from contextlib import contextmanager
from app.config import settings
from urllib.parse import urlparse


def get_connection() -> pymysql.connections.Connection:
    url = urlparse(settings.DATABASE_URL)
    return pymysql.connect(
        host=url.hostname or "127.0.0.1",
        port=url.port or 3306,
        user=url.username or "root",
        password=url.password or "",
        database=url.path.lstrip("/") or "taskmaster",
        cursorclass=pymysql.cursors.DictCursor,
        charset="utf8mb4",
    )


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(schema_path: str = "schema_mariadb.sql"):
    """Cria as tabelas no MariaDB se ainda não existirem."""
    conn = get_connection()
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            sql = f.read()
        with conn.cursor() as cursor:
            for statement in sql.split(";"):
                stmt = statement.strip()
                if stmt:
                    cursor.execute(stmt)
        conn.commit()
        print("✅ Banco de dados MariaDB inicializado.")
    except Exception as e:
        print(f"❌ Erro ao inicializar banco: {e}")
        raise
    finally:
        conn.close()