#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
IAMバインディング追加スクリプトのテスト
"""

import os
import pytest
from unittest.mock import MagicMock, patch
import tempfile
import csv
import pandas as pd

from add_bindings import validate_csv, process_csv

class TestAddBindings:
    """add_bindings.pyのテスト"""
    
    @pytest.fixture
    def valid_csv_path(self):
        """有効なCSVファイルパスを取得するフィクスチャ"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            writer = csv.writer(f)
            writer.writerow(['user_email', 'project_id', 'asset_name', 'asset_type', 'role'])
            writer.writerow(['user1@example.com', 'project-1', 
                           '//cloudresourcemanager.googleapis.com/projects/project-1', 
                           'cloudresourcemanager.googleapis.com/Project', 'roles/viewer'])
            writer.writerow(['user1@example.com', 'project-1', 
                           '//storage.googleapis.com/projects/_/buckets/bucket-1', 
                           'storage.googleapis.com/Bucket', 'roles/storage.objectViewer'])
            writer.writerow(['user2@example.com', 'project-1', 
                           '//bigquery.googleapis.com/projects/project-1/datasets/dataset_1', 
                           'bigquery.googleapis.com/Dataset', 'roles/bigquery.dataViewer'])
        
        yield f.name
        os.unlink(f.name)
    
    @pytest.fixture
    def invalid_csv_path(self):
        """無効なCSVファイルパスを取得するフィクスチャ"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            writer = csv.writer(f)
            writer.writerow(['user_email', 'project_id', 'asset_type', 'role'])  # asset_nameカラムがない
            writer.writerow(['user1@example.com', 'project-1', 'cloudresourcemanager.googleapis.com/Project', 'roles/viewer'])
        
        yield f.name
        os.unlink(f.name)
    
    @pytest.fixture
    def missing_resource_name_csv_path(self):
        """リソース名が必要なのに欠けているCSVファイルパスを取得するフィクスチャ"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            writer = csv.writer(f)
            writer.writerow(['user_email', 'project_id', 'resource_type', 'resource_name', 'role'])
            writer.writerow(['user1@example.com', 'project-1', 'project', '', 'roles/viewer'])
            writer.writerow(['user1@example.com', 'project-1', 'bucket', '', 'roles/storage.objectViewer'])  # bucketにリソース名がない
        
        yield f.name
        os.unlink(f.name)
    
    def test_validate_csv_valid(self, valid_csv_path):
        """有効なCSVファイルの検証テスト"""
        assert validate_csv(valid_csv_path) is True
    
    def test_validate_csv_invalid_columns(self, invalid_csv_path):
        """無効なCSVファイル（カラム不足）の検証テスト"""
        assert validate_csv(invalid_csv_path) is False
    
    def test_validate_csv_missing_resource_name(self, missing_resource_name_csv_path):
        """リソース名が必要なのに欠けているCSVファイルの検証テスト"""
        assert validate_csv(missing_resource_name_csv_path) is False
    
    def test_validate_csv_file_not_found(self):
        """存在しないCSVファイルの検証テスト"""
        assert validate_csv('non_existent_file.csv') is False
    
    @patch('add_bindings.IAMBindingManager')
    def test_process_csv(self, mock_iam_manager_class, valid_csv_path):
        """CSVファイル処理のテスト"""
        # IAMBindingManagerのモック
        mock_iam_manager = MagicMock()
        mock_iam_manager_class.return_value = mock_iam_manager
        
        # add_bindingメソッドが成功を返すように設定
        mock_iam_manager.add_binding.return_value = (True, {'done': True})
        
        # CSVファイルの処理
        results = process_csv(valid_csv_path, mock_iam_manager)
        
        # 検証
        assert results['total'] == 3
        assert results['success'] == 3
        assert results['failed'] == 0
        assert len(results['errors']) == 0
        
        # 各行に対してadd_bindingが呼ばれたことを確認
        assert mock_iam_manager.add_binding.call_count == 3
        
        # 呼び出し引数の検証
        calls = mock_iam_manager.add_binding.call_args_list
        
        # 1行目: プロジェクト
        assert calls[0][1]['user_email'] == 'user1@example.com'
        assert calls[0][1]['project_id'] == 'project-1'
        assert calls[0][1]['asset_name'] == '//cloudresourcemanager.googleapis.com/projects/project-1'
        assert calls[0][1]['asset_type'] == 'cloudresourcemanager.googleapis.com/Project'
        assert calls[0][1]['role'] == 'roles/viewer'
        
        # 2行目: バケット
        assert calls[1][1]['user_email'] == 'user1@example.com'
        assert calls[1][1]['project_id'] == 'project-1'
        assert calls[1][1]['asset_name'] == '//storage.googleapis.com/projects/_/buckets/bucket-1'
        assert calls[1][1]['asset_type'] == 'storage.googleapis.com/Bucket'
        assert calls[1][1]['role'] == 'roles/storage.objectViewer'
        
        # 3行目: データセット
        assert calls[2][1]['user_email'] == 'user2@example.com'
        assert calls[2][1]['project_id'] == 'project-1'
        assert calls[2][1]['asset_name'] == '//bigquery.googleapis.com/projects/project-1/datasets/dataset_1'
        assert calls[2][1]['asset_type'] == 'bigquery.googleapis.com/Dataset'
        assert calls[2][1]['role'] == 'roles/bigquery.dataViewer'
    
    @patch('add_bindings.IAMBindingManager')
    def test_process_csv_with_errors(self, mock_iam_manager_class, valid_csv_path):
        """エラーを含むCSVファイル処理のテスト"""
        # IAMBindingManagerのモック
        mock_iam_manager = MagicMock()
        mock_iam_manager_class.return_value = mock_iam_manager
        
        # 1行目は成功、2行目は失敗、3行目は例外を発生させる
        mock_iam_manager.add_binding.side_effect = [
            (True, {'done': True}),
            (False, "権限がありません"),
            Exception("APIエラー")
        ]
        
        # CSVファイルの処理
        results = process_csv(valid_csv_path, mock_iam_manager)
        
        # 検証
        assert results['total'] == 3
        assert results['success'] == 1
        assert results['failed'] == 2
        assert len(results['errors']) == 2
        
        # エラー内容の検証
        assert results['errors'][0]['row'] == 3  # 2行目 (1-indexed)
        assert "権限がありません" in results['errors'][0]['error']
        
        assert results['errors'][1]['row'] == 4  # 3行目 (1-indexed)
        assert "APIエラー" in results['errors'][1]['error']
    
    @patch('add_bindings.IAMBindingManager')
    def test_process_csv_dry_run(self, mock_iam_manager_class, valid_csv_path):
        """ドライランモードでのCSVファイル処理のテスト"""
        # IAMBindingManagerのモック
        mock_iam_manager = MagicMock()
        mock_iam_manager_class.return_value = mock_iam_manager
        
        # add_bindingメソッドが成功を返すように設定
        mock_iam_manager.add_binding.return_value = (True, None)
        
        # CSVファイルの処理 (ドライラン)
        results = process_csv(valid_csv_path, mock_iam_manager, dry_run=True)
        
        # 検証
        assert results['total'] == 3
        assert results['success'] == 3
        assert results['failed'] == 0
        
        # 各行に対してadd_bindingが呼ばれたことを確認（dry_run=Trueで）
        assert mock_iam_manager.add_binding.call_count == 3
        for call in mock_iam_manager.add_binding.call_args_list:
            assert call[1]['dry_run'] is True 