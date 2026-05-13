from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.database import get_db
from app.auth import get_current_user
import uuid
import logging
from datetime import datetime

router = APIRouter(prefix="/tasks", tags=["Tasks"])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- MODELOS ----------
class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = "todo"
    priority: str = "medium"
    due_date: Optional[str] = None
    project_id: Optional[str] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    project_id: Optional[str] = None

class ChecklistItemCreate(BaseModel):
    title: str
    position: Optional[int] = 0

class ChecklistItemUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    position: Optional[int] = None

# ---------- NOVOS MODELOS PARA COMENTÁRIOS ----------
class CommentCreate(BaseModel):
    content: str

class CommentOut(BaseModel):
    id: str
    task_id: str
    user_id: str
    content: str
    created_at: datetime

# ---------- HELPERS ----------
def _task_with_details(cursor, task_id: str) -> Optional[Dict[str, Any]]:
    cursor.execute(
        "SELECT id, project_id, created_by, title, description, status, priority, due_date, created_at, updated_at "
        "FROM tasks WHERE id = %s",
        (task_id,),
    )
    task = cursor.fetchone()
    if not task:
        return None

    cursor.execute(
        """
        SELECT ta.user_id, u.name as user_name, ta.priority
        FROM task_assignees ta
        LEFT JOIN users u ON u.id = ta.user_id
        WHERE ta.task_id = %s
        """,
        (task_id,),
    )
    assignees = cursor.fetchall() or []
    task["assignments"] = assignees

    cursor.execute(
        "SELECT id, task_id, title, status, position, created_at FROM checklist_items WHERE task_id = %s ORDER BY position",
        (task_id,),
    )
    task["checklist"] = cursor.fetchall() or []

    # carregar comentários
    cursor.execute(
        "SELECT id, task_id, user_id, content, created_at FROM comments WHERE task_id = %s ORDER BY created_at ASC",
        (task_id,),
    )
    task["comments"] = cursor.fetchall() or []

    return task

def _normalize_id_variants(id_value: str) -> List[str]:
    if not id_value:
        return []
    no_hyphen = id_value.replace("-", "")
    variants = [id_value]
    if no_hyphen != id_value:
        variants.append(no_hyphen)
    return variants

# ---------- ENDPOINTS EXISTENTES (list_tasks, get_task, etc.) ----------
# ... (mantém todos os seus endpoints já definidos)

# ---------- NOVO ENDPOINT PARA COMENTÁRIOS ----------
@router.post("/{task_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(task_id: str, body: CommentCreate, current_user=Depends(get_current_user)):
    """
    Adiciona um comentário a uma task existente.
    """
    with get_db() as conn:
        try:
            import pymysql
            cursor = conn.cursor(pymysql.cursors.DictCursor)
        except Exception:
            cursor = conn.cursor()

        comment_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO comments (id, task_id, user_id, content, created_at) VALUES (%s, %s, %s, %s, %s)",
            (comment_id, task_id, current_user["id"], body.content, datetime.utcnow()),
        )
        conn.commit()

        cursor.execute(
            "SELECT id, task_id, user_id, content, created_at FROM comments WHERE id = %s",
            (comment_id,),
        )
        row = cursor.fetchone()
        cursor.close()

    if not row:
        raise HTTPException(status_code=500, detail="Erro ao salvar comentário.")
    return row

@router.get("/{task_id}/comments", response_model=List[CommentOut])
def list_comments(task_id: str, current_user=Depends(get_current_user)):
    """
    Lista todos os comentários de uma task.
    """
    with get_db() as conn:
        try:
            import pymysql
            cursor = conn.cursor(pymysql.cursors.DictCursor)
        except Exception:
            cursor = conn.cursor()

        # carregar comentários com nome do usuário
    cursor.execute(
        """
        SELECT c.id, c.task_id, c.user_id, u.name AS user_name, c.content, c.created_at
        FROM comments c
        LEFT JOIN users u ON u.id = c.user_id
        WHERE c.task_id = %s
        ORDER BY c.created_at ASC
        """,
    (task_id,),
    )
    task["comments"] = cursor.fetchall() or []
    cursor.close()

    return rows

