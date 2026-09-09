import json
import logging
import re
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger('webssh.ai')

REQUEST_TIMEOUT = 90
PROBE_TIMEOUT = 15

LOCAL_INTENTS = [
    (r'(资源水位|系统资源|系统负载|负载情况)', 'top -bn1 | head -20', '查看CPU和内存资源占用（前20行）'),
    (r'磁盘(使用|空间|占用|情况)', 'df -h', '查看磁盘使用情况'),
    (r'内存(使用|占用|情况)', 'free -h', '查看内存使用情况'),
    (r'(进程列表|运行(中)?的进程|查看进程|列出进程)', 'ps aux', '查看所有进程'),
    (r'(网络连接|监听端口|端口(占用|监听|列表))', 'ss -tuln', '查看监听端口与网络连接'),
]

# 输入中出现这些词说明是复合/定制需求（排序、过滤、导出、指代等），交给AI处理
_COMPLEX_INTENT_RE = re.compile(
    r'(最高|最低|排序|前几|最多|最大|最小|前[0-9一二三四五六七八九十百]+|top|倒序|'
    r'过滤|筛选|包含|不含|grep|导出|保存|写入|发送|删除|杀掉|结束|重启|停止|'
    r'那个|哪些|上面|刚才|然后|再|顺便|是否|多少|为什么|怎么|如何|分析)'
)

# 快路径仅处理简短纯查询（长输入更可能是复合需求）
FAST_PATH_MAX_LEN = 30

_intents = [(re.compile(p), cmd, desc) for p, cmd, desc in LOCAL_INTENTS]


def match_local_intent(user_input: str) -> Optional[Dict]:
    """常见运维意图直接本地匹配，省去一次API调用

    仅当输入是简短的纯查询时才走快路径；含排序/过滤/导出等
    复合意图或较长的输入交给AI，避免"内存占用最高的进程"被
    劫持成 free -h 这类错配。
    """
    if len(user_input) > FAST_PATH_MAX_LEN:
        return None
    if _COMPLEX_INTENT_RE.search(user_input):
        return None
    for pattern, command, description in _intents:
        if pattern.search(user_input):
            return {'command': command, 'description': description, 'dangerous': False}
    return None


def _auth_headers(api_key: str) -> Dict:
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    return headers


