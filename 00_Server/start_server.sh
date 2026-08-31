#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if curl -fsS --max-time 2 "http://127.0.0.1:15000/" >/dev/null 2>&1; then
    echo "MES字幕助手已经在运行，正在打开浏览器。"
    open "http://127.0.0.1:15000"
    exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "未检测到 Python 3。请安装 Python 3.10 或更高版本后重新运行本文件。"
    echo "也可以将此提示发给 Codex，请它协助完成本机环境安装。"
    read -r -p "按回车键退出..."
    exit 1
fi

ENV_FILE="$SCRIPT_DIR/../.env"
HAS_API_KEY=0
if [ -f "$ENV_FILE" ] && grep -q '^DeepSeek_Key=.' "$ENV_FILE"; then
    HAS_API_KEY=1
fi

if [ "$HAS_API_KEY" -eq 0 ]; then
    echo "首次启动需要配置 DeepSeek API Key。"
    read -r -s -p "请粘贴 DeepSeek API Key，然后按回车: " DEEPSEEK_KEY
    echo
    if [ -z "$DEEPSEEK_KEY" ]; then
        echo "未输入 API Key，无法启动。"
        read -r -p "按回车键退出..."
        exit 1
    fi
    {
        echo "# 本机配置文件，请勿上传到 GitHub。"
        echo "DeepSeek_Key=$DEEPSEEK_KEY"
        echo
        echo "MES_ENABLE_ENGLISH_REFLOW=1"
    } > "$ENV_FILE"
    echo "本机 API Key 配置已保存。"
fi

if [ ! -x ".venv/bin/python" ]; then
    echo "正在创建本机运行环境，请稍候..."
    python3 -m venv .venv
fi

.venv/bin/python -m pip install -r app/requirements.txt

while IFS='=' read -r setting value; do
    case "$setting" in
        DeepSeek_Key|MES_ENABLE_ENGLISH_REFLOW)
            export "$setting=$value"
            ;;
    esac
done < "$ENV_FILE"

echo "MES字幕助手正在启动..."
echo "浏览器将打开：http://127.0.0.1:15000"

(sleep 2; open "http://127.0.0.1:15000") &

cd app
exec ../.venv/bin/python main.py
