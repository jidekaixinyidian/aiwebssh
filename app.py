import json
import logging
import os
import re
import socket
import threading
import uuid

import paramiko
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit

from ai_parser import (AICommandParser, fetch_available_models, match_local_intent,
                       test_model)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger('webssh')

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['SECRET_KEY'] = 'webssh-secret'
CORS(app, origins='*')
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading', ping_timeout=60)

sessions = {}
sessions_lock = threading.Lock()
BUF_SIZE = 1024 * 32
SSH_KEEPALIVE_SECONDS = 30

# AI会话上下文（按sid）：cwd跟踪、最近命令输出、AI对话历史
CONTEXT_MAX_COMMANDS = 3      # 记住最近几条命令及其输出
CONTEXT_OUTPUT_CHARS = 600    # 每条命令输出的截断长度
CONTEXT_MAX_ROUNDS = 6        # AI对话历史轮数（与parser一致）
context_store = {}
context_lock = threading.Lock()


def get_session_context(sid, create=False):
    """获取（或创建）sid的AI上下文"""
    with context_lock:
        ctx = context_store.get(sid)
        if ctx is None and create:
            ctx = {'cwd': '~', 'last_commands': [], 'ai_history': []}
            context_store[sid] = ctx
        return ctx


def clean_command_output(command, raw_output):
    """从原始输出中剥离命令回显行和prompt行，返回干净结果"""
    lines = raw_output.splitlines()
    cleaned = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        # 跳过命令回显行：prompt+命令，或ANSI清洗后仅剩命令本身
        if command and (s == command or
                        (command in ln and TerminalTap.PROMPT_RE.search(ln))):
            continue
        # 跳过prompt行
        if TerminalTap.PROMPT_RE.fullmatch(s) or TerminalTap.PROMPT_RE.search(s):
            # prompt行可能带在输出末尾，去掉prompt部分保留前缀
            stripped = TerminalTap.PROMPT_RE.sub('', s).strip()
            if not stripped:
                continue
            cleaned.append(stripped)
            continue
        cleaned.append(ln.rstrip())
    return '\n'.join(cleaned)


def build_context_block(ctx):
    """把会话上下文格式化为注入system prompt的文本"""
    if not ctx:
        return None
    lines = [f'- 当前目录: {ctx.get("cwd", "~")}']
    for item in ctx.get('last_commands', [])[-CONTEXT_MAX_COMMANDS:]:
        command = item.get('command', '')
        raw = (item.get('output') or '').strip()
        if not raw:
            lines.append(f'- 命令 `{command}` 刚执行，暂无输出（可能仍在运行）')
            continue
        out = clean_command_output(command, raw)
        if out:
            out = out.replace('\n', ' ⏎ ')
            if len(out) > CONTEXT_OUTPUT_CHARS:
                out = out[:CONTEXT_OUTPUT_CHARS] + '...(截断)'
            status = '' if item.get('done') else '（可能仍在输出）'
            lines.append(f'- 命令 `{command}` 的输出{status}: {out}')
        else:
            lines.append(f'- 命令 `{command}` 已执行（无有效输出）')
    return '\n'.join(lines)


def record_ai_round(sid, user_msg, assistant_msg):
    """记录一轮AI对话，供后续多轮解析使用"""
    ctx = get_session_context(sid, create=True)
    with context_lock:
        ctx['ai_history'].append({'role': 'user', 'content': user_msg})
        ctx['ai_history'].append({'role': 'assistant', 'content': assistant_msg})
        if len(ctx['ai_history']) > CONTEXT_MAX_ROUNDS * 2:
            del ctx['ai_history'][:len(ctx['ai_history']) - CONTEXT_MAX_ROUNDS * 2]


def cleanup_context(sid):
    with context_lock:
        context_store.pop(sid, None)


# 终端输出的ANSI转义序列（用于生成AI可读的上下文）
_ANSI_RE = re.compile(
    r'\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(\x07|\x1b\\)|[\x00-\x08\x0b-\x1f\x7f]'
)


def strip_ansi(text):
    """去除ANSI转义序列和控制字符"""
    return _ANSI_RE.sub('', text)


