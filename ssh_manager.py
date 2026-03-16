import paramiko
import time
from typing import Optional, Tuple

class SSHManager:
    """SSH连接管理器"""
    
    def __init__(self, host: str, username: str, password: str, port: int = 22):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.client: Optional[paramiko.SSHClient] = None
        self.connected = False
        
    def connect(self) -> Tuple[bool, str]:
        """建立SSH连接"""
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
            self.connected = True
            return True, f"成功连接到 {self.host}"
        except Exception as e:
            self.connected = False
            return False, f"连接失败: {str(e)}"
    
    def disconnect(self):
        """断开SSH连接"""
        if self.client:
            self.client.close()
            self.connected = False
    
    def execute_command(self, command: str, timeout: int = 30) -> Tuple[bool, str, str]:
        """执行SSH命令"""
        if not self.connected or not self.client:
            return False, "", "SSH未连接"
        
        try:
            stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
            output = stdout.read().decode('utf-8', errors='ignore')
            error = stderr.read().decode('utf-8', errors='ignore')
            exit_status = stdout.channel.recv_exit_status()
            
            return exit_status == 0, output, error
        except Exception as e:
            return False, "", f"命令执行失败: {str(e)}"
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.connected and self.client is not None
