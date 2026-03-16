import paramiko
import re
import time
import threading
from typing import Optional, Tuple

class InteractiveSSHManager:
    """交互式SSH连接管理器 - 支持cd、su等状态保持命令"""
    
    def __init__(self, host: str, username: str, password: str, port: int = 22):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.client: Optional[paramiko.SSHClient] = None
        self.channel: Optional[paramiko.Channel] = None
        self.connected = False
        self.current_user = username
        self.current_hostname = host
        self.current_dir = "~"
        
    def connect(self) -> Tuple[bool, str]:
        """建立SSH连接并创建交互式shell"""
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=10
            )
            
            # 创建交互式shell，设置终端类型为dumb（无颜色）
            self.channel = self.client.invoke_shell(term='dumb', width=200, height=50)
            self.channel.settimeout(0.5)
            
            # 等待shell准备好
            time.sleep(0.5)
            self._clear_buffer()
            
            # 禁用颜色和特殊字符
            commands = [
                'export TERM=dumb',
                'export PS1="$ "',  # 简化提示符
                'unset LS_COLORS',  # 禁用ls颜色
                'alias ls="ls --color=never"',  # ls不使用颜色
                'alias grep="grep --color=never"',  # grep不使用颜色
            ]
            
            for cmd in commands:
                self.channel.send(cmd + '\n')
                time.sleep(0.1)
            
            time.sleep(0.3)
            self._clear_buffer()
            
            self.connected = True
            return True, f"成功连接到 {self.host}"
        except Exception as e:
            self.connected = False
            return False, f"连接失败: {str(e)}"
    
    def disconnect(self):
        """断开SSH连接"""
        if self.channel:
            self.channel.close()
        if self.client:
            self.client.close()
        self.connected = False
    
    def get_prompt(self) -> str:
        """获取当前的shell提示符"""
        return f"{self.current_user}@{self.current_hostname}:{self.current_dir}$"
    
    def update_context(self):
        """更新当前用户、主机名和目录信息"""
        try:
            # 获取当前用户
            self.channel.send('whoami\n')
            time.sleep(0.2)
            user_output = self._read_output(2)
            user_output = self._clean_output(user_output, 'whoami')
            if user_output.strip():
                self.current_user = user_output.strip().split('\n')[0].strip()
            
            # 获取主机名
            self.channel.send('hostname\n')
            time.sleep(0.2)
            host_output = self._read_output(2)
            host_output = self._clean_output(host_output, 'hostname')
            if host_output.strip():
                self.current_hostname = host_output.strip().split('\n')[0].strip()
            
            # 获取当前目录
            self.channel.send('pwd\n')
            time.sleep(0.2)
            pwd_output = self._read_output(2)
            pwd_output = self._clean_output(pwd_output, 'pwd')
            if pwd_output.strip():
                full_path = pwd_output.strip().split('\n')[0].strip()
                # 简化路径显示
                if full_path.startswith(f'/home/{self.current_user}'):
                    self.current_dir = '~' + full_path[len(f'/home/{self.current_user}'):]
                elif full_path == f'/root' and self.current_user == 'root':
                    self.current_dir = '~'
                else:
                    self.current_dir = full_path
            
            print(f"[DEBUG] 更新上下文: {self.current_user}@{self.current_hostname}:{self.current_dir}")
        except Exception as e:
            print(f"[ERROR] 更新上下文失败: {str(e)}")
    
    def execute_command(self, command: str, timeout: int = 30) -> Tuple[bool, str, str, str]:
        """执行SSH命令（保持会话状态），返回 (success, output, error, prompt)"""
        if not self.connected or not self.channel:
            return False, "", "SSH未连接", self.get_prompt()
        
        try:
            print(f"[DEBUG] 执行命令: {command}")
            
            # 清空缓冲区
            self._clear_buffer()
            
            # 检查是否是需要密码的命令
            if command.strip().startswith('su ') or command.strip() == 'su':
                success, output, error = self._execute_su_command(command, timeout)
                # su命令后更新上下文
                if success and not error:
                    self.update_context()
                return success, output, error, self.get_prompt()
            
            # 发送命令
            self.channel.send(command + '\n')
            
            # 等待命令执行
            time.sleep(0.5)
            
            # 读取输出
            output = self._read_output(timeout)
            print(f"[DEBUG] 原始输出长度: {len(output)}")
            print(f"[DEBUG] 原始输出内容: {repr(output[:200])}")
            
            # 清理输出
            output = self._clean_output(output, command)
            print(f"[DEBUG] 清理后输出长度: {len(output)}")
            print(f"[DEBUG] 清理后输出内容: {repr(output[:200])}")
            
            # 检查是否有错误
            error = ""
            if "command not found" in output.lower():
                error = "命令未找到"
                output = ""
            elif "permission denied" in output.lower():
                error = "权限被拒绝"
            
            # cd命令后更新上下文
            if command.strip().startswith('cd ') or command.strip() == 'cd':
                self.update_context()
            
            return True, output, error, self.get_prompt()
            
        except Exception as e:
            print(f"[ERROR] 命令执行异常: {str(e)}")
            import traceback
            traceback.print_exc()
            return False, "", f"命令执行失败: {str(e)}", self.get_prompt()
    
    def _execute_su_command(self, command: str, timeout: int = 30) -> Tuple[bool, str, str]:
        """执行su命令（自动输入密码），返回 (success, output, error)"""
        try:
            print(f"[DEBUG] 执行su命令: {command}")
            
            # 发送su命令
            self.channel.send(command + '\n')
            
            # 等待密码提示
            time.sleep(0.8)
            
            # 读取提示
            prompt_output = ""
            start_time = time.time()
            while time.time() - start_time < 3:
                if self.channel.recv_ready():
                    chunk = self.channel.recv(1024).decode('utf-8', errors='ignore')
                    prompt_output += chunk
                    print(f"[DEBUG] 收到提示: {repr(chunk)}")
                    
                    # 检查是否有密码提示
                    if 'password' in chunk.lower() or 'Password' in chunk:
                        print(f"[DEBUG] 检测到密码提示，发送密码")
                        # 发送密码
                        self.channel.send(self.password + '\n')
                        time.sleep(0.8)
                        
                        # 读取认证结果
                        result_output = ""
                        result_start = time.time()
                        while time.time() - result_start < 3:
                            if self.channel.recv_ready():
                                result_chunk = self.channel.recv(1024).decode('utf-8', errors='ignore')
                                result_output += result_chunk
                                print(f"[DEBUG] 认证结果: {repr(result_chunk)}")
                                
                                # 检查是否成功（看到提示符）
                                if '$' in result_chunk or '#' in result_chunk:
                                    break
                            else:
                                time.sleep(0.1)
                        
                        # 检查认证是否失败
                        combined_output = prompt_output + result_output
                        if 'authentication failure' in combined_output.lower() or \
                           'incorrect password' in combined_output.lower() or \
                           'sorry' in combined_output.lower():
                            print(f"[DEBUG] 认证失败")
                            return True, "", "认证失败：密码错误或权限不足"
                        
                        # 认证成功
                        print(f"[DEBUG] 认证成功")
                        output = self._clean_output(combined_output, command)
                        return True, "用户切换成功", ""
                else:
                    time.sleep(0.1)
            
            # 没有密码提示，可能已经是root或不需要密码
            print(f"[DEBUG] 没有密码提示")
            output = self._clean_output(prompt_output, command)
            return True, output if output else "命令已执行", ""
                
        except Exception as e:
            print(f"[ERROR] su命令执行异常: {str(e)}")
            import traceback
            traceback.print_exc()
            return False, "", f"su命令执行失败: {str(e)}"
    
    def _clear_buffer(self):
        """清空接收缓冲区"""
        if not self.channel:
            return
        
        try:
            while self.channel.recv_ready():
                self.channel.recv(4096)
        except:
            pass
    
    def _read_output(self, timeout: int = 30) -> str:
        """读取命令输出"""
        if not self.channel:
            return ""
        
        output = ""
        start_time = time.time()
        
        while True:
            if time.time() - start_time > timeout:
                break
            
            try:
                if self.channel.recv_ready():
                    chunk = self.channel.recv(4096).decode('utf-8', errors='ignore')
                    output += chunk
                    
                    # 如果看到提示符，说明命令执行完成
                    if '$' in chunk or '#' in chunk:
                        # 再等待一小段时间，确保所有输出都接收完
                        time.sleep(0.1)
                        if self.channel.recv_ready():
                            output += self.channel.recv(4096).decode('utf-8', errors='ignore')
                        break
                else:
                    time.sleep(0.1)
            except Exception as e:
                break
        
        return output
    
    def _clean_output(self, output: str, command: str = "") -> str:
        """清理输出，移除ANSI转义序列和命令回显"""
        if not output:
            return ""
        
        # 移除所有ANSI转义序列
        # ESC [ ... m (颜色和样式)
        output = re.sub(r'\x1b\[[0-9;]*m', '', output)
        # ESC [ ... 其他控制序列
        output = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', output)
        # ESC ] ... BEL (OSC序列)
        output = re.sub(r'\x1b\][^\x07]*\x07', '', output)
        # ESC ( ... (字符集选择)
        output = re.sub(r'\x1b\([0-9A-Za-z]', '', output)
        
        # 移除回车符，统一换行
        output = output.replace('\r\n', '\n').replace('\r', '\n')
        
        # 分割成行
        lines = output.split('\n')
        
        # 移除命令回显（第一次出现的命令行）
        if command:
            cmd_stripped = command.strip()
            found_command = False
            filtered_lines = []
            for line in lines:
                # 只移除第一次出现的命令回显
                if not found_command and cmd_stripped in line:
                    found_command = True
                    continue
                filtered_lines.append(line)
            lines = filtered_lines
        
        # 移除提示符行和空行
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            
            # 跳过空行
            if not stripped:
                continue
            
            # 跳过只包含提示符的行（$ 或 # 开头且后面没有内容）
            if re.match(r'^[$#]\s*$', stripped):
                continue
            
            # 移除行首的简单提示符（$ 或 # 后面跟空格）
            cleaned = re.sub(r'^[$#]\s+', '', line)
            
            # 保留有实际内容的行
            if cleaned.strip():
                cleaned_lines.append(cleaned.rstrip())
        
        result = '\n'.join(cleaned_lines)
        
        # 如果清理后为空但原始输出不为空，返回简化的原始输出
        if not result and output.strip():
            # 至少返回去除ANSI和回车后的内容
            simple_clean = output
            simple_clean = re.sub(r'\x1b\[[0-9;]*[mA-Za-z]', '', simple_clean)
            simple_clean = simple_clean.replace('\r\n', '\n').replace('\r', '\n')
            simple_clean = '\n'.join([l.strip() for l in simple_clean.split('\n') if l.strip()])
            return simple_clean
        
        return result
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.connected and self.channel is not None and not self.channel.closed
