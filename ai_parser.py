import requests
from typing import Dict, List
import json

class AICommandParser:
    """AI命令解析器"""
    
    DANGEROUS_COMMANDS = [
        'rm -rf', 'mkfs', 'dd if=', ':(){:|:&};:', 'chmod -R 777',
        'chown -R', '> /dev/sda', 'mv /* ', 'format', 'fdisk'
    ]
    
    def __init__(self, api_key: str, api_url: str):
        self.api_key = api_key
        self.api_url = api_url.rstrip('/') + '/chat/completions'
        
    def parse_natural_language(self, user_input: str) -> Dict:
        """将自然语言转换为Linux命令"""
        
        system_prompt = """你是一个Linux运维专家助手。用户会用自然语言描述需求，你需要将其转换为对应的Linux命令。

规则：
1. 只返回JSON格式: {"command": "具体命令", "description": "命令说明", "dangerous": true/false}
2. 如果是危险命令(删除、格式化等)，设置dangerous为true
3. 常见需求映射：
   - "资源水位/系统资源" -> "top -bn1 | head -20"
   - "磁盘使用" -> "df -h"
   - "内存使用" -> "free -h"
   - "查看目录" -> "ls -lah 目录路径"
   - "进程列表" -> "ps aux"
   - "网络连接" -> "netstat -tuln"
4. 如果无法理解，返回 {"command": "", "description": "无法理解该指令", "dangerous": false}"""

        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}'
            }
            
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                "temperature": 0.3,
                "max_tokens": 500
            }
            
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            response.raise_for_status()
            result_data = response.json()
            result_text = result_data['choices'][0]['message']['content'].strip()
            
            # 提取JSON
            if '```json' in result_text:
                result_text = result_text.split('```json')[1].split('```')[0].strip()
            elif '```' in result_text:
                result_text = result_text.split('```')[1].split('```')[0].strip()
            
            result = json.loads(result_text)
            
            # 额外危险命令检查
            if not result.get('dangerous', False):
                result['dangerous'] = self._is_dangerous(result.get('command', ''))
            
            return result
            
        except Exception as e:
            return {
                "command": "",
                "description": f"AI解析失败: {str(e)}",
                "dangerous": False
            }
    
    def _is_dangerous(self, command: str) -> bool:
        """检查命令是否危险"""
        return any(dangerous in command for dangerous in self.DANGEROUS_COMMANDS)
