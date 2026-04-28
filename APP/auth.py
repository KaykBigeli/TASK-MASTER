from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from enum import Enum
from typing import Optional, List, Dict, Any
import math

from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Query, Request, APIRouter
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field

from app.config import settings
from app.database import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# ---------- Enums ----------
class TaskStatus(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    completed = "completed"

class TaskPriority(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"

# ---------- Pydantic models ----------
class TaskOut(BaseModel):
    id: str
    project_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    status: TaskStatus
    priority: TaskPriority
    due_date: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    overdue: bool = Field(False, description="True se a task estiver atrasada (due_date < agora e status != completed)")

    class Config:
        orm_mode = True

class PaginationLinks(BaseModel):
    next: Optional[str] = None
    prev: Optional[str] = None
    first: Optional[str] = None
    last: Optional[str] = None

class PaginatedTasks(BaseModel):
    items: List[TaskOut]
    total: int = Field(..., description="Total de tasks que atendem ao filtro")
    limit: int
    offset: int
    current_page: int
    total_pages: int
    links: PaginationLinks

# ---------- Helpers para compatibilidade de cursores ----------
def row_to_dict(cursor, row):
    """
    Converte uma linha retornada pelo cursor em dict.
    - Se row for None -> retorna None
    - Se row já for dict -> retorna row
    - Se row for tupla/list -> usa cursor.description para mapear nomes das colunas
    """
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    # row é tupla/list
    desc = getattr(cursor, "description", None)
    if not desc:
        return None
    keys = [col[0] for col in desc]
    return dict(zip(keys, row))

def rows_to_dicts(cursor, rows_raw):
    """
    Converte lista de rows (tuplas ou dicts) em lista de dicts.
    """
    if rows_raw is None:
        return []
    # se já for lista de dicts, retorna direto
    if len(rows_raw) > 0 and isinstance(rows_raw[0], dict):
        return rows_raw
    return [row_to_dict(cursor, r) for r in rows_raw]

# ---------- JWT helpers e autenticação ----------
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict) -> str:
    payload = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload.update({"exp": expire})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = decode_token(token)
    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token sem identificação.")

    with get_db() as conn:
        # tenta criar DictCursor para pymysql; se não for possível, usa cursor padrão
        try:
            import pymysql
            cursor = conn.cursor(pymysql.cursors.DictCursor)
        except Exception:
            cursor = conn.cursor()

        cursor.execute(
            "SELECT id, name, email, avatar_url FROM users WHERE id = %s",
            (user_id,)
        )
        row_raw = cursor.fetchone()
        user_row = row_to_dict(cursor, row_raw)
        cursor.close()

    if not user_row:
        raise HTTPException(status_code=401, detail="Usuário não encontrado.")

    return {
        "id": user_row["id"],
        "name": user_row.get("name"),
        "email": user_row.get("email"),
        "avatar_url": user_row.get("avatar_url")
    }

# ---------- Router ----------
router = APIRouter(tags=["tasks"])

@router.get(
    "/tasks/",
    response_model=PaginatedTasks,
    summary="List Tasks",
    description="Retorna as tasks criadas pelo usuário autenticado. Suporta filtros por status, prioridade e projeto, além de paginação."
)
def list_tasks(
    request: Request,
    status: Optional[TaskStatus] = Query(None, description="Filtrar por status", example="todo"),
    priority: Optional[TaskPriority] = Query(None, description="Filtrar por prioridade", example="medium"),
    project_id: Optional[str] = Query(None, description="Filtrar por ID do projeto (UUID)", example="a3f2b6c8-9d12-4e5f-8c7a-123456789abc"),
    limit: int = Query(20, ge=1, le=100, description="Número máximo de tasks retornadas"),
    offset: int = Query(0, ge=0, description="Número de tasks a pular"),
    current_user: dict = Depends(get_current_user)
):
    # valida project_id (se informado)
    if project_id:
        with get_db() as conn:
            try:
                import pymysql
                cur = conn.cursor(pymysql.cursors.DictCursor)
            except Exception:
                cur = conn.cursor()
            cur.execute("SELECT 1 FROM projects WHERE id = %s", (project_id,))
            exists_raw = cur.fetchone()
            exists = row_to_dict(cur, exists_raw)
            cur.close()
        if not exists:
            raise HTTPException(status_code=400, detail="project_id informado não existe.")

    with get_db() as conn:
        # tenta cursor dict quando possível
        try:
            import pymysql
            cursor = conn.cursor(pymysql.cursors.DictCursor)
        except Exception:
            cursor = conn.cursor()

        # montar WHERE base e params
        where_clauses = ["created_by = %s"]
        params: List[Any] = [current_user["id"]]

        if status:
            where_clauses.append("status = %s")
            params.append(status.value if isinstance(status, TaskStatus) else status)

        if priority:
            where_clauses.append("priority = %s")
            params.append(priority.value if isinstance(priority, TaskPriority) else priority)

        if project_id:
            where_clauses.append("project_id = %s")
            params.append(project_id)

        where_sql = " AND ".join(where_clauses)

        # total
        count_query = f"SELECT COUNT(*) as total FROM tasks WHERE {where_sql}"
        cursor.execute(count_query, tuple(params))
        total_row_raw = cursor.fetchone()
        total_row = row_to_dict(cursor, total_row_raw)
        total = int(total_row["total"]) if total_row and total_row.get("total") is not None else 0

        # buscar items com paginação
        data_query = f"""
            SELECT id, project_id, title, description, status, priority, due_date, created_at, updated_at
            FROM tasks
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        data_params = params.copy()
        data_params.extend([limit, offset])
        cursor.execute(data_query, tuple(data_params))
        rows_raw = cursor.fetchall()
        rows = rows_to_dicts(cursor, rows_raw)
        cursor.close()

    # calcular overdue para cada row (considerando fuso America/Sao_Paulo)
    tz = ZoneInfo("America/Sao_Paulo")
    now = datetime.now(tz)

    for r in rows:
        # garantir que r é dict
        if r is None:
            continue
        r.setdefault("overdue", False)
        due = r.get("due_date")
        if not due:
            continue

        due_dt = None
        # se o driver já retorna datetime
        if isinstance(due, datetime):
            if due.tzinfo is None:
                # assume que o datetime do DB está em UTC sem tzinfo
                due_dt = due.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
            else:
                due_dt = due.astimezone(tz)
        else:
            # tenta parse de string ISO e assume UTC se não vier com offset
            try:
                parsed = datetime.fromisoformat(due)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
                due_dt = parsed.astimezone(tz)
            except Exception:
                due_dt = None

        if due_dt and r.get("status") != TaskStatus.completed.value and due_dt < now:
            r["overdue"] = True

    # paginação: calcular páginas e links
    total_pages = math.ceil(total / limit) if total > 0 else 1
    current_page = (offset // limit) + 1 if limit > 0 else 1
    last_offset = max(0, (total_pages - 1) * limit)

    links: Dict[str, Optional[str]] = {"next": None, "prev": None, "first": None, "last": None}
    if offset + limit < total:
        links["next"] = str(request.url.include_query_params(limit=limit, offset=offset + limit))
    if offset > 0:
        prev_offset = max(0, offset - limit)
        links["prev"] = str(request.url.include_query_params(limit=limit, offset=prev_offset))
    links["first"] = str(request.url.include_query_params(limit=limit, offset=0))
    links["last"] = str(request.url.include_query_params(limit=limit, offset=last_offset))

    return {
        "items": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
        "current_page": current_page,
        "total_pages": total_pages,
        "links": links
    }
