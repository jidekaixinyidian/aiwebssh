# 智能运维助手

基于AI的智能运维助手，支持自然语言控制远程服务器。

## 功能特性

✅ SSH远程连接管理  
✅ 自然语言命令解析（基于DeepSeek AI）  
✅ 现代化Web终端界面  
✅ AI助手实时对话  
✅ 快捷命令按钮  
✅ 实时连接状态显示  
✅ 危险命令自动识别和拦截  
✅ 命令执行结果实时展示  

## 快速开始

### 方法一：使用启动脚本（推荐）

双击运行 `start.bat` 文件，脚本会自动：
1. 检查Python环境
2. 安装所需依赖
3. 启动后端服务
4. 自动打开浏览器访问 http://localhost:5000

### 方法二：手动启动

#### 1. 安装依赖

```bash
pip install -r requirements.txt
```

#### 2. 配置环境变量

编辑 `.env` 文件，配置SSH连接信息和API密钥

```env
DEEPSEEK_API_KEY=
DEEPSEEK_API_URL=https://api.deepseek.com/v1
SSH_HOST=127.0.0.1
SSH_USER=123
SSH_PASSWORD=123
SSH_PORT=22
```

#### 3. 启动后端服务

```bash
python app.py
```

服务将在 http://localhost:5000 启动，浏览器会自动打开界面

## 使用说明

1. 打开浏览器访问 http://localhost:5000
2. 系统会自动连接到配置的SSH服务器
3. 在右侧AI助手输入框中使用自然语言输入命令，例如：
   - "查看资源水位"
   - "查看/opt目录"
   - "显示磁盘使用情况"
   - "查看内存使用"
   - "列出进程"
4. 或点击快捷操作按钮快速执行常用操作
5. 命令执行结果会实时显示在中间的终端区域

## 界面说明

- **左侧边栏**: 保存的连接和最近会话
- **中间区域**: 终端命令执行和输出显示
- **右侧边栏**: AI助手对话界面
  - 输入自然语言命令
  - 查看AI建议的命令
  - 快捷操作按钮

## 安全特性

- 自动识别危险命令（rm -rf、格式化等）
- 危险命令自动拦截，不会执行
- 实时显示将要执行的具体命令
- AI会在执行前说明命令的作用

## API接口

后端提供以下REST API接口：

- `GET /` - 前端页面
- `POST /api/connect` - 建立SSH连接
- `POST /api/disconnect` - 断开连接
- `GET /api/status` - 获取连接状态
- `POST /api/chat` - 自然语言命令处理
- `POST /api/execute` - 直接执行命令
- `GET /api/quick-commands` - 获取快捷命令列表

## 技术栈

- **后端**: Flask + Paramiko + OpenAI SDK
- **前端**: HTML5 + TailwindCSS + Vanilla JavaScript
- **AI**: DeepSeek Chat API
- **SSH**: Paramiko (Python SSH库)

## 项目结构

```
.
├── app.py                 # Flask后端主程序
├── ssh_manager.py         # SSH连接管理模块
├── ai_parser.py          # AI命令解析模块
├── .env                  # 环境配置文件
├── requirements.txt      # Python依赖
├── start.bat            # Windows启动脚本
├── .vscode/
│   ├── index.html       # 前端界面
│   └── app.js          # 前端JavaScript逻辑
└── README.md           # 项目文档
```

## 常见问题

### 1. 连接失败怎么办？

检查 `.env` 文件中的SSH配置是否正确：
- 服务器地址是否可访问
- 用户名和密码是否正确
- 端口号是否正确（默认22）

### 2. AI解析失败？

确保 `.env` 中的DeepSeek API密钥有效且有足够的额度

### 3. 端口被占用？

修改 `app.py` 中的端口号：
```python
app.run(host='0.0.0.0', port=5000, debug=True)  # 改为其他端口
```

## 开发说明

如需修改或扩展功能：

1. **添加新的快捷命令**: 修改 `app.py` 中的 `QUICK_COMMANDS` 字典
2. **调整AI解析逻辑**: 修改 `ai_parser.py` 中的 `parse_natural_language` 方法
3. **修改前端样式**: 编辑 `.vscode/index.html` 中的TailwindCSS类
4. **添加新的API接口**: 在 `app.py` 中添加新的路由

## 许可证

MIT License
