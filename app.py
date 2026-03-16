import os
import json
import threading
import paramiko

from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from ai_parser import AICommandParser
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['SECRET_KEY'] = 'webssh-secret'
CORS(app, origins='*')
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading', ping_timeout=60)

ai_parser = AICommandParser(
    api_key=os.getenv('DEEPSEEK_API_KEY'),
    api_url=os.getenv('DEEPSEEK_API_URL')
)

sessions = {}
BUF_SIZE = 1024 * 32

# ─── 服务器存储（内存 + JSON文件持久化）──────────────────────────────────────
SERVERS_FILE = 'servers.json'

def load_servers_from_file():
    """从文件加载服务器列表，不存在则用.env默认值初始化"""
    if os.path.exists(SERVERS_FILE):
        try:
            with open(SERVERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    # 默认服务器（来自.env）
    default = []
    if os.getenv('SSH_HOST'):
        default.append({
            'id': 'prod-01',
            'name': 'production-01',
            'host': os.getenv('SSH_HOST', ''),
            'username': os.getenv('SSH_USER', ''),
            'password': os.getenv('SSH_PASSWORD', ''),
            'port': int(os.getenv('SSH_PORT', 22)),
            'description': 'Production Server'
        })
    save_servers_to_file(default)
    return default

def save_servers_to_file(servers):
    try:
        with open(SERVERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(servers, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'[ERROR] 保存服务器列表失败: {e}')

# 启动时加载
SERVERS = load_servers_from_file()


def ssh_read_thread(sid, chan):
    """后台线程：持续读取SSH输出并通过WebSocket推送到前端"""
    try:
        while True:
            if chan.closed:
                break
            if chan.recv_ready():
                data = chan.recv(BUF_SIZE)
                if not data:
                    break
                socketio.emit('terminal_output', {'data': data.decode('utf-8', errors='replace')}, to=sid)
            else:
                import time
                time.sleep(0.01)
    except Exception as e:
        print(f'[SSH] 读取线程异常 {sid}: {e}')
    finally:
        socketio.emit('terminal_disconnect', {'reason': 'SSH连接已断开'}, to=sid)
        cleanup_session(sid)


def cleanup_session(sid):
    """清理会话资源"""
    if sid in sessions:
        sess = sessions.pop(sid)
        try:
            if sess.get('chan'):
                sess['chan'].close()
            if sess.get('ssh'):
                sess['ssh'].close()
        except:
            pass
        print(f'[SESSION] 清理会话: {sid}')


# ─── WebSocket 事件 ───────────────────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    print(f'[WS] 客户端连接: {request.sid}')
    emit('connected', {'sid': request.sid})


@socketio.on('disconnect')
def on_disconnect():
    print(f'[WS] 客户端断开: {request.sid}')
    cleanup_session(request.sid)


@socketio.on('ssh_connect')
def on_ssh_connect(data):
    """建立SSH连接"""
    sid = request.sid
    host = data.get('host', '')
    username = data.get('username', '')
    password = data.get('password', '')
    port = int(data.get('port', 22))

    # 如果是已保存服务器且密码为空，从列表中取密码
    server_id = data.get('serverId', '')
    if server_id or not password:
        for s in SERVERS:
            if s['id'] == server_id or (s['host'] == host and s['username'] == username):
                password = s['password']
                break
    cols = int(data.get('cols', 220))
    rows = int(data.get('rows', 50))

    print(f'[SSH] 连接请求: {username}@{host}:{port} (sid={sid})')

    # 如果已有连接，先清理
    if sid in sessions:
        cleanup_session(sid)

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=host, port=port, username=username,
                       password=password, timeout=15)

        # 创建交互式shell，使用xterm终端类型（支持完整ANSI）
        chan = client.invoke_shell(term='xterm-256color', width=cols, height=rows)
        chan.settimeout(0)

        sessions[sid] = {'ssh': client, 'chan': chan}

        # 启动读取线程
        t = threading.Thread(target=ssh_read_thread, args=(sid, chan), daemon=True)
        t.start()
        sessions[sid]['thread'] = t

        emit('ssh_connected', {
            'success': True,
            'message': f'已连接到 {username}@{host}:{port}'
        })
        print(f'[SSH] 连接成功: {username}@{host}:{port}')

    except Exception as e:
        print(f'[SSH] 连接失败: {e}')
        emit('ssh_connected', {'success': False, 'message': f'连接失败: {str(e)}'})


@socketio.on('terminal_input')
def on_terminal_input(data):
    """接收前端键盘输入，转发到SSH"""
    sid = request.sid
    if sid not in sessions:
        return

    chan = sessions[sid].get('chan')
    if chan and not chan.closed:
        try:
            text = data.get('data', '')
            chan.send(text)
        except Exception as e:
            print(f'[SSH] 发送输入失败: {e}')


@socketio.on('terminal_resize')
def on_terminal_resize(data):
    """处理终端尺寸变化"""
    sid = request.sid
    if sid not in sessions:
        return

    chan = sessions[sid].get('chan')
    if chan and not chan.closed:
        try:
            cols = int(data.get('cols', 220))
            rows = int(data.get('rows', 50))
            chan.resize_pty(width=cols, height=rows)
        except Exception as e:
            print(f'[SSH] 调整终端尺寸失败: {e}')


@socketio.on('ssh_disconnect')
def on_ssh_disconnect():
    """主动断开SSH连接"""
    cleanup_session(request.sid)
    emit('terminal_disconnect', {'reason': '已主动断开连接'})


# ─── REST API ─────────────────────────────────────────────────────────────────

@app.route('/api/servers', methods=['GET'])
def get_servers():
    """获取服务器列表（隐藏密码）"""
    return jsonify({'servers': [
        {k: v for k, v in s.items() if k != 'password'}
        for s in SERVERS
    ]})


@app.route('/api/servers', methods=['POST'])
def add_server():
    """添加服务器"""
    data = request.get_json(silent=True) or {}
    host = data.get('host', '').strip()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    port = int(data.get('port', 22))
    name = data.get('name', '').strip() or host
    description = data.get('description', '').strip()

    if not host or not username:
        return jsonify({'success': False, 'message': '主机和用户名不能为空'}), 400

    # 生成唯一ID
    import uuid
    new_id = str(uuid.uuid4())[:8]

    server = {
        'id': new_id,
        'name': name,
        'host': host,
        'username': username,
        'password': password,
        'port': port,
        'description': description
    }
    SERVERS.append(server)
    save_servers_to_file(SERVERS)

    return jsonify({'success': True, 'server': {k: v for k, v in server.items() if k != 'password'}})


@app.route('/api/servers/<server_id>', methods=['DELETE'])
def delete_server(server_id):
    """删除服务器"""
    global SERVERS
    original_len = len(SERVERS)
    SERVERS = [s for s in SERVERS if s['id'] != server_id]

    if len(SERVERS) == original_len:
        return jsonify({'success': False, 'message': '服务器不存在'}), 404

    save_servers_to_file(SERVERS)
    return jsonify({'success': True})


@app.route('/api/chat', methods=['POST'])
def chat():
    """AI自然语言解析，返回命令（不执行，由前端通过WebSocket发送）"""
    try:
        data = request.get_json(silent=True) or {}
        user_input = data.get('message', '').strip()

        if not user_input:
            return jsonify({'success': False, 'message': '请输入内容'}), 400

        parsed = ai_parser.parse_natural_language(user_input)
        command = parsed.get('command', '')
        description = parsed.get('description', '')
        dangerous = parsed.get('dangerous', False)

        if not command:
            return jsonify({'success': False, 'message': description or '无法解析该指令'})

        if dangerous:
            return jsonify({
                'success': False,
                'message': f'⚠️ 危险命令: {description}',
                'parsed_command': command,
                'dangerous': True
            })

        return jsonify({
            'success': True,
            'parsed_command': command,
            'description': description,
            'dangerous': False
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'解析失败: {str(e)}'}), 500


@app.route('/')
def index():
    with open('index.html', 'r', encoding='utf-8') as f:
        return f.read()


if __name__ == '__main__':
    print('🚀 WebSSH 启动中...')
    print('📡 访问: http://localhost:5000')
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
