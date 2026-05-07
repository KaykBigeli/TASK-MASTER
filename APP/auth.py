from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from enum import Enum
from typing import Optional, List, Dict
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
        from_attributes = True   # ajuste para Pydantic v2

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
    assignments: List[TaskAssignmentOut] = []
    class Config:
        from_attributes = True

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

# ---------- Comentários ----------
class CommentCreate(BaseModel):
    content: str

class CommentOut(BaseModel):
    id: str
    task_id: str
    user_id: str
    content: str
    created_at: datetime
    class Config:
        from_attributes = True

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
    # ... (sua função list_tasks continua igual)
    pass

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

# ---------- Novo endpoint para comentários ----------
@router.post("/tasks/{task_id}/comments", response_model=CommentOut)
def add_comment(task_id: str, body: CommentCreate, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        try:
            import pymysql
            cursor = conn.cursor(pymysql.cursors.DictCursor)
        except Exception:
            cursor = conn.cursor()

        new_id = str(math.floor(datetime.utcnow().timestamp() * 1000))  # ou use UUID
        cursor.execute(
            "INSERT INTO task_comments (id, task_id, user_id, content, created_at) VALUES (%s, %s, %s, %s, %s)",
            (new_id, task_id, current_user["id"], body.content, datetime.utcnow())
        )
        conn.commit()

        cursor.execute(
            "SELECT id, task_id, user_id, content, created_at FROM task_comments WHERE id = %s",
            (new_id,)
        )
        row = cursor.fetchone()
        cursor.close()

    return row
