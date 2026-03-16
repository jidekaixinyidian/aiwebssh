#!/usr/bin/env python3
"""测试ANSI转义序列清理"""
import re

def clean_ansi(text):
    """清理ANSI转义序列"""
    # 移除所有ANSI转义序列
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    text = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', text)
    text = re.sub(r'\x1b\][^\x07]*\x07', '', text)
    text = re.sub(r'\x1b\([0-9A-Za-z]', '', text)
    text = re.sub(r'\x1b[=>]', '', text)
    text = re.sub(r'\x1b[@-_][0-?]*[ -/]*[@-~]', '', text)
    
    # 移除其他控制字符
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)
    
    return text

# 测试用例
test_cases = [
    "drwxr-xr-x 3 root root 4096 Mar 6 2025 \x1b[01;34mknem-1.1.4.90mlnx3\x1b[0m",
    "-rw-r--r-- 1 root root 1068 Jun 18 2025 L3mon",
    "drwxr-xr-x 8 root root 4096 Jan 7 01:46 \x1b[01;34mL3MON-main\x1b[0m",
]

print("测试ANSI清理:")
for test in test_cases:
    cleaned = clean_ansi(test)
    print(f"原始: {repr(test)}")
    print(f"清理: {cleaned}")
    print()