def fetch_available_models(base_url: str, api_key: str) -> List[str]:
    """从OpenAI兼容的 /models 端点拉取可用模型ID列表"""
    url = base_url.rstrip('/') + '/models'
    response = requests.get(url, headers=_auth_headers(api_key), timeout=PROBE_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    items = data.get('data') if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError(f'无法识别的模型列表格式: {type(items).__name__}')
    return sorted(item['id'] for item in items if isinstance(item, dict) and item.get('id'))


def test_model(base_url: str, api_key: str, model: str) -> Tuple[bool, str]:
    """发送最小聊天请求，验证模型配置是否可用"""
    url = base_url.rstrip('/') + '/chat/completions'
    payload = {'model': model, 'messages': [{'role': 'user', 'content': 'ping'}]}
    try:
        response = requests.post(url, headers=_auth_headers(api_key), json=payload,
                                 timeout=PROBE_TIMEOUT)
        response.raise_for_status()
        return True, '连接成功'
    except requests.RequestException as e:
        return False, str(e)


class AICommandParser:
    """AI命令解析器，适配任意OpenAI兼容Chat API"""

    DANGEROUS_COMMANDS = [
        'rm -rf', 'mkfs', 'dd if=', ':(){:|:&};:', 'chmod -R 777',
        'chown -R', '> /dev/sda', 'mv /* ', 'format', 'fdisk'
    ]

    SYSTEM_PROMPT = """你是一个Linux运维专家助手，在Web终端中帮助用户操作远程服务器。用户会用自然语言描述需求，你需要将其转换为对应的Linux命令。

规则：
1. 只返回JSON格式: {"command": "具体命令", "description": "命令说明", "dangerous": true/false}
2. 如果是危险命令(删除、格式化等)，设置dangerous为true
3. 常见需求映射：
   - "资源水位/系统资源" -> "top -bn1 | head -20"
   - "磁盘使用" -> "df -h"
   - "内存使用" -> "free -h"
   - "查看目录" -> "ls -lah 目录路径"
   - "进程列表" -> "ps aux"
   - "网络连接" -> "ss -tuln"
4. 命令将在交互式shell中执行，必须遵守：
   - 只返回非交互式命令，禁止 vim/less/top(交互模式)/tail -f 等会占住终端的程序
   - 长输出主动加 head/tail 限制行数
5. 结合上下文理解指代（"刚才那个文件"、"这个目录"），上下文会附在system消息中：
   - "当前目录"是用户shell所在目录
   - "命令`xxx`的输出"是用户刚执行过的命令及其结果
   - 用户说"分析一下/为什么/什么意思"时，基于最近命令的输出给出简短分析，返回
     {"command": "", "description": "<分析文字>", "dangerous": false}
   - 用户问"占用最高的进程"这类排序需求时，生成带sort/head的管道命令（如
     ps aux --sort=-%mem | head -6），不要返回朴素的 ps aux / free -h
6. 如果用户只是打招呼、闲聊或询问问题（不是要执行操作），返回
   {"command": "", "description": "<对用户问题的简短回答>", "dangerous": false}
7. 如果无法理解，返回 {"command": "", "description": "无法理解该指令", "dangerous": false}"""

    MAX_HISTORY_ROUNDS = 6

    def __init__(self, base_url: str, api_key: str, model: str,
                 timeout: int = REQUEST_TIMEOUT):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._http = requests.Session()

    def parse_natural_language(self, user_input: str, history: Optional[List[Dict]] = None,
                               context: Optional[str] = None) -> Dict:
        """将自然语言转换为Linux命令

        history: 之前的 [{role, content}] 对话（已含system则跳过），取最近若干轮
        context: 注入到system prompt的实时终端上下文（cwd、最近命令等）
        """
        local = match_local_intent(user_input)
        if local:
            return local
        return self._parse_with_ai(user_input, history, context)

    def _parse_with_ai(self, user_input: str, history: Optional[List[Dict]],
                       context: Optional[str]) -> Dict:
        """调用聊天API解析自然语言"""
        try:
            result_text = self._chat_json(user_input, history, context)
            result = self._extract_json(result_text)
            if not result.get('dangerous', False):
                result['dangerous'] = self._is_dangerous(result.get('command', ''))
            return result
        except requests.RequestException as e:
            logger.warning('AI请求失败: %s', e)
            return self._error(f'AI请求失败: {e}')
        except (KeyError, IndexError, ValueError) as e:
            logger.warning('AI响应解析失败: %s', e)
            return self._error(f'AI响应解析失败: {e}')

    def _chat_json(self, user_input: str, history: Optional[List[Dict]],
                   context: Optional[str]) -> str:
        """调用chat completions；若provider不支持部分参数返回400，降级为最小payload重试"""
        messages = [{'role': 'system', 'content': self._build_system_prompt(context)}]
        for msg in (history or [])[-self.MAX_HISTORY_ROUNDS * 2:]:
            if msg.get('role') in ('user', 'assistant') and msg.get('content'):
                messages.append({'role': msg['role'], 'content': str(msg['content'])})
        messages.append({'role': 'user', 'content': user_input})

        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': 0.3,
            'max_tokens': 500,
            'response_format': {'type': 'json_object'}
        }
        response = self._post_chat(payload)
        if response.status_code == 400:
            response = self._post_chat({'model': self.model, 'messages': messages})
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content'].strip()

    def _build_system_prompt(self, context: Optional[str]) -> str:
        if not context:
            return self.SYSTEM_PROMPT
        return f'{self.SYSTEM_PROMPT}\n\n当前终端上下文：\n{context}'

    def _post_chat(self, payload):
        return self._http.post(
            f'{self.base_url}/chat/completions',
            headers=_auth_headers(self.api_key),
            json=payload,
            timeout=self.timeout
        )

    @staticmethod
    def _extract_json(text: str) -> Dict:
        """从模型输出中提取JSON，兼容markdown代码块包裹"""
        if '```' in text:
            parts = text.split('```')
            for part in parts[1::2]:
                candidate = part.strip()
                if candidate.startswith('json'):
                    candidate = candidate[4:].strip()
                try:
                    return json.loads(candidate)
                except ValueError:
                    continue
            raise ValueError(f'无法从模型输出提取JSON: {text!r}')
        return json.loads(text)

    @staticmethod
    def _error(message: str) -> Dict:
        return {'command': '', 'description': message, 'dangerous': False,
                'error': True}

    def _is_dangerous(self, command: str) -> bool:
        """检查命令是否危险"""
        return any(dangerous in command for dangerous in self.DANGEROUS_COMMANDS)
