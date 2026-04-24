from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.routers import auth, tasks, projects

app = FastAPI(
    title="TaskMaster API",
    version="1.0.0",
    description="Backend do sistema de gerenciamento de tarefas.",
)
# teste da API
@app.post("/teste-direto")
def teste_direto():
    return {"message": "Se isso aparecer, o problema está no arquivo auth.py"}
# ------------------------------------------------------------------
# CORS — ajuste as origens conforme seu frontend
# ------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# Routers
# ------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(projects.router)


# ------------------------------------------------------------------
# Inicializa o banco na primeira execução
# ------------------------------------------------------------------
@app.on_event("startup")
def startup():
    init_db()

@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "message": "TaskMaster API rodando!"}