@router.get("/")
def list_tasks(current_user=Depends(get_current_user)):
    """
    Retorna tasks agrupadas por período (today, this_week, later) onde:
    - o usuário é criador (created_by) OR
    - o usuário é assignee (task_assignees.user_id)
    Cada task inclui assignments (lista de responsáveis com prioridade).
    """
    user_id = current_user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Usuário não identificado.")

    with get_db() as conn:
        try:
            import pymysql
            cursor = conn.cursor(pymysql.cursors.DictCursor)
        except Exception:
            cursor = conn.cursor()

        # Query principal: buscar tasks onde o usuário é criador ou assignee
        # usamos LEFT JOIN para incluir tasks criadas pelo usuário mesmo sem assignees
        cursor.execute(
            """
            SELECT DISTINCT t.id, t.project_id, t.created_by, t.title, t.description, t.status, t.priority, t.due_date, t.created_at, t.updated_at,
                CASE
                    WHEN t.due_date IS NOT NULL AND DATE(t.due_date) = CURDATE() THEN 'today'
                    WHEN t.due_date IS NOT NULL AND DATE(t.due_date) <= DATE_ADD(CURDATE(), INTERVAL 6 DAY) THEN 'this_week'
                    ELSE 'later'
                END AS period
            FROM tasks t
            LEFT JOIN task_assignees ta ON ta.task_id = t.id
            WHERE t.created_by = %s OR ta.user_id = %s
            ORDER BY t.due_date ASC, t.created_at DESC
            """,
            (user_id, user_id),
        )
        rows = cursor.fetchall() or []

        # montar mapa de tasks por id e inicializar assignments vazios
        tasks_by_id = {}
        for r in rows:
            tasks_by_id[r["id"]] = r
            r["assignments"] = []

        # buscar assignments para todas as tasks retornadas (evita N+1)
        if tasks_by_id:
            ids = list(tasks_by_id.keys())
            format_strings = ",".join(["%s"] * len(ids))
            cursor.execute(
                f"""
                SELECT ta.task_id, ta.user_id, u.name as user_name, ta.priority
                FROM task_assignees ta
                LEFT JOIN users u ON u.id = ta.user_id
                WHERE ta.task_id IN ({format_strings})
                """,
                tuple(ids),
            )
            ass_rows = cursor.fetchall() or []
            for a in ass_rows:
                tid = a["task_id"]
                if tid in tasks_by_id:
                    tasks_by_id[tid]["assignments"].append(a)

        cursor.close()

    # agrupar por período
    grouped = {"today": [], "this_week": [], "later": []}
    for r in rows:
        period = r.pop("period", "later") or "later"
        grouped.setdefault(period, []).append(r)

    return grouped


@router.get("/debug-tasks")
def debug_list_tasks(current_user=Depends(get_current_user)):
    """
    Endpoint temporário de debug: retorna user_id, assignments e rows da query principal.
    Use apenas para depuração.
    """
    user_id = current_user.get("id")
    logger.debug("DEBUG list_tasks called for user_id=%s", user_id)

    with get_db() as conn:
        try:
            import pymysql
            cursor = conn.cursor(pymysql.cursors.DictCursor)
        except Exception:
            cursor = conn.cursor()

        cursor.execute("SELECT * FROM task_assignees WHERE user_id = %s", (user_id,))
        ass = cursor.fetchall() or []

        cursor.execute(
            """
            SELECT DISTINCT t.id, t.title, t.created_by, ta.user_id
            FROM tasks t
            LEFT JOIN task_assignees ta ON ta.task_id = t.id
            WHERE t.created_by = %s OR ta.user_id = %s
            """,
            (user_id, user_id),
        )
        rows = cursor.fetchall() or []
        cursor.close()

    return {"user_id": user_id, "task_assignees": ass, "tasks_query_rows": rows}


@router.get("/{task_id}")
def get_task(task_id: str, current_user=Depends(get_current_user)):
    with get_db() as conn:
        try:
            import pymysql
            cursor = conn.cursor(pymysql.cursors.DictCursor)
        except Exception:
            cursor = conn.cursor()

        task = _task_with_details(cursor, task_id)
        cursor.close()

    if not task:
        raise HTTPException(status_code=404, detail="Task não encontrada.")
    return task


@router.post("/", status_code=201)
def create_task(body: TaskCreate, current_user=Depends(get_current_user)):
    task_id = str(uuid.uuid4()).replace("-", "")
    with get_db() as conn:
        try:
            import pymysql
            cursor = conn.cursor(pymysql.cursors.DictCursor)
        except Exception:
            cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO tasks (id, title, description, status, priority, due_date, project_id, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (task_id, body.title, body.description, body.status, body.priority, body.due_date, body.project_id, current_user["id"]),
        )
        conn.commit()

        task = _task_with_details(cursor, task_id)
        cursor.close()
    return task


