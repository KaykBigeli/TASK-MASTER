/* ══════════════════════════════════════
   TaskMaster — app.js (atualizado)
   ══════════════════════════════════════ */

const API = 'http://127.0.0.1:8000';

let token       = localStorage.getItem('tm_token') || '';
let currentUser = JSON.parse(localStorage.getItem('tm_user') || 'null');
let allTasks    = { today: [], this_week: [], later: [] };
let projects    = [];
let currentTask = null;
let activeFilter = null;
let isNewTask   = false;

/* ══ AUTENTICAÇÃO ══ */

function switchTab(tab) {
  document.getElementById('tabLogin').classList.toggle('active', tab === 'login');
  document.getElementById('tabRegister').classList.toggle('active', tab === 'register');
  document.getElementById('loginForm').style.display    = tab === 'login'    ? '' : 'none';
  document.getElementById('registerForm').style.display = tab === 'register' ? '' : 'none';
  document.getElementById('authError').classList.remove('show');
}

async function doLogin() {
  const email = document.getElementById('loginEmail').value.trim();
  const pass  = document.getElementById('loginPassword').value;
  if (!email || !pass) return showAuthError('Preencha todos os campos.');

  try {
    const form = new URLSearchParams({ username: email, password: pass });
    const res  = await fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: form
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) return showAuthError(data.detail || 'Erro ao entrar.');

    token = data.access_token;
    localStorage.setItem('tm_token', token);

    // Tentar buscar perfil do usuário autenticado
    // 1) Preferência: endpoint /users/me
    // 2) Fallback: buscar /users?email=... (se disponível no backend)
    let profile = null;
    try {
      profile = await api('/users/me');
    } catch (e) {
      profile = null;
    }

    if (!profile || !profile.id) {
      // fallback: tentar buscar por e-mail (se o backend suportar query)
      try {
        const usersByEmail = await api(`/users?email=${encodeURIComponent(email)}`);
        if (Array.isArray(usersByEmail) && usersByEmail.length > 0) {
          profile = usersByEmail[0];
        }
      } catch (e) {
        profile = null;
      }
    }

    if (profile && profile.id) {
      currentUser = profile;
      localStorage.setItem('tm_user', JSON.stringify(currentUser));
    } else {
      // fallback mínimo: guardar email (melhor que nada, mas sem id algumas features ficam limitadas)
      currentUser = { email };
      localStorage.setItem('tm_user', JSON.stringify(currentUser));
    }

    initApp();
  } catch (e) {
    showAuthError('Não foi possível conectar à API. Verifique se o servidor está rodando.');
  }
}

