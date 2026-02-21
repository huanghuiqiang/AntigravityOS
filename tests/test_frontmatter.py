"""agos.frontmatter 单元测试。"""

from agos.frontmatter import parse_frontmatter, build_content


class TestParseFrontmatter:
    def test_normal_yaml(self):
        content = """---
tags:
  - BouncerDump
score: 9.5
status: pending
---

# Title

Body text here.
"""
        fm, body = parse_frontmatter(content)
        assert fm["score"] == 9.5
        assert fm["status"] == "pending"
        assert "BouncerDump" in fm["tags"]
        assert body.startswith("# Title")

    def test_no_frontmatter(self):
        content = "# Just a plain note\nNo YAML here."
        fm, body = parse_frontmatter(content)
        assert fm == {}
        assert body == content

    def test_broken_yaml(self):
        content = "---\n: invalid yaml: [broken\n---\n\nBody"
        fm, body = parse_frontmatter(content)
        assert fm == {}
        assert "Body" in body

    def test_empty_frontmatter(self):
        content = "---\n\n---\n\nBody text"
        fm, body = parse_frontmatter(content)
        assert fm == {}
        assert "Body text" in body

    def test_unclosed_frontmatter(self):
        """只有开头的 --- 没有结尾的 --- 应该返回空 dict。"""
        content = "---\ntags:\n  - Test\nno closing delimiter"
        fm, body = parse_frontmatter(content)
        assert fm == {}


class TestBuildContent:
    def test_roundtrip(self):
        original_fm = {"tags": ["Axiom"], "score": 8.5}
        original_body = "# Test\n\nContent"
        built = build_content(original_fm, original_body)

        fm, body = parse_frontmatter(built)
        assert fm["tags"] == ["Axiom"]
        assert fm["score"] == 8.5
        assert body.strip().startswith("# Test")

    def test_empty_frontmatter(self):
        result = build_content({}, "just body")
        assert result == "just body"

    def test_unicode(self):
        fm = {"title": "认知架构"}
        body = "# 中文内容\n公理提炼"
        built = build_content(fm, body)
        assert "认知架构" in built
        assert "中文内容" in built
