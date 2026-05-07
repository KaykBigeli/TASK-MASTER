from fastapi import APIRouter, Depends
from app.database import get_db
from app.auth import get_current_user

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/")
def list_users(current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name, email FROM users")
            return cursor.fetchall()

@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return current_user
