from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["Tasks"])


# ---------- Schemas ----------

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = "todo"
    priority: str = "medium"
    due_date: Optional[str] = None       # formato: 'YYYY-MM-DD'
    project_id: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    project_id: Optional[str] = None


# ---------- Helpers ----------

def _task_with_assignees(conn, task_id: str) -> dict:
    task = conn.execute(
        "SELECT * FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()
    if not task:
        return None

    assignees = conn.execute(
        """
        SELECT u.id, u.name, u.avatar_url
        FROM task_assignees ta
        JOIN users u ON u.id = ta.user_id
        WHERE ta.task_id = ?
        """,
        (task_id,),
    ).fetchall()

    checklist = conn.execute(
        "SELECT * FROM checklist_items WHERE task_id = ? ORDER BY position",
        (task_id,),
    ).fetchall()

    result = dict(task)
    result["assignees"] = [dict(a) for a in assignees]
    result["checklist"] = [dict(c) for c in checklist]
    return result


# ---------- Rotas ----------

@router.get("/")
def list_tasks(current_user=Depends(get_current_user)):
    """
    Retorna todas as tasks do usuário logado, agrupadas por período:
    today / this_week / later
    """
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT t.*,
                CASE
                    WHEN date(t.due_date) = date('now')             THEN 'today'
                    WHEN date(t.due_date) <= date('now', '+6 days') THEN 'this_week'
                    ELSE                                                  'later'
                END AS period
            FROM tasks t
            LEFT JOIN task_assignees ta ON ta.task_id = t.id
            WHERE t.created_by = ? OR ta.user_id = ?
            ORDER BY t.due_date ASC
            """,
            (current_user["id"], current_user["id"]),
        ).fetchall()

    grouped = {"today": [], "this_week": [], "later": []}
    for row in rows:
        d = dict(row)
        period = d.pop("period", "later")
        grouped[period].append(d)

    return grouped


@router.get("/{task_id}")
def get_task(task_id: str, current_user=Depends(get_current_user)):
    with get_db() as conn:
        task = _task_with_assignees(conn, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task não encontrada.")
    return task


@router.post("/", status_code=201)
def create_task(body: TaskCreate, current_user=Depends(get_current_user)):
    import uuid
    task_id = str(uuid.uuid4()).replace("-", "")

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, title, description, status, priority, due_date, project_id, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                body.title,
                body.description,
                body.status,
                body.priority,
                body.due_date,
                body.project_id,
                current_user["id"],
            ),
        )
        task = _task_with_assignees(conn, task_id)

    return task


@router.patch("/{task_id}")
def update_task(task_id: str, body: TaskUpdate, current_user=Depends(get_current_user)):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar.")

    fields = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [task_id]

    with get_db() as conn:
        conn.execute(f"UPDATE tasks SET {fields} WHERE id = ?", values)
        task = _task_with_assignees(conn, task_id)

    return task


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, current_user=Depends(get_current_user)):
    with get_db() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ? AND created_by = ?",
                     (task_id, current_user["id"]))


# ---------- Assignees ----------

@router.post("/{task_id}/assignees/{user_id}", status_code=201)
def add_assignee(task_id: str, user_id: str, current_user=Depends(get_current_user)):
    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO task_assignees (task_id, user_id) VALUES (?, ?)",
                (task_id, user_id),
            )
        except Exception:
            raise HTTPException(status_code=400, detail="Usuário já atribuído.")
    return {"message": "Colaborador adicionado."}


@router.delete("/{task_id}/assignees/{user_id}", status_code=204)
def remove_assignee(task_id: str, user_id: str, current_user=Depends(get_current_user)):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM task_assignees WHERE task_id = ? AND user_id = ?",
            (task_id, user_id),
        )


# ---------- Checklist ----------

class ChecklistItemCreate(BaseModel):
    title: str
    position: Optional[int] = 0


class ChecklistItemUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    position: Optional[int] = None


@router.post("/{task_id}/checklist", status_code=201)
def add_checklist_item(task_id: str, body: ChecklistItemCreate, current_user=Depends(get_current_user)):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO checklist_items (task_id, title, position) VALUES (?, ?, ?)",
            (task_id, body.title, body.position),
        )
    return {"message": "Item adicionado."}


@router.patch("/{task_id}/checklist/{item_id}")
def update_checklist_item(task_id: str, item_id: str, body: ChecklistItemUpdate, current_user=Depends(get_current_user)):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar.")

    fields = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [item_id]
    with get_db() as conn:
        conn.execute(f"UPDATE checklist_items SET {fields} WHERE id = ?", values)
    return {"message": "Item atualizado."}


@router.delete("/{task_id}/checklist/{item_id}", status_code=204)
def delete_checklist_item(task_id: str, item_id: str, current_user=Depends(get_current_user)):
    with get_db() as conn:
        conn.execute("DELETE FROM checklist_items WHERE id = ?", (item_id,))
