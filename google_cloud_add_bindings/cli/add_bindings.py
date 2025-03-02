#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CSVファイルから権限を一括追加するためのコマンドラインツール
"""

import argparse
import logging
import os
import sys
from typing import List, Optional, Dict, Any, Tuple

import pandas as pd
from google_cloud_add_bindings.core.iam_binding_utils import IAMBindingManager

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("add_bindings.log"), logging.StreamHandler()],
)
logger = logging.getLogger("AddBindings")


def validate_csv(csv_file: str) -> bool:
    """
    CSVファイルの有効性を検証します。

    Args:
        csv_file: 検証するCSVファイルのパス

    Returns:
        検証結果（True: 有効、False: 無効）
    """
    if not os.path.exists(csv_file):
        logger.error(f"CSVファイルが存在しません: {csv_file}")
        return False

    try:
        # CSVファイルを読み込み
        df = pd.read_csv(csv_file)

        # 必須カラムの確認
        required_columns = [
            "user_email",
            "project_id",
            "asset_name",
            "asset_type",
            "role",
        ]
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            logger.error(
                f"CSVファイルに必須カラムがありません: {', '.join(missing_columns)}"
            )
            return False

        # データの存在確認
        if df.empty:
            logger.error("CSVファイルにデータがありません")
            return False

        # 各行のデータ検証
        for idx, row in df.iterrows():
            # 必須フィールドの空チェック
            empty_fields = [
                col for col in required_columns if pd.isna(row[col]) or row[col] == ""
            ]
            if empty_fields:
                logger.error(
                    f"行 {idx + 2}: 必須フィールドが空です: {', '.join(empty_fields)}"
                )
                return False

        logger.info(f"CSVファイルの検証に成功しました: {len(df)} 行のデータ")
        return True

    except Exception as e:
        logger.error(f"CSVファイルの検証中にエラーが発生しました: {str(e)}")
        return False


def process_csv(
    csv_file: str, iam_manager: IAMBindingManager, dry_run: bool = False
) -> Dict[str, Any]:
    """
    CSVファイルからIAMバインディングを処理します。

    Args:
        csv_file: 処理するCSVファイルのパス
        iam_manager: IAMBindingManagerインスタンス
        dry_run: 実際に変更を行わない検証モード

    Returns:
        処理結果を含む辞書
    """
    results = {"total": 0, "success": 0, "failed": 0, "errors": []}

    if not validate_csv(csv_file):
        logger.error("CSVファイルの検証に失敗しました")
        return results

    try:
        # CSVファイルを読み込み
        df = pd.read_csv(csv_file)
        results["total"] = len(df)

        # 各行を処理
        for idx, row in df.iterrows():
            row_num = idx + 2  # ヘッダーを考慮して1-indexedに

            try:
                user_email = row["user_email"]
                project_id = row["project_id"]
                asset_name = row["asset_name"]
                asset_type = row["asset_type"]
                role = row["role"]

                logger.info(
                    f"行 {row_num}: ユーザー {user_email} にロール {role} を追加します (アセット: {asset_name})"
                    + (" (ドライラン)" if dry_run else "")
                )

                # IAMバインディングを追加
                success, response = iam_manager.add_binding(
                    user_email=user_email,
                    role=role,
                    asset_name=asset_name,
                    asset_type=asset_type,
                    project_id=project_id,
                    dry_run=dry_run,
                )

                if success:
                    results["success"] += 1
                    logger.info(
                        f"行 {row_num}: 権限の追加に成功しました"
                        + (" (ドライラン)" if dry_run else "")
                    )
                else:
                    results["failed"] += 1
                    error_msg = f"行 {row_num}: 権限の追加に失敗しました - {response}"
                    logger.error(error_msg)
                    results["errors"].append({"row": row_num, "error": error_msg})

            except Exception as e:
                results["failed"] += 1
                error_msg = f"行 {row_num}: 処理中にエラーが発生しました - {str(e)}"
                logger.error(error_msg)
                results["errors"].append({"row": row_num, "error": error_msg})

        logger.info(
            f"CSVファイルの処理が完了しました: 成功 {results['success']}, 失敗 {results['failed']}"
            + (" (ドライラン)" if dry_run else "")
        )
        return results

    except Exception as e:
        logger.error(f"CSVファイルの処理中にエラーが発生しました: {str(e)}")
        return results


def parse_arguments(args: Optional[List[str]] = None) -> argparse.Namespace:
    """
    コマンドライン引数を解析します。

    Args:
        args: コマンドライン引数のリスト（指定しない場合はsys.argvを使用）

    Returns:
        解析された引数のNamespace
    """
    parser = argparse.ArgumentParser(
        description="CSVファイルからGoogle CloudリソースにIAM権限を一括追加するツール"
    )

    parser.add_argument(
        "csv_file", help="権限を追加するユーザーとリソースの情報を含むCSVファイル"
    )

    parser.add_argument(
        "-c",
        "--credentials",
        help="サービスアカウントキーファイルへのパス（未指定の場合はGCPの標準認証情報を使用）",
    )

    parser.add_argument(
        "--config",
        help="アセット設定ファイルへのパス（未指定の場合はデフォルト設定を使用）",
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="実際に権限を変更せずに確認のみ行う"
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="詳細なログ出力を有効にする"
    )

    return parser.parse_args(args)


def validate_args(args: argparse.Namespace) -> bool:
    """
    コマンドライン引数を検証します。

    Args:
        args: 解析された引数のNamespace

    Returns:
        検証結果（True：有効な引数、False：無効な引数）
    """
    # CSVファイルの存在確認
    if not os.path.exists(args.csv_file):
        logging.error(f"CSVファイルが見つかりません: {args.csv_file}")
        return False

    # 認証情報ファイルの存在確認（指定されている場合）
    if args.credentials and not os.path.exists(args.credentials):
        logging.error(f"認証情報ファイルが見つかりません: {args.credentials}")
        return False

    # 設定ファイルの存在確認（指定されている場合）
    if args.config and not os.path.exists(args.config):
        logging.error(f"設定ファイルが見つかりません: {args.config}")
        return False

    return True


def main(args: Optional[List[str]] = None) -> int:
    """
    メイン関数

    Args:
        args: コマンドライン引数のリスト（指定しない場合はsys.argvを使用）

    Returns:
        終了コード（0：成功、1：失敗）
    """
    # 引数の解析
    parsed_args = parse_arguments(args)

    # ロギングの設定
    log_level = logging.DEBUG if parsed_args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler("iam_bindings.log"), logging.StreamHandler()],
    )

    # 引数の検証
    if not validate_args(parsed_args):
        return 1

    try:
        # IAMマネージャーの初期化
        manager = IAMBindingManager(
            credentials_path=parsed_args.credentials,
            config_file=parsed_args.config,
            verbose=parsed_args.verbose,
        )

        logging.info("=== Google Cloud IAMバインディング追加ツール ===")
        if parsed_args.dry_run:
            logging.info("ドライラン: 実際の変更は行われません")

        # CSVファイルの処理
        results = process_csv(
            csv_file=parsed_args.csv_file,
            iam_manager=manager,
            dry_run=parsed_args.dry_run,
        )

        # 結果の表示
        logging.info(
            f"処理が完了しました: 成功 {results['success']}, 失敗 {results['failed']}"
        )

        return 0 if results["failed"] == 0 else 1

    except Exception as e:
        logging.error(f"実行中にエラーが発生しました: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
