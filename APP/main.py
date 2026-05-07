from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.routers import users, tasks, auth, projects

app = FastAPI(
    title="TaskMaster API",
    version="1.0.0",
    description="Backend do sistema de gerenciamento de tarefas.",
)
# ------------------------------------------------------------------
# CORS — ajuste as origens conforme seu frontend
# ------------------------------------------------------------------
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ------------------------------------------------------------------
# Routers
# ------------------------------------------------------------------
app.include_router(users.router)
app.include_router(tasks.router)
app.include_router(auth.router)
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

