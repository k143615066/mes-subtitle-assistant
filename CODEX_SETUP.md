# Codex 首次安装指令

本文件用于同事首次从 GitHub 获取项目时直接交给 Codex。

将下面整段内容复制给 Codex，并附上仓库地址：

```text
请将 https://github.com/k143615066/mes-subtitle-assistant 克隆到我的电脑中一个方便的位置。

这是一个本地运行的 MES 字幕助手。请检查本机是否有 Python 3.10 或更高版本；如果没有，请协助我安装可用的 Python。不要修改项目代码，不要将任何 API Key 写入 Git 或 GitHub。

完成后告诉我项目保存位置，并提示我双击项目根目录中的启动MES字幕助手.bat（Windows）或启动MES字幕助手.command（macOS）。首次启动时由启动器提示我输入自己的 DeepSeek API Key。
```

## 启动器会自动完成的事项

- 首次运行时询问 DeepSeek API Key，并保存到当前电脑的 `.env` 文件。
- 创建项目独立的 Python 虚拟环境。
- 安装运行需要的 Python 依赖。
- 启动本机服务并打开浏览器。

API Key、上传字幕、生成字幕、日志和本地运行环境都被 Git 忽略，不会上传到 GitHub。