async function doRegister() {
  const name  = document.getElementById('regName').value.trim();
  const email = document.getElementById('regEmail').value.trim();
  const pass  = document.getElementById('regPassword').value;
  if (!name || !email || !pass) return showAuthError('Preencha todos os campos.');

  try {
    const res  = await fetch(`${API}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password: pass })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) return showAuthError(data.detail || 'Erro ao criar conta.');

    showToast('Conta criada! Faça login.', 'success');
    switchTab('login');
    document.getElementById('loginEmail').value = email;
  } catch (e) {
    showAuthError('Não foi possível conectar à API.');
  }
}

function showAuthError(msg) {
  const el = document.getElementById('authError');
  el.textContent = msg;
  el.classList.add('show');
}

function logout() {
  localStorage.removeItem('tm_token');
  localStorage.removeItem('tm_user');
  token = ''; currentUser = null;
  // mostrar tela de auth
  document.getElementById('authScreen').classList.remove('hidden');
  // opcional: recarregar para limpar estado
  // location.reload();
}

/* ══ INICIALIZAÇÃO ══ */

async function initApp() {
  document.getElementById('authScreen').classList.add('hidden');
  updateSidebarUser();
  await Promise.all([loadTasks(), loadProjects()]);
}

function updateSidebarUser() {
  if (!currentUser) return;
  const name = currentUser.name || currentUser.email || 'Usuário';
  document.getElementById('sidebarName').textContent  = name;
  document.getElementById('sidebarEmail').textContent = currentUser.email || '';
  document.getElementById('sidebarAvatar').textContent = name[0].toUpperCase();
}

/* ══ API HELPER ══ */

async function api(path, opts = {}) {
  try {
    const res = await fetch(`${API}${path}`, {
      ...opts,
      headers: {
        'Authorization': token ? `Bearer ${token}` : '',
        'Content-Type': 'application/json',
        ...(opts.headers || {})
      }
    });
    if (res.status === 401) { logout(); return null; }
    if (res.status === 204) return {};
    try { return await res.json(); } catch (e) { return {}; }
  } catch (e) {
    showToast('Erro de conexão com a API', 'error');
    return null;
  }
}

/* ══ CARREGAR DADOS ══ */

async function loadTasks() {
  const data = await api('/tasks/');
  if (!data) {
    allTasks = { today: [], this_week: [], later: [] };
    renderTasks();
    return;
  }
  // backend pode retornar { items: [...] } ou lista direta
  let items = [];
  if (Array.isArray(data)) items = data;
  else if (data.items && Array.isArray(data.items)) items = data.items;
  else items = [];

  allTasks = { today: items, this_week: [], later: [] };
  renderTasks();
}

async function loadProjects() {
  const data = await api('/projects/');
  if (!data) return;
  projects = data;
  renderProjectSidebar();
  populateProjectSelect();
}

/* ══ NOVAS FUNÇÕES: USUÁRIOS E ASSIGNEES ══ */

// Carrega lista de usuários do backend
async function loadUsers() {
  const res = await api('/users/');
  return Array.isArray(res) ? res : [];
}

// Renderiza controles interativos para adicionar/remover responsáveis e ajustar prioridades
async function loadTasks() {
  const data = await api('/tasks/');
  if (!data) {
    allTasks = { today: [], this_week: [], later: [] };
    renderTasks();
    return;
  }

  // Aceitar formato { today, this_week, later }
  if (data.today || data.this_week || data.later) {
    allTasks = {
      today: data.today || [],
      this_week: data.this_week || [],
      later: data.later || []
    };
  } else if (Array.isArray(data)) {
    // fallback: lista direta
    allTasks = { today: data, this_week: [], later: [] };
  } else if (data.items && Array.isArray(data.items)) {
    allTasks = { today: data.items, this_week: [], later: [] };
  } else {
    allTasks = { today: [], this_week: [], later: [] };
  }

  renderTasks();
}

// Renderiza controles interativos para adicionar/remover responsáveis e ajustar prioridades
async function renderAssigneeOptions(taskId, currentAssignments = []) {
  const users = await loadUsers();
  const container = document.getElementById('modalAssignees');
  if (!container) return;
  container.innerHTML = '';

  // map userId -> assignment
  const assignedMap = {};
  (currentAssignments || []).forEach(a => {
    const uid = a.user_id || a.userId || a.id || a.user || a.userId;
    assignedMap[uid] = {
      user_id: uid,
      user_name: a.user_name || a.name || a.user || '',
      priority: a.priority || 'medium'
    };
  });

  if (!users.length) {
    container.innerHTML = '<div style="color:var(--muted)">Nenhum usuário encontrado.</div>';
    return;
  }

  users.forEach(u => {
    const uid = u.id || u.user_id || u.email;
    const isAssigned = !!assignedMap[uid];
    const chip = document.createElement('div');
    chip.className = 'assignee-row';
    chip.innerHTML = `
      <div class="assignee-left">
        <div class="avatar">${(u.name || u.email || '?')[0].toUpperCase()}</div>
        <div class="assignee-name">${esc(u.name || u.email || uid)}</div>
      </div>
      <div class="assignee-actions">
        <select class="assignee-priority" data-user-id="${uid}" ${isAssigned ? '' : 'disabled'}>
          <option value="high">🔴 Alta</option>
          <option value="medium">🟡 Média</option>
          <option value="low">🔵 Baixa</option>
        </select>
        <button class="btn btn-sm ${isAssigned ? 'btn-danger' : 'btn-outline'}" data-user-id="${uid}">
          ${isAssigned ? 'Remover' : 'Adicionar'}
        </button>
      </div>
    `;
    container.appendChild(chip);

    const select = chip.querySelector('.assignee-priority');
    const btn = chip.querySelector('button');

    if (isAssigned) {
      select.value = assignedMap[uid].priority || 'medium';
    }

    btn.addEventListener('click', async () => {
      btn.disabled = true;
      if (!taskId) {
        showToast('Salve a task primeiro para adicionar responsáveis.', 'error');
        btn.disabled = false;
        return;
      }
      const resp = !isAssigned
        ? await api(`/tasks/${taskId}/assignees/${uid}`, { method: 'POST' })
        : await api(`/tasks/${taskId}/assignees/${uid}`, { method: 'DELETE' });

      if (resp) {
        const updated = await api(`/tasks/${taskId}`);
        if (updated) {
          currentTask = updated;
          renderAssignees(updated.assignments || updated.assignees || []);
          renderAssigneeOptions(taskId, updated.assignments || updated.assignees || []);
        } else {
          showToast('Operação concluída, mas não foi possível atualizar a task localmente.', 'success');
        }
      } else {
        showToast('Erro ao atualizar responsáveis.', 'error');
      }
      btn.disabled = false;
    });

    select.addEventListener('change', async () => {
      const newPriority = select.value;
      if (!taskId) {
        showToast('Salve a task primeiro.', 'error');
        return;
      }
      if (!isAssigned) {
        showToast('Adicione o responsável antes de alterar a prioridade.', 'error');
        select.value = 'medium';
        return;
      }
      const resp = await api(`/tasks/${taskId}/assignments/${uid}`, {
        method: 'PATCH',
        body: JSON.stringify({ priority: newPriority })
      });
      if (resp) {
        showToast('Prioridade atualizada.', 'success');
      } else {
        showToast('Erro ao atualizar prioridade.', 'error');
      }
    });
  });
}

function renderTasks() {
  const q = (document.getElementById('searchInput')?.value || '').toLowerCase();
  const sections = [
    ['today', 'Hoje'],
    ['this_week', 'Esta Semana'],
    ['later', 'Mais Tarde']
  ];

  let total = 0, done = 0;
  let html = '<div class="filters-bar">';

  [
    [null, '⚪ Todas'],
    ['high', '🔴 Alta'],
    ['medium', '🟡 Média'],
    ['low', '🔵 Baixa']
  ].forEach(([val, label]) => {
    const active = activeFilter === val ? 'active' : '';
    html += `<button class="filter-btn ${active}" onclick="setFilter(${val ? `'${val}'` : null})">${label}</button>`;
  });
  html += '</div>';

  sections.forEach(([key, label]) => {
    const tasks = (allTasks[key] || []).filter(t => {
      // filtro por prioridade
      if (activeFilter) {
        const assignment = (t.assignments || t.assignees || []).find(a => a.user_id === (currentUser?.id));
        const prio = assignment ? assignment.priority : t.priority;
        if (prio !== activeFilter) return false;
      }
      // filtro por busca
      if (q && !t.title?.toLowerCase().includes(q)) return false;
      return true;
    });

    total += tasks.length;
    done += tasks.filter(t => t.status === 'completed').length;

    if (!tasks.length) return;

    html += `
      <div class="section">
        <div class="section-header">
          <span class="section-title">${label}</span>
          <span class="section-count">${tasks.length} task${tasks.length !== 1 ? 's' : ''}</span>
          <div class="section-line"></div>
        </div>`;

    tasks.forEach((t, i) => html += buildTaskRow(t, i));
    html += '</div>';
  });

  if (total === 0) {
    html += `
      <div class="empty-state">
        <div class="empty-icon">📋</div>
        <div class="empty-text">Nenhuma task encontrada.<br>Clique em "+ Nova Task" para começar.</div>
      </div>`;
  }

  const main = document.getElementById('mainContent');
  if (main) main.innerHTML = html;
  updateProgress(done, total);
}

/* ══ RENDERIZAÇÃO ══ */

function renderTasks() {
  const q = (document.getElementById('searchInput') && document.getElementById('searchInput').value || '').toLowerCase();
  const sections = [
    ['today',     'Hoje'],
    ['this_week', 'Esta Semana'],
    ['later',     'Mais Tarde']
  ];

  let total = 0, done = 0;

  let html = '<div class="filters-bar">';
  [
    [null,     '⚪ Todas'],
    ['high',   '🔴 Alta'],
    ['medium', '🟡 Média'],
    ['low',    '🔵 Baixa']
  ].forEach(([val, label]) => {
    const active = activeFilter === val ? 'active' : '';
    html += `<button class="filter-btn ${active}" onclick="setFilter(${val ? `'${val}'` : null})">${label}</button>`;
  });
  html += '</div>';

  sections.forEach(([key, label]) => {
    const tasks = (allTasks[key] || []).filter(t => {
      if (activeFilter) {
        const myId = currentUser && currentUser.id ? currentUser.id : null;
        const assignment = (t.assignments || t.assignees || []).find(a => (a.user_id || a.userId || a.user) === myId);
        const prio = assignment ? assignment.priority : t.priority;
        if (prio !== activeFilter) return false;
      }
      if (q && !t.title.toLowerCase().includes(q)) return false;
      return true;
    });

    total += tasks.length;
    done  += tasks.filter(t => t.status === 'completed').length;

    if (!tasks.length) return;

    html += `
      <div class="section">
        <div class="section-header">
          <span class="section-title">${label}</span>
          <span class="section-count">${tasks.length} task${tasks.length !== 1 ? 's' : ''}</span>
          <div class="section-line"></div>
        </div>`;

    tasks.forEach((t, i) => html += buildTaskRow(t, i));
    html += '</div>';
  });

  if (total === 0) {
    html += `
      <div class="empty-state">
        <div class="empty-icon">📋</div>
        <div class="empty-text">Nenhuma task encontrada.<br>Clique em "+ Nova Task" para começar.</div>
      </div>`;
  }

  const main = document.getElementById('mainContent');
  if (main) main.innerHTML = html;
  updateProgress(done, total);
}

function buildTaskRow(t, index) {
  const isDone  = t.status === 'completed';
  const date    = t.due_date ? fmtDate(t.due_date) : '';
  const labels  = { high: 'Alta', medium: 'Média', low: 'Baixa' };

  let displayPriority = t.priority;
  const myId = currentUser && currentUser.id ? currentUser.id : null;
  const assignment = (t.assignments || t.assignees || []).find(a => (a.user_id || a.userId || a.user) === myId);
  if (assignment && assignment.priority) displayPriority = assignment.priority;

  const colors  = ['#4f6ef7','#7c3aed','#10b981','#f59e0b','#ef4444','#06b6d4'];
  const initials = 'KPMARSGBT';
  const ac      = Math.min(3, Math.floor(Math.random() * 3) + 1);

  const avatars = Array(ac).fill(0).map((_, j) =>
    `<div class="avatar" style="width:24px;height:24px;font-size:10px;border:2px solid var(--surface);margin-left:${j ? '-6px' : '0'};background:${colors[(index + j) % colors.length]}">${initials[(index * 2 + j) % initials.length]}</div>`
  ).join('');

  return `
    <div class="task-row" style="animation-delay:${index * 25}ms" onclick="openTask('${t.id}')">
      <div class="task-check ${isDone ? 'done' : ''}"
           onclick="toggleTask(event, '${t.id}', '${t.status}')">
        ${isDone ? '✓' : ''}
      </div>
      <span class="task-title ${isDone ? 'done' : ''}">${esc(t.title)}</span>
      <span class="task-date">${date}</span>
      <span class="badge badge-${displayPriority}">${labels[displayPriority] || displayPriority}</span>
      <div class="collab-stack">${avatars}</div>
    </div>`;
}

function renderProjectSidebar() {
  const colors = ['#4f6ef7','#7c3aed','#10b981','#f59e0b','#ef4444'];
  const el = document.getElementById('projectList');
  if (!el) return;
  el.innerHTML = projects.map((p, i) => `
    <div class="project-item" onclick="loadTasks()">
      <div class="project-dot" style="background:${colors[i % colors.length]}"></div>
      ${esc(p.name)}
    </div>`).join('');
}

function populateProjectSelect() {
  const el = document.getElementById('modalProject');
  if (!el) return;
  el.innerHTML =
    '<option value="">Nenhum</option>' +
    projects.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('');
}

function updateProgress(done, total) {
  const label = document.getElementById('progressLabel');
  const fill  = document.getElementById('progressFill');
  if (label) label.textContent = `${done} / ${total} concluídas`;
  if (fill) fill.style.width  = total ? `${(done / total) * 100}%` : '0%';
}

/* ══ ACTIONS DE TASK ══ */

async function toggleTask(e, id, status) {
  e.stopPropagation();
  const newStatus = status === 'completed' ? 'todo' : 'completed';
  await api(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify({ status: newStatus }) });
  loadTasks();
}

async function openTask(id) {
  isNewTask = false;
  const task = await api(`/tasks/${id}`);
  if (!task) return;
  currentTask = task;
  fillModal(task);
  renderAssigneeOptions(task.id, task.assignments || task.assignees || []);
  const overlay = document.getElementById('modalOverlay');
  if (overlay) overlay.classList.add('open');
  loadUsersForSelect();
}

function fillModal(task) {
  const titleEl = document.getElementById('modalTitle');
  if (titleEl) titleEl.value = task.title || '';
  const statusEl = document.getElementById('modalStatus');
  if (statusEl) statusEl.value = task.status || 'todo';

  const assignment = (task.assignments || task.assignees || []).find(a => (a.user_id || a.userId || a.user) === (currentUser && currentUser.id));
  const priorityEl = document.getElementById('modalPriority');
  if (priorityEl) priorityEl.value = assignment ? assignment.priority : (task.priority || 'medium');

  const dueEl = document.getElementById('modalDueDate');
  if (dueEl) dueEl.value = task.due_date || '';
  const descEl = document.getElementById('modalDescription');
  if (descEl) descEl.value = task.description || '';
  const projEl = document.getElementById('modalProject');
  if (projEl) projEl.value = task.project_id || '';
  const commentEl = document.getElementById('modalComment');
  if (commentEl) commentEl.value = '';

  renderChecklist(task.checklist  || []);
  renderAssignees(task.assignments || task.assignees || []);
  renderComments(task.comments || []);
}

function renderChecklist(items) {
  const labels = { todo: 'A fazer', in_progress: 'Em andamento', completed: 'Concluído' };
  const html = items.length
    ? items.map((item, i) => `
        <div class="checklist-item">
          <div class="check-circle ${item.status === 'completed' ? 'done' : item.status === 'in_progress' ? 'progress' : ''}"
               onclick="toggleCheckItem('${item.id}', '${item.status}')">
            ${item.status === 'completed' ? '✓' : ''}
          </div>
          <span class="checklist-text">${i + 1}. ${esc(item.title)}</span>
          <span class="checklist-status-badge">${labels[item.status] || ''}</span>
        </div>`).join('')
    : '<div style="color:var(--muted);font-size:13px;padding:8px 0">Nenhum item ainda.</div>';

  const el = document.getElementById('modalChecklist');
  if (el) el.innerHTML = html;
}

function renderAssignees(assignees) {
  const html = (assignees && assignees.length)
    ? assignees.map(a => {
        const name = a.user_name || a.name || a.user || a.email || '?';
        return `<div class="assignee-chip"><div class="avatar">${(name[0] || '?').toUpperCase()}</div><span>${esc(name)}</span></div>`;
      }).join('')
    : '<span class="no-assignee">Nenhum responsável</span>';

  const el = document.getElementById('modalAssignees');
  if (el) el.innerHTML = html;
}

function renderComments(comments) {
  const container = document.getElementById('modalComments');
  if (!container) return;

  if (!comments || !comments.length) {
    container.innerHTML = '<span class="no-comment">Nenhum comentário ainda.</span>';
    return;
  }

  container.innerHTML = comments.map(c => `
    <div class="comment-row">
      <div class="comment-author">${esc(c.user_name || 'Usuário')}</div>
      <div class="comment-content">${esc(c.content)}</div>
      <div class="comment-date">${new Date(c.created_at).toLocaleString()}</div>
    </div>
  `).join('');
}

async function addAssignee() {
  const userId = document.getElementById('assigneeSelect').value;
  const priority = document.getElementById('assigneePriority').value;
  if (!userId || !currentTask) return;

  const resp = await api(`/tasks/${currentTask.id}/assignees/${userId}`, {
    method: 'POST',
    body: JSON.stringify({ priority })
  });

  if (resp) {
    showToast('Responsável adicionado!', 'success');
    // recarregar task para atualizar lista
    const updated = await api(`/tasks/${currentTask.id}`);
    if (updated) {
      currentTask = updated;
      renderAssignees(updated.assignments || []);
    }
  } else {
    showToast('Erro ao adicionar responsável.', 'error');
  }
}

async function loadUsersForSelect() {
  const users = await api('/users/');
  const select = document.getElementById('assigneeSelect');
  if (!select) return;

  select.innerHTML = '<option value="">Selecione um usuário...</option>' +
    users.map(u => `<option value="${u.id}">${esc(u.name)}</option>`).join('');
}

async function toggleCheckItem(id, status) {
  const next = status === 'completed' ? 'todo' : status === 'todo' ? 'in_progress' : 'completed';
  await api(`/tasks/${currentTask.id}/checklist/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ status: next })
  });
  const updated = await api(`/tasks/${currentTask.id}`);
  if (updated) { currentTask = updated; renderChecklist(updated.checklist || []); }
}

