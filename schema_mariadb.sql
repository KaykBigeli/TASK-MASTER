-- ============================================================
-- TaskMaster — Schema MariaDB
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id          VARCHAR(32) PRIMARY KEY DEFAULT (LOWER(HEX(RANDOM_BYTES(16)))),
    name        VARCHAR(255) NOT NULL,
    email       VARCHAR(255) NOT NULL UNIQUE,
    password    VARCHAR(255) NOT NULL,
    avatar_url  VARCHAR(500),
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
    id          VARCHAR(32) PRIMARY KEY DEFAULT (LOWER(HEX(RANDOM_BYTES(16)))),
    owner_id    VARCHAR(32) NOT NULL,
    name        VARCHAR(255) NOT NULL,
    icon        VARCHAR(50) DEFAULT 'folder',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_members (
    id          VARCHAR(32) PRIMARY KEY DEFAULT (LOWER(HEX(RANDOM_BYTES(16)))),
    project_id  VARCHAR(32) NOT NULL,
    user_id     VARCHAR(32) NOT NULL,
    role        ENUM('admin', 'member') NOT NULL DEFAULT 'member',
    joined_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_project_member (project_id, user_id),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tasks (
    id          VARCHAR(32) PRIMARY KEY,
    project_id  VARCHAR(32),
    created_by  VARCHAR(32) NOT NULL,
    title       VARCHAR(500) NOT NULL,
    description TEXT,
    status      ENUM('todo', 'in_progress', 'completed') NOT NULL DEFAULT 'todo',
    priority    ENUM('high', 'medium', 'low') NOT NULL DEFAULT 'medium',
    due_date    DATE,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS task_assignees (
    id          VARCHAR(32) PRIMARY KEY DEFAULT (LOWER(HEX(RANDOM_BYTES(16)))),
    task_id     VARCHAR(32) NOT NULL,
    user_id     VARCHAR(32) NOT NULL,
    assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_task_assignee (task_id, user_id),
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS checklist_items (
    id          VARCHAR(32) PRIMARY KEY DEFAULT (LOWER(HEX(RANDOM_BYTES(16)))),
    task_id     VARCHAR(32) NOT NULL,
    title       VARCHAR(500) NOT NULL,
    status      ENUM('todo', 'in_progress', 'completed') NOT NULL DEFAULT 'todo',
    position    INT NOT NULL DEFAULT 0,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS comments (
    id          VARCHAR(32) PRIMARY KEY DEFAULT (LOWER(HEX(RANDOM_BYTES(16)))),
    task_id     VARCHAR(32) NOT NULL,
    user_id     VARCHAR(32) NOT NULL,
    content     TEXT NOT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_tasks_project   ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date  ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_status    ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_task_assignees  ON task_assignees(task_id);
CREATE INDEX IF NOT EXISTS idx_checklist_task  ON checklist_items(task_id, position);
CREATE INDEX IF NOT EXISTS idx_comments_task   ON comments(task_id);