class TerminalTap:
    """挂在SSH会话上的轻量输出监听：跟踪cwd、按命令持续捕获输出

    输出捕获策略：命令提交后开始累计，直到输出流里再次出现shell
    prompt（说明命令结束）为止。生成AI上下文时剥离命令回显和
    prompt行，让AI看到的是干净的命令结果。
    """

    # shell prompt 形如 "user@host:~$" / "root@host:~#" / "[root@host ~]#"
    PROMPT_RE = re.compile(r'[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+:[^\n$#]*[$#]')

    def __init__(self, sid):
        self.sid = sid
        self.pending = ''   # 当前命令正在累计的原始输出

    def on_input(self, text):
        """用户输入（来自terminal_input），识别回车提交的命令（异常不影响主流程）"""
        try:
            self._on_input_impl(text)
        except Exception as e:
            logger.warning('TerminalTap处理输入失败 %s: %s', self.sid, e)

    def _on_input_impl(self, text):
        if '\n' not in text and '\r' not in text:
            return
        # 取最后一个回车之前的完整行作为命令（忽略tab补全等控制字符）
        line = text.split('\n')[0].split('\r')[0]
        line = line.strip()
        if not line:
            return
        ctx = get_session_context(self.sid, create=True)
        with context_lock:
            ctx['last_commands'].append({'command': line[:200], 'output': '',
                                         'done': False})
            if len(ctx['last_commands']) > CONTEXT_MAX_COMMANDS:
                del ctx['last_commands'][:len(ctx['last_commands']) - CONTEXT_MAX_COMMANDS]
        self.pending = ''

    def on_output(self, raw_text):
        """SSH输出流，累计并尝试解析cwd（任何异常都不影响终端主流程）"""
        try:
            self._on_output_impl(raw_text)
        except Exception as e:
            logger.warning('TerminalTap处理输出失败 %s: %s', self.sid, e)

    def _on_output_impl(self, raw_text):
        self.pending += raw_text
        ctx = get_session_context(self.sid)
        if ctx is None:
            return
        # 先清洗ANSI/OSC再解析，避免标题序列混入cwd
        clean_pending = strip_ansi(self.pending)
        with context_lock:
            # 解析cwd：识别 "user@host:~/path$" 这类prompt行
            m = re.findall(r'[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+:([^$#\n]+)[$#]', clean_pending)
            if m:
                cwd = m[-1].strip()
                if cwd and len(cwd) < 512:
                    ctx['cwd'] = cwd
            # 持续追加到最近一条未完成命令，prompt再次出现即标记完成
            for item in reversed(ctx['last_commands']):
                if not item.get('done'):
                    item['output'] = clean_pending
                    if len(item['output']) > CONTEXT_OUTPUT_CHARS * 2:
                        item['output'] = item['output'][:CONTEXT_OUTPUT_CHARS * 2]
                    if self.PROMPT_RE.search(item['output']):
                        item['done'] = True
                    break
        # 防止无限增长
        if len(self.pending) > 8192:
            self.pending = self.pending[-4096:]


taps = {}
taps_lock = threading.Lock()


def get_tap(sid, create=False):
    with taps_lock:
        tap = taps.get(sid)
        if tap is None and create:
            tap = TerminalTap(sid)
            taps[sid] = tap
        return tap


def generate_unique_id(existing_ids):
    """生成不与现有集合冲突的短ID"""
    while True:
        new_id = uuid.uuid4().hex[:12]
        if new_id not in existing_ids:
            return new_id


# ─── 服务器存储（内存 + JSON文件持久化）──────────────────────────────────────
SERVERS_FILE = 'servers.json'
servers_lock = threading.Lock()


def build_default_server():
    """根据.env配置构造默认服务器条目"""
    if not os.getenv('SSH_HOST'):
        return []
    return [{
        'id': 'prod-01',
        'name': 'production-01',
        'host': os.getenv('SSH_HOST', ''),
        'username': os.getenv('SSH_USER', ''),
        'password': os.getenv('SSH_PASSWORD', ''),
        'port': int(os.getenv('SSH_PORT', 22) or 22),
        'description': 'Production Server'
    }]


