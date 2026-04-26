from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.auth import get_current_user
import uuid

router = APIRouter(prefix="/projects", tags=["Projects"])


class ProjectCreate(BaseModel):
    name: str
    icon: Optional[str] = "folder"


@router.get("/")
def list_projects(current_user=Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT p.*
                FROM projects p
                LEFT JOIN project_members pm ON pm.project_id = p.id
                WHERE p.owner_id = %s OR pm.user_id = %s
                ORDER BY p.created_at ASC
                """,
                (current_user["id"], current_user["id"]),
            )
            return cursor.fetchall()


@router.post("/", status_code=201)
def create_project(body: ProjectCreate, current_user=Depends(get_current_user)):
    project_id = str(uuid.uuid4()).replace("-", "")
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO projects (id, name, icon, owner_id) VALUES (%s, %s, %s, %s)",
                (project_id, body.name, body.icon, current_user["id"]),
            )
            cursor.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
            return cursor.fetchone()


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, current_user=Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM projects WHERE id = %s AND owner_id = %s",
                (project_id, current_user["id"]),
            )