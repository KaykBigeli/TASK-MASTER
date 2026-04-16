import sqlite3
from contextlib import contextmanager
from app.config import settings


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DATABASE_URL)
    conn.row_factory = sqlite3.Row      # retorna linhas como dicionário
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    """Context manager para usar em rotas FastAPI via Depends."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(schema_path: str = "schema.sql"):
    """Executa o schema.sql para criar as tabelas na primeira execução."""
    conn = get_connection()
    with open(schema_path, "r") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    print("✅ Banco de dados inicializado.")
