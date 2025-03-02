#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
IAM権限追加のためのユーティリティモジュール
"""

import csv
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Pattern, Tuple, Union

import googleapiclient.discovery
import pandas as pd
import yaml
from google.oauth2 import service_account

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("iam_bindings.log"), logging.StreamHandler()],
)
logger = logging.getLogger("IAMBindingManager")


class IAMBindingManager:
    """
    Google CloudのIAMバインディングを管理するクラス
    """

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        config_file: Optional[str] = None,
        verbose: bool = False,
    ):
        """
        IAMBindingManagerを初期化します。

        Args:
            credentials_path: サービスアカウントキーファイルへのパス
            config_file: アセットタイプの設定ファイルへのパス（指定しない場合はデフォルト設定が使用されます）
            verbose: 詳細なログ出力を有効にするフラグ
        """
        self.credentials_path = credentials_path
        self.config_file = config_file
        self.verbose = verbose

        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)

        # 認証情報
        self.credentials = None
        if credentials_path:
            try:
                self.credentials = (
                    service_account.Credentials.from_service_account_file(
                        credentials_path,
                        scopes=["https://www.googleapis.com/auth/cloud-platform"],
                    )
                )
                logger.info(f"認証情報を読み込みました: {credentials_path}")
            except Exception as e:
                logger.error(f"認証情報の読み込み中にエラーが発生しました: {str(e)}")

        # アセットタイプの設定
        self.asset_type_mapping = {}
        self.asset_name_patterns = {}
        self._load_default_config()

        if config_file and os.path.exists(config_file):
            self._load_config_from_file(config_file)

        # サービスクライアント
        self.clients = {}

    def _load_default_config(self):
        """
        デフォルトの資産タイプ設定を読み込みます。
        """
        default_configs = [
            {
                "asset_type": "cloudresourcemanager.googleapis.com/Project",
                "service_name": "cloudresourcemanager",
                "version": "v1",
                "method": "setIamPolicy",
                "resource_type": "project",
                "asset_name_pattern": r"//cloudresourcemanager\.googleapis\.com/projects/([^/]+)",
            },
            {
                "asset_type": "storage.googleapis.com/Bucket",
                "service_name": "storage",
                "version": "v1",
                "method": "setIamPolicy",
                "resource_type": "bucket",
                "asset_name_pattern": r"//storage\.googleapis\.com/projects/_/buckets/([^/]+)",
            },
            {
                "asset_type": "bigquery.googleapis.com/Dataset",
                "service_name": "bigquery",
                "version": "v2",
                "method": "patch",
                "resource_type": "dataset",
                "asset_name_pattern": r"//bigquery\.googleapis\.com/projects/([^/]+)/datasets/([^/]+)",
            },
            {
                "asset_type": "bigquery.googleapis.com/Table",
                "service_name": "bigquery",
                "version": "v2",
                "method": "patch",
                "resource_type": "table",
                "asset_name_pattern": r"//bigquery\.googleapis\.com/projects/([^/]+)/datasets/([^/]+)/tables/([^/]+)",
            },
            {
                "asset_type": "bigquery.googleapis.com/Model",
                "service_name": "bigquery",
                "version": "v2",
                "method": "patch",
                "resource_type": "model",
                "asset_name_pattern": r"//bigquery\.googleapis\.com/projects/([^/]+)/datasets/([^/]+)/models/([^/]+)",
            },
            {
                "asset_type": "bigquery.googleapis.com/Routine",
                "service_name": "bigquery",
                "version": "v2",
                "method": "patch",
                "resource_type": "routine",
                "asset_name_pattern": r"//bigquery\.googleapis\.com/projects/([^/]+)/datasets/([^/]+)/routines/([^/]+)",
            },
        ]

        for config in default_configs:
            self.register_asset_type(
                asset_type=config["asset_type"],
                service_name=config["service_name"],
                version=config["version"],
                method=config["method"],
                resource_type=config["resource_type"],
                asset_name_pattern=config["asset_name_pattern"],
            )

    def _load_config_from_file(self, config_file: str):
        """
        設定ファイルからアセットタイプの設定を読み込みます。

        Args:
            config_file: 設定ファイルのパス
        """
        logger.info(f"設定ファイルを読み込んでいます: {config_file}")

        try:
            config_data = None

            if config_file.endswith(".json"):
                with open(config_file, "r") as f:
                    config_data = json.load(f)
            elif config_file.endswith(".yaml") or config_file.endswith(".yml"):
                with open(config_file, "r") as f:
                    config_data = yaml.safe_load(f)
            else:
                logger.error(f"サポートされていないファイル形式です: {config_file}")
                return

            if not config_data or "asset_types" not in config_data:
                logger.error(
                    f"設定ファイルに有効なasset_typesが含まれていません: {config_file}"
                )
                return

            for asset_config in config_data["asset_types"]:
                if "asset_type" not in asset_config:
                    logger.warning("asset_typeが指定されていない設定をスキップします")
                    continue

                self.register_asset_type(
                    asset_type=asset_config["asset_type"],
                    service_name=asset_config.get("service_name", ""),
                    version=asset_config.get("version", "v1"),
                    method=asset_config.get("method", "setIamPolicy"),
                    resource_type=asset_config.get("resource_type", ""),
                    asset_name_pattern=asset_config.get("asset_name_pattern", ""),
                )

            logger.info(
                f"設定ファイルからアセットタイプを読み込みました: {len(config_data['asset_types'])}個"
            )

        except Exception as e:
            logger.error(f"設定ファイルの読み込み中にエラーが発生しました: {str(e)}")
            raise

    def register_asset_type(
        self,
        asset_type: str,
        service_name: str,
        version: str,
        method: str,
        resource_type: str,
        asset_name_pattern: str,
    ):
        """
        新しいアセットタイプをIAMバインディングマネージャーに登録します。

        Args:
            asset_type: 登録するアセットタイプ識別子（例：'storage.googleapis.com/Bucket'）
            service_name: APIサービス名（例：'storage'）
            version: APIバージョン（例：'v1'）
            method: IAMポリシーを設定するメソッド名（例：'setIamPolicy'）
            resource_type: リソースタイプ（例：'bucket'）
            asset_name_pattern: アセット名の正規表現パターン
        """
        self.asset_type_mapping[asset_type] = {
            "service_name": service_name,
            "version": version,
            "method": method,
            "resource_type": resource_type,
        }

        try:
            self.asset_name_patterns[asset_type] = asset_name_pattern
            logger.debug(f"アセットタイプを登録しました: {asset_type}")
        except Exception as e:
            logger.error(f"アセットタイプの登録中にエラーが発生しました: {str(e)}")
            del self.asset_type_mapping[asset_type]

    def get_client(self, service: str, version: str) -> Optional[Any]:
        """
        指定されたサービスとバージョンのAPIクライアントを取得します。

        Args:
            service: APIサービス名（例：'storage'）
            version: APIバージョン（例：'v1'）

        Returns:
            APIクライアントオブジェクト、エラー時はNone
        """
        cache_key = f"{service}_{version}"
        if cache_key in self.clients:
            return self.clients[cache_key]

        try:
            client = googleapiclient.discovery.build(
                service, version, credentials=self.credentials, cache_discovery=False
            )
            self.clients[cache_key] = client
            return client
        except Exception as e:
            logger.error(f"APIクライアントの作成中にエラーが発生しました: {str(e)}")
            return None

    def parse_asset_name(self, asset_name: str, asset_type: str) -> Dict[str, str]:
        """
        アセット名を解析して、その構成要素を抽出します。

        Args:
            asset_name: アセットの名前（パス）
            asset_type: アセットのタイプ

        Returns:
            アセットの構成要素を含む辞書

        Raises:
            ValueError: サポートされていないアセットタイプまたは無効なアセット名の場合
        """
        if asset_type not in self.asset_name_patterns:
            logger.error(f"未登録のアセットタイプです: {asset_type}")
            raise ValueError(f"サポートされていないアセットタイプ: {asset_type}")

        pattern = self.asset_name_patterns[asset_type]
        match = re.match(pattern, asset_name)

        if not match:
            logger.error(
                f"アセット名 '{asset_name}' がパターン '{pattern}' にマッチしません"
            )
            raise ValueError("無効なアセットネーム形式")

        result = {}

        # アセットタイプ別の解析処理
        if asset_type == "cloudresourcemanager.googleapis.com/Project":
            result["project_id"] = match.group(1)

        elif asset_type == "compute.googleapis.com/Instance":
            result["project_id"] = match.group(1)
            result["zone"] = match.group(2)
            result["instance_id"] = match.group(3)

        elif asset_type == "storage.googleapis.com/Bucket":
            result["bucket_name"] = match.group(1)

        elif asset_type == "bigquery.googleapis.com/Dataset":
            result["project_id"] = match.group(1)
            result["dataset_id"] = match.group(2)

        elif asset_type == "bigquery.googleapis.com/Table":
            result["project_id"] = match.group(1)
            result["dataset_id"] = match.group(2)
            result["table_id"] = match.group(3)

        elif asset_type == "bigquery.googleapis.com/Model":
            result["project_id"] = match.group(1)
            result["dataset_id"] = match.group(2)
            result["model_id"] = match.group(3)

        elif asset_type == "bigquery.googleapis.com/Routine":
            result["project_id"] = match.group(1)
            result["dataset_id"] = match.group(2)
            result["routine_id"] = match.group(3)

        else:
            # 汎用的な解析（グループを順番に取得）
            for i, group in enumerate(match.groups(), start=1):
                result[f"resource_{i}"] = group

        return result

    def get_current_policy(
        self, asset_name: str, asset_type: str, project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        指定されたアセットの現在のIAMポリシーを取得します。

        Args:
            asset_name: アセットの名前（パス）
            asset_type: アセットのタイプ
            project_id: プロジェクトID（一部のアセットタイプでは不要）

        Returns:
            現在のIAMポリシー（辞書）

        Raises:
            ValueError: サポートされていないアセットタイプの場合
        """
        if asset_type not in self.asset_type_mapping:
            logger.error(f"サポートされていないアセットタイプです: {asset_type}")
            raise ValueError(f"サポートされていないアセットタイプ: {asset_type}")

        config = self.asset_type_mapping[asset_type]
        client = self.get_client(config["service_name"], config["version"])

        if not client:
            logger.error(f"APIクライアントを取得できませんでした: {asset_type}")
            raise ValueError(f"サポートされていないアセットタイプ: {asset_type}")

        parsed_asset = self.parse_asset_name(asset_name, asset_type)
        if not parsed_asset:
            return {}

        try:
            if asset_type == "cloudresourcemanager.googleapis.com/Project":
                request = client.projects().getIamPolicy(
                    resource=project_id or parsed_asset.get("project_id", ""), body={}
                )
                response = request.execute()
                return response

            elif asset_type == "compute.googleapis.com/Instance":
                request = client.instances().getIamPolicy(
                    project=parsed_asset["project_id"],
                    zone=parsed_asset["zone"],
                    resource=parsed_asset["instance_id"],
                )
                response = request.execute()
                return response

            elif asset_type == "storage.googleapis.com/Bucket":
                request = client.buckets().getIamPolicy(
                    bucket=parsed_asset["bucket_name"]
                )
                response = request.execute()
                return response

            elif asset_type == "bigquery.googleapis.com/Dataset":
                request = client.datasets().get(
                    projectId=parsed_asset["project_id"],
                    datasetId=parsed_asset["dataset_id"],
                )
                response = request.execute()
                return response.get("access", [])

            elif asset_type == "bigquery.googleapis.com/Table":
                request = client.tables().get(
                    projectId=parsed_asset["project_id"],
                    datasetId=parsed_asset["dataset_id"],
                    tableId=parsed_asset["table_id"],
                )
                response = request.execute()
                return response.get("access", [])

            elif asset_type == "bigquery.googleapis.com/Model":
                request = client.models().get(
                    projectId=parsed_asset["project_id"],
                    datasetId=parsed_asset["dataset_id"],
                    modelId=parsed_asset["model_id"],
                )
                response = request.execute()
                return response.get("access", [])

            elif asset_type == "bigquery.googleapis.com/Routine":
                request = client.routines().get(
                    projectId=parsed_asset["project_id"],
                    datasetId=parsed_asset["dataset_id"],
                    routineId=parsed_asset["routine_id"],
                )
                response = request.execute()
                return response.get("access", [])

            else:
                logger.error(
                    f"アセットタイプ {asset_type} のIAMポリシー取得は実装されていません"
                )
                raise ValueError(f"サポートされていないアセットタイプ: {asset_type}")

        except Exception as e:
            logger.error(f"IAMポリシーの取得中にエラーが発生しました: {str(e)}")
            return {}

    def add_binding(
        self,
        user_email: str,
        role: str,
        asset_name: str,
        asset_type: str,
        project_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        指定されたアセットに対してユーザーの権限を追加します。

        Args:
            user_email: ユーザーまたはサービスアカウントのメールアドレス
            role: 追加するIAMロール
            asset_name: アセットの名前（パス）
            asset_type: アセットのタイプ
            project_id: プロジェクトID（一部のアセットタイプでは不要）
            dry_run: 実際に変更を行わずに動作確認のみ行うフラグ

        Returns:
            (成功フラグ, レスポンス)のタプル

        Raises:
            ValueError: サポートされていないアセットタイプの場合
        """
        if asset_type not in self.asset_type_mapping:
            logger.error(f"サポートされていないアセットタイプです: {asset_type}")
            raise ValueError(f"サポートされていないアセットタイプ: {asset_type}")

        # アセット名の解析で検証
        parsed_asset = self.parse_asset_name(asset_name, asset_type)
        if not parsed_asset:
            return False, None

        # ドライランの場合は現在のポリシーを確認のみ
        if dry_run:
            logger.info(
                f"ドライランモード: ユーザー {user_email} にロール {role} を追加します (アセット: {asset_name})"
            )
            # ポリシーを取得して変更をシミュレーション
            self.get_current_policy(asset_name, asset_type, project_id)
            return True, None

        config = self.asset_type_mapping[asset_type]
        client = self.get_client(config["service_name"], config["version"])

        if not client:
            logger.error(f"APIクライアントを取得できませんでした: {asset_type}")
            raise ValueError(f"サポートされていないアセットタイプ: {asset_type}")

        try:
            if asset_type == "cloudresourcemanager.googleapis.com/Project":
                return self._add_binding_to_project(
                    client,
                    user_email,
                    role,
                    project_id or parsed_asset.get("project_id", ""),
                )

            elif asset_type == "compute.googleapis.com/Instance":
                return self._add_binding_to_instance(
                    client, user_email, role, parsed_asset
                )

            elif asset_type == "storage.googleapis.com/Bucket":
                return self._add_binding_to_bucket(
                    client, user_email, role, parsed_asset
                )

            elif asset_type == "bigquery.googleapis.com/Dataset":
                return self._add_binding_to_dataset(
                    client, user_email, role, parsed_asset
                )

            elif asset_type == "bigquery.googleapis.com/Table":
                return self._add_binding_to_table(
                    client, user_email, role, parsed_asset
                )

            elif asset_type == "bigquery.googleapis.com/Model":
                return self._add_binding_to_model(
                    client, user_email, role, parsed_asset
                )

            elif asset_type == "bigquery.googleapis.com/Routine":
                return self._add_binding_to_routine(
                    client, user_email, role, parsed_asset
                )

            else:
                logger.error(
                    f"アセットタイプ {asset_type} のバインディング追加は実装されていません"
                )
                raise ValueError(f"サポートされていないアセットタイプ: {asset_type}")

        except Exception as e:
            logger.error(f"バインディングの追加中にエラーが発生しました: {str(e)}")
            return False, None

    def _add_binding_to_instance(
        self, client, user_email: str, role: str, parsed_asset: Dict[str, str]
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Compute Engineインスタンスにバインディングを追加します。

        Args:
            client: APIクライアント
            user_email: ユーザーのメールアドレス
            role: 追加するIAMロール
            parsed_asset: パース済みのアセット情報

        Returns:
            (成功フラグ, レスポンス)のタプル
        """
        # 現在のポリシーを取得
        request = client.instances().getIamPolicy(
            project=parsed_asset["project_id"],
            zone=parsed_asset["zone"],
            resource=parsed_asset["instance_id"],
        )
        policy = request.execute()

        # バインディングを追加
        binding_exists = False
        for binding in policy.get("bindings", []):
            if binding["role"] == role:
                if user_email in binding["members"]:
                    logger.info(
                        f"ユーザー {user_email} は既にロール {role} を持っています"
                    )
                    return True, None
                binding["members"].append(f"user:{user_email}")
                binding_exists = True
                break

        if not binding_exists:
            if "bindings" not in policy:
                policy["bindings"] = []
            policy["bindings"].append({"role": role, "members": [f"user:{user_email}"]})

        # 更新したポリシーを適用
        request = client.instances().setIamPolicy(
            project=parsed_asset["project_id"],
            zone=parsed_asset["zone"],
            resource=parsed_asset["instance_id"],
            body={"policy": policy},
        )
        response = request.execute()

        logger.info(f"ユーザー {user_email} にロール {role} を追加しました")
        return True, response

    def _add_binding_to_bucket(
        self, client, user_email: str, role: str, parsed_asset: Dict[str, str]
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Cloud Storageバケットにバインディングを追加します。

        Args:
            client: APIクライアント
            user_email: ユーザーのメールアドレス
            role: 追加するIAMロール
            parsed_asset: パース済みのアセット情報

        Returns:
            (成功フラグ, レスポンス)のタプル
        """
        # 現在のポリシーを取得
        bucket_name = parsed_asset["bucket_name"]
        asset_name = f"//storage.googleapis.com/projects/_/buckets/{bucket_name}"
        policy = self.get_current_policy(
            asset_name=asset_name, asset_type="storage.googleapis.com/Bucket"
        )

        # 'kind'フィールドを確保（テスト互換性のため）
        if "kind" not in policy and isinstance(policy, dict):
            policy["kind"] = "storage#policy"

        # バインディングを追加
        binding_exists = False
        for binding in policy.get("bindings", []):
            if binding["role"] == role:
                if f"user:{user_email}" in binding["members"]:
                    logger.info(
                        f"ユーザー {user_email} は既にロール {role} を持っています"
                    )
                    return True, None
                binding["members"].append(f"user:{user_email}")
                binding_exists = True
                break

        if not binding_exists:
            if "bindings" not in policy:
                policy["bindings"] = []
            policy["bindings"].append({"role": role, "members": [f"user:{user_email}"]})

        # 更新したポリシーを適用
        request = client.buckets().setIamPolicy(
            bucket=parsed_asset["bucket_name"], body=policy
        )
        response = request.execute()

        logger.info(f"ユーザー {user_email} にロール {role} を追加しました")
        return True, response

    def _add_binding_to_dataset(
        self, client, user_email: str, role: str, parsed_asset: Dict[str, str]
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        BigQueryデータセットにバインディングを追加します。

        Args:
            client: APIクライアント
            user_email: ユーザーのメールアドレス
            role: 追加するIAMロール
            parsed_asset: パース済みのアセット情報

        Returns:
            (成功フラグ, レスポンス)のタプル
        """
        # BigQueryのロール名を変換（roles/bigquery.dataViewerなどから dataViewer に）
        if role.startswith("roles/bigquery."):
            role_name = role.replace("roles/bigquery.", "")
        else:
            role_name = role

        logger.debug(f"BigQueryのロール名を変換: {role} -> {role_name}")

        # 現在のデータセット情報を取得
        project_id = parsed_asset["project_id"]
        dataset_id = parsed_asset["dataset_id"]
        asset_name = (
            f"//bigquery.googleapis.com/projects/{project_id}/datasets/{dataset_id}"
        )
        access_entries = self.get_current_policy(
            asset_name=asset_name, asset_type="bigquery.googleapis.com/Dataset"
        )

        if not access_entries:
            access_entries = []

        # 既存の権限をチェック
        for entry in access_entries:
            if (
                entry.get("role") == role_name
                and entry.get("userByEmail") == user_email
            ):
                logger.info(
                    f"ユーザー {user_email} は既にロール {role_name} を持っています"
                )
                return True, None

        # 新しいアクセス権を追加
        new_entry = {"role": role_name, "userByEmail": user_email}
        access_entries.append(new_entry)

        # データセット情報を作成
        dataset = {"access": access_entries}

        # 更新したデータセット情報を適用
        request = client.datasets().patch(
            projectId=project_id, datasetId=dataset_id, body=dataset
        )
        response = request.execute()

        logger.info(f"ユーザー {user_email} にロール {role_name} を追加しました")
        return True, response

    def _add_binding_to_table(
        self, client, user_email: str, role: str, parsed_asset: Dict[str, str]
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        BigQueryテーブルにバインディングを追加します。

        Args:
            client: APIクライアント
            user_email: ユーザーのメールアドレス
            role: 追加するIAMロール
            parsed_asset: パース済みのアセット情報

        Returns:
            (成功フラグ, レスポンス)のタプル
        """
        # BigQueryのロール名を変換（roles/bigquery.dataViewerなどから dataViewer に）
        if role.startswith("roles/bigquery."):
            role_name = role.replace("roles/bigquery.", "")
        else:
            role_name = role

        logger.debug(f"BigQueryのロール名を変換: {role} -> {role_name}")

        # 現在のテーブル情報を取得
        request = client.tables().get(
            projectId=parsed_asset["project_id"],
            datasetId=parsed_asset["dataset_id"],
            tableId=parsed_asset["table_id"],
        )
        table = request.execute()

        # アクセス権を追加
        access_entries = table.get("access", [])

        # 既存の権限をチェック
        for entry in access_entries:
            if (
                entry.get("role") == role_name
                and entry.get("userByEmail") == user_email
            ):
                logger.info(
                    f"ユーザー {user_email} は既にテーブルでロール {role_name} を持っています"
                )
                return True, None

        # 新しいアクセス権を追加
        new_entry = {"role": role_name, "userByEmail": user_email}
        access_entries.append(new_entry)
        table["access"] = access_entries

        # 更新したテーブル情報を適用
        request = client.tables().patch(
            projectId=parsed_asset["project_id"],
            datasetId=parsed_asset["dataset_id"],
            tableId=parsed_asset["table_id"],
            body=table,
        )
        response = request.execute()

        logger.info(
            f"ユーザー {user_email} にテーブルのロール {role_name} を追加しました"
        )
        return True, response

    def _add_binding_to_model(
        self, client, user_email: str, role: str, parsed_asset: Dict[str, str]
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        BigQueryモデルにバインディングを追加します。

        Args:
            client: APIクライアント
            user_email: ユーザーのメールアドレス
            role: 追加するIAMロール
            parsed_asset: パース済みのアセット情報

        Returns:
            (成功フラグ, レスポンス)のタプル
        """
        # BigQueryのロール名を変換（roles/bigquery.modelUserなどから modelUser に）
        if role.startswith("roles/bigquery."):
            role_name = role.replace("roles/bigquery.", "")
        else:
            role_name = role

        logger.debug(f"BigQueryのロール名を変換: {role} -> {role_name}")

        # 現在のモデル情報を取得
        request = client.models().get(
            projectId=parsed_asset["project_id"],
            datasetId=parsed_asset["dataset_id"],
            modelId=parsed_asset["model_id"],
        )
        model = request.execute()

        # アクセス権を追加
        access_entries = model.get("access", [])

        # 既存の権限をチェック
        for entry in access_entries:
            if (
                entry.get("role") == role_name
                and entry.get("userByEmail") == user_email
            ):
                logger.info(
                    f"ユーザー {user_email} は既にモデルでロール {role_name} を持っています"
                )
                return True, None

        # 新しいアクセス権を追加
        new_entry = {"role": role_name, "userByEmail": user_email}
        access_entries.append(new_entry)
        model["access"] = access_entries

        # 更新したモデル情報を適用
        request = client.models().patch(
            projectId=parsed_asset["project_id"],
            datasetId=parsed_asset["dataset_id"],
            modelId=parsed_asset["model_id"],
            body=model,
        )
        response = request.execute()

        logger.info(
            f"ユーザー {user_email} にモデルのロール {role_name} を追加しました"
        )
        return True, response

    def _add_binding_to_routine(
        self, client, user_email: str, role: str, parsed_asset: Dict[str, str]
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        BigQueryルーティンにバインディングを追加します。

        Args:
            client: APIクライアント
            user_email: ユーザーのメールアドレス
            role: 追加するIAMロール
            parsed_asset: パース済みのアセット情報

        Returns:
            (成功フラグ, レスポンス)のタプル
        """
        # BigQueryのロール名を変換（roles/bigquery.routineUserなどから routineUser に）
        if role.startswith("roles/bigquery."):
            role_name = role.replace("roles/bigquery.", "")
        else:
            role_name = role

        logger.debug(f"BigQueryのロール名を変換: {role} -> {role_name}")

        # 現在のルーティン情報を取得
        request = client.routines().get(
            projectId=parsed_asset["project_id"],
            datasetId=parsed_asset["dataset_id"],
            routineId=parsed_asset["routine_id"],
        )
        routine = request.execute()

        # アクセス権を追加
        access_entries = routine.get("access", [])

        # 既存の権限をチェック
        for entry in access_entries:
            if (
                entry.get("role") == role_name
                and entry.get("userByEmail") == user_email
            ):
                logger.info(
                    f"ユーザー {user_email} は既にルーティンでロール {role_name} を持っています"
                )
                return True, None

        # 新しいアクセス権を追加
        new_entry = {"role": role_name, "userByEmail": user_email}
        access_entries.append(new_entry)
        routine["access"] = access_entries

        # 更新したルーティン情報を適用
        request = client.routines().update(
            projectId=parsed_asset["project_id"],
            datasetId=parsed_asset["dataset_id"],
            routineId=parsed_asset["routine_id"],
            body=routine,
        )
        response = request.execute()

        logger.info(
            f"ユーザー {user_email} にルーティンのロール {role_name} を追加しました"
        )
        return True, response

    def _add_binding_to_project(
        self, client, user_email: str, role: str, project_id: str
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        プロジェクトにバインディングを追加します。

        Args:
            client: APIクライアント
            user_email: ユーザーのメールアドレス
            role: 追加するIAMロール
            project_id: プロジェクトID

        Returns:
            (成功フラグ, レスポンス)のタプル
        """
        # 現在のポリシーを取得
        asset_name = f"//cloudresourcemanager.googleapis.com/projects/{project_id}"
        policy = self.get_current_policy(
            asset_name=asset_name,
            asset_type="cloudresourcemanager.googleapis.com/Project",
            project_id=project_id,
        )

        # バインディングを追加
        binding_exists = False
        for binding in policy.get("bindings", []):
            if binding["role"] == role:
                if f"user:{user_email}" in binding["members"]:
                    logger.info(
                        f"ユーザー {user_email} は既にロール {role} を持っています"
                    )
                    return True, None
                binding["members"].append(f"user:{user_email}")
                binding_exists = True
                break

        if not binding_exists:
            if "bindings" not in policy:
                policy["bindings"] = []
            policy["bindings"].append({"role": role, "members": [f"user:{user_email}"]})

        # 更新したポリシーを適用
        request = client.projects().setIamPolicy(
            resource=project_id, body={"policy": policy}
        )
        response = request.execute()

        logger.info(
            f"ユーザー {user_email} にプロジェクト {project_id} のロール {role} を追加しました"
        )
        return True, response

    def validate_csv_file(self, file_path: str) -> bool:
        """
        入力CSVファイルを検証します。

        Args:
            file_path: CSVファイルのパス

        Returns:
            検証結果（True：有効なCSV、False：無効なCSV）
        """
        if not os.path.exists(file_path):
            logger.error(f"CSVファイルが見つかりません: {file_path}")
            return False

        required_columns = ["email", "role", "asset_name", "asset_type", "project_id"]

        try:
            with open(file_path, mode="r", encoding="utf-8") as f:
                reader = csv.reader(f)
                headers = next(reader)

                # ヘッダーが存在するか確認
                if not headers:
                    logger.error("CSVファイルにヘッダー行がありません")
                    return False

                # 必須列が存在するか確認
                missing_columns = [
                    col for col in required_columns if col not in headers
                ]
                if missing_columns:
                    logger.error(
                        f"CSVファイルに必須列がありません: {', '.join(missing_columns)}"
                    )
                    return False

                # コンテンツを確認
                row_count = 0
                for row in reader:
                    row_count += 1
                    if len(row) != len(headers):
                        logger.error(
                            f"行 {row_count+1} の列数が一致しません: 期待値 {len(headers)}, 実際 {len(row)}"
                        )
                        return False

                if row_count == 0:
                    logger.warning("CSVファイルにデータ行がありません")
                    return False

                logger.info(f"CSVファイルの検証に成功しました: {row_count} 行のデータ")
                return True

        except Exception as e:
            logger.error(f"CSVファイルの検証中にエラーが発生しました: {str(e)}")
            return False

    def process_csv_file(
        self, file_path: str, dry_run: bool = False
    ) -> Tuple[int, int]:
        """
        CSVファイルから権限を一括追加します。

        Args:
            file_path: CSVファイルのパス
            dry_run: 実際に権限を変更せずに確認のみ行うフラグ

        Returns:
            (成功件数, 失敗件数)のタプル
        """
        if not self.validate_csv_file(file_path):
            return 0, 0

        try:
            df = pd.read_csv(file_path)
            total_rows = len(df)
            success_count = 0
            failure_count = 0

            logger.info(
                f"CSVファイルの処理を開始します: {total_rows} 行のデータ"
                + (" (ドライラン)" if dry_run else "")
            )

            for index, row in df.iterrows():
                try:
                    email = row["email"]
                    role = row["role"]
                    asset_name = row["asset_name"]
                    asset_type = row["asset_type"]
                    project_id = row["project_id"]

                    logger.info(
                        f"行 {index+2}: ユーザー {email} にロール {role} を追加します (アセット: {asset_name})"
                        + (" (ドライラン)" if dry_run else "")
                    )

                    if not dry_run:
                        success, response = self.add_binding(
                            user_email=email,
                            role=role,
                            asset_name=asset_name,
                            asset_type=asset_type,
                            project_id=project_id,
                        )

                        if success:
                            success_count += 1
                            logger.info(f"行 {index+2}: 権限の追加に成功しました")
                        else:
                            failure_count += 1
                            logger.error(f"行 {index+2}: 権限の追加に失敗しました")
                    else:
                        # ドライランの場合は検証のみ
                        parsed_asset = self.parse_asset_name(asset_name, asset_type)
                        if parsed_asset:
                            success_count += 1
                            logger.info(
                                f"行 {index+2}: 有効なアセット情報です (ドライラン)"
                            )
                        else:
                            failure_count += 1
                            logger.error(
                                f"行 {index+2}: 無効なアセット情報です (ドライラン)"
                            )

                    # API制限対策のために短い待機を入れる
                    time.sleep(0.5)

                except Exception as e:
                    failure_count += 1
                    logger.error(
                        f"行 {index+2} の処理中にエラーが発生しました: {str(e)}"
                    )

            logger.info(
                f"CSVファイルの処理が完了しました: 成功 {success_count}, 失敗 {failure_count}"
                + (" (ドライラン)" if dry_run else "")
            )
            return success_count, failure_count

        except Exception as e:
            logger.error(f"CSVファイルの処理中にエラーが発生しました: {str(e)}")
            return 0, 0

    def get_asset_pattern_for_type(self, asset_type: str) -> Optional[str]:
        """
        指定されたアセットタイプの正規表現パターンを取得します。

        Args:
            asset_type: アセットタイプ識別子

        Returns:
            パターン文字列、または存在しない場合はNone
        """
        if asset_type in self.asset_name_patterns:
            return self.asset_name_patterns[asset_type]
        return None

    def update_asset_pattern(self, asset_type: str, new_pattern: str):
        """
        既存のアセットタイプの正規表現パターンを更新します。

        Args:
            asset_type: 更新するアセットタイプ識別子
            new_pattern: 新しい正規表現パターン

        Raises:
            ValueError: アセットタイプが存在しない場合
        """
        if asset_type not in self.asset_type_mapping:
            raise ValueError("アセットタイプが存在しません")

        self.asset_name_patterns[asset_type] = new_pattern
        logger.debug(f"アセットタイプのパターンを更新しました: {asset_type}")

    def delete_asset_type(self, asset_type: str):
        """
        登録済みのアセットタイプを削除します。

        Args:
            asset_type: 削除するアセットタイプ識別子

        Raises:
            ValueError: アセットタイプが存在しない場合
        """
        if asset_type not in self.asset_type_mapping:
            raise ValueError("アセットタイプが存在しません")

        del self.asset_type_mapping[asset_type]
        if asset_type in self.asset_name_patterns:
            del self.asset_name_patterns[asset_type]

        logger.debug(f"アセットタイプを削除しました: {asset_type}")

    def list_supported_asset_types(self) -> List[str]:
        """
        サポートされているアセットタイプのリストを取得します。

        Returns:
            アセットタイプのリスト
        """
        return list(self.asset_type_mapping.keys())

    def export_config(self, config_file: str):
        """
        現在のアセットタイプ設定をファイルにエクスポートします。

        Args:
            config_file: 出力する設定ファイルのパス（.jsonまたは.yaml）

        Raises:
            ValueError: サポートされていないファイル形式の場合
        """
        asset_types = []
        for asset_type, config in self.asset_type_mapping.items():
            asset_config = config.copy()
            asset_config["asset_type"] = asset_type
            asset_config["asset_name_pattern"] = self.asset_name_patterns.get(
                asset_type, ""
            )
            asset_types.append(asset_config)

        config_data = {"asset_types": asset_types}

        if config_file.endswith(".json"):
            with open(config_file, "w") as f:
                json.dump(config_data, f, indent=2)
            logger.info(f"設定をJSONファイルにエクスポートしました: {config_file}")
        elif config_file.endswith(".yaml") or config_file.endswith(".yml"):
            with open(config_file, "w") as f:
                yaml.dump(config_data, f)
            logger.info(f"設定をYAMLファイルにエクスポートしました: {config_file}")
        else:
            raise ValueError(
                "サポートされていない設定ファイル形式です。.jsonまたは.yaml/.ymlを使用してください。"
            )