def load_servers_from_file():
    """从文件加载服务器列表，不存在则用.env默认值初始化"""
    if not os.path.exists(SERVERS_FILE):
        default = build_default_server()
        save_servers_to_file()
        return default

    try:
        with open(SERVERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        logger.warning('%s 内容不是列表，已忽略并使用默认配置', SERVERS_FILE)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning('加载 %s 失败: %s，使用默认配置（原文件未改动）', SERVERS_FILE, e)
    return build_default_server()


def save_servers_to_file():
    """将当前服务器列表持久化到文件"""
    with servers_lock:
        snapshot = list(SERVERS)
    try:
        with open(SERVERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error('保存服务器列表失败: %s', e)


SERVERS = load_servers_from_file()


def generate_server_id():
    with servers_lock:
        return generate_unique_id({s['id'] for s in SERVERS})


def parse_port(value, default=22):
    """解析端口号，无效时返回None，缺省时返回default"""
    if value in (None, ''):
        return default
    try:
        port = int(value)
    except (TypeError, ValueError):
        return None
    return port if 1 <= port <= 65535 else None


# ─── AI模型配置存储（内存 + JSON文件持久化）──────────────────────────────────
MODELS_FILE = 'models.json'
models_lock = threading.Lock()
MODEL_PARSERS = {}


def build_default_models():
    """models.json 不存在时，用.env中的DeepSeek配置初始化（仅首次）"""
    api_key = (os.getenv('DEEPSEEK_API_KEY') or '').strip()
    if not api_key:
        return []
    return [{
        'id': 'deepseek-default',
        'name': 'DeepSeek',
        'base_url': (os.getenv('DEEPSEEK_API_URL') or 'https://api.deepseek.com/v1').rstrip('/'),
        'api_key': api_key,
        'model': 'deepseek-chat',
        'is_default': True
    }]


def load_models_from_file():
    if not os.path.exists(MODELS_FILE):
        default = build_default_models()
        save_models_to_file(default)
        return default

    try:
        with open(MODELS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        logger.warning('%s 内容不是列表，已忽略', MODELS_FILE)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning('加载 %s 失败: %s（原文件未改动）', MODELS_FILE, e)
    return []


def save_models_to_file(models=None):
    if models is None:
        with models_lock:
            models = list(MODELS)
    try:
        with open(MODELS_FILE, 'w', encoding='utf-8') as f:
            json.dump(models, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error('保存模型配置失败: %s', e)


MODELS = load_models_from_file()


def public_model_view(m):
    """对外输出模型配置（隐藏API密钥）"""
    key = m.get('api_key', '')
    masked = (key[:3] + '***' + key[-4:]) if len(key) > 8 else ('***' if key else '')
    return {
        'id': m['id'],
        'name': m['name'],
        'base_url': m['base_url'],
        'model': m['model'],
        'is_default': bool(m.get('is_default')),
        'api_key_masked': masked
    }


def find_model_by_id(model_id):
    with models_lock:
        return next((m for m in MODELS if m['id'] == model_id), None)


def find_default_model():
    """返回默认模型；无默认标记时取第一个；无任何模型返回None"""
    with models_lock:
        if not MODELS:
            return None
        return next((m for m in MODELS if m.get('is_default')), MODELS[0])


def get_model_parser(config):
    """按模型配置获取解析器（缓存Session复用连接）"""
    parser = MODEL_PARSERS.get(config['id'])
    if parser is None:
        parser = AICommandParser(config['base_url'], config.get('api_key', ''),
                                 config['model'])
        MODEL_PARSERS[config['id']] = parser
    return parser


# ─── SSH 会话管理 ─────────────────────────────────────────────────────────────

def cleanup_session(sid):
    """清理会话资源（幂等，可安全重复调用）"""
    with sessions_lock:
        sess = sessions.pop(sid, None)
    if sess is None:
        return
    with taps_lock:
        taps.pop(sid, None)
    cleanup_context(sid)
    try:
        if sess.get('chan'):
            sess['chan'].close()
        if sess.get('ssh'):
            sess['ssh'].close()
    except Exception as e:
        logger.warning('关闭会话 %s 资源时出错: %s', sid, e)
    logger.info('清理会话: %s', sid)


def ssh_read_thread(sid, chan):
    """后台线程：持续读取SSH输出并通过WebSocket推送到前端

    上下文跟踪（tap）失败绝不影响终端数据流；只有SSH通道本身
    结束/出错才清理会话。
    """
    tap = get_tap(sid, create=True)
    try:
        while True:
            try:
                data = chan.recv(BUF_SIZE)
            except socket.timeout:
                if chan.closed:
                    break
                continue
            if not data:
                break
            text = data.decode('utf-8', errors='replace')
            if tap:
                tap.on_output(text)
            socketio.emit('terminal_output', {'data': text}, to=sid)
    except Exception as e:
        logger.info('读取线程结束 %s: %s', sid, e)
    finally:
        socketio.emit('terminal_disconnect', {'reason': 'SSH连接已断开'}, to=sid)
        cleanup_session(sid)


# ─── WebSocket 事件 ───────────────────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    logger.info('客户端连接: %s', request.sid)
    emit('connected', {'sid': request.sid})


@socketio.on('disconnect')
def on_disconnect():
    logger.info('客户端断开: %s', request.sid)
    cleanup_session(request.sid)


@socketio.on('ssh_connect')
def on_ssh_connect(data):
    """建立SSH连接"""
    sid = request.sid
    host = (data.get('host') or '').strip()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    port = parse_port(data.get('port'))

    if port is None:
        emit('ssh_connected', {'success': False, 'message': '端口号无效'})
        return

    # 如果是已保存服务器且密码为空，从列表中取密码
    server_id = data.get('serverId') or ''
    if server_id or not password:
        with servers_lock:
            for s in SERVERS:
                if s['id'] == server_id or (s['host'] == host and s['username'] == username):
                    password = s['password']
                    break

    cols = int(data.get('cols', 220) or 220)
    rows = int(data.get('rows', 50) or 50)

    logger.info('连接请求: %s@%s:%s (sid=%s)', username, host, port, sid)

    if not host or not username:
        emit('ssh_connected', {'success': False, 'message': '主机地址和用户名不能为空'})
        return

    cleanup_session(sid)

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=host, port=port, username=username,
                       password=password, timeout=15)
        client.get_transport().set_keepalive(SSH_KEEPALIVE_SECONDS)

        # 创建交互式shell，使用xterm终端类型（支持完整ANSI）
        chan = client.invoke_shell(term='xterm-256color', width=cols, height=rows)
        chan.settimeout(1.0)

        t = threading.Thread(target=ssh_read_thread, args=(sid, chan), daemon=True)
        with sessions_lock:
            sessions[sid] = {'ssh': client, 'chan': chan, 'thread': t}
        t.start()

        emit('ssh_connected', {
            'success': True,
            'message': f'已连接到 {username}@{host}:{port}'
        })
        logger.info('连接成功: %s@%s:%s', username, host, port)

    except Exception as e:
        logger.warning('连接失败 %s@%s:%s: %s', username, host, port, e)
        emit('ssh_connected', {'success': False, 'message': f'连接失败: {e}'})


@socketio.on('terminal_input')
def on_terminal_input(data):
    """接收前端键盘输入，转发到SSH"""
    sid = request.sid
    with sessions_lock:
        sess = sessions.get(sid)
    if not sess:
        return

    chan = sess.get('chan')
    if chan and not chan.closed:
        try:
            text = data.get('data', '')
            tap = get_tap(sid, create=True)
            if tap:
                tap.on_input(text)
            chan.send(text)
        except Exception as e:
            logger.warning('发送输入失败 %s: %s', sid, e)


@socketio.on('terminal_resize')
def on_terminal_resize(data):
    """处理终端尺寸变化"""
    sid = request.sid
    with sessions_lock:
        sess = sessions.get(sid)
    if not sess:
        return

    chan = sess.get('chan')
    if chan and not chan.closed:
        try:
            cols = int(data.get('cols', 220) or 220)
            rows = int(data.get('rows', 50) or 50)
            chan.resize_pty(width=cols, height=rows)
        except Exception as e:
            logger.warning('调整终端尺寸失败 %s: %s', sid, e)


@socketio.on('ssh_disconnect')
def on_ssh_disconnect():
    """主动断开SSH连接"""
    cleanup_session(request.sid)
    emit('terminal_disconnect', {'reason': '已主动断开连接'})


# ─── REST API：服务器 ─────────────────────────────────────────────────────────

@app.route('/api/servers', methods=['GET'])
def get_servers():
    """获取服务器列表（隐藏密码）"""
    with servers_lock:
        servers = [{k: v for k, v in s.items() if k != 'password'} for s in SERVERS]
    return jsonify({'servers': servers})


@app.route('/api/servers', methods=['POST'])
def add_server():
    """添加服务器"""
    data = request.get_json(silent=True) or {}
    host = (data.get('host') or '').strip()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    port = parse_port(data.get('port'))
    name = (data.get('name') or '').strip() or host
    description = (data.get('description') or '').strip()

    if not host or not username:
        return jsonify({'success': False, 'message': '主机和用户名不能为空'}), 400
    if port is None:
        return jsonify({'success': False, 'message': '端口号无效'}), 400

    server = {
        'id': generate_server_id(),
        'name': name,
        'host': host,
        'username': username,
        'password': password,
        'port': port,
        'description': description
    }

    with servers_lock:
        if any(s['host'] == host and s['username'] == username for s in SERVERS):
            return jsonify({'success': False, 'message': '该服务器已存在'}), 409
        SERVERS.append(server)

    save_servers_to_file()
    return jsonify({'success': True,
                    'server': {k: v for k, v in server.items() if k != 'password'}})


@app.route('/api/servers/<server_id>', methods=['DELETE'])
def delete_server(server_id):
    """删除服务器"""
    with servers_lock:
        original_len = len(SERVERS)
        SERVERS[:] = [s for s in SERVERS if s['id'] != server_id]
        deleted = len(SERVERS) < original_len

    if not deleted:
        return jsonify({'success': False, 'message': '服务器不存在'}), 404

    save_servers_to_file()
    return jsonify({'success': True})


# ─── REST API：AI模型 ─────────────────────────────────────────────────────────

@app.route('/api/models', methods=['GET'])
def get_models():
    """获取模型配置列表（隐藏API密钥）"""
    with models_lock:
        models = [public_model_view(m) for m in MODELS]
    return jsonify({'models': models})


@app.route('/api/models', methods=['POST'])
def add_model():
    """添加模型配置"""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    base_url = (data.get('base_url') or '').strip().rstrip('/')
    api_key = (data.get('api_key') or '').strip()
    model = (data.get('model') or '').strip()

    if not name or not base_url or not model:
        return jsonify({'success': False, 'message': '名称、API地址、模型ID不能为空'}), 400
    if not base_url.startswith(('http://', 'https://')):
        return jsonify({'success': False, 'message': 'API地址必须以 http:// 或 https:// 开头'}), 400

    with models_lock:
        if any(m['base_url'] == base_url and m['model'] == model for m in MODELS):
            return jsonify({'success': False, 'message': '该模型已存在（相同API地址和模型ID）'}), 409
        is_default = not MODELS or bool(data.get('is_default'))
        if is_default:
            for m in MODELS:
                m['is_default'] = False
        entry = {
            'id': generate_unique_id({m['id'] for m in MODELS}),
            'name': name,
            'base_url': base_url,
            'api_key': api_key,
            'model': model,
            'is_default': is_default
        }
        MODELS.append(entry)
        view = public_model_view(entry)

    save_models_to_file()
    return jsonify({'success': True, 'model': view})


@app.route('/api/models/<model_id>', methods=['DELETE'])
def delete_model(model_id):
    """删除模型配置；删除默认模型后自动将第一个设为默认"""
    with models_lock:
        target = next((m for m in MODELS if m['id'] == model_id), None)
        if target is None:
            return jsonify({'success': False, 'message': '模型不存在'}), 404
        was_default = target.get('is_default')
        MODELS[:] = [m for m in MODELS if m['id'] != model_id]
        if was_default and MODELS:
            MODELS[0]['is_default'] = True

    MODEL_PARSERS.pop(model_id, None)
    save_models_to_file()
    return jsonify({'success': True})


@app.route('/api/models/<model_id>/default', methods=['POST'])
def set_default_model(model_id):
    """将指定模型设为默认"""
    with models_lock:
        target = next((m for m in MODELS if m['id'] == model_id), None)
        if target is None:
            return jsonify({'success': False, 'message': '模型不存在'}), 404
        for m in MODELS:
            m['is_default'] = (m['id'] == model_id)

    save_models_to_file()
    return jsonify({'success': True})


@app.route('/api/models/probe', methods=['POST'])
def probe_models():
    """读取OpenAI兼容服务端的可用模型列表（用于添加模型时识别可选模型）"""
    data = request.get_json(silent=True) or {}
    base_url = (data.get('base_url') or '').strip().rstrip('/')
    api_key = (data.get('api_key') or '').strip()

    if not base_url.startswith(('http://', 'https://')):
        return jsonify({'success': False, 'message': 'API地址必须以 http:// 或 https:// 开头'}), 400

    try:
        models = fetch_available_models(base_url, api_key)
        return jsonify({'success': True, 'models': models})
    except requests.RequestException as e:
        return jsonify({'success': False, 'message': f'连接失败: {e}'}), 502
    except (ValueError, KeyError) as e:
        return jsonify({'success': False, 'message': f'响应解析失败: {e}'}), 502


@app.route('/api/models/test', methods=['POST'])
def test_model_endpoint():
    """测试模型连通性：传 id 测试已保存模型，或传 base_url/api_key/model 测试未保存配置"""
    data = request.get_json(silent=True) or {}

    if data.get('id'):
        config = find_model_by_id(data['id'])
        if config is None:
            return jsonify({'success': False, 'message': '模型不存在'}), 404
        ok, message = test_model(config['base_url'], config.get('api_key', ''),
                                 config['model'])
        return jsonify({'success': ok, 'message': message})

    base_url = (data.get('base_url') or '').strip().rstrip('/')
    model = (data.get('model') or '').strip()
    if not base_url or not model:
        return jsonify({'success': False, 'message': 'API地址和模型ID不能为空'}), 400

    ok, message = test_model(base_url, (data.get('api_key') or '').strip(), model)
    return jsonify({'success': ok, 'message': message})


# ─── REST API：AI对话 ─────────────────────────────────────────────────────────

@app.route('/api/chat', methods=['POST'])
def chat():
    """AI自然语言解析，返回命令（不执行，由前端确认后通过WebSocket发送）"""
    data = request.get_json(silent=True) or {}
    user_input = (data.get('message') or '').strip()
    model_id = (data.get('model_id') or '').strip() or None
    sid = (data.get('sid') or '').strip() or None

    if not user_input:
        return jsonify({'success': False, 'message': '请输入内容'}), 400

    ctx = get_session_context(sid, create=True) if sid else None
    history = list(ctx.get('ai_history', [])) if ctx else []
    context_block = build_context_block(ctx) if ctx else None

    if model_id:
        config = find_model_by_id(model_id)
        if config is None:
            return jsonify({'success': False, 'message': '所选模型不存在，可能已被删除'}), 404
    else:
        config = find_default_model()

    if config is None:
        parsed = match_local_intent(user_input)
        if not parsed:
            return jsonify({'success': False,
                            'message': '尚未配置AI模型，请点击AI助手右上角按钮添加；'
                                       '或使用常见指令（资源/磁盘/内存/进程/网络）'}), 400
    else:
        parser = get_model_parser(config)
        parsed = parser.parse_natural_language(user_input, history=history,
                                               context=context_block)

    command = parsed.get('command', '')
    description = parsed.get('description', '')
    dangerous = parsed.get('dangerous', False)

    # 记录对话历史（用户输入 + AI给出的命令/说明），供后续多轮解析；
    # 请求失败(error标记)不记录，避免污染后续对话上下文
    if ctx is not None and not parsed.get('error'):
        assistant_summary = command if command else (description or '无法解析')
        record_ai_round(sid, user_input, assistant_summary)

    if not command:
        return jsonify({'success': False, 'message': description or '无法解析该指令'})

    if dangerous:
        return jsonify({
            'success': False,
            'message': f'⚠️ 危险命令: {description}',
            'parsed_command': command,
            'dangerous': True
        })

    resp = {
        'success': True,
        'parsed_command': command,
        'description': description,
        'dangerous': False
    }
    if config is not None:
        resp['model_name'] = config['name']
    return jsonify(resp)


@app.route('/')
def index():
    return send_from_directory(app.root_path, 'index.html')


if __name__ == '__main__':
    logger.info('WebSSH 启动中...')
    logger.info('访问: http://localhost:5000')
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
