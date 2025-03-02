#!/bin/bash

# 色の定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ログ出力関数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# uvのインストール確認
if ! command -v uv &> /dev/null; then
    log_info "uvがインストールされていません。インストールします..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    if [ $? -ne 0 ]; then
        log_error "uvのインストールに失敗しました。https://github.com/astral-sh/uv を参照してください。"
        exit 1
    fi
    log_success "uvがインストールされました。"
    # シェル環境を更新
    if [ -f "$HOME/.bashrc" ]; then
        source "$HOME/.bashrc"
    fi
    if [ -f "$HOME/.zshrc" ]; then
        source "$HOME/.zshrc"
    fi
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# 仮想環境名
VENV_DIR=".venv"

# 仮想環境の作成
if [ ! -d "$VENV_DIR" ]; then
    log_info "仮想環境を作成しています..."
    uv venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        log_error "仮想環境の作成に失敗しました。"
        exit 1
    fi
    log_success "仮想環境が作成されました。"
else
    log_info "仮想環境はすでに存在しています。"
fi

# 仮想環境をアクティベート
source "$VENV_DIR/bin/activate"
log_info "仮想環境がアクティベートされました。"

# 依存関係のインストール
log_info "依存関係をインストールしています..."
uv pip install -e ".[dev]"
if [ $? -ne 0 ]; then
    log_error "依存関係のインストールに失敗しました。"
    exit 1
fi
log_success "依存関係がインストールされました。"

# Git pre-commit hookのセットアップ
if [ -d ".git" ]; then
    log_info "Git pre-commit hookを設定しています..."
    
    # pre-commitフックディレクトリが存在することを確認
    if [ ! -d ".git/hooks" ]; then
        mkdir -p .git/hooks
    fi
    
    # pre-commitフックを作成
    cat > .git/hooks/pre-commit << 'EOF'
#!/bin/bash
set -e

# 仮想環境をアクティベート
source .venv/bin/activate

# コードフォーマット
# echo "Running Black code formatter..."
# black .

echo "Running isort import sorter..."
isort .

# コード品質チェック
echo "Running Ruff linter..."
ruff check .

# 型チェック
echo "Running mypy type checker..."
mypy google_cloud_add_bindings

# セキュリティチェック
echo "Running bandit security checker..."
bandit -r google_cloud_add_bindings -c pyproject.toml

# 変更されたファイルをステージング
git add -u
EOF
    
    # pre-commitフックに実行権限を付与
    chmod +x .git/hooks/pre-commit
    
    log_success "Git pre-commit hookが設定されました。"
else
    log_warn "Gitリポジトリが見つかりません。pre-commit hookは設定されませんでした。"
fi

# VSCode設定の生成（もし必要なら）
if [ ! -d ".vscode" ]; then
    log_info "VSCode設定ディレクトリを作成しています..."
    mkdir -p .vscode
    
    # settings.jsonの作成
    cat > .vscode/settings.json << 'EOF'
{
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.mypyEnabled": true,
    "python.linting.banditEnabled": true,
    "python.formatting.provider": "none",
    "editor.formatOnSave": false,
    "editor.codeActionsOnSave": {
        "source.organizeImports": true
    },
    "python.testing.pytestEnabled": true,
    "python.testing.unittestEnabled": false,
    "python.testing.nosetestsEnabled": false,
    "python.testing.pytestArgs": [
        "tests"
    ]
}
EOF
    
    log_success "VSCode設定が生成されました。"
fi

log_success "開発環境のセットアップが完了しました。"
log_info "仮想環境を有効化するには: source $VENV_DIR/bin/activate"
log_info "テストを実行するには: ./run_tests.sh"
log_info "コードをフォーマットするには: isort ." 