async function addCheckItem() {
  const input = document.getElementById('newCheckItem');
  const title = input ? input.value.trim() : '';
  if (!title || !currentTask) return;

  await api(`/tasks/${currentTask.id}/checklist`, {
    method: 'POST',
    body: JSON.stringify({ title, position: (currentTask.checklist || []).length })
  });
  if (input) input.value = '';

  const updated = await api(`/tasks/${currentTask.id}`);
  if (updated) { currentTask = updated; renderChecklist(updated.checklist || []); }
}

function openNewTask() {
  isNewTask = true; currentTask = null;
  ['modalTitle','modalDescription','modalComment','newCheckItem'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const statusEl = document.getElementById('modalStatus');
  if (statusEl) statusEl.value = 'todo';
  const priorityEl = document.getElementById('modalPriority');
  if (priorityEl) priorityEl.value = 'medium';
  const dueEl = document.getElementById('modalDueDate');
  if (dueEl) dueEl.value = '';
  const projectEl = document.getElementById('modalProject');
  if (projectEl) projectEl.value  = '';
  const checklistEl = document.getElementById('modalChecklist');
  if (checklistEl) checklistEl.innerHTML = '';
  // render assignee options disabled until task is created
  renderAssigneeOptions('', []);
  const overlay = document.getElementById('modalOverlay');
  if (overlay) overlay.classList.add('open');
}

async function handleSave() {
  if (isNewTask) await createNewTask();
  else           await saveTask();
}

async function saveTask() {
  if (!currentTask) return;
  const body = getModalBody();
  await api(`/tasks/${currentTask.id}`, { method: 'PATCH', body: JSON.stringify(body) });
  showToast('Task salva com sucesso!', 'success');
  const updated = await api(`/tasks/${currentTask.id}`);
  if (updated) {
    currentTask = updated;
    renderAssignees(updated.assignments || updated.assignees || []);
    renderAssigneeOptions(currentTask.id, updated.assignments || updated.assignees || []);
  }
  loadTasks();
}

async function createNewTask() {
  const body = getModalBody();
  if (!body.title) return showToast('Digite um título para a task.', 'error');

  const task = await api('/tasks/', { method: 'POST', body: JSON.stringify(body) });
  if (task) {
    currentTask = task;
    isNewTask   = false;
    showToast('Task criada!', 'success');
    renderAssigneeOptions(task.id, task.assignments || task.assignees || []);
    loadTasks();
  }
}

function getModalBody() {
  return {
    title:       (document.getElementById('modalTitle') && document.getElementById('modalTitle').value) || '',
    status:      (document.getElementById('modalStatus') && document.getElementById('modalStatus').value) || 'todo',
    priority:    (document.getElementById('modalPriority') && document.getElementById('modalPriority').value) || 'medium',
    due_date:    (document.getElementById('modalDueDate') && document.getElementById('modalDueDate').value) || null,
    description: (document.getElementById('modalDescription') && document.getElementById('modalDescription').value) || null,
    project_id:  (document.getElementById('modalProject') && document.getElementById('modalProject').value) || null,
  };
}

async function deleteCurrentTask() {
  if (!currentTask) return;
  if (!confirm('Tem certeza que deseja deletar esta task?')) return;
  await api(`/tasks/${currentTask.id}`, { method: 'DELETE' });
  closeModal();
  showToast('Task removida.', 'success');
  loadTasks();
}

async function postComment() {
  const contentEl = document.getElementById('modalComment');
  const content = contentEl ? contentEl.value.trim() : '';
  if (!content || !currentTask) return;

  const resp = await api(`/tasks/${currentTask.id}/comments`, {
    method: 'POST',
    body: JSON.stringify({ content })
  });

  if (resp) {
    showToast('Comentário registrado!', 'success');
    if (contentEl) contentEl.value = '';

    // recarregar task para atualizar lista de comentários
    const updated = await api(`/tasks/${currentTask.id}`);
    if (updated) {
      currentTask = updated;
      renderComments(updated.comments || []);
    }
  } else {
    showToast('Erro ao salvar comentário.', 'error');
  }
}

/* ══ PROJETOS (MODAL) ══ */

function openProjectModal() {
  const el = document.getElementById('projectOverlay');
  if (el) el.classList.add('open');
}
function closeProjectModal() {
  const el = document.getElementById('projectOverlay');
  if (el) el.classList.remove('open');
}
async function saveProject() {
  const name = document.getElementById('projectName') ? document.getElementById('projectName').value.trim() : '';
  const description = document.getElementById('projectDescription') ? document.getElementById('projectDescription').value.trim() : '';
  if (!name) {
    showToast('Informe o nome do projeto', 'error');
    return;
  }
  const res = await api('/projects/', {
    method: 'POST',
    body: JSON.stringify({ name, description })
  });
  if (res) {
    closeProjectModal();
    showToast('Projeto criado com sucesso!', 'success');
    loadProjects();
  } else {
    showToast('Erro ao criar projeto', 'error');
  }
}

/* ══ NAVEGAÇÃO ══ */

function setView(el) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  el.classList.add('active');
  renderTasks();
}

function setFilter(priority) {
  activeFilter = priority;
  renderTasks();
}

/* ══ MODAL ══ */

function overlayClick(e) {
  if (e.target === document.getElementById('modalOverlay')) closeModal();
  if (e.target === document.getElementById('projectOverlay')) closeProjectModal();
}

function closeModal() {
  const overlay = document.getElementById('modalOverlay');
  if (overlay) overlay.classList.remove('open');
  loadTasks();
}

/* ══ UTILITÁRIOS ══ */

function fmtDate(d) {
  if (!d) return '';
  const [y, m, day] = d.split('-');
  const months = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
  return `${parseInt(day)} ${months[parseInt(m) - 1]}`;
}

function esc(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function showToast(msg, type = 'success') {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.className   = `toast ${type} show`;
  setTimeout(() => t.classList.remove('show'), 3000);
}

/* ══ BOOT ══ */
if (token) {
  initApp();
}
