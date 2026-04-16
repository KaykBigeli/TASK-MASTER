-- ============================================================
-- TaskMaster — Schema SQLite
-- ============================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- 1. Usuários
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    password    TEXT NOT NULL,
    avatar_url  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ------------------------------------------------------------
-- 2. Projetos
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    owner_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    icon        TEXT DEFAULT 'folder',   -- ex: 'folder', 'book', 'star'
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ------------------------------------------------------------
-- 3. Membros do projeto (quem pode ver/editar)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS project_members (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
    joined_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, user_id)
);

-- ------------------------------------------------------------
-- 4. Tarefas
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    project_id  TEXT REFERENCES projects(id) ON DELETE SET NULL,
    created_by  TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'todo'
                    CHECK (status IN ('todo', 'in_progress', 'completed')),
    priority    TEXT NOT NULL DEFAULT 'medium'
                    CHECK (priority IN ('high', 'medium', 'low')),
    due_date    TEXT,                    -- formato ISO: 'YYYY-MM-DD'
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Trigger para atualizar updated_at automaticamente
CREATE TRIGGER IF NOT EXISTS tasks_updated_at
    AFTER UPDATE ON tasks
    FOR EACH ROW
BEGIN
    UPDATE tasks SET updated_at = datetime('now') WHERE id = OLD.id;
END;

-- ------------------------------------------------------------
-- 5. Responsáveis pela tarefa (colaboradores)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS task_assignees (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (task_id, user_id)
);

-- ------------------------------------------------------------
-- 6. Itens da checklist
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS checklist_items (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'todo'
                    CHECK (status IN ('todo', 'in_progress', 'completed')),
    position    INTEGER NOT NULL DEFAULT 0,  -- ordem de exibição
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ------------------------------------------------------------
-- 7. Comentários
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS comments (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================
-- Índices para performance
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_tasks_project    ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date   ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_status     ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_task_assignees   ON task_assignees(task_id);
CREATE INDEX IF NOT EXISTS idx_checklist_task   ON checklist_items(task_id, position);
CREATE INDEX IF NOT EXISTS idx_comments_task    ON comments(task_id);
CREATE INDEX IF NOT EXISTS idx_project_members  ON project_members(project_id, user_id);
