---
description: 通用开发工作流 - 查看文件、运行安全命令自动执行
---

// turbo-all

## 常用安全操作

以下操作均自动执行，无需手动确认：

1. 查看文件内容
```bash
cat <文件路径>
```

2. 列出目录
```bash
ls -la <目录路径>
```

3. 搜索文件内容
```bash
grep -rn "<搜索内容>" <目录>
```

4. 查看 Git 状态
```bash
git status
```

5. 查看 Git 日志
```bash
git log -n 5 --oneline
```

6. 运行测试
```bash
npm test
```

7. 启动开发服务器
```bash
npm run dev
```

8. 安装依赖
```bash
npm install
```

9. 新建/修改文件
这些操作通过 `turbo-all` 授权命令自动执行。对于文件编辑器工具（如 `write_to_file`），我将尽可能：
- **批量合并写入**：一次性写入完整文件或多个相关文件。
- **减少琐碎修改**：避免分多次小幅修改。
- **预先告知**：在执行前简述即将写入的文件及其作用。
```bash
# 自动创建目录
mkdir -p <directory>
```
