// ─── 全局状态 ─────────────────────────────────────────────────────────────────
const API = '/api';
let socket = null;
let term = null;
let fitAddon = null;
let isConnected = false;
let currentServer = null;
let currentSid = null;
let aiBusy = false;

// ─── 初始化 ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTerminal();
  initSocket();
  loadServers();
  loadModels();

  // AI输入回车
  document.getElementById('ai-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') sendAI();
  });

  // 点击遮罩关闭模态框
  document.getElementById('connect-modal').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeConnectModal();
  });
  document.getElementById('model-modal').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeModelModal();
  });
});

// ─── xterm.js 初始化 ──────────────────────────────────────────────────────────
function initTerminal() {
  term = new Terminal({
    cursorBlink: true,
    fontSize: 14,
    fontFamily: '"JetBrains Mono", "Cascadia Code", Menlo, Monaco, "Courier New", monospace',
    theme: {
      background: '#1a1b26',
      foreground: '#c0caf5',
      cursor: '#c0caf5',
      black: '#15161e',
      red: '#f7768e',
      green: '#9ece6a',
      yellow: '#e0af68',
      blue: '#7aa2f7',
      magenta: '#bb9af7',
      cyan: '#7dcfff',
      white: '#a9b1d6',
      brightBlack: '#414868',
      brightRed: '#f7768e',
      brightGreen: '#9ece6a',
      brightYellow: '#e0af68',
      brightBlue: '#7aa2f7',
      brightMagenta: '#bb9af7',
      brightCyan: '#7dcfff',
      brightWhite: '#c0caf5',
    },
    scrollback: 5000,
    allowTransparency: false,
    convertEol: true,
  });

  fitAddon = new FitAddon.FitAddon();
  term.loadAddon(fitAddon);
  term.open(document.getElementById('terminal-container'));
  fitAddon.fit();

  // 键盘输入 → 发送到SSH
  term.onData(data => {
    if (isConnected && socket) {
      socket.emit('terminal_input', { data });
    }
  });

  // 终端尺寸变化
  term.onResize(({ cols, rows }) => {
    if (isConnected && socket) {
      socket.emit('terminal_resize', { cols, rows });
    }
  });

  // 窗口resize时自适应
  window.addEventListener('resize', () => {
    if (fitAddon) fitAddon.fit();
  });

  // 欢迎信息
  term.writeln('\x1b[1;35m  WebSSH Terminal\x1b[0m');
  term.writeln('\x1b[90m  请从左侧选择服务器或点击"新建连接"开始\x1b[0m');
  term.writeln('');
}

// ─── Socket.IO 初始化 ─────────────────────────────────────────────────────────
function initSocket() {
  socket = io({ transports: ['websocket', 'polling'] });

  socket.on('connect', () => {
    console.log('[WS] 已连接到后端');
  });

  // 服务端回传的权威sid（用于AI上下文关联，勿用客户端socket.id）
  socket.on('connected', data => {
    currentSid = data.sid;
  });

  socket.on('disconnect', () => {
    console.log('[WS] 与后端断开');
    if (isConnected) {
      setDisconnected('与后端服务断开连接');
    }
  });

  // SSH连接结果
  socket.on('ssh_connected', data => {
    const btn = document.getElementById('connect-btn');
    btn.textContent = '连接';
    btn.disabled = false;

    if (data.success) {
      closeConnectModal();
      setConnected();
      term.focus();
      addAIMsg(`✓ ${data.message}`, 'success');
    } else {
      showConnectError(data.message);
    }
  });

  // SSH输出 → xterm.js
  socket.on('terminal_output', data => {
    if (term) term.write(data.data);
  });

  // SSH断开
  socket.on('terminal_disconnect', data => {
    setDisconnected(data.reason || 'SSH连接已断开');
  });
}

// ─── 服务器列表 ───────────────────────────────────────────────────────────────
async function loadServers() {
  try {
    const res = await fetch(`${API}/servers`);
    const data = await res.json();
    renderServerList(data.servers || []);
    renderPresetList(data.servers || []);
  } catch (e) {
    console.error('[API] 加载服务器列表失败:', e);
  }
}

