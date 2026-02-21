#!/usr/bin/env python3
"""
scripts/init_env.sh 的 Python 替代版。
设置好 PYTHONPATH 以便所有子模块能互相 import。
在 cron 或手动运行任何 agent 前 source/执行此脚本。
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.environ["ANTIGRAVITY_ROOT"]  = ROOT
os.environ["ANTIGRAVITY_INBOX"] = "/Users/hugh/Documents/Obsidian/AINotes/00_Inbox"
os.environ["OBSIDIAN_VAULT"]    = "/Users/hugh/Documents/Obsidian/AINotes"

# 把 ROOT 加入 PYTHONPATH（供子进程继承）
existing = os.environ.get("PYTHONPATH", "")
os.environ["PYTHONPATH"] = f"{ROOT}:{existing}" if existing else ROOT

if __name__ == "__main__":
    print(f"ANTIGRAVITY_ROOT  = {ROOT}")
    print(f"OBSIDIAN_VAULT    = {os.environ['OBSIDIAN_VAULT']}")
    print(f"PYTHONPATH        = {os.environ['PYTHONPATH']}")
