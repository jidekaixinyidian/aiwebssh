# WebSSH - 智能运维终端

基于 Web 的 SSH 终端，集成 AI 自然语言命令解析，支持任意 OpenAI 兼容模型服务（DeepSeek / Kimi / Qwen / 本地 Ollama 等）。

## 功能特性

- 完整交互式终端（xterm.js + Paramiko PTY，支持 vim/top 等交互程序）
- 多服务器管理，一键连接/切换（servers.json 持久化）
- 多 AI 模型管理：添加任意 OpenAI 兼容服务、在线读取可用模型列表、测试连通性、快速切换
- 会话上下文：多轮对话、终端 cwd 与最近命令输出感知
- 命令确认卡片：AI 建议的命令可编辑/取消后再执行
- 自然语言命令解析（本地意图快路径 + AI 解析）
- 危险命令识别与拦截
- SSH keepalive 保持长连接

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
copy .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY（必需）和默认 SSH 信息（可选）

# 3. 启动
python app.py
```

浏览器访问 http://localhost:5000

## 使用说明

1. 点击左侧已保存的服务器，或点击"新建连接"填写主机/端口/用户名/密码
2. 在中间终端区域直接操作，与真实终端一致
3. 在右侧 AI 助手用自然语言描述操作，如：
   - "查看资源水位"
   - "查看/opt目录"
   - "显示磁盘使用情况"
   - "列出进程"
4. 命令解析结果会显示在 AI 对话中，并自动在终端执行

## 界面说明

- **左侧边栏**: 保存的服务器列表，点击连接，悬停可删除
- **中间区域**: 交互终端，工具栏含清屏/复制按钮
- **右侧边栏**: AI 助手对话、快捷操作按钮

## API 接口

### REST

- `GET /` - 前端页面
- `GET /api/servers` - 服务器列表（隐藏密码）
- `POST /api/servers` - 添加服务器
- `DELETE /api/servers/<id>` - 删除服务器
- `GET /api/models` - AI模型配置列表（隐藏密钥）
- `POST /api/models` - 添加模型配置
- `DELETE /api/models/<id>` - 删除模型配置
- `POST /api/models/<id>/default` - 设为默认模型
- `POST /api/models/probe` - 读取指定服务的可用模型列表
- `POST /api/models/test` - 测试模型连通性（传 id 或完整配置）
- `POST /api/chat` - AI自然语言解析（只解析不执行，可指定 model_id）

### WebSocket (Socket.IO)

- `ssh_connect` / `ssh_connected` - 建立 SSH 连接
- `terminal_input` / `terminal_output` - 终端输入输出流
- `terminal_resize` - 终端尺寸同步
- `ssh_disconnect` / `terminal_disconnect` - 断开连接

## 技术栈

- **后端**: Flask + flask-socketio + Paramiko
- **前端**: HTML5 + TailwindCSS + xterm.js + Socket.IO
- **AI**: DeepSeek Chat API

## 项目结构

```
.
├── app.py                 # Flask + Socket.IO 后端
├── ai_parser.py           # AI命令解析（本地快路径 + OpenAI兼容API）
├── index.html             # 前端页面
├── static/app.js          # 前端逻辑
├── servers.json           # 保存的服务器列表（运行时生成，含密码勿提交）
├── models.json            # 保存的AI模型配置（运行时生成，含密钥勿提交）
├── .env                   # 环境配置（不入库，仅用于首次初始化）
├── requirements.txt       # Python依赖
├── README.md              # 本文档
├── USAGE.md               # 使用指南
└── TERMINAL_FEATURES.md   # 终端功能与架构说明
```

## 常见问题

### 1. 连接失败？

- 检查服务器地址、端口、用户名、密码
- 确认服务器 SSH 服务运行中、防火墙放行

### 2. AI解析失败？

- 在"模型管理"中点击"测试连接"检查模型配置
- 确认 API Key 有效且有额度
- 常见意图（资源/磁盘/内存/进程/网络）无需 AI 即可解析

### 3. 端口被占用？

修改 `app.py` 末尾：

```python
socketio.run(app, host='0.0.0.0', port=8080, debug=False, allow_unsafe_werkzeug=True)
```

## 开发说明

1. **添加本地快捷意图**: 修改 `ai_parser.py` 中的 `LOCAL_INTENTS`
2. **调整AI解析逻辑**: 修改 `ai_parser.py` 中的 `SYSTEM_PROMPT`
3. **修改前端样式**: 编辑 `index.html` 中的 TailwindCSS 类
4. **添加API接口**: 在 `app.py` 中添加路由

详细使用方法见 [USAGE.md](USAGE.md)，架构说明见 [TERMINAL_FEATURES.md](TERMINAL_FEATURES.md)。

## 许可证

MIT License
