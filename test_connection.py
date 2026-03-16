"""
测试SSH连接和AI解析功能
"""
from ssh_manager import SSHManager
from ai_parser import AICommandParser
from dotenv import load_dotenv
import os

load_dotenv()

def test_ssh_connection():
    """测试SSH连接"""
    print("=" * 50)
    print("测试SSH连接")
    print("=" * 50)
    
    host = os.getenv('SSH_HOST')
    username = os.getenv('SSH_USER')
    password = os.getenv('SSH_PASSWORD')
    
    print(f"连接目标: {username}@{host}")
    
    ssh = SSHManager(host, username, password)
    success, message = ssh.connect()
    
    if success:
        print(f"✓ {message}")
        
        # 测试简单命令
        print("\n测试命令: whoami")
        success, output, error = ssh.execute_command("whoami")
        if success:
            print(f"输出: {output.strip()}")
        else:
            print(f"错误: {error}")
        
        # 测试系统信息
        print("\n测试命令: uname -a")
        success, output, error = ssh.execute_command("uname -a")
        if success:
            print(f"输出: {output.strip()}")
        
        ssh.disconnect()
        print("\n✓ SSH连接测试通过")
        return True
    else:
        print(f"✗ {message}")
        return False

def test_ai_parser():
    """测试AI解析"""
    print("\n" + "=" * 50)
    print("测试AI命令解析")
    print("=" * 50)
    
    api_key = os.getenv('DEEPSEEK_API_KEY')
    api_url = os.getenv('DEEPSEEK_API_URL')
    
    parser = AICommandParser(api_key, api_url)
    
    test_cases = [
        "查看资源水位",
        "查看/opt目录",
        "显示磁盘使用情况",
        "查看内存使用",
    ]
    
    for test_input in test_cases:
        print(f"\n输入: {test_input}")
        result = parser.parse_natural_language(test_input)
        print(f"命令: {result.get('command', 'N/A')}")
        print(f"说明: {result.get('description', 'N/A')}")
        print(f"危险: {result.get('dangerous', False)}")
    
    print("\n✓ AI解析测试完成")

def test_dangerous_commands():
    """测试危险命令检测"""
    print("\n" + "=" * 50)
    print("测试危险命令检测")
    print("=" * 50)
    
    api_key = os.getenv('DEEPSEEK_API_KEY')
    api_url = os.getenv('DEEPSEEK_API_URL')
    
    parser = AICommandParser(api_key, api_url)
    
    dangerous_inputs = [
        "删除所有文件",
        "格式化磁盘",
    ]
    
    for test_input in dangerous_inputs:
        print(f"\n输入: {test_input}")
        result = parser.parse_natural_language(test_input)
        print(f"命令: {result.get('command', 'N/A')}")
        print(f"危险: {result.get('dangerous', False)}")
        if result.get('dangerous'):
            print("✓ 正确识别为危险命令")
        else:
            print("✗ 未能识别为危险命令")

if __name__ == '__main__':
    print("\n智能运维助手 - 功能测试\n")
    
    # 测试SSH连接
    ssh_ok = test_ssh_connection()
    
    if ssh_ok:
        # 测试AI解析
        try:
            test_ai_parser()
            test_dangerous_commands()
        except Exception as e:
            print(f"\n✗ AI测试失败: {e}")
            print("提示: 请检查API密钥是否有效")
    
    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)
