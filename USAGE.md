# 使用指南

## 启动步骤

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量（首次使用）
copy .env.example .env
# 编辑 .env 填入 DeepSeek API Key 和默认 SSH 信息

# 3. 启动服务
python app.py

# 4. 浏览器访问
# http://localhost:5000
```

## 使用示例

### 1. 建立连接

- **已保存服务器**: 点击左侧列表中的服务器直接连接
- **新建连接**: 点击右上角"新建连接"，填写主机/端口/用户名/密码，可勾选"保存到服务器列表"
- **断开连接**: 点击顶部"断开"按钮

### 2. 终端操作

中间区域是完整的 xterm.js 交互终端，支持：

- 直接键入 Linux 命令执行
- `↑` / `↓` 浏览命令历史（由远端 shell 提供）
- `Tab` 命令补全、`Ctrl+C` 中断等（由远端 shell 提供）
- ANSI 256 色完整渲染
- 鼠标选中内容后点击"复制选中"

### 3. 自然语言命令

连接成功后，在右侧 AI 助手输入框用自然语言描述操作：

- **系统资源**: "查看资源水位"、"显示系统负载"
- **文件和目录**: "查看/opt目录"、"列出/var/log下的文件"
- **系统信息**: "显示磁盘使用情况"、"查看内存使用"
- **进程管理**: "列出所有进程"、"查看CPU占用最高的进程"
- **网络**: "查看网络连接"、"显示监听端口"

AI 助手具备**会话上下文**能力：

- **多轮对话**：连续追问时理解指代，如先问"查看 /var/log"，再问"按大小排序"
- **终端感知**：自动跟踪当前目录（cd 后生效）和最近几条命令的输出，"刚才那个文件多大"这类问题能正确解析
- **命令确认**：解析结果以卡片形式展示，可先编辑再执行，也可直接取消

常见意图（资源/磁盘/内存/进程/网络）在本地直接匹配，无需等待 AI 响应；
其余请求由所选模型解析后转换为命令，点击"执行"后才在终端运行。

### 4. 快捷操作按钮

点击右侧的快捷按钮一键执行：检查系统资源、磁盘使用情况、查看运行进程、查看系统日志。

## 模型管理

点击 AI 助手右上角的调节按钮打开"模型管理"，支持添加任意 OpenAI 兼容的模型服务
（DeepSeek、Kimi、通义千问、本地 Ollama / LM Studio 等）。

### 添加模型

1. 填写名称、API 地址（如 `https://api.deepseek.com/v1`）、API Key（本地服务可留空）
2. 点击 **读取模型列表**，系统会从服务的 `/models` 端点拉取可用模型，从下拉框选择
   （拉取失败也可手动填写模型 ID）
3. 点击 **测试连接** 验证配置可用
4. 点击 **添加** 保存；第一个添加的模型自动成为默认

### 切换模型

- AI 助手头部的下拉框可快速切换当前使用的模型
- 模型列表中的星标按钮可将其设为默认（页面刷新后仍生效）

### 配置存储

模型配置保存在 `models.json`（含 API Key，请勿提交到版本库）。
`.env` 中的 DeepSeek 配置仅在 `models.json` 不存在时用于初始化默认模型。

## 界面说明

| 区域 | 说明 |
|------|------|
| 左侧边栏 | 已保存的服务器列表（点击连接，悬停可删除） |
| 中间区域 | xterm.js 交互终端，工具栏含清屏/复制按钮 |
| 右侧边栏 | AI 助手对话、快捷操作按钮 |
| 顶部状态栏 | 连接状态（绿点已连接/红点未连接）、断开按钮 |
| 底部状态栏 | 当前连接的 user@host |

## 配置说明

### .env 文件

```env
# DeepSeek AI配置（仅首次启动时初始化 models.json，之后通过界面管理）
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_API_URL=https://api.deepseek.com/v1

# 默认SSH连接配置（仅在 servers.json 不存在时用于初始化）
SSH_HOST=127.0.0.1
SSH_USER=root
SSH_PASSWORD=
SSH_PORT=22
```

### servers.json

通过界面添加的服务器持久化保存在 `servers.json`，可手动编辑（JSON 数组格式）。
重复的 host + username 会被拒绝添加。

## 故障排除

### 1. 连接失败

- 检查服务器地址、端口、用户名、密码
- 确认服务器 SSH 服务正在运行
- 检查防火墙设置

### 2. AI解析失败

- 检查 `.env` 中 API 密钥是否有效、额度是否充足
- 检查本机到 `api.deepseek.com` 的网络连接
- 查看后端日志输出

### 3. 端口被占用

修改 `app.py` 末尾的启动端口：

```python
socketio.run(app, host='0.0.0.0', port=8080, debug=False, allow_unsafe_werkzeug=True)
```

### 4. 依赖安装失败

```bash
# 升级pip
python -m pip install --upgrade pip

# 使用国内镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 高级功能

### 添加本地快捷意图

编辑 `ai_parser.py` 中的 `LOCAL_INTENTS` 列表（正则 + 命令 + 说明），
匹配到的输入不会调用 AI，直接返回预设命令。

### 修改AI提示词

编辑 `ai_parser.py` 中的 `SYSTEM_PROMPT`。

### 添加新的API接口

在 `app.py` 中添加新路由：

```python
@app.route('/api/your-endpoint', methods=['POST'])
def your_function():
    return jsonify({'success': True})
```
