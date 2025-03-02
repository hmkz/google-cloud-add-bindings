#!/bin/bash
set -e

# 色の設定
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}===== Google Cloud IAMバインディング追加ツール 開発環境セットアップ =====${NC}"
echo ""

# uvがインストールされているか確認
if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}uvパッケージマネージャーがインストールされていません。インストールします...${NC}"
    curl -fsSL https://astral.sh/uv/install.sh | bash
    
    # シェルを再読み込み
    source ~/.bashrc
    echo -e "${GREEN}uvパッケージマネージャーがインストールされました${NC}"
fi

echo -e "${CYAN}uvのバージョン: $(uv --version)${NC}"
echo ""

# 仮想環境の作成
echo -e "${YELLOW}仮想環境を作成しています...${NC}"
uv venv
source .venv/bin/activate

# 依存関係のインストール
echo -e "${YELLOW}依存関係をインストールしています...${NC}"
uv pip install -e ".[dev]"

echo -e "${GREEN}開発環境のセットアップが完了しました！${NC}"
echo ""
echo -e "以下のコマンドで仮想環境を有効化してください:"
echo -e "${CYAN}source .venv/bin/activate${NC}"
echo ""
echo -e "テストを実行するには:"
echo -e "${CYAN}pytest${NC}"
echo ""
echo -e "コード整形を実行するには:"
echo -e "${CYAN}black .${NC}"
echo -e "${CYAN}isort .${NC}"
echo -e ""
echo -e "型チェックを実行するには:"
echo -e "${CYAN}mypy .${NC}" 