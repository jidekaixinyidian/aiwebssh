// ─── 全局状态 ─────────────────────────────────────────────────────────────────
const API = 'http://localhost:5000/api';
let socket = null;
let term = null;
let fitAddon = null;
let isConnected = false;
let currentServer = null;
let connectStartTime = null;

// ─── 初始化 ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTerminal();
  initSocket();
  loadServers();

  // AI输入回车
  document.getElementById('ai-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') sendAI();
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
  socket = io('http://localhost:5000', { transports: ['websocket', 'polling'] });

  socket.on('connect', () => {
    console.log('[WS] 已连接到后端, sid:', socket.id);
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
      // 直接用预设服务器ID连接，密码由后端处理
      closeConnectModal();
      term.clear();
      term.writeln(`\x1b[90m正在连接 ${s.username}@${s.host}:${s.port} ...\x1b[0m`);
      currentServer = s;
      connectStartTime = Date.now();
      const { cols, rows } = term;
      socket.emit('ssh_connect', { host: s.host, port: s.port, username: s.username, password: '', serverId: s.id, cols, rows });
    };
    list.appendChild(btn);
  });
}

// 快速连接（左侧点击，密码由后端处理）
function quickConnectServer(s) {
  if (isConnected) {
    if (!confirm(`当前已连接，确定切换到 ${s.name}？`)) return;
    doDisconnect();
  }
  term.clear();
  term.writeln(`\x1b[90m正在连接 ${s.username}@${s.host}:${s.port} ...\x1b[0m`);
  currentServer = s;
  connectStartTime = Date.now();
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
  connectStartTime = Date.now();

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

  // 延迟显示
  const latency = connectStartTime ? `${Date.now() - connectStartTime}ms` : '';
  document.getElementById('footer-latency').textContent = latency ? `延迟: ${latency}` : '';

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
  document.getElementById('footer-latency').textContent = '';

  document.getElementById('btn-disconnect').classList.add('hidden');
  document.getElementById('btn-disconnect').classList.remove('flex');

  if (term && reason) {
    term.writeln(`\r\n\x1b[31m[断开] ${reason}\x1b[0m`);
  }

  clearServerHighlight();
}

function highlightServer(host) {
  document.querySelectorAll('#server-list > div').forEach(item => {
    item.classList.remove('bg-purple-100');
  });
  if (!host) return;
  document.querySelectorAll('#server-list > div').forEach(item => {
    const text = item.querySelector('p')?.textContent || '';
    if (text.includes(host)) item.classList.add('bg-purple-100');
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

// 点击遮罩关闭
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('connect-modal').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeConnectModal();
  });
});

// ─── AI 助手 ──────────────────────────────────────────────────────────────────
function quickAI(msg) {
  document.getElementById('ai-input').value = msg;
  sendAI();
}

async function sendAI() {
  const input = document.getElementById('ai-input');
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';

  addAIMsg(msg, 'user');

  if (!isConnected) {
    addAIMsg('请先连接到服务器', 'error');
    return;
  }

  // 显示加载状态
  const loadingId = addAIMsg('解析中...', 'loading');

  try {
    const res = await fetch(`${API}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg })
    });

    removeAIMsg(loadingId);
    const data = await res.json();

    if (data.success) {
      addAIMsg(`命令: \`${data.parsed_command}\`\n${data.description || ''}`, 'assistant');
      // 通过WebSocket发送命令到终端（追加换行执行）
      if (socket && isConnected) {
        socket.emit('terminal_input', { data: data.parsed_command + '\n' });
        term.focus();
      }
    } else if (data.dangerous) {
      addAIMsg(`⚠️ 危险命令已拦截\n${data.message}`, 'warning');
    } else {
      addAIMsg(data.message || '无法解析', 'error');
    }
  } catch (e) {
    removeAIMsg(loadingId);
    addAIMsg(`请求失败: ${e.message}`, 'error');
  }
}

let aiMsgCounter = 0;
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
