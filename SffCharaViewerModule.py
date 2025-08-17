# -*- coding: utf-8 -*-
"""
SffCharaViewer Python Module
外部のPythonコードから使用するためのモジュールインターフェース

使用例:
    # GUI版
    import SffCharaViewerModule as sffv
    viewer = sffv.create_viewer()
    viewer.load_sff_file("character.sff")
    viewer.show()
    
    # API版（ヘッドレス）
    api = sffv.SFFViewerAPI()
    sprites = api.get_sprite_list("character.sff")
    image = api.extract_sprite_image("character.sff", 0)
"""

import sys
import os
from typing import Optional, List, Dict, Any, Union

# メインモジュールからインポート
from SffCharaViewer import (
    SFFViewer, SFFViewerConfig, SFFViewerAPI,
    main as run_standalone,
    create_standalone_viewer
)

# バージョン情報
__version__ = "1.0.0"
__author__ = "SffCharaViewer Development Team"


class SFFViewerModule:
    """
    SffCharaViewerのメインモジュールクラス
    GUIとAPIの両方のインターフェースを提供
    """
    
    def __init__(self, config: Optional[SFFViewerConfig] = None):
        """
        初期化
        
        Args:
            config: SFFViewerConfig オブジェクト（オプション）
        """
        self.config = config or SFFViewerConfig()
        self._viewer = None
        self._app = None
    
    def create_gui_viewer(self, show_immediately: bool = False) -> SFFViewer:
        """
        GUIビューアを作成
        
        Args:
            show_immediately: 即座に表示するかどうか
            
        Returns:
            SFFViewer: GUIビューアオブジェクト
        """
        from PyQt5.QtWidgets import QApplication
        
        # QApplicationが存在しない場合は作成
        if not QApplication.instance():
            self._app = QApplication(sys.argv)
        
        self._viewer = create_standalone_viewer(self.config)
        
        if show_immediately:
            self._viewer.show()
            if hasattr(self._viewer, 'image_window'):
                self._viewer.image_window.show()
        
        return self._viewer
    
    def get_viewer(self) -> Optional[SFFViewer]:
        """
        現在のビューアインスタンスを取得
        
        Returns:
            SFFViewer or None: ビューアオブジェクト
        """
        return self._viewer
    
    def run_event_loop(self):
        """
        Qtイベントループを実行（GUIアプリケーション用）
        """
        if self._app:
            sys.exit(self._app.exec_())
    
    @staticmethod
    def get_api() -> SFFViewerAPI:
        """
        ヘッドレスAPIインスタンスを取得
        
        Returns:
            SFFViewerAPI: APIオブジェクト
        """
        return SFFViewerAPI


# 便利な関数群
def create_viewer(config: Optional[SFFViewerConfig] = None, 
                 show: bool = False) -> SFFViewer:
    """
    SFFViewerインスタンスを作成（簡略版）
    
    Args:
        config: 設定オブジェクト
        show: 即座に表示するかどうか
        
    Returns:
        SFFViewer: ビューアオブジェクト
    """
    module = SFFViewerModule(config)
    return module.create_gui_viewer(show)


def create_config(debug_mode: bool = False, 
                 default_scale: float = 2.0,
                 window_width: int = 1200,
                 window_height: int = 800) -> SFFViewerConfig:
    """
    設定オブジェクトを作成（簡略版）
    
    Args:
        debug_mode: デバッグモード
        default_scale: デフォルトスケール
        window_width: ウィンドウ幅
        window_height: ウィンドウ高さ
        
    Returns:
        SFFViewerConfig: 設定オブジェクト
    """
    return SFFViewerConfig(
        debug_mode=debug_mode,
        default_scale=default_scale,
        window_width=window_width,
        window_height=window_height
    )


def get_sprite_info(file_path: str) -> List[Dict[str, Any]]:
    """
    SFFファイルのスプライト情報を取得（簡略版）
    
    Args:
        file_path: SFFファイルパス
        
    Returns:
        list: スプライト情報のリスト
    """
    return SFFViewerAPI.get_sprite_list(file_path)


def extract_sprite(file_path: str, sprite_index: int, 
                  output_path: Optional[str] = None):
    """
    スプライトを画像として抽出（簡略版）
    
    Args:
        file_path: SFFファイルパス
        sprite_index: スプライトインデックス
        output_path: 出力パス（Noneの場合はQImageを返す）
        
    Returns:
        QImage or bool: 画像オブジェクトまたは成功状態
    """
    return SFFViewerAPI.extract_sprite_image(file_path, sprite_index, output_path)


def run_standalone_app():
    """
    スタンドアロンアプリケーションとして実行
    """
    return run_standalone()


# エクスポートする主要なクラス・関数
__all__ = [
    'SFFViewerModule',
    'SFFViewer', 
    'SFFViewerConfig',
    'SFFViewerAPI',
    'create_viewer',
    'create_config', 
    'get_sprite_info',
    'extract_sprite',
    'run_standalone_app',
    '__version__',
    '__author__'
]


# モジュールレベルでの使用例とテスト
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='SffCharaViewer Module Test')
    parser.add_argument('--test-api', action='store_true', help='Test API functionality')
    parser.add_argument('--test-gui', action='store_true', help='Test GUI functionality')
    parser.add_argument('--file', type=str, help='SFF file for testing')
    args = parser.parse_args()
    
    if args.test_api:
        print("Testing API functionality...")
        if args.file:
            try:
                sprites = get_sprite_info(args.file)
                print(f"Found {len(sprites)} sprites in {args.file}")
                if sprites:
                    print(f"First sprite: {sprites[0]}")
            except Exception as e:
                print(f"API test failed: {e}")
        else:
            print("Please provide --file for API testing")
    
    elif args.test_gui:
        print("Testing GUI functionality...")
        config = create_config(debug_mode=True)
        viewer = create_viewer(config, show=True)
        
        if args.file:
            try:
                viewer.load_sff_file(args.file)
                print(f"Loaded file: {args.file}")
            except Exception as e:
                print(f"Failed to load file: {e}")
        
        # イベントループを実行
        module = SFFViewerModule()
        module._app = viewer.parent() if hasattr(viewer, 'parent') else None
        if not module._app:
            from PyQt5.QtWidgets import QApplication
            module._app = QApplication.instance()
        module.run_event_loop()
    
    else:
        # デフォルトはスタンドアロン実行
        run_standalone_app()
