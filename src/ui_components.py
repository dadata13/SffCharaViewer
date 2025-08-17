# -*- coding: utf-8 -*-
"""
UIコンポーネント管理モジュール
PyQt5を使用したUI要素の作成と管理を行う
"""

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from typing import Dict, Any, Optional
import json
import os

class LanguageManager:
    """言語管理クラス（設定保存機能付き）"""
    
    def __init__(self, config_file: str = "config/sffviewer_config.json"):
        # .exe実行時の設定ファイルパスを調整
        import sys
        if getattr(sys, 'frozen', False):
            # PyInstaller/.exeで実行されている場合
            exe_dir = os.path.dirname(sys.executable)
            self.config_file = os.path.join(exe_dir, config_file)
        else:
            # 通常のPythonスクリプトで実行されている場合
            self.config_file = config_file
        
        self.current_language = 'en'  # デフォルトは英語
        self.load_settings()  # 起動時に設定を読み込み
        
        self.translations = {
            'ja': {
                'menu_file': 'ファイル',
                'menu_open_sff': 'SFFファイルを開く',
                'menu_open_air': 'AIRファイルを開く', 
                'menu_save_sprite': 'スプライトを保存',
                'menu_save_all': 'すべてのスプライトを保存',
                'menu_export_gif': 'GIFを出力',
                'menu_quit': '終了',
                'menu_view': '表示',
                'menu_toggle_bg': '背景切り替え',
                'menu_view_clsn': '当たり判定表示切り替え',
                'menu_settings': '設定',
                'menu_language': '言語',
                'menu_japanese': '日本語',
                'menu_english': 'English',
                'menu_switch_to_english': 'Switch to English',
                'menu_switch_to_japanese': '日本語に切り替え',
                'sprite_list': 'スプライトリスト',
                'palette_list': 'パレットリスト',
                'animation_list': 'アニメーションリスト',
                'anim_info_default': 'アニメーション情報: (アニメーションが選択されていません)',
                'anim_info_format': 'アニメ: {anim_no} | フレーム: {frame}/{total} | グループ: {group} | 画像: {image} | 時間: {time} | X: {x} | Y: {y}',
                'play_button': '再生',
                'pause_button': '停止',
                'prev_button': '前',
                'next_button': '次',
                'speed_label': '再生速度:',
                'open_sff_dialog': 'SFFファイルを開く',
                'open_air_dialog': 'AIRファイルを開く',
                'sff_files': 'SFFファイル (*.sff)',
                'air_files': 'AIRファイル (*.air)',
                'all_files': 'すべてのファイル (*)',
                'error': 'エラー',
                'warning': '警告',
                'info': '情報',
                'loading': '読み込み中...',
                'cache_status': 'キャッシュ: {cached}/{total} images',
                
                # 新しいUIテキスト
                'main_instruction': 'SFF または DEF を開いてください',
                'button_open_file': 'SFF/DEFを開く',
                'label_display_size': '表示サイズ:',
                'checkbox_original_size': '原寸',
                'checkbox_no_alpha': '透明度無効',
                'checkbox_show_clsn': '当たり判定表示',
                'button_gif_export': 'GIF出力',
                'tooltip_gif_export': '選択したアニメをGIFに出力',
                'button_image_export': '画像出力',
                'tooltip_image_export': '現在の画像をBMP/PNG/GIFで出力',
                'button_spritesheet_all': '全シート出力',
                'tooltip_spritesheet_all': 'SFF全体のスプライトシートを出力',
                'button_spritesheet_anim': 'アニメシート出力',
                'tooltip_spritesheet_anim': '選択中のアニメーションのスプライトシートを出力',
                'button_all_gif_export': '全GIF出力',
                'tooltip_all_gif_export': '全アニメーションを個別GIFで出力',
            },
            'en': {
                'menu_file': 'File',
                'menu_open_sff': 'Open SFF File',
                'menu_open_air': 'Open AIR File',
                'menu_save_sprite': 'Save Sprite',
                'menu_save_all': 'Save All Sprites',
                'menu_export_gif': 'Export GIF',
                'menu_quit': 'Quit',
                'menu_view': 'View',
                'menu_toggle_bg': 'Toggle Background',
                'menu_view_clsn': 'Toggle Collision View',
                'menu_settings': 'Settings',
                'menu_language': 'Language',
                'menu_japanese': '日本語',
                'menu_english': 'English',
                'menu_switch_to_english': 'Switch to English',
                'menu_switch_to_japanese': '日本語に切り替え',
                'sprite_list': 'Sprite List',
                'palette_list': 'Palette List',
                'animation_list': 'Animation List',
                'anim_info_default': 'Animation Info: (No animation selected)',
                'anim_info_format': 'Anim: {anim_no} | Frame: {frame}/{total} | Group: {group} | Image: {image} | Time: {time} | X: {x} | Y: {y}',
                'play_button': 'Play',
                'pause_button': 'Pause',
                'prev_button': 'Prev',
                'next_button': 'Next',
                'speed_label': 'Speed:',
                'open_sff_dialog': 'Open SFF File',
                'open_air_dialog': 'Open AIR File',
                'sff_files': 'SFF Files (*.sff)',
                'air_files': 'AIR Files (*.air)',
                'all_files': 'All Files (*)',
                'error': 'Error',
                'warning': 'Warning',
                'info': 'Information',
                'loading': 'Loading...',
                'cache_status': 'Cache: {cached}/{total} images',
                
                # 新しいUIテキスト
                'main_instruction': 'Please open an SFF or DEF file',
                'button_open_file': 'Open SFF/DEF',
                'label_display_size': 'Display Size:',
                'checkbox_original_size': 'Original',
                'checkbox_no_alpha': 'No Alpha',
                'checkbox_show_clsn': 'Show Collision',
                'button_gif_export': 'Export GIF',
                'tooltip_gif_export': 'Export selected animation to GIF',
                'button_image_export': 'Export Image',
                'tooltip_image_export': 'Export current image as BMP/PNG/GIF',
                'button_spritesheet_all': 'Export All Sprites',
                'tooltip_spritesheet_all': 'Export sprite sheet of entire SFF',
                'button_spritesheet_anim': 'Export Anim Sprites',
                'tooltip_spritesheet_anim': 'Export sprite sheet of selected animation',
                'button_all_gif_export': 'Export All GIFs',
                'tooltip_all_gif_export': 'Export all animations as individual GIFs',
            }
        }
    
    def get_text(self, key: str, **kwargs) -> str:
        """テキストを取得（フォーマット対応）"""
        text = self.translations.get(self.current_language, {}).get(key, key)
        if kwargs:
            return text.format(**kwargs)
        return text
    
    def set_language(self, language: str):
        """言語を設定し、設定を保存"""
        if language in self.translations:
            self.current_language = language
            self.save_settings()
    
    def save_settings(self, extra_settings: dict = None):
        """設定をファイルに保存"""
        try:
            settings = {
                'language': self.current_language
            }
            # 追加の設定があれば統合
            if extra_settings:
                settings.update(extra_settings)
            
            # 設定ファイルのディレクトリが存在しない場合は作成
            config_dir = os.path.dirname(self.config_file)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Failed to save settings: {e}")
    
    def load_settings(self):
        """設定をファイルから読み込み"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self.current_language = settings.get('language', 'en')
                    return settings
        except Exception as e:
            print(f"Failed to load settings: {e}")
            self.current_language = 'en'  # デフォルトは英語
        return {}
    
    def get_opposite_language_button_text(self) -> str:
        """現在の言語の反対の言語への切り替えボタンテキストを取得"""
        if self.current_language == 'ja':
            return self.get_text('menu_switch_to_english')
        else:
            return self.get_text('menu_switch_to_japanese')
    
    def get_opposite_language(self) -> str:
        """現在の言語の反対の言語コードを取得"""
        return 'en' if self.current_language == 'ja' else 'ja'


class ImageCache:
    """画像キャッシュ管理クラス"""
    
    def __init__(self, max_cache_size: int = 100):
        self.max_cache_size = max_cache_size
        self.cache: Dict[tuple, Any] = {}  # (group, image, palette_index) -> QPixmap
        self.access_order = []  # LRU管理用
        self.cache_hits = 0
        self.cache_misses = 0
    
    def get_cache_key(self, group: int, image: int, palette_index: int = 0) -> tuple:
        """キャッシュキーを生成"""
        return (group, image, palette_index)
    
    def get(self, group: int, image: int, palette_index: int = 0) -> Optional[Any]:
        """キャッシュから画像を取得"""
        key = self.get_cache_key(group, image, palette_index)
        if key in self.cache:
            # LRU更新
            if key in self.access_order:
                self.access_order.remove(key)
            self.access_order.append(key)
            self.cache_hits += 1
            return self.cache[key]
        
        self.cache_misses += 1
        return None
    
    def put(self, group: int, image: int, palette_index: int, pixmap: Any):
        """画像をキャッシュに保存"""
        key = self.get_cache_key(group, image, palette_index)
        
        # キャッシュサイズ制限
        while len(self.cache) >= self.max_cache_size:
            if self.access_order:
                oldest_key = self.access_order.pop(0)
                if oldest_key in self.cache:
                    del self.cache[oldest_key]
        
        self.cache[key] = pixmap
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)
    
    def clear(self):
        """キャッシュをクリア"""
        self.cache.clear()
        self.access_order.clear()
        self.cache_hits = 0
        self.cache_misses = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """キャッシュ統計を取得"""
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'cache_size': len(self.cache),
            'max_size': self.max_cache_size,
            'hits': self.cache_hits,
            'misses': self.cache_misses,
            'hit_rate': hit_rate
        }


class UIHelper:
    """UI作成補助クラス"""
    
    @staticmethod
    def safe_set_label_text(label: QLabel, text: str):
        """ラベルに安全にテキストを設定"""
        if label and not label.isWidgetType() or label.parent() is None:
            return
        try:
            label.setText(text)
        except RuntimeError:
            # ウィジェットが削除されている場合は無視
            pass
    
    @staticmethod
    def create_list_widget() -> QListWidget:
        """標準的なリストウィジェットを作成"""
        list_widget = QListWidget()
        list_widget.setAlternatingRowColors(True)
        return list_widget
    
    @staticmethod
    def create_button(text: str, callback=None) -> QPushButton:
        """標準的なボタンを作成"""
        button = QPushButton(text)
        if callback:
            button.clicked.connect(callback)
        return button
    
    @staticmethod
    def create_slider(min_val: int, max_val: int, default_val: int = None) -> QSlider:
        """標準的なスライダーを作成"""
        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(min_val)
        slider.setMaximum(max_val)
        if default_val is not None:
            slider.setValue(default_val)
        return slider


class StatusBarManager:
    """ステータスバー管理クラス"""
    
    def __init__(self, status_bar: QStatusBar, language_manager: LanguageManager):
        self.status_bar = status_bar
        self.language_manager = language_manager
        self.cache_label = QLabel()
        self.status_bar.addPermanentWidget(self.cache_label)
        
    def update_cache_status(self, cache_stats: Dict[str, Any]):
        """キャッシュ状態を更新"""
        text = self.language_manager.get_text(
            'cache_status',
            cached=cache_stats['cache_size'],
            total=cache_stats['cache_size']
        )
        self.cache_label.setText(text)
    
    def show_message(self, message: str, timeout: int = 2000):
        """ステータスメッセージを表示"""
        self.status_bar.showMessage(message, timeout)
    
    def clear_status(self):
        """ステータスバーをクリア"""
        self.status_bar.clearMessage()
        self.cache_label.setText("")
