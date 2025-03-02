#!/bin/bash
set -e

# 色の設定
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}===== Google Cloud IAMバインディング追加ツール テスト実行 =====${NC}"
echo ""

# 仮想環境が存在するか確認
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}仮想環境が見つかりません。setup_dev_env.shを実行してください。${NC}"
    exit 1
fi

# 仮想環境を有効化
source .venv/bin/activate

# 必要な依存関係を確認
echo -e "${YELLOW}依存関係を確認しています...${NC}"
uv pip install -e ".[dev]"

# テストを実行
echo -e "${YELLOW}テストを実行しています...${NC}"
python -m pytest -v

if [ $? -eq 0 ]; then
    echo -e "${GREEN}全てのテストが完了しました。終了コード: 0${NC}"
else
    echo -e "${YELLOW}テストに失敗しました。終了コード: $?${NC}"
fi 