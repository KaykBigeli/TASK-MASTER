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
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Verificar se email existe
        cursor.execute("SELECT id FROM users WHERE email = %s", (body.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="E-mail já cadastrado.")
        
        # 2. Inserir usuário
        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
            (body.name, body.email, hash_password(body.password)),
        )
        
        conn.commit() # Garante a gravação no MariaDB
        
    return {"message": "Usuário criado com sucesso."}

@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends()):
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id, password FROM users WHERE email = %s", (form.username,)
        )
        user = cursor.fetchone()
        
    if not user or not verify_password(form.password, user["password"]):
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    
    token = create_access_token(data={"sub": user["id"]})
    return {"access_token": token, "token_type": "bearer"}