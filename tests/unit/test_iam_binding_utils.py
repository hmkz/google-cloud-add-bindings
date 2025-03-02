#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
IAMバインディングユーティリティのテスト
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
import yaml

from google_cloud_add_bindings.core.iam_binding_utils import IAMBindingManager


class TestIAMBindingManager:
    """IAMBindingManagerクラスのテスト"""

    @pytest.fixture
    def iam_manager(self):
        """IAMBindingManagerのインスタンスを取得するフィクスチャ"""
        return IAMBindingManager()

    @pytest.fixture
    def custom_config_json(self):
        """カスタム設定ファイル（JSON）を作成するフィクスチャ"""
        config = {
            "asset_types": [
                {
                    "asset_type": "pubsub.googleapis.com/Topic",
                    "service_name": "pubsub",
                    "version": "v1",
                    "method": "setIamPolicy",
                    "resource_type": "topic",
                    "asset_name_pattern": r"//pubsub\.googleapis\.com/projects/([^/]+)/topics/([^/]+)",
                },
                {
                    "asset_type": "cloudfunctions.googleapis.com/Function",
                    "service_name": "cloudfunctions",
                    "version": "v1",
                    "method": "setIamPolicy",
                    "resource_type": "function",
                    "asset_name_pattern": r"//cloudfunctions\.googleapis\.com/projects/([^/]+)/locations/([^/]+)/functions/([^/]+)",
                },
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            json.dump(config, f)

        yield f.name
        os.unlink(f.name)

    @pytest.fixture
    def custom_config_yaml(self):
        """カスタム設定ファイル（YAML）を作成するフィクスチャ"""
        config = {
            "asset_types": [
                {
                    "asset_type": "pubsub.googleapis.com/Subscription",
                    "service_name": "pubsub",
                    "version": "v1",
                    "method": "setIamPolicy",
                    "resource_type": "subscription",
                    "asset_name_pattern": r"//pubsub\.googleapis\.com/projects/([^/]+)/subscriptions/([^/]+)",
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            yaml.dump(config, f)

        yield f.name
        os.unlink(f.name)

    @patch(
        "google_cloud_add_bindings.core.iam_binding_utils.service_account.Credentials.from_service_account_file"
    )
    def test_init_with_credentials(self, mock_from_service_account_file):
        """認証情報を指定して初期化するテスト"""
        mock_from_service_account_file.return_value = MagicMock()

        manager = IAMBindingManager(credentials_path="test-key.json")

        assert manager.credentials is not None
        mock_from_service_account_file.assert_called_once_with(
            "test-key.json", scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )

    def test_init_without_credentials(self):
        """認証情報を指定せずに初期化するテスト"""
        manager = IAMBindingManager()

        assert manager.credentials is None

        # デフォルト設定が読み込まれていることを確認
        assert (
            "cloudresourcemanager.googleapis.com/Project" in manager.asset_type_mapping
        )
        assert "storage.googleapis.com/Bucket" in manager.asset_type_mapping
        assert "bigquery.googleapis.com/Dataset" in manager.asset_type_mapping

    def test_load_config_json(self, custom_config_json):
        """JSONファイルから設定を読み込むテスト"""
        manager = IAMBindingManager(config_file=custom_config_json)

        # カスタム設定が読み込まれていることを確認
        assert "pubsub.googleapis.com/Topic" in manager.asset_type_mapping
        assert "cloudfunctions.googleapis.com/Function" in manager.asset_type_mapping

        # Topicの設定を確認
        topic_config = manager.asset_type_mapping["pubsub.googleapis.com/Topic"]
        assert topic_config["service_name"] == "pubsub"
        assert topic_config["version"] == "v1"
        assert topic_config["method"] == "setIamPolicy"
        assert topic_config["resource_type"] == "topic"

        # パターンが設定されていることを確認
        assert "pubsub.googleapis.com/Topic" in manager.asset_name_patterns
        assert manager.asset_name_patterns["pubsub.googleapis.com/Topic"] != ""

    def test_load_config_yaml(self, custom_config_yaml):
        """YAMLファイルから設定を読み込むテスト"""
        manager = IAMBindingManager(config_file=custom_config_yaml)

        # カスタム設定が読み込まれていることを確認
        assert "pubsub.googleapis.com/Subscription" in manager.asset_type_mapping

        # Subscriptionの設定を確認
        subscription_config = manager.asset_type_mapping[
            "pubsub.googleapis.com/Subscription"
        ]
        assert subscription_config["service_name"] == "pubsub"
        assert subscription_config["version"] == "v1"
        assert subscription_config["method"] == "setIamPolicy"
        assert subscription_config["resource_type"] == "subscription"

    def test_register_asset_type(self, iam_manager):
        """新しいアセットタイプを登録するテスト"""
        # 新しいアセットタイプを登録
        iam_manager.register_asset_type(
            asset_type="cloudrun.googleapis.com/Service",
            service_name="run",
            version="v1",
            method="setIamPolicy",
            resource_type="service",
            asset_name_pattern=r"//run\.googleapis\.com/projects/([^/]+)/locations/([^/]+)/services/([^/]+)",
        )

        # 登録されたことを確認
        assert "cloudrun.googleapis.com/Service" in iam_manager.asset_type_mapping
        assert "cloudrun.googleapis.com/Service" in iam_manager.asset_name_patterns

        # 設定内容を確認
        config = iam_manager.asset_type_mapping["cloudrun.googleapis.com/Service"]
        assert config["service_name"] == "run"
        assert config["version"] == "v1"
        assert config["method"] == "setIamPolicy"
        assert config["resource_type"] == "service"

    def test_update_asset_pattern(self, iam_manager):
        """アセットパターンを更新するテスト"""
        # 既存のパターンを取得
        old_pattern = iam_manager.get_asset_pattern_for_type(
            "storage.googleapis.com/Bucket"
        )
        assert old_pattern is not None

        # パターンを更新
        new_pattern = r"//storage\.googleapis\.com/buckets/([^/]+)"
        iam_manager.update_asset_pattern("storage.googleapis.com/Bucket", new_pattern)

        # 更新されたことを確認
        updated_pattern = iam_manager.get_asset_pattern_for_type(
            "storage.googleapis.com/Bucket"
        )
        assert updated_pattern == new_pattern
        assert updated_pattern != old_pattern

    def test_delete_asset_type(self, iam_manager):
        """アセットタイプを削除するテスト"""
        # 削除前に存在することを確認
        assert "storage.googleapis.com/Bucket" in iam_manager.asset_type_mapping

        # アセットタイプを削除
        iam_manager.delete_asset_type("storage.googleapis.com/Bucket")

        # 削除されたことを確認
        assert "storage.googleapis.com/Bucket" not in iam_manager.asset_type_mapping
        assert "storage.googleapis.com/Bucket" not in iam_manager.asset_name_patterns

    def test_delete_nonexistent_asset_type(self, iam_manager):
        """存在しないアセットタイプを削除しようとするテスト"""
        with pytest.raises(ValueError, match="アセットタイプが存在しません"):
            iam_manager.delete_asset_type("nonexistent.googleapis.com/Type")

    def test_update_nonexistent_asset_pattern(self, iam_manager):
        """存在しないアセットタイプのパターンを更新しようとするテスト"""
        with pytest.raises(ValueError, match="アセットタイプが存在しません"):
            iam_manager.update_asset_pattern(
                "nonexistent.googleapis.com/Type",
                r"//nonexistent\.googleapis\.com/([^/]+)",
            )

    def test_list_supported_asset_types(self, iam_manager):
        """サポートされているアセットタイプのリストを取得するテスト"""
        types = iam_manager.list_supported_asset_types()

        # デフォルトでサポートされているタイプを確認
        assert "cloudresourcemanager.googleapis.com/Project" in types
        assert "storage.googleapis.com/Bucket" in types
        assert "bigquery.googleapis.com/Dataset" in types

    @patch("json.dump")
    def test_export_config_json(self, mock_json_dump, iam_manager, tmp_path):
        """設定をJSONファイルにエクスポートするテスト"""
        # テンポラリファイルパスを作成
        config_file = tmp_path / "config.json"

        # 設定をエクスポート
        iam_manager.export_config(str(config_file))

        # json.dumpが呼ばれたことを確認
        mock_json_dump.assert_called_once()

        # 第1引数（エクスポートされた設定）が期待通りの構造を持つことを確認
        exported_config = mock_json_dump.call_args[0][0]
        assert "asset_types" in exported_config
        assert isinstance(exported_config["asset_types"], list)

        # 少なくともいくつかのアセットタイプが含まれていることを確認
        asset_types = [item["asset_type"] for item in exported_config["asset_types"]]
        assert "cloudresourcemanager.googleapis.com/Project" in asset_types
        assert "storage.googleapis.com/Bucket" in asset_types
        assert "bigquery.googleapis.com/Dataset" in asset_types

    @patch("yaml.dump")
    def test_export_config_yaml(self, mock_yaml_dump, iam_manager, tmp_path):
        """設定をYAMLファイルにエクスポートするテスト"""
        # テンポラリファイルパスを作成
        config_file = tmp_path / "config.yaml"

        # 設定をエクスポート
        iam_manager.export_config(str(config_file))

        # yaml.dumpが呼ばれたことを確認
        mock_yaml_dump.assert_called_once()

        # 第1引数（エクスポートされた設定）が期待通りの構造を持つことを確認
        exported_config = mock_yaml_dump.call_args[0][0]
        assert "asset_types" in exported_config

    def test_export_config_invalid_extension(self, iam_manager, tmp_path):
        """無効な拡張子の設定ファイルにエクスポートしようとするテスト"""
        config_file = tmp_path / "config.txt"

        with pytest.raises(ValueError, match="サポートされていない設定ファイル形式"):
            iam_manager.export_config(str(config_file))

    def test_unsupported_asset_type(self, iam_manager):
        """サポートされていないアセットタイプのテスト"""
        with pytest.raises(ValueError, match="サポートされていないアセットタイプ"):
            iam_manager.get_current_policy(
                asset_name="//invalid.googleapis.com/projects/test-project",
                asset_type="invalid.googleapis.com/Project",
                project_id="test-project",
            )

        with pytest.raises(ValueError, match="サポートされていないアセットタイプ"):
            iam_manager.add_binding(
                user_email="user@example.com",
                role="roles/viewer",
                asset_name="//invalid.googleapis.com/projects/test-project",
                asset_type="invalid.googleapis.com/Project",
                project_id="test-project",
            )

    def test_parse_asset_name(self, iam_manager):
        """アセットネーム解析のテスト"""
        # プロジェクト
        result = iam_manager.parse_asset_name(
            "//cloudresourcemanager.googleapis.com/projects/test-project",
            "cloudresourcemanager.googleapis.com/Project",
        )
        assert result["project_id"] == "test-project"

        # バケット
        result = iam_manager.parse_asset_name(
            "//storage.googleapis.com/projects/_/buckets/test-bucket",
            "storage.googleapis.com/Bucket",
        )
        assert result["bucket_name"] == "test-bucket"

        # データセット
        result = iam_manager.parse_asset_name(
            "//bigquery.googleapis.com/projects/test-project/datasets/test_dataset",
            "bigquery.googleapis.com/Dataset",
        )
        assert result["project_id"] == "test-project"
        assert result["dataset_id"] == "test_dataset"

    def test_parse_custom_asset_name(self, iam_manager):
        """カスタムアセットタイプのアセットネーム解析テスト"""
        # カスタムアセットタイプを登録
        iam_manager.register_asset_type(
            asset_type="pubsub.googleapis.com/Topic",
            service_name="pubsub",
            version="v1",
            method="setIamPolicy",
            resource_type="topic",
            asset_name_pattern=r"//pubsub\.googleapis\.com/projects/([^/]+)/topics/([^/]+)",
        )

        # カスタムアセットネームの解析
        result = iam_manager.parse_asset_name(
            "//pubsub.googleapis.com/projects/test-project/topics/test-topic",
            "pubsub.googleapis.com/Topic",
        )

        # リソース情報が抽出されていることを確認
        assert "resource_1" in result
        assert "resource_2" in result
        assert result["resource_1"] == "test-project"
        assert result["resource_2"] == "test-topic"

    def test_invalid_asset_name(self, iam_manager):
        """無効なアセットネーム形式のテスト"""
        with pytest.raises(ValueError, match="無効なアセットネーム形式"):
            iam_manager.parse_asset_name(
                "invalid-format", "cloudresourcemanager.googleapis.com/Project"
            )

    @patch(
        "google_cloud_add_bindings.core.iam_binding_utils.IAMBindingManager.get_client"
    )
    def test_get_current_policy_project(self, mock_get_client, iam_manager):
        """プロジェクトのIAMポリシー取得テスト"""
        mock_client = MagicMock()
        mock_projects = MagicMock()
        mock_get_iam_policy = MagicMock()

        mock_get_client.return_value = mock_client
        mock_client.projects.return_value = mock_projects
        mock_projects.getIamPolicy.return_value = mock_get_iam_policy
        mock_get_iam_policy.execute.return_value = {"bindings": []}

        policy = iam_manager.get_current_policy(
            asset_name="//cloudresourcemanager.googleapis.com/projects/test-project",
            asset_type="cloudresourcemanager.googleapis.com/Project",
            project_id="test-project",
        )

        mock_get_client.assert_called_once_with("cloudresourcemanager", "v1")
        mock_projects.getIamPolicy.assert_called_once_with(
            resource="test-project", body={}
        )
        assert policy == {"bindings": []}

    @patch(
        "google_cloud_add_bindings.core.iam_binding_utils.IAMBindingManager.get_client"
    )
    def test_get_current_policy_bucket(self, mock_get_client, iam_manager):
        """バケットのIAMポリシー取得テスト"""
        mock_client = MagicMock()
        mock_buckets = MagicMock()
        mock_get_iam_policy = MagicMock()

        mock_get_client.return_value = mock_client
        mock_client.buckets.return_value = mock_buckets
        mock_buckets.getIamPolicy.return_value = mock_get_iam_policy
        mock_get_iam_policy.execute.return_value = {"bindings": []}

        policy = iam_manager.get_current_policy(
            asset_name="//storage.googleapis.com/projects/_/buckets/test-bucket",
            asset_type="storage.googleapis.com/Bucket",
            project_id="test-project",
        )

        mock_get_client.assert_called_once_with("storage", "v1")
        mock_buckets.getIamPolicy.assert_called_once_with(bucket="test-bucket")
        assert policy == {"bindings": []}

    @patch(
        "google_cloud_add_bindings.core.iam_binding_utils.IAMBindingManager.get_client"
    )
    def test_get_current_policy_dataset(self, mock_get_client, iam_manager):
        """データセットのIAMポリシー取得テスト"""
        mock_client = MagicMock()
        mock_datasets = MagicMock()
        mock_get = MagicMock()

        mock_get_client.return_value = mock_client
        mock_client.datasets.return_value = mock_datasets
        mock_datasets.get.return_value = mock_get
        mock_get.execute.return_value = {"access": []}

        policy = iam_manager.get_current_policy(
            asset_name="//bigquery.googleapis.com/projects/test-project/datasets/test_dataset",
            asset_type="bigquery.googleapis.com/Dataset",
            project_id="test-project",
        )

        mock_get_client.assert_called_once_with("bigquery", "v2")
        mock_datasets.get.assert_called_once_with(
            projectId="test-project", datasetId="test_dataset"
        )
        assert policy == []

    @patch(
        "google_cloud_add_bindings.core.iam_binding_utils.IAMBindingManager.get_current_policy"
    )
    @patch(
        "google_cloud_add_bindings.core.iam_binding_utils.IAMBindingManager.get_client"
    )
    def test_add_binding_project(
        self, mock_get_client, mock_get_current_policy, iam_manager
    ):
        """プロジェクトへのIAMバインディング追加テスト"""
        # モックの設定
        mock_get_current_policy.return_value = {
            "version": 1,
            "etag": "test-etag",
            "bindings": [
                {"role": "roles/editor", "members": ["user:existing@example.com"]}
            ],
        }

        mock_client = MagicMock()
        mock_projects = MagicMock()
        mock_set_iam_policy = MagicMock()

        mock_get_client.return_value = mock_client
        mock_client.projects.return_value = mock_projects
        mock_projects.setIamPolicy.return_value = mock_set_iam_policy
        mock_set_iam_policy.execute.return_value = {"done": True}

        # 新しいロールの追加
        success, response = iam_manager.add_binding(
            user_email="user@example.com",
            role="roles/viewer",
            asset_name="//cloudresourcemanager.googleapis.com/projects/test-project",
            asset_type="cloudresourcemanager.googleapis.com/Project",
            project_id="test-project",
        )

        assert success is True
        mock_get_current_policy.assert_called_once()
        mock_projects.setIamPolicy.assert_called_once()

        # 呼び出し引数の検証
        call_args = mock_projects.setIamPolicy.call_args[1]
        assert call_args["resource"] == "test-project"

        policy = call_args["body"]["policy"]
        assert policy["version"] == 1
        assert policy["etag"] == "test-etag"

        # 新しいロールが追加されたことを確認
        roles = {binding["role"]: binding["members"] for binding in policy["bindings"]}
        assert "roles/viewer" in roles
        assert "user:user@example.com" in roles["roles/viewer"]
        assert "roles/editor" in roles
        assert "user:existing@example.com" in roles["roles/editor"]

    @patch(
        "google_cloud_add_bindings.core.iam_binding_utils.IAMBindingManager.get_current_policy"
    )
    @patch(
        "google_cloud_add_bindings.core.iam_binding_utils.IAMBindingManager.get_client"
    )
    def test_add_binding_bucket(
        self, mock_get_client, mock_get_current_policy, iam_manager
    ):
        """バケットへのIAMバインディング追加テスト"""
        # モックの設定
        mock_get_current_policy.return_value = {
            "kind": "storage#policy",
            "bindings": [],
        }

        mock_client = MagicMock()
        mock_buckets = MagicMock()
        mock_set_iam_policy = MagicMock()

        mock_get_client.return_value = mock_client
        mock_client.buckets.return_value = mock_buckets
        mock_buckets.setIamPolicy.return_value = mock_set_iam_policy
        mock_set_iam_policy.execute.return_value = {"done": True}

        success, response = iam_manager.add_binding(
            user_email="user@example.com",
            role="roles/storage.objectViewer",
            asset_name="//storage.googleapis.com/projects/_/buckets/test-bucket",
            asset_type="storage.googleapis.com/Bucket",
            project_id="test-project",
        )

        assert success is True
        mock_get_current_policy.assert_called_once()
        mock_buckets.setIamPolicy.assert_called_once()

        # 呼び出し引数の検証
        call_args = mock_buckets.setIamPolicy.call_args[1]
        assert call_args["bucket"] == "test-bucket"

        policy = call_args["body"]
        assert policy["kind"] == "storage#policy"

        # 新しいロールが追加されたことを確認
        roles = {binding["role"]: binding["members"] for binding in policy["bindings"]}
        assert "roles/storage.objectViewer" in roles
        assert "user:user@example.com" in roles["roles/storage.objectViewer"]

    @patch(
        "google_cloud_add_bindings.core.iam_binding_utils.IAMBindingManager.get_current_policy"
    )
    @patch(
        "google_cloud_add_bindings.core.iam_binding_utils.IAMBindingManager.get_client"
    )
    def test_add_binding_dataset(
        self, mock_get_client, mock_get_current_policy, iam_manager
    ):
        """データセットへのIAMバインディング追加テスト"""
        # モックの設定
        mock_get_current_policy.return_value = []

        mock_client = MagicMock()
        mock_datasets = MagicMock()
        mock_patch = MagicMock()

        mock_get_client.return_value = mock_client
        mock_client.datasets.return_value = mock_datasets
        mock_datasets.patch.return_value = mock_patch
        mock_patch.execute.return_value = {"done": True}

        success, response = iam_manager.add_binding(
            user_email="user@example.com",
            role="roles/bigquery.dataViewer",
            asset_name="//bigquery.googleapis.com/projects/test-project/datasets/test_dataset",
            asset_type="bigquery.googleapis.com/Dataset",
            project_id="test-project",
        )

        assert success is True
        mock_get_current_policy.assert_called_once()
        mock_datasets.patch.assert_called_once()

        # 呼び出し引数の検証
        call_args = mock_datasets.patch.call_args[1]
        assert call_args["projectId"] == "test-project"
        assert call_args["datasetId"] == "test_dataset"

        access = call_args["body"]["access"]
        assert len(access) == 1
        assert (
            access[0]["role"] == "dataViewer"
        )  # roles/bigquery.dataViewer -> dataViewer
        assert access[0]["userByEmail"] == "user@example.com"

    def test_dry_run(self, iam_manager):
        """ドライランモードのテスト"""
        with patch(
            "google_cloud_add_bindings.core.iam_binding_utils.IAMBindingManager.get_current_policy"
        ) as mock_get_policy:
            mock_get_policy.return_value = {"bindings": []}

            success, response = iam_manager.add_binding(
                user_email="user@example.com",
                role="roles/viewer",
                asset_name="//cloudresourcemanager.googleapis.com/projects/test-project",
                asset_type="cloudresourcemanager.googleapis.com/Project",
                project_id="test-project",
                dry_run=True,
            )

            assert success is True
            assert response is None
            mock_get_policy.assert_called_once()
