import pymysql
from contextlib import contextmanager
from app.config import settings
from urllib.parse import urlparse

def get_connection():
    try:
        url = urlparse(settings.DATABASE_URL)
        return pymysql.connect(
            host=url.hostname or "127.0.0.1",
            port=url.port or 25789,
            user=url.username or "root",
            password=url.password or "Prometheus15!",
            database=url.path.lstrip('/') or "taskmaster",
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        # Se a URL falhar, tenta a conexão manual que funcionou no terminal
        return pymysql.connect(
            host="127.0.0.1",
            port=25789,
            user="root",
            password="Prometheus15!",
            database="taskmaster",
            cursorclass=pymysql.cursors.DictCursor
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

def init_db():
    """Teste de conexão rápido"""
    try:
        conn = get_connection()
        print("✅ Conexão com MariaDB (25789) ativa!")
        conn.close()
    except Exception as e:
        print(f"❌ Falha na conexão: {e}")