function renderServerList(servers) {
  const list = document.getElementById('server-list');
  list.innerHTML = '';

  if (servers.length === 0) {
    list.innerHTML = '<p class="text-xs text-slate-400 px-2 py-4 text-center">暂无服务器<br/>点击下方添加</p>';
    return;
  }

  servers.forEach(s => {
    const item = document.createElement('div');
    item.id = `server-item-${s.id}`;
    item.dataset.host = s.host;
    item.dataset.username = s.username;
    item.className = 'flex items-center gap-1 rounded-lg group hover:bg-purple-50 transition-colors pr-1';

    const btn = document.createElement('button');
    btn.className = 'flex items-center gap-2 flex-1 min-w-0 px-2 py-2 text-left';
    btn.innerHTML = `
      <span class="material-symbols-outlined text-slate-400 group-hover:text-purple-600 text-base shrink-0">dns</span>
      <div class="flex-1 min-w-0">
        <p class="text-xs font-semibold text-slate-700 truncate">${escHtml(s.name)}</p>
        <p class="text-[10px] text-slate-400 truncate">${escHtml(s.username)}@${escHtml(s.host)}</p>
      </div>
    `;
    btn.onclick = () => quickConnectServer(s);

    // 删除按钮（hover时显示）
    const delBtn = document.createElement('button');
    delBtn.className = 'opacity-0 group-hover:opacity-100 shrink-0 h-6 w-6 flex items-center justify-center rounded text-slate-400 hover:text-red-500 hover:bg-red-50 transition-all';
    delBtn.title = '删除';
    delBtn.innerHTML = '<span class="material-symbols-outlined text-sm">delete</span>';
    delBtn.onclick = (e) => { e.stopPropagation(); confirmDeleteServer(s); };

    item.appendChild(btn);
    item.appendChild(delBtn);
    list.appendChild(item);
  });
}

function renderPresetList(servers) {
  const list = document.getElementById('preset-list');
  list.innerHTML = '';

  servers.forEach(s => {
    const btn = document.createElement('button');
    btn.className = 'flex items-center gap-3 rounded-xl border border-slate-200 p-3 hover:bg-purple-50 hover:border-purple-300 text-left transition-all w-full';
    btn.innerHTML = `
      <span class="material-symbols-outlined text-purple-600">dns</span>
      <div>
        <p class="text-sm font-semibold text-slate-800">${escHtml(s.name)}</p>
        <p class="text-xs text-slate-400">${escHtml(s.username)}@${escHtml(s.host)}:${s.port}</p>
      </div>
    `;
    btn.onclick = () => {
      closeConnectModal();
      quickConnectServer(s);
    };
    list.appendChild(btn);
  });
}

// 快速连接（左侧点击/预设列表，密码由后端处理）
function quickConnectServer(s) {
  if (isConnected) {
    if (!confirm(`当前已连接，确定切换到 ${s.name}？`)) return;
    doDisconnect();
  }
  term.clear();
  term.writeln(`\x1b[90m正在连接 ${s.username}@${s.host}:${s.port} ...\x1b[0m`);
  currentServer = s;
  const { cols, rows } = term;
  socket.emit('ssh_connect', { host: s.host, port: s.port, username: s.username, password: '', serverId: s.id, cols, rows });
}

// 删除确认
function confirmDeleteServer(s) {
  if (!confirm(`确定删除服务器 "${s.name}"？`)) return;
  deleteServer(s.id);
}

async function deleteServer(id) {
  try {
    const res = await fetch(`${API}/servers/${id}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.success) {
      loadServers(); // 刷新列表
    }
  } catch (e) {
    console.error('[API] 删除服务器失败:', e);
  }
}

function doConnect() {
  const host = document.getElementById('input-host').value.trim();
  const port = parseInt(document.getElementById('input-port').value) || 22;
  const username = document.getElementById('input-user').value.trim();
  const password = document.getElementById('input-pass').value;
  const name = document.getElementById('input-name').value.trim() || host;
  const saveToList = document.getElementById('input-save').checked;

  if (!host || !username) {
    showConnectError('请填写主机地址和用户名');
    return;
  }

  // 如果勾选了保存，先保存再连接
  if (saveToList) {
    saveAndConnect({ host, port, username, password, name });
  } else {
    startSSHConnect({ host, port, username, password });
  }
}

async function saveAndConnect(params) {
  const btn = document.getElementById('connect-btn');
  btn.textContent = '保存中...';
  btn.disabled = true;

  try {
    const res = await fetch(`${API}/servers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params)
    });
    const data = await res.json();
    if (data.success) {
      loadServers(); // 刷新左侧列表
      startSSHConnect({ ...params, serverId: data.server.id });
    } else {
      showConnectError(data.message || '保存失败');
    }
  } catch (e) {
    showConnectError('保存失败: ' + e.message);
  }
}

