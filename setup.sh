#!/usr/bin/env bash
# paperbutler (纸上管家) deployment helper
# Copyright (C) 2026 The paperbutler Authors
# SPDX-License-Identifier: GPL-3.0-only
#
# 用法：
#   ./setup.sh                          只安装运行必需依赖
#   ./setup.sh --with-token-extractor   额外下载「配置期可选」的 token 导出工具
#
# 生成物（.venv / devices.json / token-extractor）均被 .gitignore 排除，
# 不会污染本仓库。所有 <...> 占位符需按 README 填写。

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
WITH_TOOLS="${1:-}"

echo "==> [1/3] 创建 Python 虚拟环境 .venv/"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
else
  echo "    已存在，跳过"
fi
PY="$ROOT/.venv/bin/python"

echo "==> [2/3] 安装运行依赖（见 requirements.txt）"
"$PY" -m pip install --upgrade pip -q
"$PY" -m pip install -r requirements.txt

echo "==> [3/3] 生成 devices.json 配置模板"
if [ -f devices.json ]; then
  echo "    devices.json 已存在，保留原文件"
else
  cp devices.example.json devices.json
  echo "    已生成 devices.json，请替换其中的 <...> 占位符后再启动"
fi

if [ "$WITH_TOOLS" = "--with-token-extractor" ]; then
  echo "==> [可选] 下载 Xiaomi-cloud-tokens-extractor（MIT，第三方工具）"
  if ! command -v git >/dev/null 2>&1; then
    echo "    未找到 git：请先安装 git，或按 README 的手动方式操作" >&2
    exit 1
  fi
  if [ ! -d token-extractor ]; then
    git clone --depth 1 https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor.git token-extractor
  else
    echo "    token-extractor 已存在，跳过 clone"
  fi
  if [ ! -x token-extractor/.venv/bin/python ]; then
    python3 -m venv token-extractor/.venv
  fi
  token-extractor/.venv/bin/pip install -q -r token-extractor/requirements.txt
  echo "    导出 token：cd token-extractor && .venv/bin/python token_extractor.py -s cn -o tokens.json"
elif [ -n "$WITH_TOOLS" ]; then
  echo "未知参数：$WITH_TOOLS（可用：--with-token-extractor）" >&2
  exit 1
fi

echo
echo "完成。启动：      .venv/bin/python app.py"
echo "本机控制台：      http://127.0.0.1:9090"
echo "设备侧访问地址：  http://<BRIDGE_HOST_IP>:9090  （替换为主机实际局域网 IP，必须用 http://）"