@router.patch("/{task_id}")
def update_task(task_id: str, body: TaskUpdate, current_user=Depends(get_current_user)):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar.")
    fields = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [task_id]
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"UPDATE tasks SET {fields} WHERE id = %s", values)
            conn.commit()
            task = _task_with_details(cursor, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task não encontrada.")
    return task


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, current_user=Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM tasks WHERE id = %s AND created_by = %s", (task_id, current_user["id"]))
            conn.commit()


@router.post("/{task_id}/assignees/{user_id}", status_code=201)
def add_assignee(task_id: str, user_id: str, current_user=Depends(get_current_user)):
    """
    Adiciona um assignee na tabela task_assignees.
    A prioridade inicial é a prioridade da task (se encontrada) ou 'medium'.
    Normaliza IDs para evitar problemas com hífens.
    """
    with get_db() as conn:
        try:
            import pymysql
            cursor = conn.cursor(pymysql.cursors.DictCursor)
        except Exception:
            cursor = conn.cursor()

        # garantir que a task exista
        cursor.execute("SELECT priority FROM tasks WHERE id = %s", (task_id,))
        t = cursor.fetchone()
        if not t:
            cursor.close()
            raise HTTPException(status_code=404, detail="Task não encontrada.")

        initial_priority = t.get("priority") or "medium"

        # garantir que o usuário exista (aceitar variantes com/sem hífen)
        variants = _normalize_id_variants(user_id)
        found_user = None
        for v in variants:
            cursor.execute("SELECT id FROM users WHERE id = %s", (v,))
            u = cursor.fetchone()
            if u:
                found_user = u["id"]
                break
        if not found_user:
            cursor.close()
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        try:
            cursor.execute(
                "INSERT INTO task_assignees (id, task_id, user_id, priority) VALUES (%s, %s, %s, %s)",
                (str(uuid.uuid4()).replace("-", ""), task_id, found_user, initial_priority),
            )
            conn.commit()
        except Exception as e:
            cursor.close()
            # duplicidade ou FK violada
            raise HTTPException(status_code=400, detail="Usuário já atribuído ou dados inválidos.")
        cursor.close()

    return {"message": "Colaborador adicionado."}


@router.delete("/{task_id}/assignees/{user_id}", status_code=204)
def remove_assignee(task_id: str, user_id: str, current_user=Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM task_assignees WHERE task_id = %s AND user_id = %s", (task_id, user_id))
            conn.commit()


@router.patch("/{task_id}/assignments/{user_id}")
def update_assignment_priority(task_id: str, user_id: str, body: dict, current_user=Depends(get_current_user)):
    """
    Atualiza a prioridade do assignment específico (task_assignees).
    Aceita variantes de user_id (com/sem hífen) ao procurar o registro.
    """
    new_priority = body.get("priority")
    if new_priority not in ["high", "medium", "low"]:
        raise HTTPException(status_code=400, detail="Prioridade inválida.")

    with get_db() as conn:
        try:
            import pymysql
            cursor = conn.cursor(pymysql.cursors.DictCursor)
        except Exception:
            cursor = conn.cursor()

        # tentar atualizar considerando variantes do user_id
        variants = _normalize_id_variants(user_id)
        updated = 0
        for v in variants:
            cursor.execute("UPDATE task_assignees SET priority = %s WHERE task_id = %s AND user_id = %s", (new_priority, task_id, v))
            updated += cursor.rowcount
            if updated:
                break

        if updated == 0:
            cursor.close()
            raise HTTPException(status_code=404, detail="Assignment não encontrado.")
        conn.commit()
        cursor.close()

    return {"message": "Prioridade atualizada com sucesso.", "priority": new_priority}


@router.post("/{task_id}/checklist", status_code=201)
def add_checklist_item(task_id: str, body: ChecklistItemCreate, current_user=Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO checklist_items (id, task_id, title, position) VALUES (%s, %s, %s, %s)",
                (str(uuid.uuid4()).replace("-", ""), task_id, body.title, body.position),
            )
            conn.commit()
    return {"message": "Item adicionado."}


@router.patch("/{task_id}/checklist/{item_id}")
def update_checklist_item(task_id: str, item_id: str, body: ChecklistItemUpdate, current_user=Depends(get_current_user)):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar.")
    fields = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [item_id]
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"UPDATE checklist_items SET {fields} WHERE id = %s", values)
            conn.commit()
    return {"message": "Item atualizado."}


@router.delete("/{task_id}/checklist/{item_id}", status_code=204)
def delete_checklist_item(task_id: str, item_id: str, current_user=Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM checklist_items WHERE id = %s", (item_id,))
            conn.commit()