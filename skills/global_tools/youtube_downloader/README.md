# YouTube Downloader Skill

## 指令定义 (Agent Instructions)
当你识别到用户提到 YouTube 链接并需要分析内容时，请调用本工具。

## 执行命令
```bash
python3 Agents/GlobalTools/youtube_downloader/extractor.py "<YOUTUBE_URL>" <format:txt|srt> <lang:en|zh>
```

## 输出格式
本工具输出标准 JSON：
- `success`: bool
- `filepath`: 文件生成的绝对路径
- `video_id`: 视频 ID

## 存储行为
所有文件将自动存入 `Agents/GlobalDownloads/` 文件夹。
