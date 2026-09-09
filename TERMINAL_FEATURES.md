# 终端功能说明

## 架构

前端使用 xterm.js 渲染终端，键盘输入通过 Socket.IO (WebSocket) 转发到后端；
后端用 Paramiko 建立真正的交互式 SSH shell（`invoke_shell`），输出实时推送回浏览器。
终端状态（历史、补全、颜色）全部由远端 shell 提供，前端不做任何模拟。

```
浏览器 (xterm.js) ⇄ Socket.IO ⇄ Flask (flask-socketio) ⇄ Paramiko Channel ⇄ SSH服务器
```

## 已实现的功能

### 1. 完整交互终端
- 直接键入命令执行，支持 shell 提供的 `↑↓` 历史、`Tab` 补全、`Ctrl+C` 等
- `xterm-256color` 终端类型，完整 ANSI 转义序列渲染
- 终端尺寸变化时自动同步 PTY（`resize_pty`）

### 2. 服务器管理
- 多服务器保存（`servers.json` 持久化），一键连接/切换
- 新建连接可临时使用或保存，重复 host + username 会去重

### 3. AI自然语言控制
- 右侧输入自然语言，转换为 Linux 命令在终端执行
- 常见意图（资源/磁盘/内存/进程/网络）本地正则快路径，零延迟零API消耗
- 其余由 DeepSeek（JSON mode）解析

### 4. 安全特性
- 危险命令识别（rm -rf、mkfs 等），识别后拦截不执行
- 实时连接状态显示

### 5. 连接稳定性
- SSH keepalive（30秒间隔），防止 NAT 空闲断连
- 会话资源（channel/client/线程）在断开或页面关闭时自动清理

## WebSocket 事件

| 方向 | 事件 | 说明 |
|------|------|------|
| 客户端 → 服务端 | `ssh_connect` | 建立SSH连接（host/port/username/password/serverId/cols/rows） |
| 客户端 → 服务端 | `terminal_input` | 转发键盘输入 |
| 客户端 → 服务端 | `terminal_resize` | 同步终端尺寸 |
| 客户端 → 服务端 | `ssh_disconnect` | 主动断开 |
| 服务端 → 客户端 | `ssh_connected` | 连接结果（success/message） |
| 服务端 → 客户端 | `terminal_output` | SSH 输出流 |
| 服务端 → 客户端 | `terminal_disconnect` | 连接断开通知 |

## REST API

- `GET /api/servers` - 服务器列表（不含密码）
- `POST /api/servers` - 添加服务器（host+username 去重）
- `DELETE /api/servers/<id>` - 删除服务器
- `POST /api/chat` - AI自然语言解析，返回命令（不执行）

## 文件结构

```
.
├── app.py                 # Flask + Socket.IO 后端
├── ai_parser.py           # AI命令解析（本地快路径 + DeepSeek）
├── index.html             # 前端页面
├── static/app.js          # 前端逻辑
├── servers.json           # 保存的服务器列表（运行时生成）
├── .env                   # 环境配置（不入库）
├── requirements.txt       # Python依赖
├── README.md              # 项目文档
└── USAGE.md               # 使用指南
```

## 注意事项

1. 确保SSH服务器可访问，`.env` / 界面中配置正确
2. 危险命令会被拦截，但 AI 返回的命令会直接在终端执行，请留意对话中显示的命令内容
3. 交互式命令（vim、top 等）可以正常运行，因为是真实 PTY