function startSSHConnect(params) {
  const btn = document.getElementById('connect-btn');
  btn.textContent = '连接中...';
  btn.disabled = true;
  hideConnectError();

  // 清屏并显示连接信息
  term.clear();
  term.writeln(`\x1b[90m正在连接 ${params.username}@${params.host}:${params.port} ...\x1b[0m`);

  currentServer = params;

  const { cols, rows } = term;
  socket.emit('ssh_connect', { ...params, cols, rows });
}

function doDisconnect() {
  if (socket) socket.emit('ssh_disconnect');
  setDisconnected('已主动断开连接');
}

// ─── 状态更新 ─────────────────────────────────────────────────────────────────
function setConnected() {
  isConnected = true;

  // 状态点
  const dot = document.getElementById('status-dot');
  dot.className = 'h-2 w-2 rounded-full bg-emerald-500 animate-pulse';
  document.getElementById('status-text').textContent = '已连接';

  // 标题
  if (currentServer) {
    const title = `${currentServer.username}@${currentServer.host}`;
    document.getElementById('terminal-title').textContent = title;
    document.getElementById('footer-host').textContent = title;
  }

  // 断开按钮
  document.getElementById('btn-disconnect').classList.remove('hidden');
  document.getElementById('btn-disconnect').classList.add('flex');

  // 高亮左侧服务器
  highlightServer(currentServer?.host);

  fitAddon.fit();
}

function setDisconnected(reason) {
  isConnected = false;

  const dot = document.getElementById('status-dot');
  dot.className = 'h-2 w-2 rounded-full bg-red-400';
  document.getElementById('status-text').textContent = '未连接';
  document.getElementById('terminal-title').textContent = '未连接';
  document.getElementById('footer-host').textContent = '未连接';

  document.getElementById('btn-disconnect').classList.add('hidden');
  document.getElementById('btn-disconnect').classList.remove('flex');

  if (term && reason) {
    term.writeln(`\r\n\x1b[31m[断开] ${reason}\x1b[0m`);
  }

  clearServerHighlight();
}

function highlightServer(host) {
  document.querySelectorAll('#server-list > div').forEach(item => {
    item.classList.toggle('bg-purple-100', !!host && item.dataset.host === host);
  });
}

function clearServerHighlight() {
  document.querySelectorAll('#server-list > div').forEach(item => {
    item.classList.remove('bg-purple-100');
  });
}

// ─── 终端工具 ─────────────────────────────────────────────────────────────────
function clearTerminal() {
  if (term) term.clear();
}

function copyTerminalSelection() {
  if (term) {
    const sel = term.getSelection();
    if (sel) navigator.clipboard.writeText(sel).catch(() => {});
  }
}

// ─── 模态框 ───────────────────────────────────────────────────────────────────
function openConnectModal() {
  document.getElementById('connect-modal').classList.remove('hidden');
  hideConnectError();
  // 重置按钮
  const btn = document.getElementById('connect-btn');
  btn.textContent = '连接';
  btn.disabled = false;
}

function closeConnectModal() {
  document.getElementById('connect-modal').classList.add('hidden');
}

function showConnectError(msg) {
  const el = document.getElementById('connect-error');
  el.textContent = msg;
  el.classList.remove('hidden');
  // 重置按钮
  const btn = document.getElementById('connect-btn');
  btn.textContent = '连接';
  btn.disabled = false;
}

function hideConnectError() {
  document.getElementById('connect-error').classList.add('hidden');
}

// ─── AI 助手 ──────────────────────────────────────────────────────────────────
function quickAI(msg) {
  document.getElementById('ai-input').value = msg;
  sendAI();
}

