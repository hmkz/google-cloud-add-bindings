# Google Cloud IAMバインディング追加ツール

このツールは、CSVファイルに基づいてGoogle CloudのIAMユーザーに対してロールを付与するためのユーティリティです。

## 機能

- CSVファイルからIAMユーザー、プロジェクト名、アセットネーム、アセットタイプ、ロール情報を読み込む
- Google Cloud IAM APIを使用して指定されたユーザーにロールを付与する
- 処理結果とエラーのログを出力する
- **アセットタイプとアセットネームの拡張機能**: 独自のアセットタイプを設定ファイルから追加可能

## 前提条件

- Python 3.8以上
- Google Cloudアカウントとプロジェクト
- 適切なIAM権限を持つサービスアカウント

## インストール

### パッケージマネージャー

このプロジェクトは[uv](https://github.com/astral-sh/uv)を使用してパッケージ管理を行います。uvはRustで書かれた高速なPythonパッケージマネージャーで、pipよりも高速に依存関係を解決します。

#### uvのインストール

```bash
# uvのインストール
curl -fsSL https://astral.sh/uv/install.sh | bash
```

#### 開発環境のセットアップ

```bash
# リポジトリをクローン
git clone https://github.com/yourusername/google-cloud-add-bindings.git
cd google-cloud-add-bindings

# 開発環境セットアップスクリプトを実行
./setup_dev_env.sh

# 仮想環境を有効化
source .venv/bin/activate

# Google Cloud認証の設定
gcloud auth application-default login
# または
# サービスアカウントキーを使用する場合
# export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

#### 本番環境へのインストール

```bash
# リポジトリをクローン
git clone https://github.com/yourusername/google-cloud-add-bindings.git
cd google-cloud-add-bindings

# uvで仮想環境を作成
uv venv
source .venv/bin/activate

# 依存関係のインストール
uv pip install -e .
```

## 使用方法

### CSVファイルの形式

以下の形式のCSVファイルを用意してください：

```
user_email,project_id,asset_name,asset_type,role
user@example.com,my-project,//cloudresourcemanager.googleapis.com/projects/my-project,cloudresourcemanager.googleapis.com/Project,roles/viewer
user@example.com,my-project,//storage.googleapis.com/projects/_/buckets/my-bucket,storage.googleapis.com/Bucket,roles/storage.objectViewer
user@example.com,my-project,//bigquery.googleapis.com/projects/my-project/datasets/my_dataset,bigquery.googleapis.com/Dataset,roles/bigquery.dataViewer
```

各カラムの説明：
- `user_email`: IAMユーザーのメールアドレス
- `project_id`: Google Cloudプロジェクト名
- `asset_name`: Google Cloudリソースのアセットネーム（[Cloud Asset Inventory ドキュメント](https://cloud.google.com/asset-inventory/docs/asset-names?hl=ja)参照）
- `asset_type`: リソースのアセットタイプ
- `role`: 付与するIAMロール

### デフォルトでサポートされているアセットタイプ

- `cloudresourcemanager.googleapis.com/Project` - Google Cloudプロジェクト
- `storage.googleapis.com/Bucket` - Cloud Storageバケット
- `bigquery.googleapis.com/Dataset` - BigQueryデータセット

### ツールの実行

```bash
python add_bindings.py --csv-file input.csv [--dry-run] [--credentials /path/to/service-account-key.json] [--config-file /path/to/config.yaml]
```

オプション:
- `--csv-file`: 処理するCSVファイルのパス（必須）
- `--credentials`: Google Cloudサービスアカウントキーファイルのパス（省略時はデフォルト認証情報を使用）
- `--dry-run`: 実際の変更を適用せずに処理をシミュレーションします
- `--config-file`: カスタムアセットタイプの設定ファイルのパス (.json, .yaml, .yml)
- `--export-config`: 現在のアセットタイプ設定をエクスポートするファイルパス
- `--list-asset-types`: サポートされているアセットタイプを表示する

## アセットタイプの拡張

このツールは、JSON/YAML設定ファイルを使用してカスタムアセットタイプを追加することができます。

### 設定ファイルの形式

以下は設定ファイルの例です：

#### JSON形式の例:

```json
{
  "asset_types": [
    {
      "asset_type": "pubsub.googleapis.com/Topic",
      "service_name": "pubsub",
      "version": "v1",
      "method": "setIamPolicy",
      "resource_type": "topic",
      "asset_name_pattern": "//pubsub\\.googleapis\\.com/projects/([^/]+)/topics/([^/]+)"
    },
    {
      "asset_type": "cloudfunctions.googleapis.com/Function",
      "service_name": "cloudfunctions",
      "version": "v1",
      "method": "setIamPolicy",
      "resource_type": "function",
      "asset_name_pattern": "//cloudfunctions\\.googleapis\\.com/projects/([^/]+)/locations/([^/]+)/functions/([^/]+)"
    }
  ]
}
```

#### YAML形式の例:

```yaml
asset_types:
  - asset_type: pubsub.googleapis.com/Topic
    service_name: pubsub
    version: v1
    method: setIamPolicy
    resource_type: topic
    asset_name_pattern: "//pubsub\\.googleapis\\.com/projects/([^/]+)/topics/([^/]+)"
  - asset_type: cloudfunctions.googleapis.com/Function
    service_name: cloudfunctions
    version: v1
    method: setIamPolicy
    resource_type: function
    asset_name_pattern: "//cloudfunctions\\.googleapis\\.com/projects/([^/]+)/locations/([^/]+)/functions/([^/]+)"
```

### 設定項目の説明:

- `asset_type`: アセットタイプの完全修飾名（例: `pubsub.googleapis.com/Topic`）
- `service_name`: Google Cloud APIサービス名（例: `pubsub`）
- `version`: APIバージョン（例: `v1`）
- `method`: IAMポリシー設定メソッド（通常は `setIamPolicy`）
- `resource_type`: リソースタイプの識別子（例: `topic`）
- `asset_name_pattern`: アセットネームの正規表現パターン。カッコでキャプチャするグループを含める必要があります。

### 設定ファイルの使用方法

1. 上記形式の設定ファイルを作成します
2. ツール実行時に `--config-file` オプションで指定します：

```bash
python add_bindings.py --csv-file input.csv --config-file my_asset_types.yaml
```

### 現在の設定のエクスポート

現在のアセットタイプ設定をファイルにエクスポートすることもできます：

```bash
python add_bindings.py --export-config my_config.json
```

これにより、現在読み込まれているすべてのアセットタイプ設定がファイルにエクスポートされます。
ファイル拡張子に応じて自動的にJSON形式またはYAML形式で出力されます。

## プログラムによるアセットタイプの追加

ツールを使用する際に、現在サポートされているアセットタイプを確認するには：

```bash
python add_bindings.py --list-asset-types
```

## テスト

テストを実行するには:

```bash
# 開発環境がセットアップ済みの場合
./run_tests.sh

# または手動で
source .venv/bin/activate
python -m pytest
```

## 開発ガイド

### 開発環境の準備

1. `./setup_dev_env.sh`を実行して開発環境をセットアップ
2. `source .venv/bin/activate`で仮想環境を有効化

### コード品質の確保

このプロジェクトでは以下のツールを使用して品質を確保します：

- **Black**: コードフォーマッター
  ```bash
  black .
  ```

- **isort**: importの整理
  ```bash
  isort .
  ```

- **mypy**: 型チェック
  ```bash
  mypy .
  ```

### パッケージの追加

新しい依存関係を追加するには：

```bash
# 通常の依存関係
uv pip install パッケージ名
```

```bash
# 開発用の依存関係
uv pip install --dev パッケージ名
```

その後、`pyproject.toml`を手動で更新してください。

### デプロイ

新しいバージョンをリリースする際は、`pyproject.toml`のバージョン番号を更新してください。

## トラブルシューティング

- **認証エラー**: `gcloud auth application-default login`を実行して認証情報を更新してください
- **権限エラー**: サービスアカウントに適切なIAM権限があることを確認してください
- **CSV形式エラー**: CSVファイルが正しい形式であることを確認してください
- **アセットネーム形式エラー**: アセットネームが正しい形式であることを確認してください
- **設定ファイルエラー**: 設定ファイルの形式が正しいことを確認してください。パターンは正規表現として有効である必要があります。

## カスタムアセットタイプの追加方法

新しいアセットタイプに対応するために、以下の方法で拡張できます：

1. **設定ファイルによる方法**: 上記の形式で設定ファイルを作成し、実行時に指定する
2. **プログラムによる方法**: `IAMBindingManager`クラスのインスタンスメソッドを使用する

```python
from iam_binding_utils import IAMBindingManager

# マネージャーの初期化
manager = IAMBindingManager()

# 新しいアセットタイプを登録
manager.register_asset_type(
    asset_type='cloudrun.googleapis.com/Service',
    service_name='run',
    version='v1',
    method='setIamPolicy',
    resource_type='service',
    asset_name_pattern=r'//run\.googleapis\.com/projects/([^/]+)/locations/([^/]+)/services/([^/]+)'
)
```

## ライセンス

MIT

## 貢献

プルリクエストや問題報告は歓迎します。 