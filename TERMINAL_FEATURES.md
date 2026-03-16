# 终端功能说明

## 已实现的功能

### 1. 手动输入命令
在终端底部有一个输入框，可以像正常终端一样输入Linux命令：

```bash
# 示例命令
ls -la
pwd
df -h
free -m
top -bn1
ps aux
netstat -tuln
cat /etc/os-release
```

### 2. 命令历史记录
- 按 `↑` 键：浏览上一条命令
- 按 `↓` 键：浏览下一条命令
- 自动保存最近50条命令历史

### 3. Tab键补全
输入命令开头后按 `Tab` 键自动补全常用命令：
- ls, cd, pwd, cat, grep, find
- top, ps, df, free, netstat
- vim, nano

### 4. 交互体验
- 点击终端区域自动聚焦输入框
- 命令和输出实时显示
- 支持多行输出
- 自动滚动到最新内容
- 错误信息红色显示
- 成功信息绿色显示

### 5. AI自然语言控制
在右侧AI助手输入自然语言：
- "查看资源水位"
- "查看/opt目录"
- "显示磁盘使用情况"
- "查看内存使用"
- "列出进程"

### 6. 快捷操作按钮
- Check system health - 检查系统健康状态
- List large files - 查找大文件

### 7. 安全特性
- 自动识别危险命令（rm -rf、格式化等）
- 危险命令自动拦截，不会执行
- 实时显示连接状态

## 使用方法

### 启动服务
```bash
python app.py
```

### 访问界面
打开浏览器访问：http://localhost:5000

### 三种使用方式

#### 方式1：终端直接输入
在终端底部输入框输入Linux命令，按回车执行

#### 方式2：AI自然语言
在右侧AI助手输入框输入自然语言描述，AI会自动转换为命令并执行

#### 方式3：快捷按钮
点击右侧的快捷操作按钮，快速执行预设命令

## 技术实现

### 前端
- HTML: `.vscode/index.html` - 包含终端输入框
- JavaScript: `static/app.js` - 处理用户输入和API调用
- CSS: TailwindCSS - 现代化UI设计

### 后端
- Flask: `app.py` - REST API服务
- SSH: `ssh_manager.py` - SSH连接管理
- AI: `ai_parser.py` - 自然语言解析（DeepSeek）

### API接口
- `POST /api/connect` - 建立SSH连接
- `POST /api/disconnect` - 断开连接
- `GET /api/status` - 获取连接状态
- `POST /api/chat` - AI自然语言处理
- `POST /api/execute` - 直接执行命令

## 文件结构

```
.
├── .vscode/
│   └── index.html          # 前端界面（已添加终端输入框）
├── static/
│   └── app.js             # 前端JavaScript逻辑
├── app.py                 # Flask后端主程序
├── ssh_manager.py         # SSH连接管理
├── ai_parser.py          # AI命令解析
├── .env                  # 环境配置
├── requirements.txt      # Python依赖
└── README.md            # 项目文档
```

## 注意事项

1. 确保SSH服务器可访问
2. 检查.env文件中的配置是否正确
3. 危险命令会被自动拦截
4. 命令历史最多保存50条
5. 长时间运行的命令可能会超时

## 故障排除

### 无法连接SSH
- 检查服务器地址、用户名、密码
- 确认SSH服务正在运行
- 检查防火墙设置

### 命令执行失败
- 查看终端输出的错误信息
- 检查命令语法是否正确
- 确认有足够的权限

### AI解析失败
- 检查API密钥是否有效
- 确认网络连接正常
- 查看后端日志

## 更新日志

### v1.0.0 (2026-03-03)
- ✅ 添加终端手动输入功能
- ✅ 实现命令历史记录（↑↓键）
- ✅ 添加Tab键命令补全
- ✅ 集成AI自然语言控制
- ✅ 实现危险命令拦截
- ✅ 优化用户交互体验
