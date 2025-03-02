#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Google Cloud IAMバインディングをCSVファイルから追加するメインスクリプト
"""

import argparse
import csv
import logging
import os
import sys
from typing import Dict, List

import pandas as pd

from iam_binding_utils import IAMBindingManager

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('iam_bindings.log')
    ]
)

logger = logging.getLogger(__name__)

def parse_arguments():
    """コマンドライン引数をパースします"""
    parser = argparse.ArgumentParser(description='Google Cloud IAMバインディングをCSVから追加')
    
    parser.add_argument(
        '--csv-file',
        required=True,
        help='処理するCSVファイルのパス'
    )
    
    parser.add_argument(
        '--credentials',
        help='Google Cloudサービスアカウントキーファイルのパス'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='実際の変更を適用せずに処理をシミュレーション'
    )
    
    parser.add_argument(
        '--config-file',
        help='アセットタイプ設定ファイルのパス (.json, .yaml, or .yml)'
    )
    
    parser.add_argument(
        '--export-config',
        help='現在のアセットタイプ設定をエクスポートするファイルパス'
    )
    
    parser.add_argument(
        '--list-asset-types',
        action='store_true',
        help='サポートされているアセットタイプを表示する'
    )
    
    return parser.parse_args()

def validate_csv(csv_path: str) -> bool:
    """
    CSVファイルの形式を検証します
    
    Args:
        csv_path: CSVファイルのパス
        
    Returns:
        検証結果 (True: 有効, False: 無効)
    """
    required_columns = ['user_email', 'project_id', 'asset_name', 'asset_type', 'role']
    
    try:
        df = pd.read_csv(csv_path)
        
        # 必須カラムの存在確認
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            logger.error(f"CSVに必須カラムがありません: {', '.join(missing_columns)}")
            return False
        
        # 値の検証
        if df['user_email'].isna().any():
            logger.error("user_emailにnull値があります")
            return False
        
        if df['project_id'].isna().any():
            logger.error("project_idにnull値があります")
            return False
        
        if df['asset_name'].isna().any():
            logger.error("asset_nameにnull値があります")
            return False

        if df['asset_type'].isna().any():
            logger.error("asset_typeにnull値があります")
            return False
        
        if df['role'].isna().any():
            logger.error("roleにnull値があります")
            return False
        
        return True
    
    except Exception as e:
        logger.error(f"CSV検証エラー: {e}")
        return False

def process_csv(csv_path: str, iam_manager: IAMBindingManager, dry_run: bool = False) -> Dict:
    """
    CSVファイルを処理してIAMバインディングを追加します
    
    Args:
        csv_path: CSVファイルのパス
        iam_manager: IAMBindingManagerのインスタンス
        dry_run: ドライラン実行フラグ
        
    Returns:
        処理結果の概要
    """
    results = {
        'total': 0,
        'success': 0,
        'failed': 0,
        'errors': []
    }
    
    try:
        df = pd.read_csv(csv_path)
        results['total'] = len(df)
        
        for index, row in df.iterrows():
            user_email = row['user_email']
            project_id = row['project_id']
            asset_name = row['asset_name']
            asset_type = row['asset_type']
            role = row['role']
            
            try:
                logger.info(f"処理中: {user_email}, {project_id}, {asset_name}, {asset_type}, {role}")
                
                success, response = iam_manager.add_binding(
                    user_email=user_email,
                    role=role,
                    asset_name=asset_name,
                    asset_type=asset_type,
                    project_id=project_id,
                    dry_run=dry_run
                )
                
                if success:
                    results['success'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append({
                        'row': index + 2,  # CSVの行番号（ヘッダー + 0ベース -> 1ベース）
                        'data': {
                            'user_email': user_email,
                            'project_id': project_id,
                            'asset_name': asset_name,
                            'asset_type': asset_type,
                            'role': role
                        },
                        'error': str(response)
                    })
            
            except Exception as e:
                logger.error(f"行 {index + 2} の処理中にエラーが発生しました: {e}")
                results['failed'] += 1
                results['errors'].append({
                    'row': index + 2,
                    'data': {
                        'user_email': user_email,
                        'project_id': project_id,
                        'asset_name': asset_name,
                        'asset_type': asset_type,
                        'role': role
                    },
                    'error': str(e)
                })
        
        return results
    
    except Exception as e:
        logger.error(f"CSVファイル処理エラー: {e}")
        results['failed'] = results['total']
        results['errors'].append({
            'row': 0,
            'data': {},
            'error': str(e)
        })
        return results

def main():
    """メイン関数"""
    args = parse_arguments()
    
    try:
        # IAM管理クラスの初期化
        iam_manager = IAMBindingManager(
            credentials_path=args.credentials,
            config_file=args.config_file
        )
        
        # アセットタイプの一覧表示
        if args.list_asset_types:
            asset_types = iam_manager.list_supported_asset_types()
            print("サポートされているアセットタイプ:")
            for asset_type in asset_types:
                print(f"- {asset_type}")
            return
        
        # 設定エクスポート
        if args.export_config:
            iam_manager.export_config(args.export_config)
            logger.info(f"アセットタイプ設定を {args.export_config} にエクスポートしました")
            return
        
        # CSVファイル検証
        if not validate_csv(args.csv_file):
            logger.error("CSVファイルの検証に失敗しました")
            sys.exit(1)
        
        # 処理の開始
        mode = "ドライラン" if args.dry_run else "通常実行"
        logger.info(f"{mode}モードでCSVファイル {args.csv_file} の処理を開始します")
        
        # CSVの処理
        results = process_csv(args.csv_file, iam_manager, args.dry_run)
        
        # 結果の出力
        logger.info(f"処理完了: 合計={results['total']}, 成功={results['success']}, 失敗={results['failed']}")
        
        if results['failed'] > 0:
            logger.warning("エラーが発生した行:")
            for error in results['errors']:
                logger.warning(f"行 {error['row']}: {error['error']}")
            sys.exit(1)
        
    except Exception as e:
        logger.error(f"実行エラー: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 