async function sendAI() {
  const input = document.getElementById('ai-input');
  const msg = input.value.trim();
  if (!msg || aiBusy) return;
  input.value = '';

  addAIMsg(msg, 'user');

  if (!isConnected) {
    addAIMsg('请先连接到服务器', 'error');
    return;
  }

  // 请求期间禁用输入，防止并发导致命令乱序写入终端
  aiBusy = true;
  const inputEl = document.getElementById('ai-input');
  const sendBtn = document.getElementById('ai-send-btn');
  inputEl.disabled = true;
  sendBtn.disabled = true;

  // 显示加载状态
  const loadingId = addAIMsg('解析中...', 'loading');

  try {
    const modelId = document.getElementById('model-select').value || null;
    const res = await fetch(`${API}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, model_id: modelId, sid: currentSid })
    });
    if (res.status === 404) loadModels(); // 所选模型已被删除，刷新列表

    removeAIMsg(loadingId);
    const data = await res.json();

    if (data.success) {
      const via = data.model_name ? `\n— ${data.model_name}` : '';
      addCommandCard(data.parsed_command, data.description || '', via);
    } else if (data.dangerous) {
      addAIMsg(`⚠️ 危险命令已拦截\n${data.message}`, 'warning');
    } else {
      addAIMsg(data.message || '无法解析', 'error');
    }
  } catch (e) {
    removeAIMsg(loadingId);
    addAIMsg(`请求失败: ${e.message}`, 'error');
  } finally {
    aiBusy = false;
    inputEl.disabled = false;
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

// 命令确认卡片：执行/编辑/取消
function addCommandCard(command, description, via = '') {
  const chat = document.getElementById('ai-chat');
  const card = document.createElement('div');
  card.className = 'bg-slate-50 border border-slate-200 rounded-lg p-2.5';

  const descHtml = description
    ? `<p class="text-xs text-slate-500 leading-relaxed mb-2">${escHtml(description)}${escHtml(via)}</p>`
    : '';

  card.innerHTML = `
    <div class="flex items-center justify-between mb-2">
      <span class="text-[10px] font-bold uppercase tracking-wider text-slate-400">建议命令</span>
      <span class="text-[10px] text-slate-400">执行前可编辑</span>
    </div>
    ${descHtml}
    <div class="flex items-center gap-1.5">
      <input type="text"
        class="cmd-input flex-1 min-w-0 rounded-lg border border-slate-200 bg-white px-2 py-1.5 font-mono text-[11px] text-slate-800 focus:ring-2 focus:ring-purple-200 outline-none"/>
      <button class="run-btn shrink-0 rounded-lg bg-purple-700 px-2.5 py-1.5 text-[11px] font-bold text-white hover:bg-purple-600 transition-colors">执行</button>
      <button class="edit-btn shrink-0 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[11px] font-medium text-slate-500 hover:bg-slate-100 transition-colors">编辑</button>
      <button class="cancel-btn shrink-0 h-7 w-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors" title="取消">
        <span class="material-symbols-outlined text-sm">close</span>
      </button>
    </div>
  `;

  const input = card.querySelector('.cmd-input');
  input.value = command;

  const finish = (state, finalCmd = '') => {
    card.querySelectorAll('button').forEach(b => b.remove());
    input.readOnly = true;
    input.disabled = true;
    if (state === 'run') {
      input.className = 'cmd-input flex-1 min-w-0 rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1.5 font-mono text-[11px] text-emerald-800 outline-none';
    } else {
      input.className = 'cmd-input flex-1 min-w-0 rounded-lg border border-slate-200 bg-white px-2 py-1.5 font-mono text-[11px] text-slate-400 line-through outline-none';
    }
    card.dataset.state = state;
    card.dataset.command = finalCmd;
  };

  const runCmd = (cmd) => {
    if (!cmd.trim()) return;
    if (socket && isConnected) {
      socket.emit('terminal_input', { data: cmd + '\n' });
      term.focus();
    }
    finish('run', cmd);
  };

  card.querySelector('.run-btn').onclick = () => runCmd(input.value.trim());
  card.querySelector('.edit-btn').onclick = () => {
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  };
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !input.disabled) runCmd(input.value.trim());
  });
  card.querySelector('.cancel-btn').onclick = () => finish('cancel', '');

  chat.appendChild(card);
  chat.scrollTop = chat.scrollHeight;
}

let aiMsgCounter = 0;

// ─── 模型管理 ─────────────────────────────────────────────────────────────────
let modelListCache = [];

async function loadModels() {
  try {
    const res = await fetch(`${API}/models`);
    const data = await res.json();
    modelListCache = data.models || [];
    renderModelSelect();
    renderModelList();
  } catch (e) {
    console.error('[API] 加载模型列表失败:', e);
  }
}

function renderModelSelect() {
  const sel = document.getElementById('model-select');
  const prev = sel.value;
  sel.innerHTML = '';

  if (!modelListCache.length) {
    sel.innerHTML = '<option value="">暂无模型</option>';
    sel.disabled = true;
    return;
  }
  sel.disabled = false;
  modelListCache.forEach(m => {
    const opt = document.createElement('option');
    opt.value = m.id;
    opt.textContent = m.is_default ? `${m.name} ·默认` : m.name;
    sel.appendChild(opt);
  });
  const current = modelListCache.find(m => m.id === prev);
  const def = modelListCache.find(m => m.is_default) || modelListCache[0];
  sel.value = (current || def).id;
}

function renderModelList() {
  const list = document.getElementById('model-list');
  list.innerHTML = '';

  if (!modelListCache.length) {
    list.innerHTML = '<p class="text-xs text-slate-400 px-1 py-2">暂无模型，请在下方添加</p>';
    return;
  }

  modelListCache.forEach(m => {
    const item = document.createElement('div');
    item.className = 'flex items-center gap-1 rounded-xl border border-slate-200 p-3 group';
    item.innerHTML = `
      <div class="flex-1 min-w-0">
        <p class="text-sm font-semibold text-slate-800 flex items-center gap-1.5">
          ${escHtml(m.name)}
          ${m.is_default ? '<span class="text-[10px] bg-purple-100 text-purple-700 rounded px-1.5 py-0.5">默认</span>' : ''}
        </p>
        <p class="text-[10px] text-slate-400 truncate font-mono">${escHtml(m.model)} @ ${escHtml(m.base_url.replace(/^https?:\/\//, ''))}</p>
      </div>
    `;

    const mkBtn = (icon, title, onclick, hoverColor = 'hover:text-purple-700') => {
      const b = document.createElement('button');
      b.title = title;
      b.className = `shrink-0 h-7 w-7 flex items-center justify-center rounded-lg text-slate-400 ${hoverColor} hover:bg-slate-50 transition-colors`;
      b.innerHTML = `<span class="material-symbols-outlined text-base">${icon}</span>`;
      b.onclick = onclick;
      return b;
    };

    if (!m.is_default) {
      item.appendChild(mkBtn('star', '设为默认', () => setDefaultModel(m.id)));
    }
    item.appendChild(mkBtn('network_check', '测试连接', () => testSavedModel(m)));
    item.appendChild(mkBtn('delete', '删除', () => {
      if (confirm(`确定删除模型 "${m.name}"？`)) deleteModel(m.id);
    }, 'hover:text-red-500'));

    list.appendChild(item);
  });
}

function modelFormMsg(msg, type) {
  const el = document.getElementById('model-form-msg');
  if (!msg) { el.classList.add('hidden'); return; }
  el.textContent = msg;
  el.className = `text-xs rounded-lg px-3 py-2 ${
    type === 'error' ? 'text-red-600 bg-red-50'
    : type === 'success' ? 'text-emerald-600 bg-emerald-50'
    : 'text-slate-600 bg-slate-50'
  }`;
}

function readModelForm() {
  return {
    name: document.getElementById('m-name').value.trim(),
    base_url: document.getElementById('m-url').value.trim(),
    api_key: document.getElementById('m-key').value.trim(),
    model: document.getElementById('m-model').value.trim()
  };
}

async function fetchModelList() {
  const { base_url, api_key } = readModelForm();
  if (!base_url) { modelFormMsg('请先填写 API 地址', 'error'); return; }

  const btn = document.getElementById('m-fetch-btn');
  btn.textContent = '读取中...'; btn.disabled = true;
  modelFormMsg('正在读取模型列表...', '');

  try {
    const res = await fetch(`${API}/models/probe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_url, api_key })
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.message || '读取失败');

    const sel = document.getElementById('m-model-select');
    sel.innerHTML = '';
    data.models.forEach(id => {
      const o = document.createElement('option');
      o.value = id; o.textContent = id;
      sel.appendChild(o);
    });
    sel.classList.remove('hidden');

    const input = document.getElementById('m-model');
    const cur = input.value.trim();
    input.value = data.models.includes(cur) ? cur : (data.models[0] || cur);
    sel.value = input.value;

    modelFormMsg(`读取到 ${data.models.length} 个模型，可从下拉框切换`, 'success');
  } catch (e) {
    modelFormMsg(`读取失败: ${e.message}`, 'error');
  } finally {
    btn.textContent = '读取模型列表'; btn.disabled = false;
  }
}

async function testModelForm() {
  const f = readModelForm();
  if (!f.base_url || !f.model) { modelFormMsg('请填写 API 地址和模型 ID', 'error'); return; }
  modelFormMsg('测试中...', '');

  try {
    const res = await fetch(`${API}/models/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(f)
    });
    const data = await res.json();
    modelFormMsg(data.message, data.success ? 'success' : 'error');
  } catch (e) {
    modelFormMsg(`测试失败: ${e.message}`, 'error');
  }
}

async function testSavedModel(m) {
  modelFormMsg(`正在测试 "${m.name}" ...`, '');
  try {
    const res = await fetch(`${API}/models/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: m.id })
    });
    const data = await res.json();
    modelFormMsg(`${m.name}: ${data.message}`, data.success ? 'success' : 'error');
  } catch (e) {
    modelFormMsg(`测试失败: ${e.message}`, 'error');
  }
}

