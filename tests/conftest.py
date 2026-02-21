"""测试共享 fixtures。"""

import os
import pytest
from pathlib import Path


@pytest.fixture
def tmp_vault(tmp_path):
    """创建临时 Vault 结构用于测试。"""
    inbox = tmp_path / "00_Inbox"
    inbox.mkdir()

    # 创建一个标准 Bouncer 笔记
    note = inbox / "Bouncer - Test Article.md"
    note.write_text("""---
tags:
  - BouncerDump
score: 9.2
status: pending
source: "https://example.com/article"
title: "Test Article"
created: "2026-02-21"
---

# Test Article

> [!abstract] 核心公理 (Axiom)
> 测试公理内容

> [!info] 守门员判决理由 (Reason)
> 测试判决理由
""", encoding="utf-8")

    # 创建一个损坏的笔记（无 frontmatter）
    broken = inbox / "broken_note.md"
    broken.write_text("# 没有 frontmatter 的笔记\n内容", encoding="utf-8")

    return tmp_path


@pytest.fixture(autouse=True)
def env_override(tmp_vault, monkeypatch):
    """测试时自动将 OBSIDIAN_VAULT 指向临时目录。"""
    monkeypatch.setenv("OBSIDIAN_VAULT", str(tmp_vault))
