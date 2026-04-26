import uuid
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from app.database import get_db
from app.auth import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Auth"])


class RegisterInput(BaseModel):
    name: str
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/register", status_code=201)
def register(body: RegisterInput):
    user_id = str(uuid.uuid4()).replace("-", "")
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE email = %s", (body.email,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="E-mail já cadastrado.")
            cursor.execute(
                "INSERT INTO users (id, name, email, password) VALUES (%s, %s, %s, %s)",
                (user_id, body.name, body.email, hash_password(body.password)),
            )
    return {"message": "Usuário criado com sucesso."}


@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends()):
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, password FROM users WHERE email = %s", (form.username,)
            )
            user = cursor.fetchone()
    if not user or not verify_password(form.password, user["password"]):
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    token = create_access_token({"sub": user["id"]})
    return {"access_token": token, "token_type": "bearer"}