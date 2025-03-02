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

# 終了時の処理
cleanup() {
    if [ $? -ne 0 ]; then
        log_error "テスト実行中にエラーが発生しました。"
        exit 1
    fi
}

trap cleanup EXIT

# 仮想環境が存在するか確認
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    log_error "仮想環境が見つかりません。セットアップスクリプトを実行してください: ./setup_dev_env.sh"
    exit 1
fi

# 仮想環境をアクティベート
source "$VENV_DIR/bin/activate"
log_info "仮想環境がアクティベートされました。"

# 依存関係の確認
log_info "依存関係を確認しています..."
uv pip install -e ".[dev]" --quiet
if [ $? -ne 0 ]; then
    log_error "依存関係のインストールに失敗しました。"
    exit 1
fi

# 静的解析を実行（オプション）
if [ "$1" == "--full" ]; then
    log_info "コード品質チェックを実行しています..."
    
    log_info "Blackによるフォーマットチェック..."
    black --check . || log_warn "Blackチェックに失敗しました。'black .'を実行してコードをフォーマットしてください。"
    
    log_info "isortによるインポート順序チェック..."
    isort --check . || log_warn "isortチェックに失敗しました。'isort .'を実行してインポートを整理してください。"
    
    log_info "Ruffによるlintチェック..."
    ruff check . || log_warn "Ruffチェックに失敗しました。"
    
    log_info "mypyによる型チェック..."
    mypy google_cloud_add_bindings || log_warn "型チェックに失敗しました。"
    
    log_info "banditによるセキュリティチェック..."
    bandit -r google_cloud_add_bindings -c pyproject.toml || log_warn "セキュリティチェックに失敗しました。"
fi

# テストを実行
log_info "テストを実行しています..."
python -m pytest tests -v --cov=google_cloud_add_bindings --cov-report=term-missing

# 終了コードを保存
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    log_success "全てのテストが完了しました。"
else
    log_error "テストに失敗しました。終了コード: $EXIT_CODE"
fi

# カバレッジレポートを生成（HTMLレポート）
if [ "$1" == "--full" ]; then
    log_info "カバレッジHTMLレポートを生成しています..."
    python -m pytest tests --cov=google_cloud_add_bindings --cov-report=html
    log_success "HTMLレポートが 'htmlcov' ディレクトリに生成されました。"
fi

exit $EXIT_CODE 