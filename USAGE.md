# 使用指南

## 启动步骤

### Windows用户

1. 双击 `start.bat` 文件
2. 等待依赖安装和服务启动
3. 浏览器会自动打开 http://localhost:5000

### 手动启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动服务
python app.py

# 3. 浏览器访问
# http://localhost:5000
```

## 测试连接

运行测试脚本验证SSH和AI功能：

```bash
python test_connection.py
```

## 使用示例

### 1. 自然语言命令

在右侧AI助手输入框中输入：

- **查看系统资源**
  - "查看资源水位"
  - "显示系统负载"
  - "检查系统健康状态"

- **文件和目录操作**
  - "查看/opt目录"
  - "列出/var/log下的文件"
  - "查找大文件"

- **系统信息**
  - "显示磁盘使用情况"
  - "查看内存使用"
  - "显示系统信息"

- **进程管理**
  - "列出所有进程"
  - "查看CPU占用最高的进程"
  - "显示内存占用情况"

- **网络相关**
  - "查看网络连接"
  - "显示监听端口"
  - "查看网络状态"

### 2. 快捷操作按钮

点击右侧的快捷按钮：
- **Check system health** - 检查系统健康状态
- **List large files** - 列出大文件

### 3. 直接执行建议命令

AI会在对话中建议命令，点击"Execute"按钮直接执行

## AI助手功能

### 命令解析

AI会将你的自然语言转换为Linux命令：

```
你说: "查看资源水位"
AI解析: top -bn1 | head -20
```

### 危险命令拦截

AI会自动识别并拦截危险命令：

```
你说: "删除所有文件"
AI响应: ⚠️ 危险命令警告 - 该命令可能造成系统损坏，已被阻止执行
```

### 命令说明

每次执行前，AI会说明命令的作用：

```
执行命令: df -h
说明: 显示磁盘使用情况，以人类可读的格式
```

## 界面说明

### 左侧边栏
- **Saved Connections**: 保存的连接配置
- **Recent Sessions**: 最近的会话记录
- **New Connection**: 添加新连接（当前版本使用.env配置）

### 中间终端区域
- 显示命令执行历史
- 实时输出命令结果
- 模拟真实终端体验

### 右侧AI助手
- **输入框**: 输入自然语言命令
- **快捷按钮**: 常用操作快速访问
- **建议命令**: AI推荐的命令
- **对话历史**: 查看之前的交互

### 顶部状态栏
- **连接状态**: 绿点表示已连接，红点表示未连接
- **服务器信息**: 显示当前连接的服务器

### 底部状态栏
- **SSH版本**: SSH协议版本
- **密钥信息**: 使用的认证方式
- **延迟**: 网络延迟
- **运行时间**: 服务器运行时间

## 配置说明

### .env 文件

```env
# DeepSeek AI配置
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_API_URL=https://api.deepseek.com/v1

# SSH连接配置
SSH_HOST=127.0.0.1
SSH_USER=1234
SSH_PASSWORD=1234
SSH_PORT=22
```

### 修改SSH连接

编辑 `.env` 文件，修改以下参数：
- `SSH_HOST`: 服务器地址
- `SSH_USER`: 用户名
- `SSH_PASSWORD`: 密码
- `SSH_PORT`: SSH端口（默认22）

### 修改API配置

如果使用其他AI服务，修改：
- `DEEPSEEK_API_KEY`: API密钥
- `DEEPSEEK_API_URL`: API地址

## 安全建议

1. **不要将 .env 文件提交到版本控制**
   - 已添加到 .gitignore
   - 包含敏感信息（密码、API密钥）

2. **使用SSH密钥认证**
   - 比密码认证更安全
   - 可修改 `ssh_manager.py` 支持密钥认证

3. **限制网络访问**
   - 默认绑定 0.0.0.0（所有网络接口）
   - 生产环境建议改为 127.0.0.1（仅本地）

4. **定期更新依赖**
   ```bash
   pip install -r requirements.txt --upgrade
   ```

## 故障排除

### 1. 连接失败

**问题**: 无法连接到SSH服务器

**解决方案**:
- 检查服务器地址是否正确
- 确认用户名和密码
- 验证服务器SSH服务是否运行
- 检查防火墙设置

### 2. AI解析失败

**问题**: AI无法解析命令

**解决方案**:
- 检查API密钥是否有效
- 确认API额度是否充足
- 检查网络连接
- 查看后端日志

### 3. 端口被占用

**问题**: 5000端口已被使用

**解决方案**:
修改 `app.py` 中的端口：
```python
app.run(host='0.0.0.0', port=8080, debug=True)
```

### 4. 依赖安装失败

**问题**: pip安装依赖出错

**解决方案**:
```bash
# 升级pip
python -m pip install --upgrade pip

# 使用国内镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 高级功能

### 添加自定义快捷命令

编辑 `app.py` 中的 `QUICK_COMMANDS` 字典：

```python
QUICK_COMMANDS = {
    "资源水位": "top -bn1 | head -20",
    "磁盘使用": "df -h",
    "你的命令名": "你的Linux命令",
}
```

### 修改AI提示词

编辑 `ai_parser.py` 中的 `system_prompt`：

```python
system_prompt = """你是一个Linux运维专家助手..."""
```

### 添加新的API接口

在 `app.py` 中添加新路由：

```python
@app.route('/api/your-endpoint', methods=['POST'])
def your_function():
    # 你的逻辑
    return jsonify({'success': True})
```

## 技术支持

如遇到问题：
1. 查看后端日志输出
2. 检查浏览器控制台错误
3. 运行 `test_connection.py` 诊断
4. 查看 README.md 常见问题部分
