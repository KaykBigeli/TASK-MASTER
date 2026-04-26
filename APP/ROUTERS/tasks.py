from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.auth import get_current_user
import uuid

router = APIRouter(prefix="/tasks", tags=["Tasks"])


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


def _task_with_details(cursor, task_id: str):
    cursor.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
    task = cursor.fetchone()
    if not task:
        return None
    cursor.execute(
        """
        SELECT u.id, u.name, u.avatar_url
        FROM task_assignees ta
        JOIN users u ON u.id = ta.user_id
        WHERE ta.task_id = %s
        """,
        (task_id,),
    )
    task["assignees"] = cursor.fetchall()
    cursor.execute(
        "SELECT * FROM checklist_items WHERE task_id = %s ORDER BY position",
        (task_id,),
    )
    task["checklist"] = cursor.fetchall()
    return task


@router.get("/")
def list_tasks(current_user=Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT t.*,
                    CASE
                        WHEN DATE(t.due_date) = CURDATE() THEN 'today'
                        WHEN DATE(t.due_date) <= DATE_ADD(CURDATE(), INTERVAL 6 DAY) THEN 'this_week'
                        ELSE 'later'
                    END AS period
                FROM tasks t
                LEFT JOIN task_assignees ta ON ta.task_id = t.id
                WHERE t.created_by = %s OR ta.user_id = %s
                ORDER BY t.due_date ASC
                """,
                (current_user["id"], current_user["id"]),
            )
            rows = cursor.fetchall()

    grouped = {"today": [], "this_week": [], "later": []}
    for row in rows:
        period = row.pop("period", "later")
        grouped[period].append(row)
    return grouped


@router.get("/{task_id}")
def get_task(task_id: str, current_user=Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as cursor:
            task = _task_with_details(cursor, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task não encontrada.")
    return task


@router.post("/", status_code=201)
def create_task(body: TaskCreate, current_user=Depends(get_current_user)):
    task_id = str(uuid.uuid4()).replace("-", "")
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO tasks (id, title, description, status, priority, due_date, project_id, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (task_id, body.title, body.description, body.status,
                 body.priority, body.due_date, body.project_id, current_user["id"]),
            )
            return _task_with_details(cursor, task_id)


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
            return _task_with_details(cursor, task_id)


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, current_user=Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM tasks WHERE id = %s AND created_by = %s",
                (task_id, current_user["id"]),
            )


@router.post("/{task_id}/assignees/{user_id}", status_code=201)
def add_assignee(task_id: str, user_id: str, current_user=Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    "INSERT INTO task_assignees (task_id, user_id) VALUES (%s, %s)",
                    (task_id, user_id),
                )
            except Exception:
                raise HTTPException(status_code=400, detail="Usuário já atribuído.")
    return {"message": "Colaborador adicionado."}


@router.delete("/{task_id}/assignees/{user_id}", status_code=204)
def remove_assignee(task_id: str, user_id: str, current_user=Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM task_assignees WHERE task_id = %s AND user_id = %s",
                (task_id, user_id),
            )


@router.post("/{task_id}/checklist", status_code=201)
def add_checklist_item(task_id: str, body: ChecklistItemCreate, current_user=Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO checklist_items (task_id, title, position) VALUES (%s, %s, %s)",
                (task_id, body.title, body.position),
            )
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
    return {"message": "Item atualizado."}


@router.delete("/{task_id}/checklist/{item_id}", status_code=204)
def delete_checklist_item(task_id: str, item_id: str, current_user=Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM checklist_items WHERE id = %s", (item_id,))