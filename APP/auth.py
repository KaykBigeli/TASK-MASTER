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
class TaskAssignmentOut(BaseModel):
    user_id: str
    user_name: Optional[str] = None
    priority: TaskPriority

    class Config:
        orm_mode = True

class TaskOut(BaseModel):
    id: str
    project_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    status: TaskStatus
    due_date: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    overdue: bool = Field(False, description="True se a task estiver atrasada")
    assignments: List[TaskAssignmentOut] = []   # lista de responsáveis com prioridade própria

    class Config:
        orm_mode = True

class PaginationLinks(BaseModel):
    next: Optional[str] = None
    prev: Optional[str] = None
    first: Optional[str] = None
    last: Optional[str] = None

class PaginatedTasks(BaseModel):
    items: List[TaskOut]
    total: int
    limit: int
    offset: int
    current_page: int
    total_pages: int
    links: PaginationLinks

# ---------- Helpers ----------
def row_to_dict(cursor, row):
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    desc = getattr(cursor, "description", None)
    if not desc:
        return None
    keys = [col[0] for col in desc]
    return dict(zip(keys, row))

def rows_to_dicts(cursor, rows_raw):
    if rows_raw is None:
        return []
    if len(rows_raw) > 0 and isinstance(rows_raw[0], dict):
        return rows_raw
    return [row_to_dict(cursor, r) for r in rows_raw]

# ---------- JWT helpers ----------
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou expirado.")

def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = decode_token(token)
    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token sem identificação.")

    with get_db() as conn:
        try:
            import pymysql
            cursor = conn.cursor(pymysql.cursors.DictCursor)
        except Exception:
            cursor = conn.cursor()
        cursor.execute("SELECT id, name, email FROM users WHERE id = %s", (user_id,))
        row_raw = cursor.fetchone()
        user_row = row_to_dict(cursor, row_raw)
        cursor.close()

    if not user_row:
        raise HTTPException(status_code=401, detail="Usuário não encontrado.")

    return {"id": user_row["id"], "name": user_row.get("name"), "email": user_row.get("email")}

# ---------- Router ----------
router = APIRouter(tags=["tasks"])

@router.get("/tasks/", response_model=PaginatedTasks)
def list_tasks(
    request: Request,
    status: Optional[TaskStatus] = Query(None),
    project_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user)
):
    with get_db() as conn:
        try:
            import pymysql
            cursor = conn.cursor(pymysql.cursors.DictCursor)
        except Exception:
            cursor = conn.cursor()

        # buscar tasks onde o usuário é assignment
        count_query = """
            SELECT COUNT(DISTINCT t.id) as total
            FROM tasks t
            JOIN task_assignments a ON a.task_id = t.id
            WHERE a.user_id = %s
        """
        cursor.execute(count_query, (current_user["id"],))
        total_row = row_to_dict(cursor, cursor.fetchone())
        total = int(total_row["total"]) if total_row else 0

        data_query = """
            SELECT DISTINCT t.id, t.project_id, t.title, t.description, t.status, t.due_date, t.created_at, t.updated_at
            FROM tasks t
            JOIN task_assignments a ON a.task_id = t.id
            WHERE a.user_id = %s
            ORDER BY t.created_at DESC
            LIMIT %s OFFSET %s
        """
        cursor.execute(data_query, (current_user["id"], limit, offset))
        rows = rows_to_dicts(cursor, cursor.fetchall())

        # carregar assignments de cada task
        for r in rows:
            cursor.execute("""
                SELECT a.user_id, u.name as user_name, a.priority
                FROM task_assignments a
                JOIN users u ON u.id = a.user_id
                WHERE a.task_id = %s
            """, (r["id"],))
            r["assignments"] = rows_to_dicts(cursor, cursor.fetchall())

        cursor.close()

    # calcular overdue
    tz = ZoneInfo("America/Sao_Paulo")
    now = datetime.now(tz)
    for r in rows:
        r.setdefault("overdue", False)
        due = r.get("due_date")
        if isinstance(due, datetime) and r.get("status") != TaskStatus.completed.value and due < now:
            r["overdue"] = True

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

# ---------- Novo endpoint para atualizar prioridade ----------
@router.patch("/tasks/{task_id}/assignments/{user_id}")
def update_assignment_priority(task_id: str, user_id: str, body: Dict[str, TaskPriority], current_user: dict = Depends(get_current_user)):
    new_priority = body.get("priority")
    if new_priority not in TaskPriority.__members__.values():
        raise HTTPException(status_code=400, detail="Prioridade inválida.")

    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE task_assignments SET priority = %s WHERE task_id = %s AND user_id = %s",
                (new_priority, task_id, user_id)
            )
            conn.commit()
    return {"message": "Prioridade atualizada com sucesso."}
