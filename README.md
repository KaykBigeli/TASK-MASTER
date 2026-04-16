# TaskMaster — Backend

API REST construída com **FastAPI** + **SQLite**.

## Estrutura do projeto

```
taskmaster/
├── schema.sql              ← script de criação do banco
├── requirements.txt
├── .env
└── app/
    ├── main.py             ← entrada da aplicação
    ├── config.py           ← variáveis de ambiente
    ├── database.py         ← conexão com SQLite
    ├── auth.py             ← JWT + hash de senha
    └── routers/
        ├── auth.py         ← POST /auth/register, POST /auth/login
        ├── tasks.py        ← CRUD de tarefas, checklist e assignees
        └── projects.py     ← CRUD de projetos
```

## Instalação

```bash
# 1. Criar e ativar o ambiente virtual
python -m venv venv
source venv/bin/activate      # Linux/Mac
venv\Scripts\activate         # Windows

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Garantir que o schema.sql está na raiz do projeto

# 4. Rodar o servidor
uvicorn app.main:app --reload
```

O banco `taskmaster.db` será criado automaticamente na primeira execução.

## Endpoints disponíveis

| Método | Rota                                    | Descrição                        |
|--------|-----------------------------------------|----------------------------------|
| POST   | /auth/register                          | Registrar novo usuário           |
| POST   | /auth/login                             | Login — retorna JWT              |
| GET    | /tasks/                                 | Listar tasks agrupadas por período |
| POST   | /tasks/                                 | Criar task                       |
| GET    | /tasks/{id}                             | Detalhe da task (com checklist)  |
| PATCH  | /tasks/{id}                             | Atualizar task                   |
| DELETE | /tasks/{id}                             | Deletar task                     |
| POST   | /tasks/{id}/assignees/{user_id}         | Adicionar colaborador            |
| DELETE | /tasks/{id}/assignees/{user_id}         | Remover colaborador              |
| POST   | /tasks/{id}/checklist                   | Adicionar item na checklist      |
| PATCH  | /tasks/{id}/checklist/{item_id}         | Atualizar item da checklist      |
| DELETE | /tasks/{id}/checklist/{item_id}         | Remover item da checklist        |
| GET    | /projects/                              | Listar projetos do usuário       |
| POST   | /projects/                              | Criar projeto                    |
| DELETE | /projects/{id}                          | Deletar projeto                  |

## Documentação interativa

Com o servidor rodando, acesse:
- Swagger UI: http://localhost:8000/docs
- ReDoc:       http://localhost:8000/redoc

## Autenticação

Todas as rotas (exceto `/auth/*`) exigem o header:
```
Authorization: Bearer <token>
```

O token é obtido no endpoint `POST /auth/login`.
