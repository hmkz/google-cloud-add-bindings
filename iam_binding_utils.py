#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
IAMバインディングの操作を行うためのユーティリティモジュール
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml
from google.oauth2 import service_account
from googleapiclient import discovery, errors

# ロガーの設定
logger = logging.getLogger(__name__)


class IAMBindingManager:
    """Google Cloud IAMバインディングを管理するクラス"""

    def __init__(
        self, credentials_path: Optional[str] = None, config_file: Optional[str] = None
    ):
        """
        IAMBindingManagerを初期化します

        Args:
            credentials_path: サービスアカウントキーファイルのパス (省略時はデフォルト認証情報を使用)
            config_file: アセットタイプ設定ファイルのパス (省略時はデフォルトの設定を使用)
        """
        self.clients = {}  # APIクライアントのキャッシュ

        # アセットタイプとIAM API操作のマッピング
        self.asset_type_mapping = {}

        # アセットネームの正規表現パターン
        self.asset_name_patterns = {}

        # 設定ファイルの読み込み
        if config_file:
            self.load_config(config_file)
        else:
            # デフォルト設定
            self._load_default_config()

        # 認証情報の設定
        if credentials_path:
            self.credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        else:
            self.credentials = None  # デフォルト認証を使用

    def _load_default_config(self):
        """デフォルトのアセットタイプ設定を読み込みます"""
        # プロジェクト
        self.register_asset_type(
            asset_type="cloudresourcemanager.googleapis.com/Project",
            service_name="cloudresourcemanager",
            version="v1",
            method="setIamPolicy",
            resource_type="project",
            asset_name_pattern=r"//cloudresourcemanager\.googleapis\.com/projects/([^/]+)",
        )

        # バケット
        self.register_asset_type(
            asset_type="storage.googleapis.com/Bucket",
            service_name="storage",
            version="v1",
            method="setIamPolicy",
            resource_type="bucket",
            asset_name_pattern=r"//storage\.googleapis\.com/projects/[^/]+/buckets/([^/]+)",
        )

        # データセット
        self.register_asset_type(
            asset_type="bigquery.googleapis.com/Dataset",
            service_name="bigquery",
            version="v2",
            method="update",
            resource_type="dataset",
            asset_name_pattern=r"//bigquery\.googleapis\.com/projects/([^/]+)/datasets/([^/]+)",
        )

        # BigQueryテーブル
        self.register_asset_type(
            asset_type="bigquery.googleapis.com/Table",
            service_name="bigquery",
            version="v2",
            method="update",
            resource_type="table",
            asset_name_pattern=r"//bigquery\.googleapis\.com/projects/([^/]+)/datasets/([^/]+)/tables/([^/]+)",
        )

        # BigQueryモデル
        self.register_asset_type(
            asset_type="bigquery.googleapis.com/Model",
            service_name="bigquery",
            version="v2",
            method="update",
            resource_type="model",
            asset_name_pattern=r"//bigquery\.googleapis\.com/projects/([^/]+)/datasets/([^/]+)/models/([^/]+)",
        )

        # BigQueryルーティン
        self.register_asset_type(
            asset_type="bigquery.googleapis.com/Routine",
            service_name="bigquery",
            version="v2",
            method="update",
            resource_type="routine",
            asset_name_pattern=r"//bigquery\.googleapis\.com/projects/([^/]+)/datasets/([^/]+)/routines/([^/]+)",
        )

    def load_config(self, config_file: str):
        """
        設定ファイルからアセットタイプ設定を読み込みます

        Args:
            config_file: 設定ファイルのパス (.json, .yaml, .yml)

        Raises:
            ValueError: 無効な設定ファイル形式またはファイルが存在しない場合
        """
        if not os.path.exists(config_file):
            raise ValueError(f"設定ファイルが見つかりません: {config_file}")

        file_ext = os.path.splitext(config_file)[1].lower()

        try:
            if file_ext == ".json":
                with open(config_file, "r") as f:
                    config = json.load(f)
            elif file_ext in [".yaml", ".yml"]:
                with open(config_file, "r") as f:
                    config = yaml.safe_load(f)
            else:
                raise ValueError(f"サポートされていない設定ファイル形式: {file_ext}")

            # 設定の読み込み
            asset_types = config.get("asset_types", [])
            for asset_type_config in asset_types:
                self.register_asset_type(
                    asset_type=asset_type_config["asset_type"],
                    service_name=asset_type_config["service_name"],
                    version=asset_type_config["version"],
                    method=asset_type_config["method"],
                    resource_type=asset_type_config["resource_type"],
                    asset_name_pattern=asset_type_config["asset_name_pattern"],
                )

            logger.info(
                f"設定ファイルから {len(asset_types)} 個のアセットタイプを読み込みました: {config_file}"
            )

        except Exception as e:
            logger.error(f"設定ファイルの読み込みエラー: {e}")
            raise ValueError(f"設定ファイルの読み込みに失敗しました: {e}")

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
        新しいアセットタイプを登録します

        Args:
            asset_type: アセットタイプの識別子 (例: cloudresourcemanager.googleapis.com/Project)
            service_name: Google Cloud サービス名
            version: API バージョン
            method: IAMポリシー設定メソッド
            resource_type: リソースタイプ
            asset_name_pattern: アセットネームの正規表現パターン
        """
        self.asset_type_mapping[asset_type] = {
            "service_name": service_name,
            "version": version,
            "method": method,
            "resource_type": resource_type,
        }

        self.asset_name_patterns[asset_type] = asset_name_pattern
        logger.debug(f"アセットタイプを登録しました: {asset_type}")

    def get_client(self, service_name: str, version: str) -> discovery.Resource:
        """
        指定されたサービスのAPIクライアントを取得します

        Args:
            service_name: Google Cloudサービス名
            version: APIバージョン

        Returns:
            APIクライアントのインスタンス
        """
        client_key = f"{service_name}_{version}"

        if client_key not in self.clients:
            self.clients[client_key] = discovery.build(
                service_name, version, credentials=self.credentials
            )

        return self.clients[client_key]

    def parse_asset_name(self, asset_name: str, asset_type: str) -> Dict[str, str]:
        """
        アセットネームを解析してリソース情報を抽出します

        Args:
            asset_name: アセットの完全な名前
            asset_type: アセットのタイプ

        Returns:
            リソース情報を含む辞書

        Raises:
            ValueError: サポートされていないアセットタイプまたは無効なアセットネーム形式の場合
        """
        if asset_type not in self.asset_type_mapping:
            raise ValueError(f"サポートされていないアセットタイプ: {asset_type}")

        if asset_type not in self.asset_name_patterns:
            raise ValueError(f"アセットネームパターンが未定義: {asset_type}")

        pattern = self.asset_name_patterns[asset_type]
        match = re.match(pattern, asset_name)

        if not match:
            raise ValueError(
                f"無効なアセットネーム形式: {asset_name} (タイプ: {asset_type})"
            )

        result = {}

        # 正規表現のグループからリソース情報を抽出
        if asset_type == "cloudresourcemanager.googleapis.com/Project":
            result["project_id"] = match.group(1)

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

        # カスタムアセットタイプの処理
        else:
            # グループの数に基づいて汎用的に抽出
            # 例えば、1つのグループならリソース名として扱う
            resource_type = self.asset_type_mapping[asset_type]["resource_type"]

            if match.lastindex == 1:
                result[f"{resource_type}_name"] = match.group(1)
            else:
                # 複数のグループがある場合は番号付きで保存
                for i in range(1, match.lastindex + 1):
                    result[f"resource_{i}"] = match.group(i)

        return result

    def get_current_policy(
        self, asset_name: str, asset_type: str, project_id: str
    ) -> Dict:
        """
        リソースの現在のIAMポリシーを取得します

        Args:
            asset_name: アセットの完全な名前
            asset_type: アセットのタイプ
            project_id: プロジェクトID

        Returns:
            現在のIAMポリシー

        Raises:
            ValueError: サポートされていないアセットタイプが指定された場合
            Exception: API呼び出し中にエラーが発生した場合
        """
        if asset_type not in self.asset_type_mapping:
            raise ValueError(f"サポートされていないアセットタイプ: {asset_type}")

        resource_config = self.asset_type_mapping[asset_type]
        client = self.get_client(
            resource_config["service_name"], resource_config["version"]
        )

        resource_info = self.parse_asset_name(asset_name, asset_type)

        try:
            # 組み込みアセットタイプの処理
            if asset_type == "cloudresourcemanager.googleapis.com/Project":
                response = (
                    client.projects()
                    .getIamPolicy(resource=resource_info["project_id"], body={})
                    .execute()
                )
                return response

            elif asset_type == "storage.googleapis.com/Bucket":
                response = (
                    client.buckets()
                    .getIamPolicy(bucket=resource_info["bucket_name"])
                    .execute()
                )
                return response

            elif asset_type == "bigquery.googleapis.com/Dataset":
                response = (
                    client.datasets()
                    .get(
                        projectId=resource_info["project_id"],
                        datasetId=resource_info["dataset_id"],
                    )
                    .execute()
                )
                return response.get("access", [])

            elif asset_type == "bigquery.googleapis.com/Table":
                response = (
                    client.tables()
                    .get(
                        projectId=resource_info["project_id"],
                        datasetId=resource_info["dataset_id"],
                        tableId=resource_info["table_id"],
                    )
                    .execute()
                )
                return response.get("access", [])

            elif asset_type == "bigquery.googleapis.com/Model":
                response = (
                    client.models()
                    .get(
                        projectId=resource_info["project_id"],
                        datasetId=resource_info["dataset_id"],
                        modelId=resource_info["model_id"],
                    )
                    .execute()
                )
                return response.get("access", [])

            elif asset_type == "bigquery.googleapis.com/Routine":
                response = (
                    client.routines()
                    .get(
                        projectId=resource_info["project_id"],
                        datasetId=resource_info["dataset_id"],
                        routineId=resource_info["routine_id"],
                    )
                    .execute()
                )
                return response.get("access", [])

            # カスタムアセットタイプの汎用処理
            else:
                # ここにカスタムアセットタイプのポリシー取得ロジックを追加
                # リソースタイプに応じて適切なAPIメソッドを動的に呼び出す
                resource_type = resource_config["resource_type"]

                # 拡張可能なポリシー取得処理
                # 実際のAPIは異なるため、ここでは例として汎用的な処理を示す
                method_name = f"get_{resource_type}_policy"
                if hasattr(self, method_name):
                    custom_method = getattr(self, method_name)
                    return custom_method(client, resource_info, project_id)
                else:
                    logger.warning(
                        f"カスタムポリシー取得メソッドが未定義: {method_name}"
                    )
                    raise ValueError(
                        f"アセットタイプ {asset_type} のポリシー取得方法が実装されていません"
                    )

        except errors.HttpError as e:
            logger.error(f"IAMポリシー取得エラー: {e}")
            raise

    def add_binding(
        self,
        user_email: str,
        role: str,
        asset_name: str,
        asset_type: str,
        project_id: str,
        dry_run: bool = False,
    ) -> Tuple[bool, Any]:
        """
        IAMバインディングを追加します

        Args:
            user_email: ユーザーまたはサービスアカウントのメールアドレス
            role: 付与するロール (roles/storage.objectViewerなど)
            asset_name: アセットの完全な名前
            asset_type: アセットのタイプ
            project_id: プロジェクトID
            dry_run: True の場合、実際の変更は行わずシミュレーションのみ行う

        Returns:
            (成功フラグ, レスポンス) のタプル

        Raises:
            ValueError: 無効なパラメータが指定された場合
            Exception: API呼び出し中にエラーが発生した場合
        """
        if asset_type not in self.asset_type_mapping:
            raise ValueError(f"サポートされていないアセットタイプ: {asset_type}")

        resource_config = self.asset_type_mapping[asset_type]
        client = self.get_client(
            resource_config["service_name"], resource_config["version"]
        )

        # アセットネームからリソース情報を取得
        resource_info = self.parse_asset_name(asset_name, asset_type)

        try:
            # 現在のポリシーを取得
            current_policy = self.get_current_policy(asset_name, asset_type, project_id)

            # ドライランの場合はログ出力のみ
            if dry_run:
                logger.info(
                    f"[ドライラン] ユーザー {user_email} にロール {role} を {asset_name} に付与します"
                )
                return True, None

            # 組み込みアセットタイプの処理
            if asset_type == "cloudresourcemanager.googleapis.com/Project":
                return self._add_binding_to_project(
                    client, user_email, role, resource_info, current_policy
                )

            elif asset_type == "storage.googleapis.com/Bucket":
                return self._add_binding_to_bucket(
                    client, user_email, role, resource_info, current_policy
                )

            elif asset_type == "bigquery.googleapis.com/Dataset":
                return self._add_binding_to_dataset(
                    client, user_email, role, resource_info, current_policy
                )

            elif asset_type == "bigquery.googleapis.com/Table":
                return self._add_binding_to_table(
                    client, user_email, role, resource_info, current_policy
                )

            elif asset_type == "bigquery.googleapis.com/Model":
                return self._add_binding_to_model(
                    client, user_email, role, resource_info, current_policy
                )

            elif asset_type == "bigquery.googleapis.com/Routine":
                return self._add_binding_to_routine(
                    client, user_email, role, resource_info, current_policy
                )

            # カスタムアセットタイプの汎用処理
            else:
                # リソースタイプに応じた処理メソッドを動的に呼び出す
                resource_type = resource_config["resource_type"]
                method_name = f"add_binding_to_{resource_type}"

                if hasattr(self, method_name):
                    custom_method = getattr(self, method_name)
                    return custom_method(
                        client, user_email, role, resource_info, current_policy
                    )
                else:
                    logger.warning(
                        f"カスタムバインディング追加メソッドが未定義: {method_name}"
                    )
                    raise ValueError(
                        f"アセットタイプ {asset_type} のバインディング追加方法が実装されていません"
                    )

        except errors.HttpError as e:
            logger.error(f"IAMバインディング追加エラー: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"予期せぬエラー: {e}")
            return False, str(e)

    def _add_binding_to_project(
        self, client, user_email, role, resource_info, current_policy
    ):
        """プロジェクトにバインディングを追加する内部メソッド"""
        bindings = current_policy.get("bindings", [])

        # 既存のロールを検索
        role_exists = False
        for binding in bindings:
            if binding["role"] == role:
                if f"user:{user_email}" not in binding["members"]:
                    binding["members"].append(f"user:{user_email}")
                role_exists = True
                break

        # ロールが存在しない場合は新規作成
        if not role_exists:
            bindings.append({"role": role, "members": [f"user:{user_email}"]})

        # ポリシーを更新
        response = (
            client.projects()
            .setIamPolicy(
                resource=resource_info["project_id"], body={"policy": current_policy}
            )
            .execute()
        )

        logger.info(
            f"ユーザー {user_email} にロール {role} をプロジェクト {resource_info['project_id']} に付与しました"
        )
        return True, response

    def _add_binding_to_bucket(
        self, client, user_email, role, resource_info, current_policy
    ):
        """バケットにバインディングを追加する内部メソッド"""
        bindings = current_policy.get("bindings", [])

        # 既存のロールを検索
        role_exists = False
        for binding in bindings:
            if binding["role"] == role:
                if f"user:{user_email}" not in binding["members"]:
                    binding["members"].append(f"user:{user_email}")
                role_exists = True
                break

        # ロールが存在しない場合は新規作成
        if not role_exists:
            bindings.append({"role": role, "members": [f"user:{user_email}"]})

        # ポリシーを更新
        response = (
            client.buckets()
            .setIamPolicy(bucket=resource_info["bucket_name"], body=current_policy)
            .execute()
        )

        logger.info(
            f"ユーザー {user_email} にロール {role} をバケット {resource_info['bucket_name']} に付与しました"
        )
        return True, response

    def _add_binding_to_dataset(
        self, client, user_email, role, resource_info, current_policy
    ):
        """
        BigQueryデータセットにIAMバインディングを追加します

        Args:
            client: BigQuery API クライアント
            user_email: IAMユーザーのメールアドレス
            role: 付与するロール
            resource_info: リソース情報
            current_policy: 現在のIAMポリシー

        Returns:
            (success, response) タプル
        """
        try:
            project_id = resource_info["project_id"]
            dataset_id = resource_info["dataset_id"]

            # BigQueryデータセットのアクセス権は特殊な形式
            # rolesプレフィックスとbigquery.を削除して適用する必要がある
            # 例: roles/bigquery.dataViewer -> dataViewer
            if role.startswith("roles/bigquery."):
                role_name = role.replace("roles/bigquery.", "")
            else:
                # 他の形式の場合はそのまま使用
                role_name = role

            new_access = current_policy.copy() if current_policy else []

            # 既存のアクセス権を確認
            for access in new_access:
                if (
                    access.get("userByEmail") == user_email
                    and access.get("role") == role_name
                ):
                    logger.info(f"既にアクセス権があります: {user_email}, {role}")
                    return True, None

            # 新しいアクセス権を追加
            new_access.append({"userByEmail": user_email, "role": role_name})

            datasets = client.datasets()
            response = datasets.patch(
                projectId=project_id, datasetId=dataset_id, body={"access": new_access}
            ).execute()

            logger.info(
                f"データセットにバインディングを追加しました: {project_id}, {dataset_id}, {user_email}, {role}"
            )
            return True, response

        except Exception as e:
            logger.error(f"データセットへのバインディング追加エラー: {e}")
            raise e

    def _add_binding_to_table(
        self, client, user_email, role, resource_info, current_policy
    ):
        """
        BigQueryテーブルにIAMバインディングを追加します

        Args:
            client: BigQuery API クライアント
            user_email: IAMユーザーのメールアドレス
            role: 付与するロール
            resource_info: リソース情報
            current_policy: 現在のIAMポリシー

        Returns:
            (success, response) タプル
        """
        try:
            project_id = resource_info["project_id"]
            dataset_id = resource_info["dataset_id"]
            table_id = resource_info["table_id"]

            # BigQueryテーブルのアクセス権は特殊な形式
            if role.startswith("roles/bigquery."):
                role_name = role.replace("roles/bigquery.", "")
            else:
                role_name = role

            new_access = current_policy.copy() if current_policy else []

            # 既存のアクセス権を確認
            for access in new_access:
                if (
                    access.get("userByEmail") == user_email
                    and access.get("role") == role_name
                ):
                    logger.info(f"既にアクセス権があります: {user_email}, {role}")
                    return True, None

            # 新しいアクセス権を追加
            new_access.append({"userByEmail": user_email, "role": role_name})

            tables = client.tables()
            response = tables.patch(
                projectId=project_id,
                datasetId=dataset_id,
                tableId=table_id,
                body={"access": new_access},
            ).execute()

            logger.info(
                f"テーブルにバインディングを追加しました: {project_id}, {dataset_id}, {table_id}, {user_email}, {role}"
            )
            return True, response

        except Exception as e:
            logger.error(f"テーブルへのバインディング追加エラー: {e}")
            raise e

    def _add_binding_to_model(
        self, client, user_email, role, resource_info, current_policy
    ):
        """
        BigQueryモデルにIAMバインディングを追加します

        Args:
            client: BigQuery API クライアント
            user_email: IAMユーザーのメールアドレス
            role: 付与するロール
            resource_info: リソース情報
            current_policy: 現在のIAMポリシー

        Returns:
            (success, response) タプル
        """
        try:
            project_id = resource_info["project_id"]
            dataset_id = resource_info["dataset_id"]
            model_id = resource_info["model_id"]

            # BigQueryモデルのアクセス権は特殊な形式
            if role.startswith("roles/bigquery."):
                role_name = role.replace("roles/bigquery.", "")
            else:
                role_name = role

            new_access = current_policy.copy() if current_policy else []

            # 既存のアクセス権を確認
            for access in new_access:
                if (
                    access.get("userByEmail") == user_email
                    and access.get("role") == role_name
                ):
                    logger.info(f"既にアクセス権があります: {user_email}, {role}")
                    return True, None

            # 新しいアクセス権を追加
            new_access.append({"userByEmail": user_email, "role": role_name})

            models = client.models()
            response = models.patch(
                projectId=project_id,
                datasetId=dataset_id,
                modelId=model_id,
                body={"access": new_access},
            ).execute()

            logger.info(
                f"モデルにバインディングを追加しました: {project_id}, {dataset_id}, {model_id}, {user_email}, {role}"
            )
            return True, response

        except Exception as e:
            logger.error(f"モデルへのバインディング追加エラー: {e}")
            raise e

    def _add_binding_to_routine(
        self, client, user_email, role, resource_info, current_policy
    ):
        """
        BigQueryルーティンにIAMバインディングを追加します

        Args:
            client: BigQuery API クライアント
            user_email: IAMユーザーのメールアドレス
            role: 付与するロール
            resource_info: リソース情報
            current_policy: 現在のIAMポリシー

        Returns:
            (success, response) タプル
        """
        try:
            project_id = resource_info["project_id"]
            dataset_id = resource_info["dataset_id"]
            routine_id = resource_info["routine_id"]

            # BigQueryルーティンのアクセス権は特殊な形式
            if role.startswith("roles/bigquery."):
                role_name = role.replace("roles/bigquery.", "")
            else:
                role_name = role

            new_access = current_policy.copy() if current_policy else []

            # 既存のアクセス権を確認
            for access in new_access:
                if (
                    access.get("userByEmail") == user_email
                    and access.get("role") == role_name
                ):
                    logger.info(f"既にアクセス権があります: {user_email}, {role}")
                    return True, None

            # 新しいアクセス権を追加
            new_access.append({"userByEmail": user_email, "role": role_name})

            routines = client.routines()
            response = routines.patch(
                projectId=project_id,
                datasetId=dataset_id,
                routineId=routine_id,
                body={"access": new_access},
            ).execute()

            logger.info(
                f"ルーティンにバインディングを追加しました: {project_id}, {dataset_id}, {routine_id}, {user_email}, {role}"
            )
            return True, response

        except Exception as e:
            logger.error(f"ルーティンへのバインディング追加エラー: {e}")
            raise e

    def export_config(self, config_file: str):
        """
        現在のアセットタイプ設定を設定ファイルにエクスポートします

        Args:
            config_file: 出力する設定ファイルのパス (.json, .yaml, .yml)

        Raises:
            ValueError: 無効な設定ファイル形式の場合
        """
        asset_types = []

        for asset_type, mapping in self.asset_type_mapping.items():
            asset_type_config = {
                "asset_type": asset_type,
                "service_name": mapping["service_name"],
                "version": mapping["version"],
                "method": mapping["method"],
                "resource_type": mapping["resource_type"],
                "asset_name_pattern": self.asset_name_patterns.get(asset_type, ""),
            }
            asset_types.append(asset_type_config)

        config = {"asset_types": asset_types}

        file_ext = os.path.splitext(config_file)[1].lower()

        try:
            if file_ext == ".json":
                with open(config_file, "w") as f:
                    json.dump(config, f, indent=2)
            elif file_ext in [".yaml", ".yml"]:
                with open(config_file, "w") as f:
                    yaml.dump(config, f, default_flow_style=False)
            else:
                raise ValueError(f"サポートされていない設定ファイル形式: {file_ext}")

            logger.info(f"設定を {config_file} にエクスポートしました")

        except Exception as e:
            logger.error(f"設定のエクスポートエラー: {e}")
            raise ValueError(f"設定のエクスポートに失敗しました: {e}")

    def list_supported_asset_types(self) -> List[str]:
        """
        サポートされているアセットタイプのリストを返します

        Returns:
            アセットタイプのリスト
        """
        return list(self.asset_type_mapping.keys())

    # 以下は拡張用のユーティリティメソッド

    def get_asset_pattern_for_type(self, asset_type: str) -> Optional[str]:
        """
        指定したアセットタイプのパターンを取得します

        Args:
            asset_type: アセットタイプ

        Returns:
            パターン文字列、存在しない場合はNone
        """
        return self.asset_name_patterns.get(asset_type)

    def update_asset_pattern(self, asset_type: str, pattern: str):
        """
        既存のアセットタイプのパターンを更新します

        Args:
            asset_type: 更新するアセットタイプ
            pattern: 新しいパターン

        Raises:
            ValueError: アセットタイプが存在しない場合
        """
        if asset_type not in self.asset_type_mapping:
            raise ValueError(f"アセットタイプが存在しません: {asset_type}")

        self.asset_name_patterns[asset_type] = pattern
        logger.info(f"アセットタイプのパターンを更新しました: {asset_type}")

    def delete_asset_type(self, asset_type: str):
        """
        アセットタイプを削除します

        Args:
            asset_type: 削除するアセットタイプ

        Raises:
            ValueError: アセットタイプが存在しない場合
        """
        if asset_type not in self.asset_type_mapping:
            raise ValueError(f"アセットタイプが存在しません: {asset_type}")

        del self.asset_type_mapping[asset_type]

        if asset_type in self.asset_name_patterns:
            del self.asset_name_patterns[asset_type]

        logger.info(f"アセットタイプを削除しました: {asset_type}")