async function addModel() {
  const f = readModelForm();
  if (!f.name || !f.base_url || !f.model) {
    modelFormMsg('名称、API 地址、模型 ID 不能为空', 'error');
    return;
  }

  try {
    const res = await fetch(`${API}/models`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(f)
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.message || '添加失败');

    ['m-name', 'm-url', 'm-key', 'm-model'].forEach(id => {
      document.getElementById(id).value = '';
    });
    document.getElementById('m-model-select').classList.add('hidden');
    modelFormMsg(`模型 "${data.model.name}" 已添加`, 'success');
    loadModels();
  } catch (e) {
    modelFormMsg(e.message, 'error');
  }
}

async function deleteModel(id) {
  try {
    const res = await fetch(`${API}/models/${id}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.success) loadModels();
  } catch (e) {
    console.error('[API] 删除模型失败:', e);
  }
}

async function setDefaultModel(id) {
  try {
    const res = await fetch(`${API}/models/${id}/default`, { method: 'POST' });
    const data = await res.json();
    if (data.success) loadModels();
  } catch (e) {
    console.error('[API] 设置默认模型失败:', e);
  }
}

function openModelModal() {
  document.getElementById('model-modal').classList.remove('hidden');
  modelFormMsg('');
  loadModels();
}

function closeModelModal() {
  document.getElementById('model-modal').classList.add('hidden');
}
function addAIMsg(text, type = 'assistant') {
  const chat = document.getElementById('ai-chat');
  const id = `ai-msg-${++aiMsgCounter}`;
  const div = document.createElement('div');
  div.id = id;

  const styles = {
    user: 'bg-purple-100 ml-6 rounded-lg p-2.5',
    assistant: 'bg-slate-50 border border-slate-200 rounded-lg p-2.5',
    success: 'bg-emerald-50 border border-emerald-200 rounded-lg p-2.5',
    error: 'bg-red-50 border border-red-200 rounded-lg p-2.5',
    warning: 'bg-amber-50 border border-amber-200 rounded-lg p-2.5',
    loading: 'bg-slate-50 rounded-lg p-2.5 animate-pulse',
  };

  div.className = styles[type] || styles.assistant;

  // 处理代码块格式
  const formatted = escHtml(text).replace(/`([^`]+)`/g, '<code class="bg-purple-100 text-purple-700 px-1 rounded font-mono text-[11px]">$1</code>');
  div.innerHTML = `<p class="text-xs text-slate-700 leading-relaxed whitespace-pre-line">${formatted}</p>`;

  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return id;
}

function removeAIMsg(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

// ─── 工具函数 ─────────────────────────────────────────────────────────────────
function escHtml(str) {
  const d = document.createElement('div');
  d.textContent = String(str);
  return d.innerHTML;
}
