"""
agos.frontmatter
───────────────────────
YAML Frontmatter 解析/构建的唯一实现。
消灭 bridge.py 和 stats.py 中的重复 _parse_frontmatter。
"""

import yaml


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    拆分 YAML frontmatter 和正文。

    Returns:
        (frontmatter_dict, body_str)
        如果没有 frontmatter，返回 ({}, 原始内容)
    """
    if not content.startswith("---"):
        return {}, content

    end = content.find("\n---", 3)
    if end == -1:
        return {}, content

    yaml_str = content[3:end].strip()
    body = content[end + 4:].lstrip("\n")

    try:
        fm = yaml.safe_load(yaml_str) or {}
    except yaml.YAMLError:
        fm = {}

    return fm, body


def build_content(frontmatter: dict, body: str) -> str:
    """把 frontmatter dict + body 重新组合成完整笔记字符串。"""
    if not frontmatter:
        return body
    fm_str = yaml.dump(
        frontmatter, allow_unicode=True, default_flow_style=False
    ).rstrip()
    return f"---\n{fm_str}\n---\n\n{body}"
