from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.auth import get_current_user

router = APIRouter(prefix="/projects", tags=["Projects"])


class ProjectCreate(BaseModel):
    name: str
    icon: Optional[str] = "folder"


@router.get("/")
def list_projects(current_user=Depends(get_current_user)):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT p.*
            FROM projects p
            LEFT JOIN project_members pm ON pm.project_id = p.id
            WHERE p.owner_id = ? OR pm.user_id = ?
            ORDER BY p.created_at ASC
            """,
            (current_user["id"], current_user["id"]),
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/", status_code=201)
def create_project(body: ProjectCreate, current_user=Depends(get_current_user)):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO projects (name, icon, owner_id) VALUES (?, ?, ?)",
            (body.name, body.icon, current_user["id"]),
        )
        project = conn.execute(
            "SELECT * FROM projects WHERE owner_id = ? ORDER BY created_at DESC LIMIT 1",
            (current_user["id"],),
        ).fetchone()
    return dict(project)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, current_user=Depends(get_current_user)):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM projects WHERE id = ? AND owner_id = ?",
            (project_id, current_user["id"]),
        )
