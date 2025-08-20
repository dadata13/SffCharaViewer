"""SffCharaViewer.py (Enhanced Modular Version)

SffCharaViewer - 格闘ゲーム用スプライトファイル(.sff)とアニメーション(.air)のビューア

機能:
 - SFF v1 / v2 読み込み (PNG fmt=10 含む)
 - スプライト一覧 / パレット一覧 / パレットプレビュー
 - 画像表示は別ウィンドウ (ImageWindow)
 - 動的キャンバス (拡大縮小対応)
 - 拡大率 (%) 指定 / 原寸表示トグル / Rキーでドラッグ位置リセット
 - 簡易 AIR アニメ再生 (60FPS)
 - 画像キャッシュ機能（パフォーマンス最適化）
 - 日本語/英語 言語切り替え
 - 改良されたアニメーション時間表示

新機能:
 - ImageCache: 画像の一時キャッシュで高速化
 - LanguageManager: 多言語対応
 - StatusBarManager: ステータス表示管理
 - UIHelper: UI作成補助機能

使用例:
    # スタンドアロン実行
    python SffCharaViewer.py
    
    # 他のコードから使用
    from SffCharaViewer import SFFViewer, SFFViewerConfig
    config = SFFViewerConfig(window_width=800, debug_mode=False)
    viewer = SFFViewer(config)
    viewer.load_sff_file("character.sff")
    viewer.show()

クラス構成:
 - SFFViewerConfig: 設定管理
 - SFFRenderer: 画像レンダリング処理  
 - DraggableGraphicsView: ドラッグ可能なビュー
 - ImageWindow: 画像表示ウィンドウ
 - SFFViewer: メインビューアクラス
"""

from __future__ import annotations
import os, sys, re, logging
from typing import Dict, List, Tuple, Optional, Union
from dataclasses import dataclass

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# PyQt5のインポート（GUI機能用）
try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QFileDialog, QLabel, QPushButton, QVBoxLayout, QWidget,
        QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QListWidget, QHBoxLayout,
        QSpinBox, QCheckBox, QDialog, QDialogButtonBox, QRadioButton, QMessageBox, QComboBox,
        QMenuBar, QMenu, QAction, QStatusBar, QSlider
    )
    from PyQt5.QtGui import QPixmap, QImage, QColor, QPainter, qRgb, QPen, QBrush, QTransform
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal
    from PyQt5 import QtCore
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    # ヘッドレス実行時のダミークラス（必要に応じて）
    print("[INFO] PyQt5が利用できません。ヘッドレスモードで実行します。")

# 新しいモジュールのインポート
from src.ui_components import LanguageManager, ImageCache, UIHelper, StatusBarManager
from src.air_parser import AIRParser, parse_air
from src.sff_core import SFFParser, parse_sff

from src.sff_parser import SFFv1Reader as SFFReader

# SFFv2パーサーのインポート（安全なインポート）
try:
    from src.sffv2_parser import SFFv2Reader as SFFV2Reader, decode_sprite_v2
except ImportError:
    try:
        from sffv2_parser import SFFv2Reader as SFFV2Reader, decode_sprite_v2
    except ImportError:
        # フォールバック: v2機能無効
        SFFV2Reader = None
        decode_sprite_v2 = None
        print("[WARNING] SFFv2パーサーが利用できません。SFFv1のみサポートします。")


@dataclass
class SFFViewerConfig:
    """SFFViewer設定クラス"""
    # ウィンドウサイズ
    window_width: int = 620
    window_height: int = 760
    image_window_width: int = 820
    image_window_height: int = 640
    
    # 表示設定
    default_scale: float = 2.0
    min_scale: int = 25
    max_scale: int = 500
    
    # キャンバス設定
    canvas_margin: int = 4          # 余白をさらに小さく
    min_canvas_size: Tuple[int, int] = (200, 150)
    max_canvas_size: Tuple[int, int] = (4096, 4096)
    default_canvas_size: Tuple[int, int] = (800, 600)  # 固定キャンバスサイズ
    fixed_canvas_size: Tuple[int, int] = (800, 600)   # シンプル固定サイズ
    
    # アニメーション設定
    animation_fps: int = 60
    auto_fit_sprite: bool = True        # スプライト選択時に自動フィット（有効化）
    auto_fit_on_anim_start: bool = True # アニメ開始時に自動フィット（有効化）
    
    # キャンバス拡大設定
    enable_canvas_scale_multiplier: bool = False  # キャンバス自動2倍拡大を無効化
    canvas_scale_multiplier: float = 1.0         # キャンバス拡大率（1.0 = 等倍）
    
    # Clsn表示設定
    show_clsn: bool = False             # Clsn（当たり判定）表示フラグ
    clsn1_color: Tuple[int, int, int, int] = (255, 0, 0, 128)    # Clsn1（防御判定）色：赤
    clsn2_color: Tuple[int, int, int, int] = (0, 0, 255, 128)    # Clsn2（攻撃判定）色：青
    clsn1_default_color: Tuple[int, int, int, int] = (128, 0, 128, 128)  # Clsn1Default値がある場合：紫
    clsn2_default_color: Tuple[int, int, int, int] = (0, 255, 0, 128)    # Clsn2Default値がある場合：緑
    clsn_line_width: int = 2            # Clsnボックスの線の太さ
    
    # 座標変換設定
    canvas_inner_margin_px: float = 0.0  # キャンバス内部余白（ピクセル）
    
    # デバッグ設定
    debug_mode: bool = True


# 設定エイリアス
Config = SFFViewerConfig


class SFFRenderer:
    """SFF画像レンダリング処理クラス"""
    
    def __init__(self, config: SFFViewerConfig):
        self.config = config
    
    def render_sprite(self, reader, index: int, palette_idx: Optional[int] = None, 
                     is_v2: bool = False, act_palettes: Optional[List] = None) -> Tuple[QImage, List[Tuple[int,int,int,int]]]:
        """スプライトをQImageにレンダリング"""
        if is_v2:
            pal_idx = palette_idx if palette_idx is not None and palette_idx >= 0 else None
            decoded, palette, w, h, mode = decode_sprite_v2(reader, index, palette_override=pal_idx)
        else:
            s = reader.sprites[index]
            
            # パレットオーバーライドの決定
            palette_override = None
            if (palette_idx is not None and palette_idx >= 1 and 
                act_palettes is not None and palette_idx - 1 < len(act_palettes)):
                # ACTパレットを使用（palette_idx - 1 because 0 is SFF's own palette）
                palette_override = act_palettes[palette_idx - 1]
                print(f"[DEBUG] Using ACT palette {palette_idx - 1}: first color {palette_override[0]}, last color {palette_override[-1]}")
            elif palette_idx is not None and palette_idx >= 1:
                print(f"[DEBUG] ACT palette requested (idx={palette_idx}) but not available (has_act_palettes={act_palettes is not None}, count={len(act_palettes) if act_palettes else 0})")
            
            # SFFv1でもパレットオーバーライドを使用
            decoded, palette, w, h = reader.get_image(index, s.get('pal_idx', 0), palette_override=palette_override)
            mode = 'indexed'
        
        return self._create_qimage(decoded, palette, w, h, mode)
    
    def _create_qimage(self, decoded, palette, w: int, h: int, mode: str) -> Tuple[QImage, List[Tuple[int,int,int,int]]]:
        """デコードされたデータからQImageを作成"""
        if mode == 'rgba':
            img = QImage(w, h, QImage.Format_RGBA8888)
            stride = img.bytesPerLine()
            row_bytes = w * 4
            try:
                ptr = img.bits(); ptr.setsize(stride * h)
                mv = memoryview(ptr)
                if stride == row_bytes:
                    mv[:row_bytes * h] = decoded[:row_bytes * h]
                else:
                    for y in range(h):
                        src_off = y * row_bytes
                        dst_off = y * stride
                        mv[dst_off:dst_off+row_bytes] = decoded[src_off:src_off+row_bytes]
            except Exception as e:
                if self.config.debug_mode:
                    logging.warning(f"RGBA copy fallback (stride issue): {e}")
                img = QImage(bytes(decoded[:w*h*4]), w, h, QImage.Format_RGBA8888)
        else:
            img = QImage(w, h, QImage.Format_Indexed8)
            table = [QColor(r,g,b,a).rgba() for (r,g,b,a) in palette]
            img.setColorTable(table)
            stride = img.bytesPerLine()
            try:
                ptr = img.bits(); ptr.setsize(stride * h)
                mv = memoryview(ptr)
                if stride == w:
                    mv[:w*h] = decoded[:w*h]
                else:
                    for y in range(h):
                        src_off = y * w
                        dst_off = y * stride
                        mv[dst_off:dst_off+w] = decoded[src_off:src_off+w]
            except Exception as e:
                if self.config.debug_mode:
                    logging.warning(f"Indexed8 stride copy failed -> RGBA fallback: {e}")
                # RGBA fallbackの実装
                rgba = bytearray()
                for i in decoded[:w*h]:
                    if 0 <= i < len(palette):
                        r,g,b,a = palette[i]
                    else:
                        r=g=b=0; a=0
                    rgba.extend([r,g,b,a])
                img = QImage(w, h, QImage.Format_RGBA8888)
                stride2 = img.bytesPerLine(); row_bytes2 = w*4
                try:
                    ptr2 = img.bits(); ptr2.setsize(stride2*h)
                    mv2 = memoryview(ptr2)
                    if stride2 == row_bytes2:
                        mv2[:row_bytes2*h] = rgba[:row_bytes2*h]
                    else:
                        for y in range(h):
                            so = y*row_bytes2; do = y*stride2
                            mv2[do:do+row_bytes2] = rgba[so:so+row_bytes2]
                except: pass
        
        return img, palette
    
    def remove_alpha(self, qimg: QImage) -> QImage:
        """透明度を除去して白背景に合成"""
        if qimg.format() != QImage.Format_ARGB32:
            qimg = qimg.convertToFormat(QImage.Format_ARGB32)
        
        result = QImage(qimg.width(), qimg.height(), QImage.Format_RGB32)
        result.fill(QColor(255, 255, 255))
        
        painter = QPainter(result)
        painter.drawImage(0, 0, qimg)
        painter.end()
        
        return result
    
    def create_checkerboard_pattern(self, width: int, height: int, square_size: int = 16) -> QImage:
        """チェッカーボードパターンを生成"""
        image = QImage(width, height, QImage.Format_RGB32)
        
        # チェッカーボードの色（明るいグレーと暗いグレー）
        light_color = QColor(240, 240, 240)  # 明るいグレー
        dark_color = QColor(200, 200, 200)   # 暗いグレー
        
        painter = QPainter(image)
        try:
            for y in range(0, height, square_size):
                for x in range(0, width, square_size):
                    # チェッカーボードパターンの計算
                    is_light = ((x // square_size) + (y // square_size)) % 2 == 0
                    color = light_color if is_light else dark_color
                    
                    # 正方形を描画
                    rect_width = min(square_size, width - x)
                    rect_height = min(square_size, height - y)
                    painter.fillRect(x, y, rect_width, rect_height, color)
        finally:
            painter.end()
        
        return image
    
    def calculate_dynamic_canvas_size(self, reader, scale_factor: float, original_size: bool) -> Tuple[int, int]:
        """全スプライトの軸込みのバウンディングボックスを計算して、それを元にキャンバスサイズを決定する"""
        if not reader or not hasattr(reader, 'sprites'):
            base_w, base_h = self.config.default_canvas_size
        else:
            min_x = min_y = 0
            max_x = max_y = 0
            for sprite in reader.sprites:
                w = sprite.get('width', 0)
                h = sprite.get('height', 0)
                # SFFv1では 'axisx'/'axisy'、SFFv2では 'x_axis'/'y_axis' を使用
                ax = sprite.get('axisx', sprite.get('x_axis', 0))
                ay = sprite.get('axisy', sprite.get('y_axis', 0))

                # 左上と右下の座標を計算
                left   = -ax
                top    = -ay
                right  = left + w
                bottom = top + h

                min_x = min(min_x, left)
                min_y = min(min_y, top)
                max_x = max(max_x, right)
                max_y = max(max_y, bottom)

            base_w = max(self.config.default_canvas_size[0], (max_x - min_x) + self.config.canvas_margin)
            base_h = max(self.config.default_canvas_size[1], (max_y - min_y) + self.config.canvas_margin)

        # ベースキャンバスサイズの拡大処理（設定で制御）
        if self.config.enable_canvas_scale_multiplier:
            base_w = int(base_w * self.config.canvas_scale_multiplier)
            base_h = int(base_h * self.config.canvas_scale_multiplier)

        scale = scale_factor if not original_size else 1.0
        canvas_w = int(base_w * scale)
        canvas_h = int(base_h * scale)
        canvas_w = max(self.config.min_canvas_size[0], min(self.config.max_canvas_size[0], canvas_w))
        canvas_h = max(self.config.min_canvas_size[1], min(self.config.max_canvas_size[1], canvas_h))
        return canvas_w, canvas_h
    
    def canvas_size_for_sprite(self, sprite: dict, scale_factor: float, original_size: bool) -> Tuple[int, int]:
        """選択中スプライト専用のキャンバスサイズ計算"""
        w = sprite.get('width', 0)
        h = sprite.get('height', 0)
        base_w = max(self.config.min_canvas_size[0], w + self.config.canvas_margin)
        base_h = max(self.config.min_canvas_size[1], h + self.config.canvas_margin)

        # ベースキャンバスサイズを2倍にする
        base_w *= 2
        base_h *= 2

        scale = 1.0  # ズーム非連動　scale_factor（既定 200%）を削除
        cw = int(base_w * scale)
        ch = int(base_h * scale)
        cw = max(self.config.min_canvas_size[0], min(self.config.max_canvas_size[0], cw))
        ch = max(self.config.min_canvas_size[1], min(self.config.max_canvas_size[1], ch))
        return cw, ch


class AIRParser:
    """AIRファイル解析クラス"""
    
    @staticmethod
    def parse_air(path: str) -> Dict[int, List[Dict[str, int]]]:
        """非常に簡易な AIR パーサ (Begin Action + LoopStart対応)"""
        anims: Dict[int, List[Dict[str, int]]] = {}
        cur: Optional[List[Dict[str, int]]] = None
        current_clsn1_default = []
        current_clsn2_default = []
        # Default値の状態を追跡
        current_clsn1_default_count = 0
        current_clsn2_default_count = 0
        
        # フレーム専用の一時リスト（非Defaultの判定用）
        frame_clsn1 = None  # None = 未開始, List = 一時リストあり
        frame_clsn2 = None  # None = 未開始, List = 一時リストあり
        
        if not os.path.isfile(path):
            return anims
        
        try:
            with open(path, 'r', encoding='utf-8-sig', errors='ignore') as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith(';'): 
                        continue
                    
                    m = re.match(r'^\[?\s*begin\s+action\s+(-?\d+)\s*\]?$', line, re.I)
                    if m:
                        no = int(m.group(1))
                        cur = []
                        anims[no] = cur
                        # 新しいアニメーション開始時にClsnデフォルトをリセット
                        current_clsn1_default = []
                        current_clsn2_default = []
                        # フレーム専用一時リストもリセット
                        frame_clsn1 = None
                        frame_clsn2 = None
                        continue
                    
                    if cur is None: 
                        continue
                    
                    # Clsn情報の処理
                    if 'clsn' in line.lower():  # 空白がある行にも対応
                        try:
                            # Default値の状態と一時リストも渡す
                            current_clsn1_default_count, current_clsn2_default_count, frame_clsn1, frame_clsn2 = AIRParser._parse_clsn_line(
                                line, cur, current_clsn1_default, current_clsn2_default,
                                current_clsn1_default_count, current_clsn2_default_count,
                                frame_clsn1, frame_clsn2
                            )
                            continue
                        except Exception as e:
                            pass
                    
                    # LoopStartタグの検出
                    if line.lower().strip() in ('loopstart', 'loop start'):
                        # LoopStartマーカーをフレームリストに追加
                        # 一時リストがあればそれを使用、なければdefaultを使用
                        final_clsn1 = frame_clsn1 if frame_clsn1 is not None else current_clsn1_default
                        final_clsn2 = frame_clsn2 if frame_clsn2 is not None else current_clsn2_default
                        
                        cur.append({
                            'group': -1, 'image': -1, 'x': 0, 'y': 0, 
                            'duration': 1, 'flip': 0, 'loopstart': True,
                            'clsn1': final_clsn1.copy(),
                            'clsn2': final_clsn2.copy()
                        })
                        
                        # 一時リストをクリア（次フレームへ持ち越さない）
                        frame_clsn1 = None
                        frame_clsn2 = None
                        continue
                    
                    parts = [p.strip() for p in line.split(',')]
                    if len(parts) < 3: 
                        continue
                    
                    try:
                        g = int(parts[0])
                        i = int(parts[1])
                        x = int(parts[2]) if len(parts) > 2 and parts[2] else 0
                        y = int(parts[3]) if len(parts) > 3 and parts[3] else 0
                        d = int(parts[4]) if len(parts) > 4 and parts[4] else 1
                        flip_raw = parts[5] if len(parts) > 5 else ''
                        
                        # 反転・合成パラメータの解析
                        flip_h = False
                        flip_v = False
                        blend_mode = 'normal'
                        alpha_value = 1.0
                        
                        if flip_raw:
                            flip_upper = flip_raw.upper().strip()
                            # 反転処理
                            if 'H' in flip_upper:
                                flip_h = True
                            if 'V' in flip_upper:
                                flip_v = True
                            
                            # 合成処理
                            if 'A1' in flip_upper:
                                blend_mode = 'add'
                                alpha_value = 0.5
                            elif 'A' in flip_upper:
                                blend_mode = 'add'
                                alpha_value = 1.0
                            elif 'S' in flip_upper:
                                blend_mode = 'subtract'
                        
                        # 従来のflip値も保持（後方互換性）
                        flip_legacy = 0
                        if flip_h and flip_v:
                            flip_legacy = 3
                        elif flip_h:
                            flip_legacy = 1
                        elif flip_v:
                            flip_legacy = 2
                        
                        frame_data = {
                            'group': g, 'image': i, 'x': x, 'y': y, 
                            'duration': d, 'flip': flip_legacy,
                            'flip_h': flip_h, 'flip_v': flip_v,
                            'blend_mode': blend_mode, 'alpha_value': alpha_value,
                            'clsn1': (frame_clsn1 if frame_clsn1 is not None else current_clsn1_default).copy(),
                            'clsn2': (frame_clsn2 if frame_clsn2 is not None else current_clsn2_default).copy()
                        }
                        cur.append(frame_data)
                        
                        # 一時リストをクリア（次フレームへ持ち越さない）
                        frame_clsn1 = None
                        frame_clsn2 = None
                    except: 
                        pass
        except Exception as e:
            logging.warning(f"AIR parsing error: {e}")
        
        return anims
    
    @staticmethod
    def _parse_clsn_line(line: str, current_frames: Optional[List[Dict]], 
                        current_clsn1_default: List[Dict], 
                        current_clsn2_default: List[Dict],
                        clsn1_default_count: int = 0,
                        clsn2_default_count: int = 0,
                        frame_clsn1: Optional[List[Dict]] = None,
                        frame_clsn2: Optional[List[Dict]] = None) -> Tuple[int, int, Optional[List[Dict]], Optional[List[Dict]]]:
        """Clsn行を解析してDefault値やClsnボックスを記録"""
        # フレームが空でもClsnDefaultとClsn定義は記録する
        
        line_lower = line.lower().strip()  # 先頭の空白を削除
        
        # Clsn1Default: 4
        clsn1_default_match = re.search(r'clsn1default\s*:\s*(\d+)', line_lower)
        if clsn1_default_match:
            count = int(clsn1_default_match.group(1))
            current_clsn1_default.clear()
            return count, clsn2_default_count, frame_clsn1, frame_clsn2  # 新しいdefault値を返す
        
        # Clsn2Default: 4
        clsn2_default_match = re.search(r'clsn2default\s*:\s*(\d+)', line_lower)
        if clsn2_default_match:
            count = int(clsn2_default_match.group(1))
            current_clsn2_default.clear()
            return clsn1_default_count, count, frame_clsn1, frame_clsn2  # 新しいdefault値を返す
        
        # Clsn1[0] = x1, y1, x2, y2 (空白含む対応)
        # 座標形式: x1=左, y1=下, x2=右, y2=上
        clsn1_match = re.match(r'\s*clsn1\[(\d+)\]\s*=\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*(.+)', line_lower)
        if clsn1_match:
            index = int(clsn1_match.group(1))
            left = int(clsn1_match.group(2).strip())      # x1 = 左
            bottom = int(clsn1_match.group(3).strip())    # y1 = 下
            right = int(clsn1_match.group(4).strip())     # x2 = 右
            top = int(clsn1_match.group(5).strip())       # y2 = 上
            
            box = {
                'x1': left, 'y1': top, 'x2': right, 'y2': bottom,  # 描画用に上下を調整
                'has_default': clsn1_default_count > 0  # Default値があるかを記録
            }
            
            # 一時リストがあれば一時リストへ、なければdefaultリストへ
            target_list = frame_clsn1 if frame_clsn1 is not None else current_clsn1_default
            
            # リストを拡張して適切なインデックスに配置
            while len(target_list) <= index:
                target_list.append({})
            target_list[index] = box
            return clsn1_default_count, clsn2_default_count, frame_clsn1, frame_clsn2
        
        # Clsn2[0] = x1, y1, x2, y2 (空白含む対応)
        # 座標形式: x1=左, y1=下, x2=右, y2=上
        clsn2_match = re.match(r'\s*clsn2\[(\d+)\]\s*=\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*(.+)', line_lower)
        if clsn2_match:
            index = int(clsn2_match.group(1))
            left = int(clsn2_match.group(2).strip())      # x1 = 左
            bottom = int(clsn2_match.group(3).strip())    # y1 = 下
            right = int(clsn2_match.group(4).strip())     # x2 = 右
            top = int(clsn2_match.group(5).strip())       # y2 = 上
            
            box = {
                'x1': left, 'y1': top, 'x2': right, 'y2': bottom,  # 描画用に上下を調整
                'has_default': clsn2_default_count > 0  # Default値があるかを記録
            }
            
            # 一時リストがあれば一時リストへ、なければdefaultリストへ
            target_list = frame_clsn2 if frame_clsn2 is not None else current_clsn2_default
            
            # リストを拡張して適切なインデックスに配置
            while len(target_list) <= index:
                target_list.append({})
            target_list[index] = box
            return clsn1_default_count, clsn2_default_count, frame_clsn1, frame_clsn2
        
        # Clsn1: n (非Default) - 一時リストを開始
        clsn1_count_match = re.search(r'clsn1\s*:\s*(\d+)', line_lower)
        if clsn1_count_match:
            # 一時リストを開始（defaultには触れない）
            frame_clsn1 = []
            return 0, clsn2_default_count, frame_clsn1, frame_clsn2
        
        # Clsn2: n (非Default) - 一時リストを開始
        clsn2_count_match = re.search(r'clsn2\s*:\s*(\d+)', line_lower)
        if clsn2_count_match:
            # 一時リストを開始（defaultには触れない）
            frame_clsn2 = []
            return clsn1_default_count, 0, frame_clsn1, frame_clsn2
        
        return clsn1_default_count, clsn2_default_count, frame_clsn1, frame_clsn2


class DEFParser:
    """DEFファイル解析クラス"""
    
    @staticmethod
    def parse_def(path: str) -> Tuple[Optional[str], Optional[str], Optional[Tuple[int, int]], Optional[str]]:
        """DEF から sprite=, anim=, localcoord=, st= を取得"""
        sff_raw: Optional[str] = None
        air_raw: Optional[str] = None
        st_raw: Optional[str] = None
        localcoord: Optional[Tuple[int, int]] = None
        
        if not os.path.isfile(path):
            return None, None, None, None
        
        try:
            with open(path,'r', encoding='utf-8', errors='ignore') as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith(';'): 
                        continue
                    
                    # コメント除去
                    if ';' in line:
                        line = line.split(';',1)[0].rstrip()
                    
                    lower = line.lower()
                    
                    if lower.startswith('sprite') and '=' in line and sff_raw is None:
                        sff_raw = line.split('=',1)[1].strip()
                    elif lower.startswith('anim') and '=' in line and air_raw is None:
                        air_raw = line.split('=',1)[1].strip()
                    elif lower.startswith('st') and '=' in line and st_raw is None:
                        st_raw = line.split('=',1)[1].strip()
                    elif lower.startswith('localcoord') and '=' in line and localcoord is None:
                        coord_str = line.split('=',1)[1].strip()
                        # localcoord = 320,240 形式をパース
                        if ',' in coord_str:
                            try:
                                parts = coord_str.split(',')
                                if len(parts) >= 2:
                                    x = int(parts[0].strip())
                                    y = int(parts[1].strip())
                                    localcoord = (x, y)
                            except ValueError:
                                pass
                    
                    if sff_raw and air_raw and st_raw and localcoord:
                        break
        except Exception as e:
            logging.warning(f"DEF parsing error: {e}")
        
        def clean(v: Optional[str]) -> Optional[str]:
            if v is None: 
                return None
            v = v.strip().strip('"\'')
            return v if v else None
        
        return clean(sff_raw), clean(air_raw), localcoord, clean(st_raw)
    
    @staticmethod
    def parse_st_file(path: str) -> Tuple[float, float]:
        """STファイルから[Size]セクションのxscale, yscaleを取得"""
        xscale = 1.0
        yscale = 1.0
        
        if not os.path.isfile(path):
            return xscale, yscale
        
        try:
            in_size_section = False
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith(';'):
                        continue
                    
                    # セクション判定
                    if line.startswith('[') and line.endswith(']'):
                        section_name = line[1:-1].strip().lower()
                        in_size_section = (section_name == 'size')
                        continue
                    
                    if not in_size_section:
                        continue
                    
                    # コメント除去
                    if ';' in line:
                        line = line.split(';', 1)[0].rstrip()
                    
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip().lower()
                        value = value.strip()
                        
                        if key == 'xscale' and value:
                            try:
                                xscale = float(value)
                            except ValueError:
                                pass
                        elif key == 'yscale' and value:
                            try:
                                yscale = float(value)
                            except ValueError:
                                pass
        except Exception as e:
            logging.warning(f"ST file parsing error: {e}")
        
        return xscale, yscale
    
    @staticmethod
    def get_localcoord_scale_factor(localcoord: Optional[Tuple[int, int]]) -> float:
        """localcoordに基づくスケールファクターを計算"""
        if localcoord is None:
            return 1.0  # 100%
        
        width, height = localcoord
        if width == 320 and height == 240:
            return 1.0  # 100%
        elif width == 640 and height == 480:
            return 0.75  # 75%
        elif width == 1280 and height == 720:
            return 0.5   # 50%
        else:
            return 1.0  # デフォルト 100%
    
    @staticmethod
    def resolve_asset_path(base_dir: str, rel: Optional[str]) -> Optional[str]:
        """DEF 内指定の相対/絶対パス文字列を実ファイルに解決"""
        if not rel: 
            return None
        
        rel = rel.replace('\\', os.sep).replace('/', os.sep).strip()
        rel = rel.strip('"\'')
        
        if os.path.isabs(rel):
            return rel if os.path.isfile(rel) else None
        
        cand = os.path.normpath(os.path.join(base_dir, rel))
        if os.path.isfile(cand):
            return cand
        
        # ファイル名のみ合致検索 (大文字小文字無視)
        fname = os.path.basename(rel).lower()
        try:
            for entry in os.listdir(base_dir):
                p = os.path.join(base_dir, entry)
                if os.path.isfile(p) and entry.lower() == fname:
                    return p
        except Exception:
            pass
        
        return None
    
    @staticmethod
    def parse_def_palettes(path: str) -> List[str]:
        """DEFファイルからpal.actの情報を取得"""
        palettes = []
        
        if not os.path.isfile(path):
            return palettes
        
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith(';'):
                        continue
                    
                    # コメント除去
                    if ';' in line:
                        line = line.split(';', 1)[0].rstrip()
                    
                    # pal.act = ファイル名の形式を探す
                    if line.lower().startswith('pal') and '=' in line:
                        pal_file = line.split('=', 1)[1].strip().strip('"\'')
                        if pal_file and pal_file.lower().endswith('.act'):
                            palettes.append(pal_file)
        except Exception as e:
            logging.warning(f"DEF palette parsing error: {e}")
        
        return palettes
    
    @staticmethod
    def load_act_palette(path: str) -> Optional[List[Tuple[int, int, int, int]]]:
        """ACTファイルからパレットを読み込み"""
        if not os.path.isfile(path):
            return None
        
        try:
            with open(path, 'rb') as f:
                data = f.read()
                if len(data) < 768:  # 256色 * 3バイト
                    return None
                
                palette = []
                for i in range(256):
                    offset = i * 3
                    if offset + 2 < len(data):
                        # 標準的なRGB順序で読み込み
                        r = data[offset]
                        g = data[offset + 1]
                        b = data[offset + 2]
                        a = 255 if i > 0 else 0  # インデックス0は透明
                        palette.append((r, g, b, a))
                    else:
                        palette.append((0, 0, 0, 0))
                
                # パレットの順番を逆転（255番から0番へ）
                palette.reverse()
                
                # ACTパレットの最初の数色をデバッグ出力
                print(f"[DEBUG] ACT palette loaded from {path}")
                print(f"[DEBUG] ACT palette first 5 colors: {palette[:5]}")
                print(f"[DEBUG] ACT palette last 5 colors: {palette[-5:]}")
                print(f"[DEBUG] ACT palette file size: {len(data)} bytes")
                print(f"[DEBUG] Palette order reversed")
                
                return palette
        except Exception as e:
            logging.warning(f"ACT file loading error: {e}")
            return None


# レガシー関数（後方互換性のため）
def parse_air(path: str) -> Dict[int, List[Dict[str, int]]]:
    """レガシー関数 - 新しい air_parser モジュールを使用"""
    from src.air_parser import parse_air as new_parse_air
    return new_parse_air(path)


def parse_def(path: str) -> Tuple[Optional[str], Optional[str]]:
    """レガシー関数 - 後方互換性のため"""
    sff_raw, air_raw, _, _ = DEFParser.parse_def(path)
    return sff_raw, air_raw


def _resolve_asset_path(base_dir: str, rel: Optional[str]) -> Optional[str]:
    """レガシー関数 - 後方互換性のため"""
    return DEFParser.resolve_asset_path(base_dir, rel)


class DraggableGraphicsView(QGraphicsView):
    """ドラッグ可能なグラフィックビュー（キャンバス全体を移動）"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.viewer: Optional['SFFViewer'] = None
        self._last_pan_point = None
        self._is_panning = False
        
        # ドラッグでパンを有効にする
        self.setDragMode(QGraphicsView.NoDrag)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._last_pan_point = e.pos()
            self._is_panning = True
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._is_panning and self._last_pan_point:
            # キャンバス全体をパン（移動）
            delta = e.pos() - self._last_pan_point
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            self._last_pan_point = e.pos()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._is_panning = False
            self._last_pan_point = None
            self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(e)


class ImageWindow(QMainWindow):
    """画像表示ウィンドウ"""
    
    # シグナル定義
    window_closed = pyqtSignal()
    
    def __init__(self, viewer: 'SFFViewer', config: SFFViewerConfig):
        super().__init__(viewer)
        self.config = config
        self.viewer = viewer
        self.language_manager = viewer.language_manager  # 言語管理を追加
        
        # ウィンドウタイトルを言語対応
        self.update_window_title()
        
        # ウィンドウの透過設定（マゼンタ背景では不要）
        # self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        self.view = DraggableGraphicsView()
        self.view.viewer = viewer
        self.scene = QGraphicsScene()
        self.view.setScene(self.scene)
        
        # シーンの背景もライトグレーに設定（チェッカーボードパターンと調和）
        self.scene.setBackgroundBrush(QBrush(QColor(220, 220, 220, 255)))  # ライトグレー
        
        # シーン再利用のための要素
        self.current_pixmap_item = None  # 現在表示中のPixmapItem
        self.scene_initialized = False   # シーンが初期化済みかどうか
        
        # パン機能のためのスクロールバー設定
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # キャンバスを画像ウィンドウの中心に配置
        self.view.setAlignment(Qt.AlignCenter)
        
        # 画像表示領域の背景色をライトグレーに設定（チェッカーボードパターンと調和）
        self.view.setStyleSheet("QGraphicsView { background-color: rgb(220, 220, 220); }")
        
        # メインウィジェットとレイアウトを作成
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 画像ビューを追加
        layout.addWidget(self.view)
        
        # アニメ情報表示ラベルを追加
        self.anim_info_label = QLabel()
        self.anim_info_label.setMaximumHeight(80)
        self.anim_info_label.setMinimumHeight(80)
        self.anim_info_label.setWordWrap(True)
        self.anim_info_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.anim_info_label.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                padding: 5px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 10px;
            }
        """)
        self.anim_info_label.setText("アニメーション情報: (アニメーションが選択されていません)")
        layout.addWidget(self.anim_info_label)
        
        self.setCentralWidget(main_widget)
        
        self.resize(config.image_window_width, config.image_window_height)
        
        # 最小サイズを設定（完全にリサイズ可能）
        self.setMinimumSize(600, 480)
    
    def update_window_title(self):
        """ウィンドウタイトルを更新"""
        if self.language_manager.current_language == 'en':
            title = 'SffCharaViewer Image Viewer'
        else:
            title = 'SffCharaViewer 画像ビューア'
        self.setWindowTitle(title)
    
    def update_ui_texts(self):
        """UI上のテキストを現在の言語で更新"""
        self.update_window_title()
        # アニメーション情報ラベルも言語に応じて更新
        if hasattr(self, 'anim_info_label'):
            default_text = self.language_manager.get_text('anim_info_default')
            UIHelper.safe_set_label_text(self.anim_info_label, default_text)

    def update_ui_language(self):
        """UI言語を更新"""
        self.update_ui_texts()

    def update_anim_info(self, anim_no, frame_index, total_frames, frame_data):
        """アニメーション情報を更新（言語対応・時間修正版）"""
        if hasattr(self, 'language_manager') and self.language_manager:
            lang_mgr = self.language_manager
        else:
            lang_mgr = None
            
        if frame_data:
            # 時間情報を正しく取得（duration または time フィールド）
            time_value = frame_data.get('duration', frame_data.get('time', 0))
            
            if lang_mgr:
                info_text = lang_mgr.get_text(
                    'anim_info_format',
                    anim_no=anim_no,
                    frame=frame_index + 1,
                    total=total_frames,
                    group=frame_data.get('group', 0),
                    image=frame_data.get('image', 0),
                    time=time_value,
                    x=frame_data.get('x', 0),
                    y=frame_data.get('y', 0)
                )
            else:
                info_text = (
                    f"アニメ: {anim_no} | フレーム: {frame_index + 1}/{total_frames} | "
                    f"グループ: {frame_data.get('group', 0)} | 画像: {frame_data.get('image', 0)} | "
                    f"時間: {time_value} | X: {frame_data.get('x', 0)} | Y: {frame_data.get('y', 0)}"
                )
        else:
            if lang_mgr:
                info_text = lang_mgr.get_text('anim_info_default')
            else:
                info_text = "アニメーション情報: (アニメーションが選択されていません)"
        
        UIHelper.safe_set_label_text(self.anim_info_label, info_text)

    def clear_anim_info(self):
        """アニメーション情報をクリア（言語対応版）"""
        if hasattr(self, 'language_manager') and self.language_manager:
            text = self.language_manager.get_text('anim_info_default')
        else:
            text = "アニメーション情報: (アニメーションが選択されていません)"
        UIHelper.safe_set_label_text(self.anim_info_label, text)

    def closeEvent(self, e):
        self.window_closed.emit()
        super().closeEvent(e)


class SFFViewer(QMainWindow):
    """メインSFFビューアクラス"""
    
    # シグナル定義
    sprite_changed = pyqtSignal(int)  # スプライトが変更された時
    animation_started = pyqtSignal(int)  # アニメーションが開始された時
    file_loaded = pyqtSignal(str)  # ファイルが読み込まれた時
    
    def _safe_set_label_text(self, text: str):
        """ラベルテキストを安全に設定するヘルパー関数（長すぎるテキストは省略）"""
        if hasattr(self, 'label') and self.label is not None:
            try:
                # テキストが長すぎる場合は省略表示
                max_length = 80  # 最大文字数
                if len(text) > max_length:
                    display_text = text[:max_length-3] + "..."
                else:
                    display_text = text
                self.label.setText(display_text)
            except RuntimeError:
                # UIコンポーネントが削除されている場合は無視
                pass
    
    def __init__(self, config: Optional[SFFViewerConfig] = None, parent=None):
        super().__init__(parent)
        self.config = config or SFFViewerConfig()
        
        # 実行ファイルのディレクトリを保存（.exe対応版）
        if getattr(sys, 'frozen', False):
            # PyInstaller/.exeで実行されている場合
            self.script_dir = os.path.dirname(sys.executable)
        else:
            # 通常のPythonスクリプトで実行されている場合
            self.script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 新機能の初期化
        self.language_manager = LanguageManager("config/SffCharaViewer_config.json")
        settings = self.language_manager.load_settings()  # 設定を読み込み
        
        # UI表示用の言語状態（toggle_language用）
        self.ui_display_language = self.language_manager.current_language
        
        # ファイルダイアログ用ディレクトリ管理（設定から復元）
        self.last_opened_dir = settings.get('last_opened_dir', self.script_dir)
        
        self.image_cache = ImageCache(max_cache_size=200)  # キャッシュサイズ200枚
        
        # ウィンドウタイトルを言語対応
        self.update_window_title()
        
        # 内部状態
        self.reader = None
        self.is_v2 = False
        self.scale_factor = self.config.default_scale
        self.original_size = False
        self.no_alpha = False
        
        # 最大キャンバスサイズ（SFF読み込み時に計算される）
        self.max_canvas_width = self.config.min_canvas_size[0]
        self.max_canvas_height = self.config.min_canvas_size[1]
        
        # キャンバススケーリング追跡用
        self._last_canvas_scale_x = None
        self._last_canvas_scale_y = None
        self._scaled_canvas_width = None
        self._scaled_canvas_height = None
        
        # ビュー中央配置制御
        self._view_centered_after_scaling = False
        
        # フィット関連
        self.original_size = False
        self.no_alpha = False
        
        # アニメーション用の固定ビュー状態
        self._anim_view_transform = None
        self._anim_h_scroll = None
        self._anim_v_scroll = None
        
        # DEF関連の新しいプロパティ
        self.localcoord_scale = 1.0  # localcoordに基づくスケール
        self.st_xscale = 1.0         # STファイルのxscale
        self.st_yscale = 1.0         # STファイルのyscale
        
        # Clsn表示用
        self.current_frame_data = None  # 現在のフレームデータ（Clsn情報含む）
        
        # ACTパレット関連
        self.act_palettes = []       # DEFから読み込んだACTパレットのリスト
        self.act_palette_names = []  # ACTパレットのファイル名リスト
        
        # レンダラー
        self.renderer = SFFRenderer(self.config)
        
        # 初回中心配置フラグ
        self.initial_center_applied = False
        
        # アニメ関連
        self.animations = {}
        self.current_anim = None
        self.anim_index = 0
        self.anim_ticks_left = 0
        self._anim_no_list = []  # 並び保持
        
        # LoopStart関連
        self.loop_start_index = -1  # LoopStartフレームのインデックス
        self.loop_target_index = -1 # LoopStartの次のフレーム（ループ対象）のインデックス
        self.loop_count = 0         # 現在のループ回数
        self.max_loop_time = 5.0    # 5秒間ループ
        self.loop_start_time = 0.0  # ループ開始時刻
        
        # UIを構築
        self._setup_ui()
        
        # ステータスバー管理
        self.status_bar_manager = StatusBarManager(self.statusBar(), self.language_manager)
        
    def update_window_title(self):
        """ウィンドウタイトルを更新"""
        if self.language_manager.current_language == 'en':
            title = 'SffCharaViewer (Enhanced Modular Version)'
        else:
            title = 'SffCharaViewer (拡張モジュール版)'
        self.setWindowTitle(title)
        
        # レンダリングキャッシュ（最適化用）
        self.render_cache = {}      # sprite_index -> (QImage, palette) のキャッシュ
        self.max_cache_size = 50    # 最大キャッシュサイズ
        
        self.timer = QTimer(self)
        self.timer.setInterval(1000 // self.config.animation_fps)
        self.timer.timeout.connect(self.step_animation)

        # 画像ウィンドウ
        self.image_window = ImageWindow(self, self.config)
        self.image_window.window_closed.connect(self._on_image_window_closed)
        
        # ウィンドウサイズ設定
        self.resize(self.config.window_width, self.config.window_height)
        self.image_window.show()

        # UI 構築
        self._setup_ui()
        self.arrange_windows()
        
        # 初期キャンバスサイズを設定
        self.update_canvas_size()
    
    def _setup_ui(self):
        """UI構築"""
        # ファイル履歴の初期化
        self.recent_files = []
        self.max_recent_files = 10
        
        # メニューバーを作成
        self._setup_menu_bar()
        
        # メインレイアウト設定
        container = QWidget()
        self.setCentralWidget(container)
        
        root = QVBoxLayout()
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)
        
        # ファイル操作部
        top = QHBoxLayout()
        top.setSpacing(5)
        top.setContentsMargins(5, 5, 5, 5)
        self.label = QLabel(self.language_manager.get_text('main_instruction'))
        self.label.setWordWrap(True)  # ワードラップを有効化
        self.label.setMaximumHeight(50)  # 最大高さを制限
        self.open_btn = QPushButton(self.language_manager.get_text('button_open_file'))
        self.open_btn.clicked.connect(self.open_file)
        
        # 言語切り替えボタンを追加
        self.language_btn = QPushButton(self.language_manager.get_opposite_language_button_text())
        self.language_btn.clicked.connect(self.toggle_language)
        self.language_btn.setMaximumWidth(150)
        
        top.addWidget(self.label, 1)
        top.addWidget(self.language_btn)
        top.addWidget(self.open_btn)
        root.addLayout(top)

        # 表示オプション部
        opt = QHBoxLayout()
        opt.setSpacing(5)
        opt.setContentsMargins(5, 0, 5, 5)
        opt.addWidget(QLabel(self.language_manager.get_text('label_display_size')))
        
        # 段階的スケール選択
        self.scale_combo = QComboBox()
        self.scale_values = [25, 50, 75, 100, 125, 150, 175, 200, 250, 300, 400, 500]
        for value in self.scale_values:
            self.scale_combo.addItem(f'{value}%')
        
        # デフォルト値を設定（100%に最も近い値）
        default_scale_percent = int(self.config.default_scale * 100)
        if default_scale_percent in self.scale_values:
            default_index = self.scale_values.index(default_scale_percent)
        else:
            # 最も近い値を見つける
            default_index = min(range(len(self.scale_values)), 
                              key=lambda i: abs(self.scale_values[i] - default_scale_percent))
        self.scale_combo.setCurrentIndex(default_index)
        self.scale_combo.currentIndexChanged.connect(self.on_scale_combo_changed)
        opt.addWidget(self.scale_combo)
        
        self.chk_original = QCheckBox(self.language_manager.get_text('checkbox_original_size'))
        self.chk_original.toggled.connect(self.on_original_toggled)
        opt.addWidget(self.chk_original)
        
        self.chk_no_alpha = QCheckBox(self.language_manager.get_text('checkbox_no_alpha'))
        self.chk_no_alpha.toggled.connect(self.on_no_alpha_toggled)
        opt.addWidget(self.chk_no_alpha)
        
        self.chk_show_clsn = QCheckBox(self.language_manager.get_text('checkbox_show_clsn'))
        self.chk_show_clsn.toggled.connect(self.on_show_clsn_toggled)
        opt.addWidget(self.chk_show_clsn)
        
        # UI構築後にスケールファクターを同期
        self._sync_scale_factor()
        
        # キャンバス設定
        opt.addStretch()
        root.addLayout(opt)

        # リスト部
        lists = QHBoxLayout()
        lists.setSpacing(0)
        lists.setContentsMargins(5, 0, 5, 5)
        
        # アニメリスト
        anim_layout = QVBoxLayout()
        anim_layout.setSpacing(2)
        anim_layout.setContentsMargins(0, 0, 0, 0)
        
        self.anim_list = QListWidget()
        self.anim_list.currentRowChanged.connect(self.on_anim_selected)
        self.anim_list.setMinimumWidth(110)
        self.anim_list.setMaximumWidth(140)
        self.anim_list.setToolTip('アクション番号 (フレーム数)')
        anim_layout.addWidget(self.anim_list, 1)
        
        # GIF出力ボタン
        self.gif_export_btn = QPushButton(self.language_manager.get_text('button_gif_export'))
        self.gif_export_btn.clicked.connect(self.export_animation_gif)
        self.gif_export_btn.setEnabled(False)
        self.gif_export_btn.setToolTip(self.language_manager.get_text('tooltip_gif_export'))
        anim_layout.addWidget(self.gif_export_btn)
        
        # 画像出力ボタン
        self.image_export_btn = QPushButton(self.language_manager.get_text('button_image_export'))
        self.image_export_btn.clicked.connect(self.export_current_image)
        self.image_export_btn.setEnabled(False)
        self.image_export_btn.setToolTip(self.language_manager.get_text('tooltip_image_export'))
        anim_layout.addWidget(self.image_export_btn)
        
        # スプライトシート出力ボタン（全体）
        self.spritesheet_all_export_btn = QPushButton(self.language_manager.get_text('button_spritesheet_all'))
        self.spritesheet_all_export_btn.clicked.connect(self.export_all_spritesheet)
        self.spritesheet_all_export_btn.setEnabled(False)
        self.spritesheet_all_export_btn.setToolTip(self.language_manager.get_text('tooltip_spritesheet_all'))
        anim_layout.addWidget(self.spritesheet_all_export_btn)
        
        # スプライトシート出力ボタン（アニメ単体）
        self.spritesheet_anim_export_btn = QPushButton(self.language_manager.get_text('button_spritesheet_anim'))
        self.spritesheet_anim_export_btn.clicked.connect(self.export_animation_spritesheet)
        self.spritesheet_anim_export_btn.setEnabled(False)
        self.spritesheet_anim_export_btn.setToolTip(self.language_manager.get_text('tooltip_spritesheet_anim'))
        anim_layout.addWidget(self.spritesheet_anim_export_btn)
        
        # 全GIF出力ボタン
        self.all_gif_export_btn = QPushButton(self.language_manager.get_text('button_all_gif_export'))
        self.all_gif_export_btn.clicked.connect(self.export_all_animations_gif)
        self.all_gif_export_btn.setEnabled(False)
        self.all_gif_export_btn.setToolTip(self.language_manager.get_text('tooltip_all_gif_export'))
        anim_layout.addWidget(self.all_gif_export_btn)
        
        lists.addLayout(anim_layout, 1)
        
        # スプライト/パレット
        self.sprite_list = QListWidget()
        self.sprite_list.currentRowChanged.connect(self._on_sprite_selected)
        self.palette_list = QListWidget()
        self.palette_list.currentRowChanged.connect(lambda _r: self.refresh_current_sprite())
        
        # パレット状態表示ラベル
        self.palette_status_label = QLabel('パレット選択: 有効')
        self.palette_status_label.setStyleSheet("color: green; font-size: 10px;")
        
        lists.addWidget(self.sprite_list, 1)
        lists.addWidget(self.palette_list, 1)
        lists.addWidget(self.palette_status_label, 0)
        
        # パレットプレビュー
        self.palette_preview = QLabel('Palette')
        self.palette_preview.setFixedSize(256, 256)
        self.palette_preview.setScaledContents(True)  # 枠に合わせて拡大/縮小
        lists.addWidget(self.palette_preview)
        
        root.addLayout(lists)

        container.setLayout(root)
    
    def _setup_menu_bar(self):
        """メニューバーを設定"""
        menubar = self.menuBar()
        
        # 既存のメニューをクリアして重複を防ぐ
        menubar.clear()
        
        # ファイルメニュー
        file_menu = menubar.addMenu(self.language_manager.get_text('menu_file'))
        
        # 開くアクション
        open_action = QAction(self.language_manager.get_text('menu_open_sff'), self)
        open_action.setShortcut('Ctrl+O')
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        
        # 最近のファイル用セパレータ
        file_menu.addSeparator()
        
        # 最近のファイルメニューのプレースホルダー
        self.recent_files_menu = QMenu('最近のファイル(&R)', self)
        file_menu.addMenu(self.recent_files_menu)
        self._update_recent_files_menu()
        
        # 終了アクション
        file_menu.addSeparator()
        exit_action = QAction(self.language_manager.get_text('menu_quit'), self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 設定メニュー（言語切り替えを削除）
        # settings_menu = menubar.addMenu(self.language_manager.get_text('menu_settings'))
    
    def _add_to_recent_files(self, file_path):
        """ファイルを履歴に追加"""
        # 既に存在する場合は削除
        if file_path in self.recent_files:
            self.recent_files.remove(file_path)
        
        # 先頭に追加
        self.recent_files.insert(0, file_path)
        
        # 最大数を超えた場合は末尾を削除
        if len(self.recent_files) > self.max_recent_files:
            self.recent_files = self.recent_files[:self.max_recent_files]
        
        # メニューを更新
        self._update_recent_files_menu()
    
    def _update_recent_files_menu(self):
        """最近のファイルメニューを更新"""
        if not hasattr(self, 'recent_files_menu'):
            return
        
        # メニューをクリア
        self.recent_files_menu.clear()
        
        if not self.recent_files:
            # 履歴がない場合
            no_files_action = self.recent_files_menu.addAction('(履歴なし)')
            no_files_action.setEnabled(False)
        else:
            # 履歴ファイルを追加
            for i, file_path in enumerate(self.recent_files):
                filename = os.path.basename(file_path)
                action_text = f'{i+1}. {filename}'
                action = self.recent_files_menu.addAction(action_text)
                action.setToolTip(file_path)  # フルパスをツールチップに
                action.triggered.connect(lambda checked, path=file_path: self._open_recent_file(path))
            
            # 履歴クリア
            self.recent_files_menu.addSeparator()
            clear_action = self.recent_files_menu.addAction('履歴をクリア')
            clear_action.triggered.connect(self._clear_recent_files)
    
    def toggle_language(self):
        """言語を切り替え（UI表示のみ）"""
        # UI表示用の言語を切り替え
        if self.ui_display_language == 'ja':
            self.ui_display_language = 'en'
        else:
            self.ui_display_language = 'ja'
        
        # 一時的にlanguage_managerの言語を切り替えてUI更新
        original_lang = self.language_manager.current_language
        self.language_manager.current_language = self.ui_display_language
        
        # UIのみを更新
        self.update_ui_language()
        
        # 言語設定を元に戻す（永続化はしない）
        self.language_manager.current_language = original_lang
    
    def change_language(self, language: str):
        """言語を変更（完全な言語切り替え）"""
        if language == self.language_manager.current_language:
            return
            
        self.language_manager.set_language(language)
        
        # 言語切り替えボタンのテキストを更新
        if hasattr(self, 'language_switch_action'):
            opposite_text = self.language_manager.get_opposite_language_button_text()
            self.language_switch_action.setText(opposite_text)
            
            # コールバック関数も更新
            self.language_switch_action.triggered.disconnect()
            opposite_lang = self.language_manager.get_opposite_language()
            self.language_switch_action.triggered.connect(lambda: self.change_language(opposite_lang))
        
        # UIを更新
        self.update_window_title()
        self.update_ui_language()
        
        # 画像ウィンドウがある場合も更新
        if hasattr(self, 'image_window') and self.image_window:
            self.image_window.language_manager = self.language_manager
            if hasattr(self.image_window, 'update_ui_language'):
                self.image_window.update_ui_language()
    
    def update_ui_language(self):
        """UI上のテキストを現在の言語で更新"""
        # メインラベル
        if hasattr(self, 'label'):
            self.label.setText(self.language_manager.get_text('main_instruction'))
        
        # ボタンテキストの更新
        if hasattr(self, 'open_btn'):
            self.open_btn.setText(self.language_manager.get_text('button_open_file'))
        
        if hasattr(self, 'language_btn'):
            self.language_btn.setText(self.language_manager.get_opposite_language_button_text())
        
        # チェックボックスのテキスト更新
        if hasattr(self, 'chk_original'):
            self.chk_original.setText(self.language_manager.get_text('checkbox_original_size'))
        
        if hasattr(self, 'chk_no_alpha'):
            self.chk_no_alpha.setText(self.language_manager.get_text('checkbox_no_alpha'))
        
        if hasattr(self, 'chk_show_clsn'):
            self.chk_show_clsn.setText(self.language_manager.get_text('checkbox_show_clsn'))
        
        # エクスポートボタンのテキスト更新
        if hasattr(self, 'gif_export_btn'):
            self.gif_export_btn.setText(self.language_manager.get_text('button_gif_export'))
            self.gif_export_btn.setToolTip(self.language_manager.get_text('tooltip_gif_export'))
        
        if hasattr(self, 'image_export_btn'):
            self.image_export_btn.setText(self.language_manager.get_text('button_image_export'))
            self.image_export_btn.setToolTip(self.language_manager.get_text('tooltip_image_export'))
        
        if hasattr(self, 'spritesheet_all_export_btn'):
            self.spritesheet_all_export_btn.setText(self.language_manager.get_text('button_spritesheet_all'))
            self.spritesheet_all_export_btn.setToolTip(self.language_manager.get_text('tooltip_spritesheet_all'))
        
        if hasattr(self, 'spritesheet_anim_export_btn'):
            self.spritesheet_anim_export_btn.setText(self.language_manager.get_text('button_spritesheet_anim'))
            self.spritesheet_anim_export_btn.setToolTip(self.language_manager.get_text('tooltip_spritesheet_anim'))
        
        if hasattr(self, 'all_gif_export_btn'):
            self.all_gif_export_btn.setText(self.language_manager.get_text('button_all_gif_export'))
            self.all_gif_export_btn.setToolTip(self.language_manager.get_text('tooltip_all_gif_export'))
        
        # ラベルの更新
        for layout_index in range(self.centralWidget().layout().count()):
            layout_item = self.centralWidget().layout().itemAt(layout_index)
            if hasattr(layout_item, 'layout') and layout_item.layout():
                for widget_index in range(layout_item.layout().count()):
                    widget_item = layout_item.layout().itemAt(widget_index)
                    if hasattr(widget_item, 'widget') and widget_item.widget():
                        widget = widget_item.widget()
                        if isinstance(widget, QLabel) and widget.text() in ['表示サイズ:', 'Display Size:']:
                            widget.setText(self.language_manager.get_text('label_display_size'))
        
        # メニューバーの更新
        self._setup_menu_bar()
    
    def _open_recent_file(self, file_path):
        """最近のファイルを開く"""
        if os.path.exists(file_path):
            self.load_sff_file(file_path)
        else:
            # ファイルが存在しない場合は履歴から削除
            if file_path in self.recent_files:
                self.recent_files.remove(file_path)
                self._update_recent_files_menu()
            
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, 'ファイルが見つかりません', 
                              f'ファイルが見つかりません:\n{file_path}\n\n履歴から削除しました。')
    
    def _clear_recent_files(self):
        """ファイル履歴をクリア"""
        self.recent_files.clear()
        self._update_recent_files_menu()
    
    def _on_sprite_selected(self, row: int):
        """スプライト選択時の処理"""
        # アニメーションを停止
        self.stop_animation()
        
        # アニメ情報をクリア
        if hasattr(self, 'image_window') and self.image_window:
            self.image_window.clear_anim_info()
        
        # アニメーションリストの選択を解除
        self.anim_list.setCurrentRow(-1)
        
        # 画面を更新
        self.refresh_current_sprite()
        
        if row >= 0:
            self.sprite_changed.emit(row)
            # スプライト選択時は個別の出力ボタンを有効化
            self.image_export_btn.setEnabled(True)
            self.spritesheet_anim_export_btn.setEnabled(True)
        else:
            # 選択解除時は個別の出力ボタンのみ無効化
            self.image_export_btn.setEnabled(False)
            self.spritesheet_anim_export_btn.setEnabled(False)
        
        # 全体系の出力ボタンはファイル読み込み完了時に常に有効
        if self.reader and hasattr(self.reader, 'sprites'):
            self.spritesheet_all_export_btn.setEnabled(True)
            self.all_gif_export_btn.setEnabled(bool(self.animations))
    
    def _on_image_window_closed(self):
        """画像ウィンドウが閉じられた時の処理"""
        if hasattr(self, '_standalone_mode') and self._standalone_mode:
            QApplication.instance().quit()
    
    # パブリック API メソッド
    def clear_previous_file_data(self):
        """前のファイルのデータを完全にクリアする"""
        print("[DEBUG] 前のファイルデータをクリア中...")
        
        # アニメーション関連データをクリア
        self.animations = {}
        self.current_anim = None
        self.current_frame = 0
        self.frame_start_time = 0
        self.anim_list.clear()
        self._anim_no_list = []
        
        # スプライト選択をクリア
        self.sprite_list.setCurrentRow(-1)
        self.anim_list.setCurrentRow(-1)
        self.palette_list.setCurrentRow(-1)
        
        # リストをクリア
        self.sprite_list.clear()
        self.palette_list.clear()
        
        # 出力ボタンを無効化
        self.image_export_btn.setEnabled(False)
        self.gif_export_btn.setEnabled(False)
        self.spritesheet_anim_export_btn.setEnabled(False)
        self.spritesheet_all_export_btn.setEnabled(False)
        self.all_gif_export_btn.setEnabled(False)
        
        # タイマーを停止
        if hasattr(self, 'timer'):
            self.timer.stop()
        
        # アニメーション状態をリセット
        self.playing = False
        
        # ビュー状態をリセット
        self.current_sprite_index = 0
        self.current_palette_index = 0
        
        # リーダーをクリア（一時的）
        old_reader = self.reader
        self.reader = None
        
        # キャッシュをクリア
        if hasattr(self, 'image_cache'):
            self.image_cache.clear()
        
        # 画像ウィンドウをクリア
        if hasattr(self, 'image_window') and hasattr(self.image_window, 'scene'):
            self.image_window.scene.clear()
        
        # ステータスバーをクリア
        if hasattr(self, 'status_bar_manager'):
            self.status_bar_manager.clear_status()
        
        print("[DEBUG] 前のファイルデータクリア完了")

    def load_sff_file(self, path: str) -> bool:
        """SFFファイルを読み込む
        
        Args:
            path: SFFファイルのパス
            
        Returns:
            読み込み成功時True、失敗時False
        """
        try:
            # 前のファイルのデータを完全にクリア
            self.clear_previous_file_data()
            
            # スケール値をリセット（SFFファイル単体読み込み時）
            self.localcoord_scale = 1.0
            self.st_xscale = 1.0
            self.st_yscale = 1.0
            
            # ACTパレット情報をクリア
            self.act_palettes.clear()
            self.act_palette_names.clear()
            
            # 初回中心配置フラグをリセット
            self.initial_center_applied = False
            
            # ビュー初期化フラグをリセット（新しいファイル読み込み時）
            self._view_initialized = False
            self._view_centered_after_scaling = False
            self._force_center_view = True  # ファイル読み込み時は強制中央配置
            
            # シーン初期化フラグをリセット
            if hasattr(self, 'image_window') and hasattr(self.image_window, 'scene_initialized'):
                self.image_window.scene_initialized = False
            
            # 現在のPixmapItemもリセット
            if hasattr(self, 'image_window') and hasattr(self.image_window, 'current_pixmap_item'):
                self.image_window.current_pixmap_item = None
            
            # レンダリングキャッシュをクリア
            self.clear_render_cache()
            
            # SFFファイルと同じディレクトリにDEFファイルがあるかチェック
            base_dir = os.path.dirname(path)
            sff_name = os.path.splitext(os.path.basename(path))[0]
            
            print(f"[DEBUG] SFF読み込み: {path}")
            print(f"[DEBUG] Base dir: {base_dir}")
            print(f"[DEBUG] SFF name: {sff_name}")
            
            # 同名のDEFファイルを探す
            potential_def_files = [
                os.path.join(base_dir, f"{sff_name}.def"),
                # キャラクター名が異なる場合もあるので、ディレクトリ内の全DEFファイルをチェック
            ]
            
            print(f"[DEBUG] 最初の候補DEF: {potential_def_files[0]}")
            
            # ディレクトリ内の全DEFファイルも候補に追加
            if os.path.exists(base_dir):
                print(f"[DEBUG] ディレクトリ存在確認OK: {base_dir}")
                for file in os.listdir(base_dir):
                    if file.lower().endswith('.def'):
                        def_path = os.path.join(base_dir, file)
                        if def_path not in potential_def_files:
                            potential_def_files.append(def_path)
                            print(f"[DEBUG] DEFファイル候補に追加: {def_path}")
            
            print(f"[DEBUG] 全DEF候補: {potential_def_files}")
            
            # DEFファイルからACTパレットを読み込み
            def_found = False
            for def_path in potential_def_files:
                print(f"[DEBUG] DEFファイルを検査中: {def_path}")
                if os.path.exists(def_path):
                    try:
                        print(f"[DEBUG] DEFファイル存在確認OK: {def_path}")
                        # DEFファイルが指定するSFFファイルが現在読み込み中のSFFファイルと一致するかチェック
                        sff_raw, _, _, _ = DEFParser.parse_def(def_path)
                        print(f"[DEBUG] DEFファイル内のSFF指定: {sff_raw}")
                        if sff_raw:
                            expected_sff_path = DEFParser.resolve_asset_path(base_dir, sff_raw)
                            print(f"[DEBUG] 解決されたSFFパス: {expected_sff_path}")
                            print(f"[DEBUG] 現在のSFFパス: {path}")
                            if expected_sff_path and os.path.samefile(expected_sff_path, path):
                                print(f"[DEBUG] SFF読み込み時にDEFファイルを発見: {def_path}")
                                self._load_act_palettes_from_def(def_path, base_dir)
                                def_found = True
                                break
                            else:
                                print(f"[DEBUG] SFFパスが一致しません")
                    except Exception as e:
                        print(f"[DEBUG] DEFファイル {def_path} の解析に失敗: {e}")
                        continue
                else:
                    print(f"[DEBUG] DEFファイルが存在しません: {def_path}")
            
            if not def_found and self.config.debug_mode:
                print(f"[DEBUG] SFFファイル {path} に対応するDEFファイルが見つかりませんでした")
            
            self._load_sff_internal(path)
            self.file_loaded.emit(path)
            
            # ファイル読み込み完了後に自動スケーリングを実行
            print(f"[DEBUG] SFFファイル読み込み完了 - 自動スケーリング実行")
            self._auto_scale_to_fit()
            
            # ファイル履歴に追加
            self._add_to_recent_files(path)
            
            return True
        except Exception as e:
            if self.config.debug_mode:
                logging.error(f"SFF load error: {e}")
            self._safe_set_label_text(f'読み込み失敗: {e}')
            return False
    
    def load_def_file(self, path: str) -> bool:
        """DEFファイルを読み込む
        
        Args:
            path: DEFファイルのパス
            
        Returns:
            読み込み成功時True、失敗時False
        """
        try:
            # 前のファイルのデータを完全にクリア
            self.clear_previous_file_data()
            
            # 初回中心配置フラグをリセット
            self.initial_center_applied = False
            
            # ビュー初期化フラグをリセット（新しいファイル読み込み時）
            self._view_centered_after_scaling = False
            self._force_center_view = True  # ファイル読み込み時は強制中央配置
            
            # シーン初期化フラグをリセット
            if hasattr(self, 'image_window') and hasattr(self.image_window, 'scene_initialized'):
                self.image_window.scene_initialized = False
            
            # 現在のPixmapItemもリセット
            if hasattr(self, 'image_window') and hasattr(self.image_window, 'current_pixmap_item'):
                self.image_window.current_pixmap_item = None
            
            # レンダリングキャッシュをクリア
            self.clear_render_cache()
            
            sff_raw, air_raw, localcoord, st_raw = DEFParser.parse_def(path)
            base = os.path.dirname(path)
            sff_path = DEFParser.resolve_asset_path(base, sff_raw)
            air_path = DEFParser.resolve_asset_path(base, air_raw)
            st_path = DEFParser.resolve_asset_path(base, st_raw) if st_raw else None
            
            if not sff_path:
                raise FileNotFoundError(f'sprite= で指定された SFF が見つかりません: {sff_raw}')
            
            # localcoordに基づくスケールファクターを設定
            self.localcoord_scale = DEFParser.get_localcoord_scale_factor(localcoord)
            if self.config.debug_mode:
                print(f"[DEF] localcoord: {localcoord}, scale: {self.localcoord_scale}")
            
            # STファイルからxscale/yscaleを取得
            if st_path:
                self.st_xscale, self.st_yscale = DEFParser.parse_st_file(st_path)
                if self.config.debug_mode:
                    print(f"[DEF] ST file: {st_path}, xscale: {self.st_xscale}, yscale: {self.st_yscale}")
            else:
                self.st_xscale = 1.0
                self.st_yscale = 1.0
            
            # ACTパレットファイルを読み込み
            self._load_act_palettes_from_def(path, base)
            
            self._load_sff_internal(sff_path)
            
            if air_path:
                print(f"[DEBUG] AIRファイル読み込み開始: {air_path}")
                self.animations = parse_air(air_path)
                print(f"[DEBUG] AIRファイル読み込み完了: {len(self.animations)}個のアニメーション")
                
                # 各アニメーションの詳細をデバッグ出力
                for anim_no, frames in list(self.animations.items())[:3]:  # 最初の3つだけ
                    print(f"[DEBUG] アニメ{anim_no}: {len(frames)}フレーム")
                    for i, frame in enumerate(frames[:2]):  # 最初の2フレームだけ
                        clsn1_count = len(frame.get('clsn1', []))
                        clsn2_count = len(frame.get('clsn2', []))
                        print(f"[DEBUG]   フレーム{i}: group={frame.get('group')}, image={frame.get('image')}, clsn1={clsn1_count}, clsn2={clsn2_count}")
                        if clsn1_count > 0:
                            print(f"[DEBUG]     clsn1: {frame.get('clsn1')}")
                        if clsn2_count > 0:
                            print(f"[DEBUG]     clsn2: {frame.get('clsn2')}")
                
                self.populate_animations()
                if self.animations:
                    self.start_animation(self._anim_no_list[0])
            
            self.file_loaded.emit(path)
            
            # ファイル読み込み完了後に自動スケーリングを実行
            print(f"[DEBUG] DEFファイル読み込み完了 - 自動スケーリング実行")
            self._auto_scale_to_fit()
            
            # ファイル履歴に追加
            self._add_to_recent_files(path)
            
            return True
        except Exception as e:
            if self.config.debug_mode:
                logging.error(f"DEF load error: {e}")
            # UIコンポーネントが有効かどうかチェック
            self._safe_set_label_text(f'読み込み失敗: {e}')
            return False
    
    def get_current_sprite_index(self) -> Optional[int]:
        """現在選択中のスプライトインデックスを取得"""
        return self.sprite_list.currentRow() if self.sprite_list.currentRow() >= 0 else None
    
    def set_sprite_index(self, index: int) -> bool:
        """スプライトインデックスを設定"""
        if 0 <= index < self.sprite_list.count():
            self.sprite_list.setCurrentRow(index)
            return True
        return False
    
    def get_sprite_count(self) -> int:
        """スプライト数を取得"""
        return len(self.reader.sprites) if self.reader and hasattr(self.reader, 'sprites') else 0
    
    def export_current_sprite(self, save_path: str, format: str = 'PNG') -> bool:
        """現在のスプライトを画像ファイルとして出力"""
        try:
            idx = self.get_current_sprite_index()
            if idx is None or not self.reader:
                return False
            
            qimg, _ = self.renderer.render_sprite(
                self.reader, idx, 
                self.palette_list.currentRow() if self.palette_list.currentRow() >= 0 else None,
                self.is_v2,
                self.act_palettes
            )
            
            return qimg.save(save_path, format)
        except Exception as e:
            if self.config.debug_mode:
                logging.error(f"Export error: {e}")
            return False
    
    def get_sprite_info(self, index: Optional[int] = None) -> Optional[Dict]:
        """スプライト情報を取得"""
        if not self.reader or not hasattr(self.reader, 'sprites'):
            return None
        
        idx = index if index is not None else self.get_current_sprite_index()
        if idx is None or not (0 <= idx < len(self.reader.sprites)):
            return None
        
        sprite = self.reader.sprites[idx]
        return {
            'index': idx,
            'group_no': sprite.get('group_no', 0),
            'sprite_no': sprite.get('sprite_no', 0),
            'width': sprite.get('width', 0),
            'height': sprite.get('height', 0),
            'x_axis': sprite.get('x_axis', 0),
            'y_axis': sprite.get('y_axis', 0),
        }
    
    def get_animation_list(self) -> List[int]:
        """利用可能なアニメーション番号のリストを取得"""
        return self._anim_no_list.copy()
    
    def is_animation_playing(self) -> bool:
        """アニメーションが再生中かどうか"""
        return self.timer.isActive()
    
    def _capture_view_state(self):
        """現在のビューの状態を取得"""
        view = self.image_window.view
        return (view.transform(),
                view.horizontalScrollBar().value(),
                view.verticalScrollBar().value())
    
    def _store_anim_view_state(self, transform, h, v):
        """アニメーション用のビュー状態を保存"""
        self._anim_view_transform = transform
        self._anim_h_scroll = h
        self._anim_v_scroll = v
    
    def _restore_anim_view_state(self):
        """アニメーション用のビュー状態を復元（クランプ付き）"""
        if self._anim_view_transform is None:
            return
        view = self.image_window.view
        view.setTransform(self._anim_view_transform)
        
        # スクロール位置を安全に復元（クランプ）
        hbar = view.horizontalScrollBar()
        vbar = view.verticalScrollBar()
        if self._anim_h_scroll is not None:
            hbar.setValue(max(hbar.minimum(), min(hbar.maximum(), self._anim_h_scroll)))
        if self._anim_v_scroll is not None:
            vbar.setValue(max(vbar.minimum(), min(vbar.maximum(), self._anim_v_scroll)))
    
    def stop_animation(self):
        """アニメーション停止"""
        if self.timer.isActive():
            self.timer.stop()
        
        # アニメーション状態をクリア
        self.current_anim = None
        self.current_frame_data = None  # ★追加：判定データを確実にクリア
        
        # LoopStart関連の状態をリセット
        self.loop_start_index = -1
        self.loop_target_index = -1
        self.loop_count = 0
        self.loop_start_time = 0.0
        
        # アニメーション停止時は現在の固定状態を通常状態として保存
        if (hasattr(self, 'image_window') and self.image_window and self.image_window.view.scene() and
            self._anim_view_transform is not None):
            view = self.image_window.view
            # 現在の固定状態を通常状態として保存
            self.saved_view_transform = self._anim_view_transform
            self.saved_h_scroll = self._anim_h_scroll  
            self.saved_v_scroll = self._anim_v_scroll
            print(f"[DEBUG] アニメーション停止 - 固定状態を通常状態として保存: h_scroll={self._anim_h_scroll}, v_scroll={self._anim_v_scroll}")
        
        # アニメーション固定状態をクリア
        self._anim_view_transform = None
        self._anim_h_scroll = None
        self._anim_v_scroll = None
    
    def clear_render_cache(self):
        """レンダリングキャッシュをクリア"""
        self.render_cache.clear()
        print(f"[DEBUG] レンダリングキャッシュクリア")
    
    def pause_animation(self):
        """アニメーション一時停止/再開"""
        if self.timer.isActive():
            self.timer.stop()
        else:
            self.timer.start()
    
    def _load_act_palettes_from_def(self, def_path: str, base_dir: str):
        """DEFファイルからACTパレットを読み込み"""
        self.act_palettes.clear()
        self.act_palette_names.clear()
        
        # DEFファイルからパレット情報を取得
        palette_files = DEFParser.parse_def_palettes(def_path)
        print(f"[DEBUG] Found {len(palette_files)} palette files in DEF: {palette_files}")
        
        for pal_file in palette_files:
            pal_path = DEFParser.resolve_asset_path(base_dir, pal_file)
            print(f"[DEBUG] Processing palette file: {pal_file} -> {pal_path}")
            if pal_path:
                palette = DEFParser.load_act_palette(pal_path)
                if palette:
                    self.act_palettes.append(palette)
                    self.act_palette_names.append(os.path.basename(pal_file))
                    print(f"[DEBUG] Successfully loaded ACT palette: {pal_file} (first color: {palette[0]}, last color: {palette[-1]})")
                    if self.config.debug_mode:
                        print(f"[DEF] Loaded ACT palette: {pal_file}")
                else:
                    print(f"[DEBUG] Failed to load ACT palette: {pal_file}")
            else:
                print(f"[DEBUG] Could not resolve path for palette file: {pal_file}")
        
        print(f"[DEBUG] Total ACT palettes loaded: {len(self.act_palettes)}")
    
    # 内部メソッド
    def _load_sff_internal(self, path: str):
        """SFFファイルの内部読み込み処理"""
        print(f"[DEBUG] _load_sff_internal開始: {path}")
        
        with open(path,'rb') as f:
            sig = f.read(12)
            f.seek(0)
            print(f"[DEBUG] SFFシグネチャ: {sig[:12]}")
            if sig.startswith(b'ElecbyteSpr'):
                f.seek(12)
                ver = tuple(f.read(4))
                f.seek(0)
                print(f"[DEBUG] SFFバージョン: {ver}")
                if ver in [(0,0,0,2),(0,1,0,2)]:
                    print(f"[DEBUG] SFFv2として認識")
                    self.reader = SFFV2Reader(path)
                    self.is_v2 = True
                else:
                    print(f"[DEBUG] SFFv1として認識（Elecbyte形式）")
                    self.reader = SFFReader(path)
                    self.is_v2 = False
            else:
                print(f"[DEBUG] SFFv1として認識（従来形式）")
                self.reader = SFFReader(path)
                self.is_v2 = False
        
        # 読み込み順序
        print(f"[DEBUG] データ読み込み開始 (v2={self.is_v2})")
        if self.is_v2:
            with open(path,'rb') as f:
                print(f"[DEBUG] SFFv2: ヘッダー読み込み開始")
                self.reader.read_header(f)
                print(f"[DEBUG] SFFv2: パレット読み込み開始")
                self.reader.read_palettes(f)
                print(f"[DEBUG] SFFv2: スプライト読み込み開始")
                self.reader.read_sprites(f)
        else:
            with open(path,'rb') as f:
                print(f"[DEBUG] SFFv1: ヘッダー読み込み開始")
                self.reader.read_header(f)
                print(f"[DEBUG] SFFv1: スプライト読み込み開始")
                self.reader.read_sprites(f)
                print(f"[DEBUG] SFFv1: パレット読み込み開始")
                self.reader.read_palettes(f)
        
        print(f"[DEBUG] UI更新開始")
        # UIコンポーネントが有効かどうかチェック
        self._safe_set_label_text(os.path.basename(path))
        
        # SFF全体の最大画像サイズを計算
        print(f"[DEBUG] 最大画像サイズ計算開始")
        self._calculate_max_image_size()
        
        # キャンバススケールキャッシュをリセット（新しいSFFファイル読み込み時）
        self._reset_canvas_scale_cache()
        
        print(f"[DEBUG] リスト作成開始")
        self.populate_lists()
        print(f"[DEBUG] _load_sff_internal完了")

    def _reset_canvas_scale_cache(self):
        """キャンバススケールキャッシュをリセット"""
        self._last_canvas_scale_x = None
        self._last_canvas_scale_y = None
        self._scaled_canvas_width = None
        self._scaled_canvas_height = None
        self._view_centered_after_scaling = False  # ビュー中央配置フラグもリセット
        print(f"[DEBUG] キャンバススケールキャッシュリセット")

    def _to_canvas_xy(self, origin_x, origin_y, ax, ay, dx, dy, obj_x, obj_y, scx, scy):
        """オブジェクト座標をキャンバス座標に変換（GIF出力用）"""
        # 実効軸位置の計算
        effective_axis_x = ax + dx
        effective_axis_y = ay + dy
        
        # オブジェクト座標を実効軸からの相対位置として扱う
        relative_x = obj_x
        relative_y = obj_y
        
        # キャンバス座標への変換
        # origin_x, origin_y がキャンバス中心で、実効軸がそこに配置される
        canvas_x = origin_x - effective_axis_x + relative_x * scx
        canvas_y = origin_y - effective_axis_y + relative_y * scy
        
        return int(round(canvas_x)), int(round(canvas_y))

    def _center_view_on_image(self):
        """ビューを画像の中心に移動（画像処理完了後用）"""
        if not hasattr(self, 'image_window') or not self.image_window:
            return
            
        view = self.image_window.view
        scene = view.scene()
        
        if not scene or not self.image_window.current_pixmap_item:
            return
        
        # ビューとシーンの更新を確実にするため、少し待つ
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(10, self._do_center_view_on_image)
        
    def _do_center_view_on_image(self):
        """実際のビュー中央配置処理"""
        if not hasattr(self, 'image_window') or not self.image_window:
            return
            
        view = self.image_window.view
        scene = view.scene()
        
        if not scene or not self.image_window.current_pixmap_item:
            return
            
        # 現在の画像アイテムの境界を取得
        pixmap_item = self.image_window.current_pixmap_item
        pixmap_rect = pixmap_item.boundingRect()
        
        # 画像の中心をシーン座標で計算
        item_center_x = pixmap_rect.width() / 2
        item_center_y = pixmap_rect.height() / 2
        
        # ビューポートのサイズを取得してやや上にずらすオフセットを計算
        viewport_rect = view.viewport().rect()
        vertical_offset = viewport_rect.height() * 0.30  # ビューポート高さの30%上にずらす
        
        # 画像中心からやや上にずらした位置に配置
        target_y = item_center_y - vertical_offset
        view.centerOn(item_center_x, target_y)
        
        print(f"[DEBUG] ビュー中央配置完了（やや上配置）: 画像サイズ({pixmap_rect.width():.1f}x{pixmap_rect.height():.1f}), 中心({item_center_x:.1f},{target_y:.1f}), オフセット={vertical_offset:.1f}")
        
        # スクロール値をログ出力
        h_scroll = view.horizontalScrollBar().value()
        v_scroll = view.verticalScrollBar().value()
        print(f"[DEBUG] スクロール位置: h={h_scroll}, v={v_scroll}")

    def _axis_symmetric_canvas(self, w, h, ax, ay, margin, min_size, max_size):
        """軸対称キャンバスサイズを計算（軸をキャンバス中心に置く前提）"""
        """軸対称キャンバスサイズを計算（軸をキャンバス中心に置く前提）"""
        left   = ax + margin
        right  = (w - ax) + margin
        top    = ay + margin
        bottom = (h - ay) + margin
        cw = 2 * max(left, right)
        ch = 2 * max(top, bottom)
        cw = max(min_size[0], min(max_size[0], cw))
        ch = max(min_size[1], min(max_size[1], ch))
        return cw, ch

    def _calculate_max_image_size(self):
        """SFF全体の最大画像サイズを計算"""
        max_width = 0
        max_height = 0
        max_canvas_w = 0
        max_canvas_h = 0
        
        if not self.reader:
            return
            
        try:
            # 全スプライトの画像サイズと軸位置から最適キャンバスサイズを計算
            m = self.config.canvas_margin  # 余白
            
            for i, sprite in enumerate(self.reader.sprites):
                if i % 100 == 0:  # 進捗表示
                    print(f"[DEBUG] 最大サイズ計算中: {i}/{len(self.reader.sprites)}")
                
                try:
                    # メタデータから画像サイズと軸位置を取得（image_dataは不要）
                    w = getattr(sprite, 'width', 0)
                    h = getattr(sprite, 'height', 0)
                    ax = getattr(sprite, 'axisx', 0)
                    ay = getattr(sprite, 'axisy', 0)
                    
                    # 各スプライトの最適キャンバスサイズを計算
                    # cw = 2 * max(ax + m, (w - ax) + m)
                    # ch = 2 * max(ay + m, (h - ay) + m)
                    cw = 2 * max(ax + m, (w - ax) + m)
                    ch = 2 * max(ay + m, (h - ay) + m)
                    
                    # 全体の最大値を更新
                    if w > max_width:
                        max_width = w
                    if h > max_height:
                        max_height = h
                    if cw > max_canvas_w:
                        max_canvas_w = cw
                    if ch > max_canvas_h:
                        max_canvas_h = ch
                            
                except Exception as e:
                    # 個別の画像エラーは無視して続行
                    continue
            
            # 最適キャンバスサイズの決定（提供された式を使用）
            # 最小サイズ保証を適用
            min_w, min_h = self.config.min_canvas_size
            self.max_canvas_width = max(min_w, max_canvas_w)
            self.max_canvas_height = max(min_h, max_canvas_h)
            
            print(f"[DEBUG] 最大画像サイズ: {max_width}x{max_height}")
            print(f"[DEBUG] 計算されたキャンバス: {max_canvas_w}x{max_canvas_h}")
            print(f"[DEBUG] 最終キャンバスサイズ: {self.max_canvas_width}x{self.max_canvas_height}")
            
        except Exception as e:
            print(f"[DEBUG] 最大サイズ計算エラー: {e}")
            # エラー時はデフォルト値を使用
            self.max_canvas_width = self.config.min_canvas_size[0]
            self.max_canvas_height = self.config.min_canvas_size[1]

    # ---------- window arrangement ----------
    def arrange_windows(self):
        """ウィンドウ配置調整"""
        from PyQt5.QtWidgets import QDesktopWidget
        screen = QDesktopWidget().screenGeometry()
        gap = 8
        mw, mh = self.width(), self.height()
        iw, ih = self.image_window.width(), self.image_window.height()
        
        if mw + iw + gap <= screen.width():
            sx = (screen.width() - (mw + iw + gap))//2
            sy = (screen.height() - max(mh, ih))//2
            self.move(sx, sy)
            self.image_window.move(sx + mw + gap, sy)
        else:
            total_h = mh + ih + gap
            sx = (screen.width() - max(mw, iw))//2
            sy = (screen.height() - total_h)//2
            self.move(sx, sy)
            self.image_window.move(sx, sy + mh + gap)

    def showEvent(self, e):
        super().showEvent(e)
        self.arrange_windows()

    # ---------- file loading ---------- 
    def open_file(self):
        """ファイル選択ダイアログ"""
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open SFF/DEF', self.last_opened_dir, 'SFF/DEF (*.sff *.def);;All (*)'
        )
        if not path: 
            return
        
        # 開いたファイルのディレクトリを記録し設定に保存
        self.last_opened_dir = os.path.dirname(path)
        self.language_manager.save_settings({'last_opened_dir': self.last_opened_dir})
        
        if path.lower().endswith('.def'):
            self.load_def_file(path)
        else:
            self.load_sff_file(path)
    
    # ---------- lists ----------
    def populate_lists(self):
        print(f"[DEBUG] populate_lists開始")
        self.sprite_list.clear(); self.palette_list.clear()
        if not self.reader: 
            print(f"[DEBUG] readerがNoneのため処理終了")
            return
        
        print(f"[DEBUG] スプライト数: {len(self.reader.sprites)}")
        for i,s in enumerate(self.reader.sprites):
            g = s.get('group_no',0); n = s.get('sprite_no',0)
            w = s.get('width',0); h = s.get('height',0)
            self.sprite_list.addItem(f'{i}:({g},{n}) {w}x{h}')
        
        print(f"[DEBUG] パレット情報追加開始 (v2={self.is_v2})")
        # 初期選択を削除（自動選択しない）
        if self.is_v2:
            palette_count = len(getattr(self.reader,'palettes',[]))
            print(f"[DEBUG] SFFv2パレット数: {palette_count}")
            for i,_ in enumerate(getattr(self.reader,'palettes',[])):
                self.palette_list.addItem(f'Pal {i}')
        else:
            # SFFv1の場合
            if getattr(self.reader,'palettes',None):
                print(f"[DEBUG] SFFv1パレット追加")
                self.palette_list.addItem('Palette 0')
            
            # DEFから読み込んだACTパレットを追加
            print(f"[DEBUG] ACTパレット数: {len(self.act_palette_names)}")
            for i, name in enumerate(self.act_palette_names):
                print(f"[DEBUG] ACTパレット追加: {name}")
                self.palette_list.addItem(f'ACT {i}: {name}')
        
        if self.palette_list.count(): 
            print(f"[DEBUG] 初期パレット選択")
            self.palette_list.setCurrentRow(0)
        
        print(f"[DEBUG] refresh_current_sprite呼び出し")
        self.refresh_current_sprite()
        
        # ファイル読み込み完了時にグローバル出力ボタンを有効化
        if self.reader and hasattr(self.reader, 'sprites'):
            self.spritesheet_all_export_btn.setEnabled(True)
            self.all_gif_export_btn.setEnabled(True)
        
        print(f"[DEBUG] populate_lists完了")
        
        # 固定キャンバスサイズは動的計算に置き換えたため、初期化は不要
        # self.initialize_fixed_canvas_size()

    def initialize_fixed_canvas_size(self):
        """全スプライトの軸込みバウンディングボックスに基づいて固定キャンバスサイズを決定"""
        if not self.reader or not self.reader.sprites:
            self.fixed_canvas_size = (800, 600)  # デフォルトサイズ
            print(f"[DEBUG] 固定キャンバスサイズ（デフォルト）: {self.fixed_canvas_size}")
            return
        
        # 新しいバウンディングボックス計算を使用
        try:
            # calculate_dynamic_canvas_sizeメソッドを使用して適切なサイズを計算
            canvas_w, canvas_h = self.calculate_dynamic_canvas_size(self.reader, 1.0, True)
            
            # 最小サイズを保証
            canvas_w = max(canvas_w, 400)
            canvas_h = max(canvas_h, 300)
            
            self.fixed_canvas_size = (canvas_w, canvas_h)
            
            print(f"[DEBUG] 固定キャンバスサイズ初期化: 軸込みバウンディングボックスベース -> 固定キャンバス{canvas_w}x{canvas_h}")
        except Exception as e:
            self.fixed_canvas_size = (800, 600)
            print(f"[DEBUG] 固定キャンバスサイズ（エラー）: {self.fixed_canvas_size}, エラー: {e}")

    def populate_animations(self):
        """AIR 読み込み後にアニメ一覧を作成"""
        self.anim_list.clear()
        self._anim_no_list = []
        if not self.animations:
            return
        for no, frames in sorted(self.animations.items(), key=lambda x: x[0]):
            self._anim_no_list.append(no)
            self.anim_list.addItem(f'{no} ({len(frames)})')
        # 初期選択を削除（自動選択しない）
        
        # アニメーション読み込み完了時にGIF出力ボタンを有効化
        if self.animations:
            self.all_gif_export_btn.setEnabled(True)

    def calculate_combined_scale(self, debug: bool = False) -> Tuple[float, float]:
        """統合スケールを計算（localcoord + ST + UI）"""
        # 基本スケール（localcoord + ST）
        combined_scale_x = self.localcoord_scale * self.st_xscale
        combined_scale_y = self.localcoord_scale * self.st_yscale
        
        # UIスケール（固定キャンバスでは制限付き）
        if not self.original_size:
            ui_scale = self.scale_factor
            # 固定キャンバスでの最大スケール制限
            max_scale = 2.5
            ui_scale = min(ui_scale, max_scale)
            
            combined_scale_x *= ui_scale
            combined_scale_y *= ui_scale
        
        if debug and self.config.debug_mode:
            print(f"[統合スケール] localcoord: {self.localcoord_scale}, ST: ({self.st_xscale}, {self.st_yscale})")
            print(f"[統合スケール] UI(制限後): {ui_scale if not self.original_size else 1.0}, 結果: ({combined_scale_x:.2f}, {combined_scale_y:.2f})")
        
        return combined_scale_x, combined_scale_y

    def calculate_optimal_canvas_size(self) -> Tuple[int, int]:
        """すべての画像が収まる最適なキャンバスサイズを計算（スケーリング前）"""
        if not self.reader or not self.reader.sprites:
            return 800, 600  # デフォルトサイズ
        
        max_width = 0
        max_height = 0
        
        # すべてのスプライトをチェック
        for i, sprite in enumerate(self.reader.sprites):
            sprite_w = sprite.get('width', 0)
            sprite_h = sprite.get('height', 0)
            axis_x = sprite.get('axis_x', 0)
            axis_y = sprite.get('axis_y', 0)
            
            # 軸を考慮した必要サイズを計算
            # 左端：軸位置 + マージン
            # 右端：(画像幅 - 軸位置) + マージン  
            # 上端：軸位置 + マージン
            # 下端：(画像高さ - 軸位置) + マージン
            left_space = axis_x + self.config.canvas_margin
            right_space = (sprite_w - axis_x) + self.config.canvas_margin
            top_space = axis_y + self.config.canvas_margin
            bottom_space = (sprite_h - axis_y) + self.config.canvas_margin
            
            # 軸を中心に配置するため、左右・上下の最大値を2倍
            req_w = 2 * max(left_space, right_space)
            req_h = 2 * max(top_space, bottom_space)
            
            max_width = max(max_width, req_w)
            max_height = max(max_height, req_h)
        
        # 適切な範囲に制限（より大きな値を許可）
        canvas_w = max(800, min(max_width, 1600))
        canvas_h = max(600, min(max_height, 1200))
        
        print(f"[DEBUG] 全スプライト対応キャンバス: {canvas_w}x{canvas_h}")
        return canvas_w, canvas_h

    def on_anim_selected(self, row: int):
        if row < 0 or row >= len(self._anim_no_list):
            # アニメーション選択解除
            # 個別エクスポートボタンのみ無効化
            self.gif_export_btn.setEnabled(False)
            self.spritesheet_anim_export_btn.setEnabled(False)
            self.image_export_btn.setEnabled(False)
            # グローバルボタンはファイル読み込み状態のみで判定
            if self.reader and hasattr(self.reader, 'sprites'):
                self.spritesheet_all_export_btn.setEnabled(True)
                self.all_gif_export_btn.setEnabled(True)
            else:
                self.spritesheet_all_export_btn.setEnabled(False)
                self.all_gif_export_btn.setEnabled(False)
            return
        
        no = self._anim_no_list[row]
        
        # スプライトリストの選択を解除
        self.sprite_list.setCurrentRow(-1)
        
        # 個別エクスポートボタンを有効化
        self.gif_export_btn.setEnabled(True)
        self.image_export_btn.setEnabled(True)
        self.spritesheet_anim_export_btn.setEnabled(True)
        # グローバルボタンは常に有効（ファイル読み込み済み前提）
        self.spritesheet_all_export_btn.setEnabled(True)
        self.all_gif_export_btn.setEnabled(True)
        
        # アニメーション開始
        self.start_animation(no)
        
        # アニメ開始時に一度だけフィット
        if self.config.debug_mode:
            print(f"[アニメ選択] アニメ {no} を開始")

    # ---------- events ----------
    def calculate_scaled_canvas_size(self) -> Tuple[int, int]:
        """スケール値に応じたキャンバス（描画領域）サイズを計算"""
        base_w, base_h = 800, 600  # ベースキャンバスサイズ
        
        # UIスケール値に応じてキャンバスサイズを調整
        scale = max(0.1, self.scale_factor)  # 最小スケール制限
        
        # スケールに比例してキャンバスサイズを変更
        scaled_w = int(base_w * scale)
        scaled_h = int(base_h * scale)
        
        # ウィンドウサイズは固定なので、キャンバスサイズの制限を調整
        # 最小サイズ制限
        scaled_w = max(200, scaled_w)
        scaled_h = max(150, scaled_h)
        
        # 最大サイズ制限（ウィンドウ内に収まるように）
        # 実際のウィンドウサイズより少し小さく設定
        max_w = getattr(self.config, 'image_window_width', 820) - 40
        max_h = getattr(self.config, 'image_window_height', 640) - 40
        scaled_w = min(max_w, scaled_w)
        scaled_h = min(max_h, scaled_h)
        
        return scaled_w, scaled_h
    
    def update_canvas_size(self):
        """キャンバスサイズを現在のスケールに合わせて更新（ウィンドウサイズは変更しない）"""
        new_w, new_h = self.calculate_scaled_canvas_size()
        
        # 設定を更新（描画領域のサイズのみ）
        self.config.fixed_canvas_size = (new_w, new_h)
        
        # ウィンドウサイズは変更せず、描画領域のサイズのみ更新
        # 描画処理で使用されるキャンバスサイズが変更されるため、
        # スケールに応じて描画領域が拡大縮小される
        
        if self.config.debug_mode:
            print(f"[キャンバスサイズ更新] スケール: {self.scale_factor:.2f}, 描画領域サイズ: {new_w}x{new_h}")

    def on_scale_combo_changed(self):
        """スケールコンボボックス変更時の処理"""
        selected_scale = self.scale_values[self.scale_combo.currentIndex()]
        self.scale_factor = selected_scale / 100.0
        self._reset_canvas_scale_cache()  # スケール変更時にキャッシュリセット
        
        # スケール変更時は強制的にビュー中央配置を行う
        self._force_center_view = True
        self._view_centered_after_scaling = False
        
        self.update_canvas_size()  # キャンバスサイズを更新
        self.refresh_current_sprite()  # 現在のスプライトを再描画

    def on_scale_changed(self):
        """旧スケールスピンボックス用（互換性のため残す）"""
        if hasattr(self, 'scale_spin'):
            self.scale_factor = self.scale_spin.value()/100.0
        self._reset_canvas_scale_cache()  # スケール変更時にキャッシュリセット
        self.update_canvas_size()  # キャンバスサイズを更新
        self.refresh_current_sprite()

    def on_original_toggled(self, checked: bool):
        self.original_size = checked
        self._reset_canvas_scale_cache()  # Original Size切り替え時にキャッシュリセット
        
        # 原寸表示切り替え時は強制的にビュー中央配置を行う
        self._force_center_view = True
        self._view_centered_after_scaling = False
        
        # スケール選択の有効/無効を切り替え
        if hasattr(self, 'scale_combo'):
            self.scale_combo.setEnabled(not checked)
        if hasattr(self, 'scale_spin'):  # 互換性のため
            self.scale_spin.setEnabled(not checked)
            
        self.refresh_current_sprite()
    
    def on_no_alpha_toggled(self, checked: bool):
        self.no_alpha = checked
        self.refresh_current_sprite()
    
    def on_show_clsn_toggled(self, checked: bool):
        self.config.show_clsn = checked
        print(f"[DEBUG] Clsn表示切り替え: checked={checked}, config.show_clsn={self.config.show_clsn}")
        # 判定表示の切り替え時にレンダリングキャッシュをクリア
        if hasattr(self, 'render_cache'):
            self.render_cache.clear()
            print(f"[DEBUG] Clsn表示切り替え - キャッシュクリア")
        self.refresh_current_sprite()
    
    def _sync_scale_factor(self):
        """UIのスケール選択と内部のスケールファクターを同期"""
        if hasattr(self, 'scale_combo'):
            selected_scale = self.scale_values[self.scale_combo.currentIndex()]
            self.scale_factor = selected_scale / 100.0
    
    def _auto_scale_to_fit(self):
        """読み込み時は100%でウィンドウ内に画像が収まるよう配置（キャンバスを無視）"""
        if not self.reader or not hasattr(self, 'image_window') or not self.image_window:
            return
        
        if self.chk_original.isChecked():
            return  # 原寸表示時は自動スケーリングしない
        
        print(f"[DEBUG] _auto_scale_to_fit開始（100%基準）")
        
        # 画像ウィンドウの実際の表示領域を取得
        view_rect = self.image_window.view.viewport().rect()
        window_width = max(view_rect.width() - 40, 300)  # 最小300px確保
        window_height = max(view_rect.height() - 40, 200)  # 最小200px確保
        
        print(f"[DEBUG] ウィンドウ表示領域: {window_width}x{window_height}")
        
        # 現在選択中または最初のスプライトの実際のサイズを取得
        current_index = self.get_current_sprite_index()
        sprite_index = current_index if current_index is not None and current_index < len(self.reader.sprites) else 0
        
        if sprite_index < len(self.reader.sprites):
            sprite = self.reader.sprites[sprite_index]
            sprite_width = sprite.get('width', 0)
            sprite_height = sprite.get('height', 0)
            
            print(f"[DEBUG] 対象スプライト[{sprite_index}]: {sprite_width}x{sprite_height}")
            
            if sprite_width > 0 and sprite_height > 0:
                # まず100%スケール（scale_values内の100を探す）を設定
                try:
                    scale_100_index = self.scale_values.index(100)
                    self.scale_combo.setCurrentIndex(scale_100_index)
                    print(f"[DEBUG] 100%スケール設定完了")
                    
                    # 100%でウィンドウに収まるかチェック
                    if sprite_width <= window_width and sprite_height <= window_height:
                        print(f"[DEBUG] 100%でウィンドウに収まります")
                    else:
                        # 収まらない場合は縮小スケールを計算
                        scale_x = window_width / sprite_width
                        scale_y = window_height / sprite_height
                        optimal_scale = min(scale_x, scale_y)
                        
                        # スケール範囲を制限（10%〜100%）
                        optimal_scale = min(optimal_scale, 1.0)  # 最大100%
                        optimal_scale = max(optimal_scale, 0.1)  # 最小10%
                        
                        print(f"[DEBUG] 縮小が必要: 計算スケール={optimal_scale:.3f}")
                        
                        # 利用可能なスケール値から最も近い値を選択
                        optimal_scale_percent = int(optimal_scale * 100)
                        best_scale = min(self.scale_values, key=lambda x: abs(x - optimal_scale_percent))
                        
                        print(f"[DEBUG] 最適スケール: {optimal_scale_percent}% → 選択スケール: {best_scale}%")
                        
                        # スケールを設定
                        scale_index = self.scale_values.index(best_scale)
                        self.scale_combo.setCurrentIndex(scale_index)
                        print(f"[DEBUG] 縮小スケール設定完了: {best_scale}%")
                    
                    # スケール変更後にビュー中央配置を強制実行
                    self._view_centered_after_scaling = False
                    
                except ValueError:
                    print(f"[DEBUG] 100%スケールが見つかりません - デフォルト動作")
            else:
                print(f"[DEBUG] 無効なスプライトサイズ: {sprite_width}x{sprite_height}")
        else:
            print(f"[DEBUG] スプライト取得失敗: index={sprite_index}, total={len(self.reader.sprites) if self.reader else 0}")
    
    # ---------- rendering ----------
    def refresh_current_sprite(self):
        print(f"[DEBUG] refresh_current_sprite開始")
        
        if not self.reader: 
            print(f"[DEBUG] readerがNone - 空のキャンバス表示")
            # 何もない場合は空のキャンバスを表示
            self.show_empty_canvas()
            # パレットUIを無効化
            self.palette_list.setEnabled(False)
            self.palette_status_label.setText("パレット選択: 無効 (ファイル未読み込み)")
            self.palette_status_label.setStyleSheet("color: gray; font-size: 10px;")
            return
        
        # アニメーション中の場合
        if self.is_animating():
            print(f"[DEBUG] アニメーション中 - フレーム表示")
            self.display_current_animation_frame()
            return
        
        # 通常のスプライト表示
        idx = self.sprite_list.currentRow()
        print(f"[DEBUG] 選択スプライトインデックス: {idx}")
        if idx < 0: 
            print(f"[DEBUG] スプライト未選択 - 空のキャンバス表示")
            # 何も選択されていない場合は空のキャンバスを表示
            self.show_empty_canvas()
            # パレットUIを無効化
            self.palette_list.setEnabled(False)
            self.palette_status_label.setText("パレット選択: 無効 (スプライト未選択)")
            self.palette_status_label.setStyleSheet("color: gray; font-size: 10px;")
            return
            
        try:
            # パレットUIの有効性を確認
            should_enable_palette = self._should_enable_palette_ui(idx)
            self._update_palette_ui_status(should_enable_palette, idx)
            
            print(f"[DEBUG] スプライト {idx} のレンダリング開始")
            # 通常のスプライト表示時はClsnデータをクリア
            self.current_frame_data = None
            # レンダリングキャッシュをクリア（判定表示の残存を防ぐ）
            if hasattr(self, 'render_cache'):
                self.render_cache.clear()
                print(f"[DEBUG] レンダリングキャッシュクリア")
            
            qimg, palette = self.render_sprite(idx)
            print(f"[DEBUG] レンダリング完了: 画像={qimg is not None}, パレット={palette is not None}")
            
            # 軸計算: 基準軸 + スプライト軸 + AIR軸
            axis_x, axis_y = self.calculate_display_axis(idx)
            print(f"[DEBUG] 表示軸: ({axis_x}, {axis_y})")
            
            if self.config.debug_mode:
                canvas_w, canvas_h = self.calculate_dynamic_canvas_size(self.reader, 1.0, True)
                print(f"[スプライト表示] スプライト {idx}: キャンバスサイズ: {canvas_w} x {canvas_h}")
            
            print(f"[DEBUG] 画像描画開始")
            self.draw_image(qimg, axis_x, axis_y)
            if palette: 
                print(f"[DEBUG] パレットプレビュー更新")
                self.update_palette_preview(palette)
            print(f"[DEBUG] refresh_current_sprite完了")
        except Exception as e:
            print(f"[DEBUG] refresh_current_sprite エラー: {e}")
            import traceback; traceback.print_exc()
            # エラー時は空のキャンバスを表示
            self.show_empty_canvas()
            self.palette_list.setEnabled(False)
            self.palette_status_label.setText("パレット選択: 無効 (エラー)")
            self.palette_status_label.setStyleSheet("color: red; font-size: 10px;")
            self._safe_set_label_text(f'表示失敗: {e}')

    def _should_enable_palette_ui(self, sprite_idx):
        """スプライトに対してパレットUIを有効にするべきかを判定"""
        try:
            if not self.reader or sprite_idx < 0 or sprite_idx >= len(self.reader.sprites):
                return False
            
            sprite = self.reader.sprites[sprite_idx]
            
            if self.is_v2:
                # SFFv2の場合
                fmt = sprite.get('fmt', -1)
                
                # PNG形式（fmt=10）の場合、実際にRGBA形式かを確認
                if fmt == 10:
                    try:
                        # 安全なimportとdecode処理
                        rgba_check_result = self._check_png_rgba_format(sprite_idx)
                        if rgba_check_result == 'rgba':
                            print(f"[DEBUG] スプライト {sprite_idx}: PNG RGBA形式のためパレット無効")
                            return False
                        elif rgba_check_result == 'indexed':
                            print(f"[DEBUG] スプライト {sprite_idx}: PNG indexed but no palette - パレット有効")
                            return True
                    except Exception as e:
                        print(f"[DEBUG] スプライト {sprite_idx}: PNG判定エラー: {e}")
                        # エラー時はパレット有効として扱う
                        return True
                
                # 専用パレット（使用回数1回）の場合
                pal_idx = sprite.get('pal_idx', 0)
                if hasattr(self.reader, 'dedicated_palette_indices') and pal_idx in self.reader.dedicated_palette_indices:
                    print(f"[DEBUG] スプライト {sprite_idx}: 専用パレット {pal_idx} のためパレット選択無効")
                    return False
                
                # 通常のインデックス形式
                return True
            else:
                # SFFv1の場合は常にパレット有効
                return True
                
        except Exception as e:
            print(f"[DEBUG] パレットUI判定エラー: {e}")
            return True  # エラー時は有効として扱う

    def _check_png_rgba_format(self, sprite_idx):
        """PNG形式スプライトのRGBA/Indexed判定（安全版）"""
        try:
            # decode_sprite_v2の利用可能性チェック
            if decode_sprite_v2 is None:
                print(f"[DEBUG] decode_sprite_v2が利用できません")
                return 'indexed'  # 利用不可時はindexedとして扱う
            
            # デコード処理
            decoded_data, palette, w, h, mode = decode_sprite_v2(self.reader, sprite_idx)
            
            if mode == 'rgba':
                return 'rgba'
            elif mode == 'indexed':
                return 'indexed'
            else:
                print(f"[DEBUG] 未知のmode: {mode}")
                return 'indexed'  # 不明時はindexedとして扱う
                
        except Exception as e:
            print(f"[DEBUG] PNG形式チェックエラー: {e}")
            return 'indexed'  # エラー時はindexedとして扱う

    def _update_palette_ui_status(self, should_enable, sprite_idx):
        """パレットUIの状態を更新"""
        self.palette_list.setEnabled(should_enable)
        
        if not should_enable:
            # 無効化の理由を表示
            sprite = self.reader.sprites[sprite_idx] if self.reader and sprite_idx >= 0 else None
            if sprite:
                fmt = sprite.get('fmt', -1)
                pal_idx = sprite.get('pal_idx', 0)
                
                if self.is_v2 and fmt == 10:
                    png_format = self._check_png_rgba_format(sprite_idx)
                    if png_format == 'rgba':
                        reason = "RGBA画像 (パレット不要)"
                        self.palette_status_label.setText(f"パレット選択: 無効 ({reason})")
                        self.palette_status_label.setStyleSheet("color: blue; font-size: 10px;")
                        print(f"[DEBUG] スプライト {sprite_idx}: パレットUI無効化 - {reason}")
                        return
                
                if (hasattr(self.reader, 'dedicated_palette_indices') and 
                    pal_idx in self.reader.dedicated_palette_indices):
                    reason = f"専用パレット (Pal {pal_idx})"
                    self.palette_status_label.setText(f"パレット選択: 固定 ({reason})")
                    self.palette_status_label.setStyleSheet("color: orange; font-size: 10px;")
                    print(f"[DEBUG] スプライト {sprite_idx}: パレットUI固定表示 - {reason}")
                    return
            
            # その他の理由
            self.palette_status_label.setText("パレット選択: 無効")
            self.palette_status_label.setStyleSheet("color: red; font-size: 10px;")
        else:
            # 有効な場合
            self.palette_status_label.setText("パレット選択: 有効")
            self.palette_status_label.setStyleSheet("color: green; font-size: 10px;")
    
    def display_current_animation_frame(self):
        """現在のアニメーションフレームを表示"""
        if not self.animations or self.current_anim not in self.animations:
            # アニメ情報をクリア
            if hasattr(self, 'image_window') and self.image_window:
                self.image_window.clear_anim_info()
            return
        
        frames = self.animations[self.current_anim]
        if not frames or self.anim_index >= len(frames):
            return

        try:
            # ★前フレームの判定を完全クリア
            self.current_frame_data = None

            frame = frames[self.anim_index]
            
            # アニメ情報を更新
            if hasattr(self, 'image_window') and self.image_window:
                self.image_window.update_anim_info(
                    self.current_anim, 
                    self.anim_index, 
                    len(frames), 
                    frame
                )

            # LoopStart は表示用でないので空キャンバスだけ表示して終了
            if frame.get('loopstart', False):
                self.show_empty_canvas()
                return

            # ★このフレームの判定をセット（clsn がなければ空のまま）
            self.current_frame_data = frame
            clsn1_count = len([box for box in frame.get('clsn1', []) if box]) if frame.get('clsn1') else 0
            clsn2_count = len([box for box in frame.get('clsn2', []) if box]) if frame.get('clsn2') else 0

            sprite_idx = self.find_sprite_index(frame.get('group', 0), frame.get('image', 0))
            
            if sprite_idx is not None:
                print(f"[DEBUG] アニメーション - スプライト {sprite_idx} をレンダリング")
                
                # パレットUIの有効性を確認・更新
                should_enable_palette = self._should_enable_palette_ui(sprite_idx)
                self._update_palette_ui_status(should_enable_palette, sprite_idx)
                
                # パレット選択を考慮してレンダリング
                qimg, palette = self.render_sprite(sprite_idx)
                print(f"[DEBUG] アニメーション - レンダリング完了: 画像={qimg is not None}, パレット={palette is not None}")
                
                # 軸計算: 基準軸 + スプライト軸 + AIR軸
                axis_x, axis_y = self.calculate_display_axis(sprite_idx)
                
                # AIRのオフセットも追加
                air_x = frame.get('x', 0)
                air_y = frame.get('y', 0)
                axis_x += air_x
                axis_y += air_y
                
                print(f"[DEBUG] アニメーション - 表示軸: ({axis_x}, {axis_y}), AIRオフセット: ({air_x}, {air_y})")
                
                self.draw_image(qimg, axis_x, axis_y, frame_data=frame)
                if palette: 
                    self.update_palette_preview(palette)
                
                if self.config.debug_mode:
                    # 現在のフレームのスプライトサイズに基づいてキャンバスサイズを計算
                    sprite = self.reader.sprites[sprite_idx]
                    sprite_w = sprite.get('width', 0)
                    sprite_h = sprite.get('height', 0)
                    canvas_w = max(sprite_w * 3, 400)
                    canvas_h = max(sprite_h * 3, 300)
                    
                    print(f"[アニメ表示] フレーム {self.anim_index}: スプライト {sprite_idx}, AIR offset: ({air_x}, {air_y})")
                    print(f"[アニメ表示] キャンバスサイズ: {canvas_w} x {canvas_h}")
            else:
                print(f"[DEBUG] アニメーション - スプライトが見つかりません: group={frame.get('group', 0)}, image={frame.get('image', 0)}")
                # スプライトが見つからない場合は判定データをクリアして空のキャンバスを表示
                self.current_frame_data = None
                self.show_empty_canvas()
                # パレットUIを無効化
                self.palette_list.setEnabled(False)
                self.palette_status_label.setText("パレット選択: 無効 (スプライト見つからず)")
                self.palette_status_label.setStyleSheet("color: gray; font-size: 10px;")
            
        except Exception as e:
            print(f"[DEBUG] refresh_current_sprite エラー: {e}")
            import traceback
            traceback.print_exc()
            self._safe_set_label_text(f'アニメーション表示失敗: {e}')
            # エラー時は判定データをクリアして空のキャンバスを表示
            self.current_frame_data = None
            self.show_empty_canvas()
            # パレットUIを無効化
            self.palette_list.setEnabled(False)
            self.palette_status_label.setText("パレット選択: 無効 (エラー)")
            self.palette_status_label.setStyleSheet("color: gray; font-size: 10px;")
    
    def show_empty_canvas(self):
        """空のキャンバスを表示（適応サイズ版）"""
        print(f"[DEBUG] show_empty_canvas開始")
        
        try:
            # 適度なサイズの空キャンバスを作成
            base_canvas_w = 600  # 空の場合は中程度のサイズ
            base_canvas_h = 450
            
            # ベースキャンバスサイズの拡大処理
            if self.config.enable_canvas_scale_multiplier:
                canvas_w = int(base_canvas_w * self.config.canvas_scale_multiplier)
                canvas_h = int(base_canvas_h * self.config.canvas_scale_multiplier)
                print(f"[DEBUG] 空キャンバスサイズ決定: ベース{base_canvas_w}x{base_canvas_h} → {self.config.canvas_scale_multiplier}倍適用後{canvas_w}x{canvas_h}")
            else:
                canvas_w = base_canvas_w
                canvas_h = base_canvas_h
                print(f"[DEBUG] 空キャンバスサイズ決定: {canvas_w}x{canvas_h} (拡大なし)")
            
            if self.config.debug_mode:
                print(f"[空キャンバス] サイズ: {canvas_w}x{canvas_h}")
            
            canvas = QImage(canvas_w, canvas_h, QImage.Format_ARGB32)
            # チェッカーボードパターンの背景を作成
            checkerboard = self.renderer.create_checkerboard_pattern(canvas_w, canvas_h)
            
            # チェッカーボードパターンをキャンバスにコピー
            painter_bg = QPainter(canvas)
            painter_bg.drawImage(0, 0, checkerboard)
            painter_bg.end()
            
            print(f"[DEBUG] キャンバス作成完了（チェッカーボード背景）")
            
            # 既存のシーンを再利用（最適化）
            view = self.image_window.view
            scene = view.scene()  # 既存のシーンを取得
            
            # PixmapItemの更新または作成
            pixmap = QPixmap.fromImage(canvas)
            if self.image_window.current_pixmap_item is None:
                # 初回：新しいPixmapItemを作成し、原点(0,0)に配置
                self.image_window.current_pixmap_item = QGraphicsPixmapItem(pixmap)
                self.image_window.current_pixmap_item.setPos(0, 0)
                scene.addItem(self.image_window.current_pixmap_item)
                print(f"[DEBUG] 新しい空キャンバスPixmapItem作成・追加")
            else:
                # 2回目以降：既存のPixmapItemを更新
                self.image_window.current_pixmap_item.setPixmap(pixmap)
                self.image_window.current_pixmap_item.setPos(0, 0)
                print(f"[DEBUG] 空キャンバスPixmapItem更新")
            
            # シーンサイズを設定 - pixmapの実際のサイズに設定
            scene_rect = QtCore.QRectF(0, 0, pixmap.width(), pixmap.height())
            scene.setSceneRect(scene_rect)
            self.image_window.scene_initialized = True
            print(f"[DEBUG] 空キャンバスシーン更新完了: シーンサイズ({pixmap.width()}x{pixmap.height()})")
            
            # アニメーション中の状態保存処理
            is_anim = self.is_animating()
            if is_anim and self.image_window.current_pixmap_item is not None:
                t, hs, vs = self._capture_view_state()
                self._store_anim_view_state(t, hs, vs)
                print(f"[DEBUG] 空キャンバス - アニメーション中パン位置更新: h_scroll={hs}, v_scroll={vs}")
            
            # 表示状態の決定（最適化版：シーン差し替えなし）
            if is_anim:
                # アニメーション中は更新された状態を復元
                self._restore_anim_view_state()
                print(f"[DEBUG] アニメーション中 - 空キャンバス更新状態復元: h_scroll={self._anim_h_scroll}, v_scroll={self._anim_v_scroll}")
            elif not is_anim and (not hasattr(self, '_view_initialized') or not self._view_initialized):
                # 初回表示時：キャンバス中央に表示
                view.centerOn(canvas_w / 2, canvas_h / 2)
                print(f"[DEBUG] 初回表示 - 空キャンバス中央表示")
                self._view_initialized = True
            elif hasattr(self, 'saved_view_transform') and self.saved_view_transform is not None:
                # 通常時：保存された状態を復元
                view.setTransform(self.saved_view_transform)
                view.horizontalScrollBar().setValue(self.saved_h_scroll)
                view.verticalScrollBar().setValue(self.saved_v_scroll)
                print(f"[DEBUG] 空キャンバス - 保存状態復元: h_scroll={self.saved_h_scroll}, v_scroll={self.saved_v_scroll}")
            else:
                # フォールバック：キャンバス中央に表示
                view.centerOn(canvas_w / 2, canvas_h / 2)
                print(f"[DEBUG] 空キャンバス - フォールバック（中央配置）")
            
            print(f"[DEBUG] 空キャンバスビュー設定完了")
            
            if self.config.debug_mode:
                print(f"[空キャンバス表示] サイズ: {canvas_w}x{canvas_h}")
            
            print(f"[DEBUG] show_empty_canvas完了")
                
        except Exception as e:
            self._safe_set_label_text(f'空キャンバス表示失敗: {e}')
    
    def calculate_display_axis(self, sprite_idx: int) -> Tuple[int, int]:
        """表示軸を計算: スプライト軸 + AIR軸 (基準軸は使わない)"""
        # スプライト軸: 表示中のスプライトの x_axis, y_axis
        sprite_x = 0
        sprite_y = 0
        if hasattr(self.reader, 'sprites') and 0 <= sprite_idx < len(self.reader.sprites):
            s = self.reader.sprites[sprite_idx]
            # SFFv1では 'axisx'/'axisy'、SFFv2では 'x_axis'/'y_axis' を使用
            sprite_x = s.get('axisx', s.get('x_axis', 0)) or 0
            sprite_y = s.get('axisy', s.get('y_axis', 0)) or 0
        
        # AIR軸: アニメ中の軸位置 (x, y)
        air_x = 0
        air_y = 0
        if self.is_animating():
            frames = self.animations.get(self.current_anim, [])
            if frames and 0 <= self.anim_index < len(frames):
                frame = frames[self.anim_index]
                air_x = frame.get('x', 0)
                air_y = frame.get('y', 0)
        
        # 軸位置の合計（基準軸は除外）
        total_x = sprite_x + air_x
        total_y = sprite_y + air_y
        
        # 軸値の妥当性をチェック（画像サイズの2倍を超える場合は制限）
        if hasattr(self.reader, 'sprites') and 0 <= sprite_idx < len(self.reader.sprites):
            s = self.reader.sprites[sprite_idx]
            img_w = s.get('width', 0)
            img_h = s.get('height', 0)
            
            # 軸値が画像サイズの2倍を超える場合は制限
            max_axis_x = img_w * 2
            max_axis_y = img_h * 2
            
            if abs(total_x) > max_axis_x:
                if self.config.debug_mode:
                    print(f"[軸制限] X軸値 {total_x} が範囲外のため制限: ±{max_axis_x}")
                total_x = max_axis_x if total_x > 0 else -max_axis_x
            
            if abs(total_y) > max_axis_y:
                if self.config.debug_mode:
                    print(f"[軸制限] Y軸値 {total_y} が範囲外のため制限: ±{max_axis_y}")
                total_y = max_axis_y if total_y > 0 else -max_axis_y
        
        # デバッグ情報を出力
        if self.config.debug_mode:
            print(f"[軸計算デバッグ] sprite_idx: {sprite_idx}")
            print(f"[軸計算デバッグ] sprite_axis: ({sprite_x}, {sprite_y})")
            print(f"[軸計算デバッグ] air_axis: ({air_x}, {air_y})")
            print(f"[軸計算デバッグ] total_axis: ({total_x}, {total_y})")
        
        if hasattr(self.reader, 'sprites') and 0 <= sprite_idx < len(self.reader.sprites):
            s = self.reader.sprites[sprite_idx]
            if self.config.debug_mode:
                print(f"[軸計算デバッグ] 画像サイズ: {s.get('width', 0)} x {s.get('height', 0)}")
                print(f"[軸計算デバッグ] RAWデータ: axisx={s.get('axisx')}, axisy={s.get('axisy')}, x_axis={s.get('x_axis')}, y_axis={s.get('y_axis')}")
        
        return total_x, total_y
    
    def get_base_axis(self) -> Tuple[int, int]:
        """基準軸: グループ0,0の画像から算出 (X中央, Y底辺)"""
        if not self.reader or not hasattr(self.reader, 'sprites'):
            return 0, 0
        
        # グループ0,0のスプライトを探す
        for i, sprite in enumerate(self.reader.sprites):
            if sprite.get('group_no', 0) == 0 and sprite.get('sprite_no', 0) == 0:
                w = sprite.get('width', 0)
                h = sprite.get('height', 0)
                return w // 2, h  # X中央, Y底辺
        
        # 見つからない場合は最初のスプライトで代替
        if self.reader.sprites:
            sprite = self.reader.sprites[0]
            w = sprite.get('width', 0)
            h = sprite.get('height', 0)
            return w // 2, h
        
        return 0, 0
    
    def get_max_sprite_size(self) -> int:
        """最大スプライトサイズを取得（幅と高さの最大値）"""
        if not self.reader or not hasattr(self.reader, 'sprites'):
            return self.config.canvas_margin  # フォールバック
        
        max_size = 0
        for sprite in self.reader.sprites:
            w = sprite.get('width', 0)
            h = sprite.get('height', 0)
            max_size = max(max_size, w, h)
        
        return max_size if max_size > 0 else self.config.canvas_margin
    
    def get_average_sprite_size(self) -> Tuple[int, int]:
        """全スプライトの平均サイズを取得（幅と高さそれぞれの平均値）"""
        if not self.reader or not hasattr(self.reader, 'sprites') or not self.reader.sprites:
            return self.config.default_canvas_size  # フォールバック
        
        total_width = 0
        total_height = 0
        count = len(self.reader.sprites)
        
        for sprite in self.reader.sprites:
            w = sprite.get('width', 0)
            h = sprite.get('height', 0)
            total_width += w
            total_height += h
        
        # 平均値を計算し、マージンを追加
        avg_width = int(total_width / count) + self.config.canvas_margin * 2
        avg_height = int(total_height / count) + self.config.canvas_margin * 2
        
        # 最小サイズ制限を適用
        avg_width = max(avg_width, self.config.min_canvas_size[0])
        avg_height = max(avg_height, self.config.min_canvas_size[1])
        
        return avg_width, avg_height
    
    def get_animation_average_sprite_size(self, anim_no: int) -> Tuple[int, int]:
        """指定したアニメーションで使用されるスプライトの平均サイズを取得"""
        if not self.reader or not hasattr(self.reader, 'sprites') or not self.reader.sprites:
            return self.config.default_canvas_size
        
        if anim_no not in self.animations:
            return self.get_average_sprite_size()  # アニメーションが見つからない場合は全体平均
        
        frames = self.animations[anim_no]
        if not frames:
            return self.get_average_sprite_size()
        
        total_width = 0
        total_height = 0
        count = 0
        
        # アニメーションで使用されるスプライトのサイズを集計
        for frame in frames:
            group = frame.get('group', 0)
            image = frame.get('image', 0)
            sprite_idx = self.find_sprite_index(group, image)
            
            if sprite_idx is not None and 0 <= sprite_idx < len(self.reader.sprites):
                sprite = self.reader.sprites[sprite_idx]
                w = sprite.get('width', 0)
                h = sprite.get('height', 0)
                total_width += w
                total_height += h
                count += 1
        
        if count == 0:
            return self.get_average_sprite_size()  # スプライトが見つからない場合は全体平均
        
        # 平均値を計算し、マージンを追加
        avg_width = int(total_width / count) + self.config.canvas_margin * 2
        avg_height = int(total_height / count) + self.config.canvas_margin * 2
        
        # 最小サイズ制限を適用
        avg_width = max(avg_width, self.config.min_canvas_size[0])
        avg_height = max(avg_height, self.config.min_canvas_size[1])
        
        return avg_width, avg_height
    
    def get_all_frames_min_bounds(self) -> Tuple[int, int]:
        """全フレームの軸の最小値を取得（改良されたオフセット式用）"""
        if not self.reader or not hasattr(self.reader, 'sprites'):
            return 0, 0
        
        min_x = float('inf')
        min_y = float('inf')
        
        # 現在のアニメーションがある場合、そのフレーム群の範囲を計算
        if self.is_animating() and self.current_anim in self.animations:
            frames = self.animations[self.current_anim]
            for frame in frames:
                group = frame.get('group', 0)
                image = frame.get('image', 0)
                sprite_idx = self.find_sprite_index(group, image)
                
                if sprite_idx is not None and 0 <= sprite_idx < len(self.reader.sprites):
                    sprite = self.reader.sprites[sprite_idx]
                    sprite_axis_x = sprite.get('x_axis', 0) or 0
                    sprite_axis_y = sprite.get('y_axis', 0) or 0
                    air_x = frame.get('x', 0)
                    air_y = frame.get('y', 0)
                    
                    # 統合スケールを適用
                    combined_scale_x, combined_scale_y = self.calculate_combined_scale()
                    
                    total_x = int((sprite_axis_x + air_x) * combined_scale_x)
                    total_y = int((sprite_axis_y + air_y) * combined_scale_y)
                    
                    min_x = min(min_x, total_x)
                    min_y = min(min_y, total_y)
        else:
            # アニメーションがない場合は全スプライトの範囲を計算
            for sprite in self.reader.sprites:
                sprite_axis_x = sprite.get('x_axis', 0) or 0
                sprite_axis_y = sprite.get('y_axis', 0) or 0
                
                # 統合スケールを適用
                combined_scale_x, combined_scale_y = self.calculate_combined_scale()
                
                total_x = int(sprite_axis_x * combined_scale_x)
                total_y = int(sprite_axis_y * combined_scale_y)
                
                min_x = min(min_x, total_x)
                min_y = min(min_y, total_y)
        
        # 無限大の場合は0を返す
        if min_x == float('inf'):
            min_x = 0
        if min_y == float('inf'):
            min_y = 0
        
        return int(min_x), int(min_y)
    
    def is_animating(self) -> bool:
        """アニメーション中かどうか"""
        return (self.current_anim is not None and 
                self.timer.isActive() and 
                self.current_anim in self.animations)

    def _apply_flip_transform(self, qimg: QImage, flip_h: bool, flip_v: bool) -> QImage:
        """画像に反転変換を適用"""
        if not flip_h and not flip_v:
            return qimg
        
        # QTransformを使用して反転を適用
        transform = QTransform()
        
        if flip_h:
            transform.scale(-1, 1)  # 水平反転
        if flip_v:
            transform.scale(1, -1)  # 垂直反転
        
        # 変換を適用
        flipped_img = qimg.transformed(transform, QtCore.Qt.FastTransformation)
        
        print(f"[DEBUG] 反転処理完了: 元サイズ={qimg.width()}x{qimg.height()}, 変換後={flipped_img.width()}x{flipped_img.height()}")
        return flipped_img

    def _fill_checkerboard_background(self, canvas: QImage):
        """チェッカーボード背景でキャンバスを塗りつぶし"""
        painter = QPainter(canvas)
        
        # チェッカーボードのサイズ
        checker_size = 16
        
        # 明るい色と暗い色
        light_color = QColor(240, 240, 240)  # 薄いグレー
        dark_color = QColor(200, 200, 200)   # 濃いグレー
        
        # キャンバス全体をチェッカーボードで塗りつぶし
        for y in range(0, canvas.height(), checker_size):
            for x in range(0, canvas.width(), checker_size):
                # チェッカーボードパターンの計算
                checker_x = x // checker_size
                checker_y = y // checker_size
                is_light = (checker_x + checker_y) % 2 == 0
                
                # 色を選択
                color = light_color if is_light else dark_color
                painter.fillRect(x, y, checker_size, checker_size, color)
        
        painter.end()

    def _apply_blend_mode(self, canvas: QImage, sprite_img: QImage, blend_mode: str, alpha_value: float, pos_x: int, pos_y: int) -> QImage:
        """合成モードを適用して画像をキャンバスに合成"""
        if blend_mode == 'normal':
            # 通常合成（既存の処理）
            painter = QPainter(canvas)
            if alpha_value < 1.0:
                painter.setOpacity(alpha_value)
            painter.drawImage(pos_x, pos_y, sprite_img)
            painter.end()
            return canvas
        
        # 特殊合成モード用の処理
        result = QImage(canvas)
        painter = QPainter(result)
        
        if blend_mode == 'add':
            # 加算合成
            painter.setCompositionMode(QPainter.CompositionMode_Plus)
            if alpha_value < 1.0:
                painter.setOpacity(alpha_value)
            painter.drawImage(pos_x, pos_y, sprite_img)
        elif blend_mode == 'subtract':
            # 減算合成（近似）
            painter.setCompositionMode(QPainter.CompositionMode_Difference)
            painter.drawImage(pos_x, pos_y, sprite_img)
        
        painter.end()
        return result

    def render_sprite(self, index: int) -> Tuple[QImage, List[Tuple[int,int,int,int]]]:
        """スプライトレンダリング（新キャッシュシステム使用）"""
        pal_idx = self.palette_list.currentRow() if self.palette_list.currentRow() >= 0 else None
        
        # スプライト情報を取得
        if not self.reader or index < 0 or index >= len(self.reader.sprites):
            return QImage(), []
            
        sprite_info = self.reader.sprites[index]
        group = sprite_info.get('group_no', 0)
        image = sprite_info.get('sprite_no', 0)
        
        # キャッシュキーを決定 - RGBA形式の場合はパレットを無視
        cache_palette_key = pal_idx or 0
        if self.is_v2:
            fmt = sprite_info.get('fmt', -1)
            if fmt == 10:  # PNG形式の場合、RGBA判定してキーを調整
                try:
                    if decode_sprite_v2 is not None:
                        # 簡易チェック用に一度デコード（結果はキャッシュされる）
                        decoded_data, palette, w, h, mode = decode_sprite_v2(self.reader, index)
                        if mode == 'rgba':
                            cache_palette_key = -1  # RGBA形式の場合は固定キーを使用
                            if self.config.debug_mode:
                                print(f"[Cache] スプライト {index}: RGBA形式のためパレットキー無視")
                except Exception:
                    pass  # エラー時は通常のキーを使用
        
        # キャッシュから取得を試行
        cached_result = self.image_cache.get(group, image, cache_palette_key)
        if cached_result is not None:
            if self.config.debug_mode:
                print(f"[Cache HIT] Group:{group}, Image:{image}, Palette:{cache_palette_key}")
            return cached_result
        
        # キャッシュになければレンダリング
        if self.config.debug_mode:
            print(f"[Cache MISS] Group:{group}, Image:{image}, Palette:{cache_palette_key}")
            
        result = self.renderer.render_sprite(self.reader, index, pal_idx, self.is_v2, self.act_palettes)
        
        # キャッシュに保存
        self.image_cache.put(group, image, cache_palette_key, result)
        
        # ステータス更新
        if hasattr(self, 'status_bar_manager'):
            self.status_bar_manager.update_cache_status(self.image_cache.get_stats())
        
        return result

    def draw_image(self, qimg: Optional[QImage], axis_x: int = 0, axis_y: int = 0, frame_data: Optional[Dict] = None):
        """画像をキャンバスに描画（座標処理優先版）"""
        print(f"[DEBUG] draw_image開始 - 軸: ({axis_x}, {axis_y})")
        
        # 軸位置をインスタンス変数として保存（Clsn描画で使用）
        self.current_axis_x = axis_x
        self.current_axis_y = axis_y
        
        if self.config.debug_mode:
            print(f"[draw_image] 開始 - 軸: ({axis_x}, {axis_y})")
        
        if qimg is None: 
            print(f"[DEBUG] 画像がNullのため終了")
            return
        
        print(f"[DEBUG] 元画像サイズ: {qimg.width()}x{qimg.height()}")
        
        # ====== STEP 1: 反転・合成処理（スケーリング前に適用） ======
        
        # フレーム情報から反転・合成パラメータを取得
        flip_h = False
        flip_v = False
        blend_mode = 'normal'
        alpha_value = 1.0
        
        if frame_data:
            flip_h = frame_data.get('flip_h', False)
            flip_v = frame_data.get('flip_v', False)
            blend_mode = frame_data.get('blend_mode', 'normal')
            alpha_value = frame_data.get('alpha_value', 1.0)
            print(f"[DEBUG] フレーム反転・合成: H={flip_h}, V={flip_v}, blend={blend_mode}, alpha={alpha_value}")
        
        # 画像変換を適用
        base_img = qimg
        
        # 反転処理
        if flip_h or flip_v:
            print(f"[DEBUG] 反転処理適用: H={flip_h}, V={flip_v}")
            base_img = self._apply_flip_transform(base_img, flip_h, flip_v)
        
        # 透明度無効化処理（反転後に適用）
        if self.no_alpha:
            base_img = self.renderer.remove_alpha(base_img)
        
        # 統合スケールを計算
        combined_scale_x, combined_scale_y = self.calculate_combined_scale(debug=True)
        
        # ====== STEP 2: キャンバスサイズ決定（スケーリング前） ======
        
        # 全画像対応の基本キャンバスサイズを取得
        canvas_w, canvas_h = self.calculate_optimal_canvas_size()
        
        print(f"[DEBUG] 基本キャンバス: {canvas_w}x{canvas_h}")
        
        # 無スケール原点（キャンバス中心）
        origin_x = canvas_w / 2
        origin_y = canvas_h / 2
        
        # ====== STEP 3: 画像配置計算（スケーリング前） ======
        
        # 画像サイズ
        base_img_w, base_img_h = base_img.width(), base_img.height()
        
        # 画像の描画位置を計算（軸を考慮）
        # キャンバス中心から軸位置を差し引いて画像左上座標を決定
        draw_x = origin_x - axis_x
        draw_y = origin_y - axis_y
        
        # 画像がキャンバス外に出ないように調整
        draw_x = max(0, min(draw_x, canvas_w - base_img_w))
        draw_y = max(0, min(draw_y, canvas_h - base_img_h))
        
        print(f"[DEBUG] 画像配置: 位置({draw_x:.1f},{draw_y:.1f}), サイズ({base_img_w}x{base_img_h})")
        
        # ====== STEP 4: キャンバス作成と画像描画 ======
        
        # チェッカーボード背景のキャンバスを作成
        canvas = QImage(canvas_w, canvas_h, QImage.Format_ARGB32)
        self._fill_checkerboard_background(canvas)
        
        print(f"[DEBUG] キャンバス作成: {canvas_w}x{canvas_h} (チェッカーボード背景)")
        
        # QPainterで画像を描画
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing, True)
        print(f"[DEBUG] QPainter状態初期化完了")
        
        # 画像を描画
        painter.drawImage(int(draw_x), int(draw_y), base_img)
        print(f"[DEBUG] 画像描画: 位置({int(draw_x)},{int(draw_y)}), サイズ({base_img_w}x{base_img_h})")
        
        # Clsn描画（必要に応じて）
        if self.config.show_clsn and frame_data:
            print(f"[DEBUG] Clsn描画開始 - show_clsn={self.config.show_clsn}, frame_data存在={frame_data is not None}")
            if frame_data:
                clsn1_data = frame_data.get('clsn1', [])
                clsn2_data = frame_data.get('clsn2', [])
                print(f"[DEBUG] Clsn1データ: {len(clsn1_data)}個, Clsn2データ: {len(clsn2_data)}個")
                if clsn1_data:
                    print(f"[DEBUG] Clsn1詳細: {clsn1_data}")
                if clsn2_data:
                    print(f"[DEBUG] Clsn2詳細: {clsn2_data}")
            # Clsn描画処理（画像と同じ座標系で）
            # 画像軸位置を基準として、CLSNボックスを描画
            axis_screen_x = draw_x + axis_x  # 画像内の軸位置をスクリーン座標に変換
            axis_screen_y = draw_y + axis_y
            self._draw_clsn_boxes_qt(painter, axis_screen_x, axis_screen_y, draw_x, draw_y, 1.0, 1.0, frame_data)
        else:
            print(f"[DEBUG] Clsn描画スキップ - show_clsn={self.config.show_clsn}, frame_data存在={frame_data is not None}")
        
        painter.end()
        
        # ====== STEP 5: スケーリング適用 ======
        
        # 統合スケールを計算
        combined_scale_x, combined_scale_y = self.calculate_combined_scale(debug=True)
        
        # スケーリングが必要な場合のみ適用
        if abs(combined_scale_x - 1.0) > 0.01 or abs(combined_scale_y - 1.0) > 0.01:
            scaled_w = int(canvas_w * combined_scale_x)
            scaled_h = int(canvas_h * combined_scale_y)
            
            # 最大サイズ制限を適用
            max_w, max_h = 1600, 1200
            if scaled_w > max_w or scaled_h > max_h:
                scale_factor = min(max_w / scaled_w, max_h / scaled_h)
                scaled_w = int(scaled_w * scale_factor)
                scaled_h = int(scaled_h * scale_factor)
                print(f"[DEBUG] 出力サイズ制限適用: 最終サイズ({scaled_w}x{scaled_h})")
            
            canvas = canvas.scaled(scaled_w, scaled_h, Qt.KeepAspectRatio, Qt.FastTransformation)
            print(f"[DEBUG] 最終スケーリング適用: {canvas_w}x{canvas_h} → {scaled_w}x{scaled_h}")
        else:
            print(f"[DEBUG] スケーリングなし")
        
        print(f"[DEBUG] 描画処理完了")
        
        # ====== STEP 6: 画像表示更新 ======
        
        # QPixmapに変換して表示
        pixmap = QPixmap.fromImage(canvas)
        
        # 既存のPixmapItemがあれば更新、なければ新規作成
        if hasattr(self.image_window, 'current_pixmap_item') and self.image_window.current_pixmap_item:
            self.image_window.current_pixmap_item.setPixmap(pixmap)
            # PixmapItemを原点(0,0)に配置
            self.image_window.current_pixmap_item.setPos(0, 0)
            print(f"[DEBUG] 既存のPixmapItem更新 (スケール適用キャンバス: {canvas.width()}x{canvas.height()})")
        else:
            # 新規PixmapItemを作成し、原点(0,0)に配置
            self.image_window.current_pixmap_item = QGraphicsPixmapItem(pixmap)
            self.image_window.current_pixmap_item.setPos(0, 0)
            self.image_window.scene.addItem(self.image_window.current_pixmap_item)
            print(f"[DEBUG] 新規PixmapItem作成 (スケール適用キャンバス: {canvas.width()}x{canvas.height()})")
        
        # シーンの境界を更新 - pixmapの実際のサイズに設定
        scene_rect = QtCore.QRectF(0, 0, pixmap.width(), pixmap.height())
        self.image_window.scene.setSceneRect(scene_rect)
        print(f"[DEBUG] シーン更新完了: シーンサイズ({pixmap.width()}x{pixmap.height()})")
        
        # ビューの位置を復元
        if hasattr(self.image_window, 'restore_scroll_position'):
            self.image_window.restore_scroll_position()
            print(f"[DEBUG] 通常モード - 保存状態復元: h_scroll={getattr(self.image_window, '_saved_h_scroll', 'None')}, v_scroll={getattr(self.image_window, '_saved_v_scroll', 'None')}")
        
        # 画像の位置とスケーリング処理完了後のビュー中央配置
        # ファイル読み込み直後またはスケール変更時は必ず中央配置を実行
        should_center = (
            not getattr(self, '_view_centered_after_scaling', False) or  # 初回表示
            not getattr(self, 'initial_center_applied', False) or        # ファイル読み込み直後
            getattr(self, '_force_center_view', False)                    # 強制中央配置フラグ
        )
        
        if should_center:
            self._center_view_on_image()
            self._view_centered_after_scaling = True
            self.initial_center_applied = True
            self._force_center_view = False  # フラグをリセット
            print(f"[DEBUG] ビュー中央配置実行（ファイル読み込み後 or スケール変更）")
        else:
            print(f"[DEBUG] ビュー中央配置スキップ（すでに配置済み）")
        
        print(f"[DEBUG] draw_image完了")

    def _get_current_clsn_state(self) -> dict:
        """現在のClsn表示状態を取得"""
        return {
            'show_clsn': getattr(self.config, 'show_clsn', False),
            'clsn1_data': self.current_frame_data.get('clsn1', []) if hasattr(self, 'current_frame_data') and self.current_frame_data else [],
            'clsn2_data': self.current_frame_data.get('clsn2', []) if hasattr(self, 'current_frame_data') and self.current_frame_data else [],
        }

    def _draw_clsn_boxes_qt(self, painter, axis_screen_x, axis_screen_y, tx, ty, scx, scy, frame, margin_px=0):
        """判定ボックスを画像と同じ座標系で描画（Qt用）"""
        print(f"[DEBUG] _draw_clsn_boxes_qt開始 - axis_screen=({axis_screen_x}, {axis_screen_y}), scale=({scx}, {scy})")
        
        def rect_xyxy(x1, y1, x2, y2):
            # 判定ボックスは軸からの相対座標で定義されている
            # MUGENのCLSN座標系：
            # - X軸: 右向きがプラス（Qt同様）
            # - Y軸: 下向きがプラス（Qt同様）だが、座標値は軸を基準とした相対値
            p1_x = int(axis_screen_x + x1 * scx)
            p1_y = int(axis_screen_y + y1 * scy)  
            p2_x = int(axis_screen_x + x2 * scx)
            p2_y = int(axis_screen_y + y2 * scy)  
            
            print(f"[DEBUG] 座標変換: CLSN({x1},{y1},{x2},{y2}) -> 軸座標({axis_screen_x},{axis_screen_y}) -> スクリーン({p1_x},{p1_y},{p2_x},{p2_y})")
            
            x1_, y1_ = min(p1_x, p2_x), min(p1_y, p2_y)
            x2_, y2_ = max(p1_x, p2_x), max(p1_y, p2_y)
            return x1_, y1_, x2_, y2_

        # Clsn2=赤(攻撃), Clsn1=青(被弾) に統一
        clsn2_boxes = frame.get('clsn2', [])
        clsn1_boxes = frame.get('clsn1', [])
        
        print(f"[DEBUG] 描画対象: Clsn2={len(clsn2_boxes)}個, Clsn1={len(clsn1_boxes)}個")
        
        painter.setPen(QPen(QColor(*self.config.clsn2_color), self.config.clsn_line_width))
        for i, b in enumerate(clsn2_boxes):
            if b:  # 空でないボックスのみ描画
                x1, y1, x2, y2 = rect_xyxy(b['x1'], b['y1'], b['x2'], b['y2'])
                print(f"[DEBUG] Clsn2[{i}]描画: ({b['x1']}, {b['y1']}, {b['x2']}, {b['y2']}) -> ({x1}, {y1}, {x2}, {y2})")
                painter.drawRect(x1, y1, x2-x1, y2-y1)
            
        painter.setPen(QPen(QColor(*self.config.clsn1_color), self.config.clsn_line_width))
        for i, b in enumerate(clsn1_boxes):
            if b:  # 空でないボックスのみ描画
                x1, y1, x2, y2 = rect_xyxy(b['x1'], b['y1'], b['x2'], b['y2'])
                print(f"[DEBUG] Clsn1[{i}]描画: ({b['x1']}, {b['y1']}, {b['x2']}, {b['y2']}) -> ({x1}, {y1}, {x2}, {y2})")
                painter.drawRect(x1, y1, x2-x1, y2-y1)

    def _get_current_clsn_state(self) -> dict:
        """現在の判定表示状態を詳細に取得"""
        if not hasattr(self, 'current_frame_data') or not self.current_frame_data:
            return {}
        
        state = {}
        frame_data = self.current_frame_data
        
        # Clsn1の詳細状態
        clsn1_boxes = frame_data.get('clsn1', [])
        if clsn1_boxes:
            clsn1_state = []
            for i, box in enumerate(clsn1_boxes):
                if box:  # 有効なボックスのみ
                    box_state = {
                        'x1': box.get('x1', 0),
                        'y1': box.get('y1', 0), 
                        'x2': box.get('x2', 0),
                        'y2': box.get('y2', 0),
                        'has_default': box.get('has_default', False)
                    }
                    clsn1_state.append((i, box_state))
            if clsn1_state:
                state['clsn1'] = clsn1_state
        
        # Clsn2の詳細状態
        clsn2_boxes = frame_data.get('clsn2', [])
        if clsn2_boxes:
            clsn2_state = []
            for i, box in enumerate(clsn2_boxes):
                if box:  # 有効なボックスのみ
                    box_state = {
                        'x1': box.get('x1', 0),
                        'y1': box.get('y1', 0),
                        'x2': box.get('x2', 0), 
                        'y2': box.get('y2', 0),
                        'has_default': box.get('has_default', False)
                    }
                    clsn2_state.append((i, box_state))
            if clsn2_state:
                state['clsn2'] = clsn2_state
        
        return state

    def export_animation_gif(self):
        """GIFアニメーション出力（統一座標変換システム使用）"""
        if not PIL_AVAILABLE:
            self._safe_set_label_text('エラー: PIL/Pillowライブラリが必要です')
            return
        
        # 現在選択されているアニメーションを取得
        current_row = self.anim_list.currentRow()
        if current_row < 0 or current_row >= len(self._anim_no_list):
            self._safe_set_label_text('アニメーションが選択されていません')
            return
        
        anim_no = self._anim_no_list[current_row]
        if anim_no not in self.animations:
            self._safe_set_label_text('アニメーションデータが見つかりません')
            return
        
        # ファイル保存ダイアログ
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            f'アニメーション {anim_no} をGIFで保存',
            os.path.join(self.script_dir, f'animation_{anim_no}.gif'),
            'GIF files (*.gif)'
        )
        
        if not file_path:
            return
        
        self._safe_set_label_text('GIF出力中...')
        QApplication.processEvents()
        
        try:
            frames = self.animations[anim_no]
            if not frames:
                self._safe_set_label_text('アニメーションフレームが空です')
                return
            
            # ====== 1) 全フレームのBBOXを事前計算（判定も含む） ======
            min_left = min_top = 10**9
            max_right = max_bottom = -10**9
            
            prepared = []  # 各フレームの必要情報を先に集める
            for fr in frames:
                if fr.get('loopstart'):  # ループマーカーはスキップ
                    continue
                
                # スプライト画像を取得
                sprite_idx = self.find_sprite_index(fr.get('group', 0), fr.get('image', 0))
                if sprite_idx is None:
                    continue
                
                qimg, _ = self.render_sprite(sprite_idx)
                if qimg is None:
                    continue
                
                w, h = qimg.width(), qimg.height()
                
                # 軸とAIRのオフセット
                spr = self.reader.sprites[sprite_idx]
                # SFFv1では 'axisx'/'axisy'、SFFv2では 'x_axis'/'y_axis' を使用
                ax = spr.get('axisx', spr.get('x_axis', 0))
                ay = spr.get('axisy', spr.get('y_axis', 0))
                dx, dy = fr.get('x', 0), fr.get('y', 0)
                
                # 画像のBBOX
                left = -ax + dx
                top = -ay + dy
                right = left + w
                bottom = top + h
                
                # 判定ボックスも考慮（表示設定に関係なく全体のサイズを計算）
                for clsn_key in ['clsn1', 'clsn2']:
                    clsn_boxes = fr.get(clsn_key, [])
                    for box in clsn_boxes:
                        if box:
                            x1, y1 = box.get('x1', 0), box.get('y1', 0)
                            x2, y2 = box.get('x2', 0), box.get('y2', 0)
                            
                            # 判定ボックスの位置計算
                            clsn_left = min(x1, x2) + dx
                            clsn_top = min(y1, y2) + dy  
                            clsn_right = max(x1, x2) + dx
                            clsn_bottom = max(y1, y2) + dy
                            
                            left = min(left, clsn_left)
                            top = min(top, clsn_top)
                            right = max(right, clsn_right)
                            bottom = max(bottom, clsn_bottom)
                
                min_left = min(min_left, left)
                min_top = min(min_top, top)
                max_right = max(max_right, right)
                max_bottom = max(max_bottom, bottom)
                
                prepared.append((qimg, ax, ay, dx, dy, w, h, fr))
            
            if not prepared:
                self._safe_set_label_text('有効なフレームがありません')
                return
            
            margin = 20  # 余白サイズ
            canvas_w = int((max_right - min_left) + margin * 2)
            canvas_h = int((max_bottom - min_top) + margin * 2)
            
            origin_x = -min_left + margin
            origin_y = -min_top + margin
            
            print(f"[GIF] キャンバスサイズ: {canvas_w}x{canvas_h}, 原点: ({origin_x}, {origin_y})")
            
            # ====== 2) 各フレーム画像を同じ原点で作る ======
            pil_frames = []
            durations = []
            for qimg, ax, ay, dx, dy, w, h, fr in prepared:
                flip_h = fr.get('flip_h', False)
                flip_v = fr.get('flip_v', False)
                blend_mode = fr.get('blend_mode', 'normal')
                alpha_value = fr.get('alpha_value', 1.0)
                print(f"[GIF] フレーム処理: 軸({ax},{ay}), オフセット({dx},{dy}), サイズ({w},{h})")
                print(f"[GIF] 反転・合成: H={flip_h}, V={flip_v}, blend={blend_mode}, alpha={alpha_value}")
                
                # キャンバス作成
                base = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
                
                # QImage -> PIL変換
                qimg_rgba = qimg.convertToFormat(QImage.Format_RGBA8888)
                ptr = qimg_rgba.constBits()
                ptr.setsize(qimg_rgba.byteCount())
                
                # バイト配列を正しく取得
                img_bytes = bytearray()
                bytes_per_line = qimg_rgba.bytesPerLine()
                for y in range(h):
                    line_start = y * bytes_per_line
                    line_end = line_start + w * 4
                    img_bytes.extend(ptr[line_start:line_end])
                
                pil = Image.frombytes('RGBA', (w, h), bytes(img_bytes))
                
                # 反転・合成処理を適用
                flip_h = fr.get('flip_h', False)
                flip_v = fr.get('flip_v', False)
                blend_mode = fr.get('blend_mode', 'normal')
                alpha_value = fr.get('alpha_value', 1.0)
                
                # 反転処理
                if flip_h:
                    pil = pil.transpose(Image.FLIP_LEFT_RIGHT)
                    print(f"[GIF] 水平反転適用")
                if flip_v:
                    pil = pil.transpose(Image.FLIP_TOP_BOTTOM)
                    print(f"[GIF] 垂直反転適用")
                
                # 透明度処理
                if alpha_value < 1.0:
                    alpha_channel = pil.split()[-1]  # アルファチャンネル取得
                    alpha_channel = alpha_channel.point(lambda x: int(x * alpha_value))  # 透明度調整
                    pil.putalpha(alpha_channel)
                    print(f"[GIF] 透明度調整: {alpha_value}")
                
                # 画像配置位置の計算（通常時と同じロジック）
                effective_axis_x = ax + dx
                effective_axis_y = ay + dy
                img_x = origin_x - effective_axis_x
                img_y = origin_y - effective_axis_y
                
                print(f"[GIF] PIL配置: 原点({origin_x},{origin_y}), 軸({ax},{ay}), オフセット({dx},{dy}) → 配置位置({img_x},{img_y})")
                
                # 配置位置をキャンバス内に制限
                img_x = max(0, min(canvas_w - w, img_x))
                img_y = max(0, min(canvas_h - h, img_y))
                
                # 合成モードを考慮した配置
                if blend_mode == 'normal':
                    base.paste(pil, (img_x, img_y), pil)
                elif blend_mode == 'add':
                    # 加算合成（PIL）
                    temp = Image.new('RGBA', base.size, (0, 0, 0, 0))
                    temp.paste(pil, (img_x, img_y), pil)
                    base = Image.alpha_composite(base, temp)
                    print(f"[GIF] 加算合成適用")
                elif blend_mode == 'subtract':
                    # 減算合成（近似処理）
                    temp = Image.new('RGBA', base.size, (0, 0, 0, 0))
                    temp.paste(pil, (img_x, img_y), pil)
                    # 簡易減算として、元画像から新画像を引く（PIL制限による近似）
                    base = Image.alpha_composite(base, temp)
                    print(f"[GIF] 減算合成適用（近似）")
                else:
                    base.paste(pil, (img_x, img_y), pil)
                
                # 判定合成（config設定に基づく）
                show_clsn1 = self.config.show_clsn
                show_clsn2 = self.config.show_clsn
                
                print(f"[GIF] 判定表示設定: show_clsn={self.config.show_clsn}")
                
                # 判定データの存在確認
                has_clsn1 = fr.get('clsn1') and any(box for box in fr.get('clsn1', []) if box)
                has_clsn2 = fr.get('clsn2') and any(box for box in fr.get('clsn2', []) if box)
                print(f"[GIF] 判定データ存在: Clsn1={has_clsn1}, Clsn2={has_clsn2}")
                
                if self.config.show_clsn and (has_clsn1 or has_clsn2):
                    print(f"[GIF] 判定描画実行")
                    self._draw_clsn_on_pil(base, origin_x, origin_y, ax, ay, dx, dy, fr, show_clsn1, show_clsn2)
                else:
                    print(f"[GIF] 判定描画スキップ")
                
                pil_frames.append(base)
                durations.append(max(1, int(fr.get('duration', 1))) * (1000 // 60))  # ms
            
            # ====== 3) GIF保存 ======
            print(f"[GIF] フレーム数: {len(pil_frames)}")
            
            # デバッグ用：最初のフレームの内容確認
            if pil_frames:
                first_frame = pil_frames[0]
                print(f"[GIF] 最初のフレーム: サイズ{first_frame.size}, モード{first_frame.mode}")
                
                # フレームに画像データがあるかチェック
                bbox = first_frame.getbbox()
                if bbox:
                    print(f"[GIF] 画像データ範囲: {bbox}")
                else:
                    print(f"[GIF] 警告: 最初のフレームが空です")
            
            # RGBAからPモードに変換（透明度保持）
            converted_frames = []
            for i, frame in enumerate(pil_frames):
                if frame.mode == 'RGBA':
                    # 透明度を保持してパレット化（改良版）
                    try:
                        # アルファチャンネルを分離
                        r, g, b, a = frame.split()
                        
                        # 完全に透明でない部分のマスク作成
                        alpha_threshold = 128  # 透明度の閾値
                        mask = a.point(lambda x: 255 if x >= alpha_threshold else 0)
                        
                        # 背景を透明色に設定（RGB 0,0,0 を透明色として使用）
                        transparent_color = (0, 0, 0)
                        rgb_frame = Image.new('RGB', frame.size, transparent_color)
                        
                        # 不透明部分のみ元の色を配置
                        rgb_data = frame.convert('RGB')
                        rgb_frame.paste(rgb_data, mask=mask)
                        
                        # パレット化
                        palette_frame = rgb_frame.quantize(colors=255)
                        
                        # 透明色（黒）のインデックスを取得
                        # 黒に最も近い色を透明色とする
                        palette_data = palette_frame.getpalette()
                        if palette_data:
                            # パレットから黒に最も近い色のインデックスを検索
                            min_distance = float('inf')
                            transparent_index = 0
                            
                            for idx in range(min(256, len(palette_data) // 3)):
                                r_pal = palette_data[idx * 3]
                                g_pal = palette_data[idx * 3 + 1] 
                                b_pal = palette_data[idx * 3 + 2]
                                distance = r_pal + g_pal + b_pal  # 黒(0,0,0)からの距離
                                if distance < min_distance:
                                    min_distance = distance
                                    transparent_index = idx
                            
                            # 透明色のインデックスを設定
                            palette_frame.info['transparency'] = transparent_index
                            print(f"[GIF] フレーム{i+1}: 透明色インデックス={transparent_index}")
                        
                        converted_frames.append(palette_frame)
                        
                    except Exception as e:
                        print(f"[GIF] フレーム{i+1} 透明度処理失敗、フォールバック: {e}")
                        # フォールバック：RGBで保存
                        rgb_frame = frame.convert('RGB')
                        palette_frame = rgb_frame.quantize(colors=256)
                        converted_frames.append(palette_frame)
                else:
                    # 非RGBA画像の処理
                    converted_frame = frame.convert('P')
                    converted_frames.append(converted_frame)
                
                print(f"[GIF] フレーム{i+1}変換完了: {converted_frames[-1].mode}")
            
            
            # GIF保存（透明度有効）
            if converted_frames:
                try:
                    # 保存オプション設定
                    save_kwargs = {
                        'save_all': True,
                        'append_images': converted_frames[1:] if len(converted_frames) > 1 else [],
                        'duration': durations,
                        'loop': 0,
                        'disposal': 2,
                        'optimize': False  # パレット問題を避けるためoptimize無効
                    }
                    
                    # 透明度設定：全フレームに適用
                    for frame in converted_frames:
                        if hasattr(frame, 'info') and 'transparency' in frame.info:
                            save_kwargs['transparency'] = frame.info['transparency']
                            print(f"[GIF] 透明度設定適用: {frame.info['transparency']}")
                            break  # 最初に見つかった透明度設定を使用
                    
                    # 静止画（1フレーム）の場合の特別処理
                    if len(converted_frames) == 1:
                        first_frame = converted_frames[0]
                        
                        # 透明度が設定されていない場合、手動で黒を透明色に設定
                        if 'transparency' not in save_kwargs:
                            # 黒色のインデックスを探す
                            palette_data = first_frame.getpalette()
                            if palette_data:
                                for idx in range(min(256, len(palette_data) // 3)):
                                    r_pal = palette_data[idx * 3]
                                    g_pal = palette_data[idx * 3 + 1] 
                                    b_pal = palette_data[idx * 3 + 2]
                                    if r_pal + g_pal + b_pal == 0:  # 黒色
                                        save_kwargs['transparency'] = idx
                                        first_frame.info['transparency'] = idx
                                        print(f"[GIF] 静止画透明度手動設定: インデックス{idx}")
                                        break
                        
                        # 静止画の場合はappend_imagesを空にする
                        save_kwargs['append_images'] = []
                        save_kwargs['save_all'] = False
                    
                    first_frame = converted_frames[0]
                    first_frame.save(file_path, **save_kwargs)
                    
                    self._safe_set_label_text(f'GIF出力完了: {file_path}')
                    print(f"[GIF出力完了] {len(converted_frames)}フレーム, 透明度{'有' if 'transparency' in save_kwargs else '無'}, {file_path}")
                    
                except Exception as save_error:
                    print(f"[GIF] 保存エラー、フォールバック実行: {save_error}")
                    # フォールバック：より単純な透明度処理
                    try:
                        fallback_frames = []
                        for i, original_frame in enumerate(pil_frames):
                            if original_frame.mode == 'RGBA':
                                # シンプルな透明度処理：完全透明を黒で置換
                                r, g, b, a = original_frame.split()
                                rgb_data = Image.merge('RGB', (r, g, b))
                                
                                # 背景を黒で埋める
                                background = Image.new('RGB', rgb_data.size, (0, 0, 0))
                                
                                # アルファマスクで合成
                                mask = a.point(lambda x: x if x > 128 else 0)
                                result = Image.composite(rgb_data, background, mask)
                                
                                # パレット化
                                palette_frame = result.quantize(colors=256)
                                
                                # 黒を透明色に設定
                                palette_data = palette_frame.getpalette()
                                if palette_data:
                                    # 黒に最も近い色を探す
                                    for idx in range(min(256, len(palette_data) // 3)):
                                        r_pal = palette_data[idx * 3]
                                        g_pal = palette_data[idx * 3 + 1] 
                                        b_pal = palette_data[idx * 3 + 2]
                                        if r_pal + g_pal + b_pal <= 10:  # ほぼ黒色
                                            palette_frame.info['transparency'] = idx
                                            print(f"[GIF] フォールバック透明色: インデックス{idx}")
                                            break
                                
                                fallback_frames.append(palette_frame)
                            else:
                                fallback_frames.append(original_frame.convert('P'))
                        
                        # フォールバック保存
                        if fallback_frames:
                            save_kwargs = {
                                'save_all': len(fallback_frames) > 1,
                                'append_images': fallback_frames[1:] if len(fallback_frames) > 1 else [],
                                'duration': durations,
                                'loop': 0,
                                'optimize': False
                            }
                            
                            # 透明度設定
                            first_fallback = fallback_frames[0]
                            if hasattr(first_fallback, 'info') and 'transparency' in first_fallback.info:
                                save_kwargs['transparency'] = first_fallback.info['transparency']
                            
                            first_fallback.save(file_path, **save_kwargs)
                            
                            self._safe_set_label_text(f'GIF出力完了(フォールバック): {file_path}')
                            print(f"[GIF出力完了] フォールバック成功: {len(fallback_frames)}フレーム, {file_path}")
                        else:
                            raise ValueError("フォールバックフレーム生成に失敗")
                            
                    except Exception as fallback_error:
                        print(f"[GIF] フォールバック失敗、RGB出力: {fallback_error}")
                        # 最終フォールバック：RGB出力（透明度なし）
                        rgb_frames = []
                        for frame in pil_frames:
                            rgb_frame = Image.new('RGB', frame.size, (0, 0, 0))
                            if frame.mode == 'RGBA':
                                rgb_frame.paste(frame.convert('RGB'), mask=frame.split()[-1])
                            else:
                                rgb_frame = frame.convert('RGB')
                            rgb_frames.append(rgb_frame)
                        
                        rgb_frames[0].save(file_path,
                            save_all=len(rgb_frames) > 1,
                            append_images=rgb_frames[1:] if len(rgb_frames) > 1 else [],
                            duration=durations,
                            loop=0,
                            optimize=False)
                        
                        self._safe_set_label_text(f'GIF出力完了(透明度なし): {file_path}')
                        print(f"[GIF出力完了] RGB出力: {len(rgb_frames)}フレーム, {file_path}")
            else:
                self._safe_set_label_text('GIF出力エラー: フレームの変換に失敗しました')
                print(f"[GIF出力エラー] フレームの変換に失敗")
            
        except Exception as e:
            self._safe_set_label_text(f'GIF出力エラー: {str(e)}')
            print(f"[GIF出力エラー] {e}")
            import traceback
            traceback.print_exc()

    def _draw_clsn_on_pil(self, base_img, origin_x, origin_y, ax, ay, dx, dy, frame, show_clsn1=True, show_clsn2=True):
        """判定の描画（GIF用）- 通常時と同じ座標計算"""
        from PIL import ImageDraw
        draw = ImageDraw.Draw(base_img, "RGBA")
        
        print(f"[GIF判定] 描画開始: 原点({origin_x},{origin_y}), 軸({ax},{ay}), オフセット({dx},{dy})")
        
        # 画像の描画開始位置を計算（通常時のbase_px, base_pyと同じロジック）
        effective_axis_x = ax + dx
        effective_axis_y = ay + dy
        img_x = origin_x - effective_axis_x
        img_y = origin_y - effective_axis_y
        
        print(f"[GIF判定] 画像描画開始位置: ({img_x},{img_y})")
        
        # Clsn1（防御/赤）
        if show_clsn1:
            clsn1_boxes = frame.get('clsn1', [])
            valid_boxes = [box for box in clsn1_boxes if box]
            print(f"[GIF判定] Clsn1: {len(valid_boxes)}個のボックス")
            for i, box in enumerate(clsn1_boxes):
                if box:
                    x1, y1 = box.get('x1', 0), box.get('y1', 0)
                    x2, y2 = box.get('x2', 0), box.get('y2', 0)
                    
                    # 通常時と同じ座標計算: Clsn座標をスプライト画像内座標に変換
                    sprite_x1 = x1 + ax
                    sprite_y1 = y1 + ay
                    sprite_x2 = x2 + ax
                    sprite_y2 = y2 + ay
                    
                    # 最終スクリーン座標
                    final_x1 = img_x + sprite_x1
                    final_y1 = img_y + sprite_y1
                    final_x2 = img_x + sprite_x2
                    final_y2 = img_y + sprite_y2
                    
                    # 左上/右下に正規化
                    left = min(final_x1, final_x2)
                    top = min(final_y1, final_y2)
                    right = max(final_x1, final_x2)
                    bottom = max(final_y1, final_y2)
                    
                    print(f"[DEBUG] GIF用Clsn1[{i}]: 元座標({x1},{y1},{x2},{y2}) → スプライト座標({sprite_x1},{sprite_y1},{sprite_x2},{sprite_y2}) → 描画座標({left},{top},{right},{bottom})")
                    draw.rectangle([left, top, right, bottom], outline=(255, 0, 0, 255), width=2)
            
        # Clsn2（攻撃/青）
        if show_clsn2:
            clsn2_boxes = frame.get('clsn2', [])
            valid_boxes = [box for box in clsn2_boxes if box]
            print(f"[GIF判定] Clsn2: {len(valid_boxes)}個のボックス")
            for i, box in enumerate(clsn2_boxes):
                if box:
                    x1, y1 = box.get('x1', 0), box.get('y1', 0)
                    x2, y2 = box.get('x2', 0), box.get('y2', 0)
                    
                    # 通常時と同じ座標計算: Clsn座標をスプライト画像内座標に変換
                    sprite_x1 = x1 + ax
                    sprite_y1 = y1 + ay
                    sprite_x2 = x2 + ax
                    sprite_y2 = y2 + ay
                    
                    # 最終スクリーン座標
                    final_x1 = img_x + sprite_x1
                    final_y1 = img_y + sprite_y1
                    final_x2 = img_x + sprite_x2
                    final_y2 = img_y + sprite_y2
                    
                    # 左上/右下に正規化
                    left = min(final_x1, final_x2)
                    top = min(final_y1, final_y2)
                    right = max(final_x1, final_x2)
                    bottom = max(final_y1, final_y2)
                    
                    print(f"[DEBUG] GIF用Clsn2[{i}]: 元座標({x1},{y1},{x2},{y2}) → スプライト座標({sprite_x1},{sprite_y1},{sprite_x2},{sprite_y2}) → 描画座標({left},{top},{right},{bottom})")
                    draw.rectangle([left, top, right, bottom], outline=(0, 0, 255, 255), width=2)

        return base_img

    def _draw_clsn_boxes(self, painter: QPainter, img_x: int, img_y: int, scale_x: float, scale_y: float):
        """Clsn当たり判定ボックスを描画"""
        # 複数の条件で判定表示をスキップ
        if not self.config.show_clsn:
            print(f"[DEBUG] Clsn描画スキップ - show_clsn無効")
            return
        
        if not hasattr(self, 'current_frame_data') or not self.current_frame_data:
            print(f"[DEBUG] Clsn描画スキップ - フレームデータなし")
            return
        
        if not painter or not painter.isActive():
            print(f"[DEBUG] Clsn描画スキップ - Painter無効")
            return
            
        try:
            # Painterの判定描画用状態をリセット
            painter.setRenderHint(QPainter.Antialiasing, True)  # 判定ボックスはアンチエイリアシング有効
            painter.setBrush(QBrush())  # 塗りつぶしなし
            print(f"[DEBUG] QPainter状態初期化完了")
            
            frame_data = self.current_frame_data
            print(f"[DEBUG] Clsn描画開始 - フレームデータあり")
            
            # Clsn1 (防御判定) を描画
            clsn1_boxes = frame_data.get('clsn1', [])
            if clsn1_boxes and any(box for box in clsn1_boxes if box):  # 有効なボックスがある場合のみ
                print(f"[DEBUG] Clsn1描画: {len([box for box in clsn1_boxes if box])}個のボックス")
                painter.setBrush(QBrush())  # 塗りつぶしなし
                for i, box in enumerate(clsn1_boxes):
                    if box:  # 空のボックスをスキップ
                        has_default = box.get('has_default', False)
                        # Default値があるかどうかで色を変更
                        if has_default:
                            # Clsn1Default値がある場合は紫色
                            painter.setPen(QPen(QColor(*self.config.clsn1_default_color), self.config.clsn_line_width))
                        else:
                            # 通常の赤色
                            painter.setPen(QPen(QColor(*self.config.clsn1_color), self.config.clsn_line_width))
                        self._draw_clsn_box(painter, box, img_x, img_y, 1.0, 1.0)
            
            # Clsn2 (攻撃判定) を描画
            clsn2_boxes = frame_data.get('clsn2', [])
            if clsn2_boxes and any(box for box in clsn2_boxes if box):  # 有効なボックスがある場合のみ
                print(f"[DEBUG] Clsn2描画: {len([box for box in clsn2_boxes if box])}個のボックス")
                painter.setBrush(QBrush())  # 塗りつぶしなし
                for i, box in enumerate(clsn2_boxes):
                    if box:  # 空のボックスをスキップ
                        has_default = box.get('has_default', False)
                        # Default値があるかどうかで色を変更
                        if has_default:
                            # Clsn2Default値がある場合は緑色
                            painter.setPen(QPen(QColor(*self.config.clsn2_default_color), self.config.clsn_line_width))
                        else:
                            # 通常の青色
                            painter.setPen(QPen(QColor(*self.config.clsn2_color), self.config.clsn_line_width))
                        self._draw_clsn_box(painter, box, img_x, img_y, 1.0, 1.0)
            
            if not clsn1_boxes and not clsn2_boxes:
                print(f"[DEBUG] Clsn描画 - 判定ボックスなし")
                        
        except Exception as e:
            print(f"[DEBUG] Clsn描画内部エラー: {e}")

    def _draw_clsn_box(self, painter: QPainter, box: Dict[str, int], img_x: int, img_y: int, scale_x: float, scale_y: float):
        """個別のClsnボックスを描画（元座標系版）"""
        if not painter or not painter.isActive():
            return
            
        try:
            # Clsn座標はキャラクターの軸を原点とした座標系
            x1, y1 = box.get('x1', 0), box.get('y1', 0)
            x2, y2 = box.get('x2', 0), box.get('y2', 0)
            
            # 現在のスプライトの軸位置を取得（元座標系）
            axis_x = getattr(self, 'current_axis_x', 0)
            axis_y = getattr(self, 'current_axis_y', 0)
            
            # Clsn座標をスプライト画像内座標に変換（元座標系）
            # img_x, img_yは画像の描画開始位置（元座標系）
            sprite_x1 = x1 + axis_x
            sprite_y1 = y1 + axis_y
            sprite_x2 = x2 + axis_x
            sprite_y2 = y2 + axis_y
            
            # 最終スクリーン座標（スケールは後から適用されるため、ここでは1.0）
            final_x1 = img_x + sprite_x1
            final_y1 = img_y + sprite_y1
            final_x2 = img_x + sprite_x2
            final_y2 = img_y + sprite_y2
            
            # 矩形の幅と高さ
            width = final_x2 - final_x1
            height = final_y2 - final_y1
            
            # 矩形を描画（元座標系で描画、スケールは最後に適用される）
            painter.drawRect(final_x1, final_y1, width, height)
            
            if self.config.debug_mode:
                print(f"[DEBUG] Clsnボックス描画(元座標系): 軸({axis_x},{axis_y}) Clsn座標({x1},{y1},{x2},{y2}) → スプライト座標({sprite_x1},{sprite_y1},{sprite_x2},{sprite_y2}) → 最終座標({final_x1},{final_y1},{final_x2},{final_y2})")
            
        except Exception as e:
            print(f"[DEBUG] Clsnボックス描画エラー: {e}")

    def update_palette_preview(self, palette: List[Tuple[int,int,int,int]]):
        """パレットプレビューを更新"""
        prev = QImage(16, 16, QImage.Format_ARGB32)
        p = QPainter(prev)
        for i, (r, g, b, a) in enumerate(palette[:256]):
            p.fillRect(i % 16, i // 16, 1, 1, QColor(r, g, b, a))
        p.end()
        self.palette_preview.setPixmap(QPixmap.fromImage(prev.scaled(256, 256)))

    # ---------- animation ----------
    def step_animation(self):
        if not self.animations or self.current_anim not in self.animations: 
            return
        
        frames = self.animations[self.current_anim]
        if not frames: 
            return
        
        # 先にカウントダウン
        self.anim_ticks_left -= 1
        if self.anim_ticks_left > 0:
            return
        
        # 0になったので次フレームへ進める
        next_index = self.anim_index + 1
        
        # アニメーション終端チェック
        if next_index >= len(frames):
            # アニメーション終端に到達
            if hasattr(self, 'loop_target_index') and self.loop_target_index >= 0:
                # LoopStartが設定されている場合、その次のフレームに戻る
                self.anim_index = self.loop_target_index
                print(f"[DEBUG] アニメーション終端 - LoopStartの次のフレーム{self.loop_target_index}に戻る")
            else:
                # LoopStartがない場合は最初に戻る
                self.anim_index = 0
                print(f"[DEBUG] アニメーション終端 - 最初のフレームに戻る")
        else:
            # 通常の次フレーム
            self.anim_index = next_index
        
        # 進んだフレームの情報を取得
        frame = frames[self.anim_index]
        
        # LoopStartフレームの処理
        if frame.get('loopstart', False):
            if self.loop_start_time == 0.0:
                # 初回LoopStart到達 - 次のフレームからループを開始
                import time
                self.loop_start_time = time.time()
                print(f"[DEBUG] LoopStart到達 - 次のフレームからループ開始")
                
                # 次のフレームのインデックスを計算
                next_index = (self.anim_index + 1) % len(frames)
                if next_index < len(frames):
                    self.loop_target_index = next_index
                    print(f"[DEBUG] ループ対象フレーム: インデックス {next_index}")
                    # すぐに次のフレームに移動
                    self.anim_index = next_index
                    next_frame = frames[next_index]
                    self.anim_ticks_left = max(1, next_frame.get('duration', 1))
                else:
                    # フレームがない場合は最初に戻る
                    self.loop_target_index = 0
                    self.anim_index = 0
                    next_frame = frames[0]
                    self.anim_ticks_left = max(1, next_frame.get('duration', 1))
            else:
                # LoopStart中の処理（現在のフレームを5秒間継続）
                import time
                elapsed = time.time() - self.loop_start_time
                if elapsed >= self.max_loop_time:
                    # 5秒経過したのでループ終了、通常アニメーション継続
                    print(f"[DEBUG] LoopStart終了 - 通常アニメーション継続")
                    self.loop_start_time = 0.0
                    
                    # 次のフレームに進む
                    next_index = self.anim_index + 1
                    if next_index >= len(frames):
                        # アニメーション終端に到達
                        if hasattr(self, 'loop_target_index') and self.loop_target_index >= 0:
                            # LoopStartの次のフレームに戻る
                            self.anim_index = self.loop_target_index
                        else:
                            # 最初に戻る
                            self.anim_index = 0
                    else:
                        self.anim_index = next_index
                    
                    # 次のフレームのdurationを設定
                    next_frame = frames[self.anim_index]
                    self.anim_ticks_left = max(1, next_frame.get('duration', 1))
                else:
                    # LoopStartの次のフレームからのループを継続
                    if hasattr(self, 'loop_target_index'):
                        self.anim_index = self.loop_target_index
                        target_frame = frames[self.loop_target_index]
                        self.anim_ticks_left = max(1, target_frame.get('duration', 1))
                        print(f"[DEBUG] LoopStart継続中 - フレーム{self.loop_target_index}でループ")
                    else:
                        # フォールバック
                        self.anim_ticks_left = max(1, frame.get('duration', 1))
        else:
            # 通常のフレーム処理：このフレームのdurationを設定
            self.anim_ticks_left = max(1, frame.get('duration', 1))
        
        # ここで初めて描画更新（このフレームのdurationがこのフレームに適用される）
        self.refresh_current_sprite()

    def start_animation(self, anim_no: int):
        if anim_no not in self.animations: 
            return
        
        # アニメーション開始時にビューの状態を固定保存
        if hasattr(self, 'image_window') and self.image_window and self.image_window.view.scene():
            view = self.image_window.view
            self._anim_view_transform = view.transform()
            self._anim_h_scroll = view.horizontalScrollBar().value()
            self._anim_v_scroll = view.verticalScrollBar().value()
            print(f"[DEBUG] アニメーション開始 - ビュー状態固定保存: h_scroll={self._anim_h_scroll}, v_scroll={self._anim_v_scroll}")
        
        self.current_anim = anim_no
        self.anim_index = 0
        
        # 追加：最初のフレームのdurationを反映
        frames = self.animations[anim_no]
        if frames:
            first_frame = frames[0]
            self.anim_ticks_left = max(1, first_frame.get('duration', 1))
        else:
            self.anim_ticks_left = 1
        
        # LoopStartの検索とループ関連の初期化
        self.loop_start_index = -1
        self.loop_target_index = -1
        self.loop_count = 0
        self.loop_start_time = 0.0
        
        # LoopStartフレームを検索
        for i, frame in enumerate(frames):
            if frame.get('loopstart', False):
                self.loop_start_index = i
                # LoopStartの次のフレームをループ対象として設定
                next_index = (i + 1) % len(frames)
                self.loop_target_index = next_index
                print(f"[DEBUG] LoopStart検出: インデックス {i}, ループ対象: インデックス {next_index}")
                break
        
        # 最初のフレームを表示
        self.refresh_current_sprite()
        
        if not self.timer.isActive(): 
            self.timer.start()

    def find_sprite_index(self, group: int, image: int) -> Optional[int]:
        """グループ・画像番号からスプライトインデックスを検索"""
        if not self.reader or not hasattr(self.reader, 'sprites'):
            return None
        
        for i, sprite in enumerate(self.reader.sprites):
            sprite_group = sprite.get('group_no', 0)
            sprite_image = sprite.get('sprite_no', 0)
            if sprite_group == group and sprite_image == image:
                return i
        
        return None

    # ---------- key events & close ----------
    def keyPressEvent(self, e):
        """キーボードイベント処理"""
        if e.key() == Qt.Key_Escape:
            if hasattr(self, '_standalone_mode') and self._standalone_mode:
                QApplication.instance().quit()
            return
        if e.key() == Qt.Key_R:
            # ビューのパン位置をリセット
            if hasattr(self, 'image_window') and self.image_window:
                self.image_window.view.resetTransform()
            # ビュー初期化フラグをリセットして次回は中央配置を適用
            self._view_initialized = False
            # 画像を再描画して中心配置を適用
            self.refresh_current_sprite()
            return
        if e.key() == Qt.Key_Space:
            self.pause_animation()
            return
        
        # スケール変更ショートカット
        if e.key() == Qt.Key_Plus or e.key() == Qt.Key_Equal:
            # + キーで拡大
            self._change_scale(1)
            return
        if e.key() == Qt.Key_Minus:
            # - キーで縮小
            self._change_scale(-1)
            return
        if e.key() == Qt.Key_0:
            # 0 キーで100%に戻す
            self._set_scale_to_100()
            return
            
        super().keyPressEvent(e)

    def _change_scale(self, direction):
        """スケールを段階的に変更 (direction: 1=拡大, -1=縮小)"""
        if not hasattr(self, 'scale_combo') or self.chk_original.isChecked():
            return
        
        current_index = self.scale_combo.currentIndex()
        new_index = current_index + direction
        
        if 0 <= new_index < len(self.scale_values):
            self.scale_combo.setCurrentIndex(new_index)

    def _set_scale_to_100(self):
        """スケールを100%に設定"""
        if not hasattr(self, 'scale_combo') or self.chk_original.isChecked():
            return
        
        try:
            index_100 = self.scale_values.index(100)
            self.scale_combo.setCurrentIndex(index_100)
        except ValueError:
            # 100%が存在しない場合は最も近い値を選択
            closest_index = min(range(len(self.scale_values)), 
                               key=lambda i: abs(self.scale_values[i] - 100))
            self.scale_combo.setCurrentIndex(closest_index)

    def closeEvent(self, e):
        """ウィンドウ閉じるイベント"""
        if hasattr(self, '_standalone_mode') and self._standalone_mode:
            QApplication.instance().quit()
        super().closeEvent(e)

    def export_current_image(self):
        """現在の画像を出力（GIF出力と同じ処理）"""
        if not PIL_AVAILABLE:
            self._safe_set_label_text('エラー: PIL/Pillowライブラリが必要です')
            return
        
        # 現在選択されているスプライトを取得
        current_row = self.sprite_list.currentRow()
        if current_row < 0 or current_row >= len(self.reader.sprites):
            self._safe_set_label_text('エラー: スプライトが選択されていません')
            return
        
        sprite_idx = current_row
        
        # ファイル保存ダイアログ
        file_path, file_type = QFileDialog.getSaveFileName(
            self,
            '画像を保存',
            os.path.join(self.script_dir, f'sprite_{sprite_idx}'),
            'BMP files (*.bmp);;PNG files (*.png);;GIF files (*.gif)'
        )
        
        if not file_path:
            return
        
        self._safe_set_label_text('画像出力中...')
        QApplication.processEvents()
        
        try:
            # 生の画像データを取得（キャンバスエリア無視）
            qimg, _ = self.render_sprite_raw(sprite_idx)
            if qimg is None or qimg.isNull():
                self._safe_set_label_text('エラー: 画像の取得に失敗しました')
                return
            
            # QImageをPIL Imageに変換
            qimg_rgba = qimg.convertToFormat(QImage.Format_RGBA8888)
            w, h = qimg_rgba.width(), qimg_rgba.height()
            ptr = qimg_rgba.constBits()
            ptr.setsize(qimg_rgba.byteCount())
            
            img_bytes = bytearray()
            bytes_per_line = qimg_rgba.bytesPerLine()
            for y in range(h):
                line_start = y * bytes_per_line
                line_end = line_start + w * 4
                img_bytes.extend(ptr[line_start:line_end])
            
            pil_img = Image.frombytes('RGBA', (w, h), bytes(img_bytes))
            
            # 画像をトリミング（透明領域を削除）
            trimmed_img = self._trim_single_image(pil_img)
            print(f"[画像出力] 生データ取得→トリミング: {pil_img.size} → {trimmed_img.size}")
            
            # ファイル形式に応じて保存
            if 'BMP' in file_type:
                # BMPは透明度非対応なので背景をマゼンタにする
                background = Image.new('RGB', trimmed_img.size, (255, 0, 255))
                background.paste(trimmed_img, mask=trimmed_img.split()[3] if trimmed_img.mode == 'RGBA' else None)
                background.save(file_path, 'BMP')
            elif 'PNG' in file_type:
                # PNGは透明度保持
                trimmed_img.save(file_path, 'PNG')
            elif 'GIF' in file_type:
                # GIFは透明度保持
                if trimmed_img.mode == 'RGBA':
                    try:
                        # アルファチャンネルを分離
                        r, g, b, a = trimmed_img.split()
                        
                        # 完全に透明な部分にマゼンタ色(255,0,255)を設定（透明色として使用）
                        transparent_color = (255, 0, 255)  # マゼンタを透明色に
                        rgb_img = Image.new('RGB', trimmed_img.size, transparent_color)
                        
                        # アルファ値が0でない部分のみ元の色を使用
                        mask = a.point(lambda x: 255 if x > 0 else 0)
                        rgb_img.paste(trimmed_img.convert('RGB'), mask=mask)
                        
                        # パレット化（透明色を含む）
                        palette_img = rgb_img.quantize(colors=255)  # 255色（透明色用に1色残す）
                        
                        # パレットを調整
                        palette = palette_img.getpalette()
                        if palette:
                            if len(palette) < 768:
                                palette.extend([0] * (768 - len(palette)))
                            # 最後の色をマゼンタ（透明色）に設定
                            palette[765:768] = [255, 0, 255]
                            palette_img.putpalette(palette)
                        
                        # 透明部分をマゼンタ色に変換
                        pixels = list(palette_img.getdata())
                        rgb_pixels = list(rgb_img.getdata())
                        new_pixels = []
                        
                        for j, pixel in enumerate(pixels):
                            if rgb_pixels[j] == transparent_color:
                                new_pixels.append(255)  # マゼンタのインデックス
                            else:
                                new_pixels.append(pixel)
                        
                        palette_img.putdata(new_pixels)
                        palette_img.save(file_path, 'GIF', transparency=255)
                        
                    except Exception as e:
                        print(f"[GIF] 透明度処理失敗、フォールバック: {e}")
                        # フォールバック：RGBに変換
                        rgb_img = trimmed_img.convert('RGB')
                        rgb_img.save(file_path, 'GIF')
                else:
                    trimmed_img.save(file_path, 'GIF')
            
            self._safe_set_label_text(f'画像を保存しました: {file_path}')
            
        except Exception as e:
            self._safe_set_label_text(f'エラー: {str(e)}')
            print(f"[画像出力エラー] {e}")
            import traceback
            traceback.print_exc()

    def export_all_spritesheet(self):
        """SFF全体のスプライトシート出力"""
        if not PIL_AVAILABLE:
            self._safe_set_label_text('エラー: PIL/Pillowライブラリが必要です')
            return
        
        if not self.reader or not hasattr(self.reader, 'sprites'):
            self._safe_set_label_text('エラー: SFFファイルが読み込まれていません')
            return
        
        # ファイル保存ダイアログ
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            'SFF全体スプライトシートを保存',
            os.path.join(self.script_dir, 'sff_all_sprites.png'),
            'PNG files (*.png)'
        )
        
        if not file_path:
            return
        
        self._safe_set_label_text('SFF全体スプライトシート生成中...')
        QApplication.processEvents()
        
        try:
            sprites = self._get_all_sprites_sorted()
            
            if not sprites:
                self._safe_set_label_text('エラー: 出力するスプライトがありません')
                return
            
            spritesheet = self._create_single_spritesheet(sprites, max_columns=25, padding=3)
            
            if spritesheet:
                # キャンバスエリアを無視して画像部分のみを抽出
                if hasattr(spritesheet, 'extract_image_area'):
                    output_sheet = spritesheet.extract_image_area()
                    print(f"[全体スプライトシート] 画像エリアのみ抽出: {output_sheet.size}")
                else:
                    output_sheet = spritesheet
                
                # 不要な透過領域をトリミング
                trimmed_spritesheet = self._trim_transparent_areas(output_sheet)
                if trimmed_spritesheet:
                    output_sheet = trimmed_spritesheet
                    print(f"[全体スプライトシート] トリミング完了: {output_sheet.size}")
                
                output_sheet.save(file_path, 'PNG')
                # 統計情報を表示
                sprite_count = len(sprites)
                # Noneでないスプライト（有効な画像）の数をカウント
                valid_sprites = sum(1 for sprite in sprites if sprite is not None)
                invalid_sprites = sprite_count - valid_sprites
                self._safe_set_label_text(f'SFF全体スプライトシート保存完了: {file_path} (有効:{valid_sprites}個, 無効:{invalid_sprites}個)')
                print(f"[全体スプライトシート] 保存完了: {file_path}")
                print(f"[全体スプライトシート] 統計: 総スプライト{sprite_count}個, 有効画像{valid_sprites}個, 無効画像{invalid_sprites}個, サイズ{output_sheet.size}")
            else:
                self._safe_set_label_text('エラー: SFF全体スプライトシートの生成に失敗しました')
            
        except Exception as e:
            self._safe_set_label_text(f'エラー: {str(e)}')
            print(f"[全体スプライトシート] エラー: {e}")
            import traceback
            traceback.print_exc()

    def export_animation_spritesheet(self):
        """選択中のアニメーションのスプライトシート出力"""
        if not PIL_AVAILABLE:
            self._safe_set_label_text('エラー: PIL/Pillowライブラリが必要です')
            return
        
        if not self.reader or not hasattr(self.reader, 'sprites'):
            self._safe_set_label_text('エラー: SFFファイルが読み込まれていません')
            return
        
        selected_rows = self.anim_list.selectionModel().selectedRows()
        if not selected_rows:
            self._safe_set_label_text('エラー: アニメーションが選択されていません')
            return
        
        # _anim_no_list から実際のアニメーション番号を取得
        row_index = selected_rows[0].row()
        if row_index >= len(self._anim_no_list):
            self._safe_set_label_text('エラー: 選択されたアニメーションが無効です')
            return
        
        anim_no = self._anim_no_list[row_index]
        
        # ファイル保存ダイアログ
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            'アニメーションスプライトシートを保存',
            os.path.join(self.script_dir, f'animation_{anim_no}_spritesheet.png'),
            'PNG files (*.png)'
        )
        
        if not file_path:
            return
        
        self._safe_set_label_text(f'アニメーション {anim_no} スプライトシート生成中...')
        QApplication.processEvents()
        
        try:
            sprites = self._get_animation_sprites_sorted()
            
            if not sprites:
                self._safe_set_label_text('エラー: 選択中のアニメーションに出力するスプライトがありません')
                return
            
            spritesheet = self._create_single_spritesheet(sprites, max_columns=25, padding=3)
            
            if spritesheet:
                # キャンバスエリアを無視して画像部分のみを抽出
                if hasattr(spritesheet, 'extract_image_area'):
                    output_sheet = spritesheet.extract_image_area()
                    print(f"[アニメーションスプライトシート] 画像エリアのみ抽出: {output_sheet.size}")
                else:
                    output_sheet = spritesheet
                
                # 不要な透過領域をトリミング
                trimmed_spritesheet = self._trim_transparent_areas(output_sheet)
                if trimmed_spritesheet:
                    output_sheet = trimmed_spritesheet
                    print(f"[アニメーションスプライトシート] トリミング完了: {output_sheet.size}")
                
                output_sheet.save(file_path, 'PNG')
                # 統計情報を表示
                sprite_count = len(sprites)
                # Noneでないスプライト（有効な画像）の数をカウント
                valid_sprites = sum(1 for sprite in sprites if sprite is not None)
                invalid_sprites = sprite_count - valid_sprites
                self._safe_set_label_text(f'アニメーション {anim_no} スプライトシート保存完了: {file_path} (有効:{valid_sprites}個, 無効:{invalid_sprites}個)')
                print(f"[アニメーションスプライトシート] 保存完了: {file_path}")
                print(f"[アニメーションスプライトシート] 統計: 総スプライト{sprite_count}個, 有効画像{valid_sprites}個, 無効画像{invalid_sprites}個, サイズ{output_sheet.size}")
            else:
                self._safe_set_label_text('エラー: アニメーションスプライトシートの生成に失敗しました')
            
        except Exception as e:
            self._safe_set_label_text(f'エラー: {str(e)}')
            print(f"[アニメーションスプライトシート] エラー: {e}")
            import traceback
            traceback.print_exc()

    def _get_all_sprites_sorted(self):
        """全スプライトをグループ・番号順でソートして取得"""
        sprites = []
        for i, sprite in enumerate(self.reader.sprites):
            sprites.append((i, sprite))
        
        # グループ番号、スプライト番号でソート
        sprites.sort(key=lambda x: (x[1].get('group_no', 0), x[1].get('sprite_no', 0)))
        return sprites

    def _get_animation_sprites_sorted(self):
        """選択中のアニメーションで使用されるスプライトを取得"""
        selected_rows = self.anim_list.selectionModel().selectedRows()
        
        if not selected_rows:
            return []
        
        # _anim_no_list から実際のアニメーション番号を取得
        row_index = selected_rows[0].row()
        if row_index >= len(self._anim_no_list):
            return []
        
        anim_no = self._anim_no_list[row_index]
        
        if anim_no not in self.animations:
            return []
        
        # アニメーションで使用されるスプライトを収集
        frames = self.animations[anim_no]
        sprite_indices = set()
        
        for frame in frames:
            if frame.get('loopstart'):
                continue
            
            group = frame.get('group', 0)
            image = frame.get('image', 0)
            sprite_idx = self.find_sprite_index(group, image)
            
            if sprite_idx is not None:
                sprite_indices.add(sprite_idx)
        
        # インデックス順にソート
        sprites = []
        for idx in sorted(sprite_indices):
            sprites.append((idx, self.reader.sprites[idx]))
        
        return sprites

    def _create_single_spritesheet(self, sprites, max_columns=25, padding=3):
        """1枚の大きなスプライトシートを生成"""
        if not sprites:
            print("[1枚スプライトシート] エラー: スプライトリストが空")
            return None
        
        try:
            # 各スプライトの画像を取得
            sprite_images = []
            sprite_info = []  # (画像, グループ番号, スプライト番号, 正常フラグ) の情報
            max_width = 0
            max_height = 0
            normal_count = 0  # 正常レンダリング数
            placeholder_count = 0  # プレースホルダー数
            
            print(f"[1枚スプライトシート] 処理開始: {len(sprites)} スプライト")
            
            for sprite_idx, sprite in sprites:
                try:
                    qimg, _ = self.render_sprite_raw(sprite_idx)
                    if qimg is None or qimg.isNull():
                        print(f"[1枚スプライトシート] スキップ: スプライト {sprite_idx} (NULL画像)")
                        continue
                    
                    # プレースホルダーかどうかを判定（背景色で判定）
                    is_placeholder = False
                    sample_color = qimg.pixel(min(5, qimg.width()-1), min(5, qimg.height()-1))
                    red = (sample_color >> 16) & 0xFF
                    green = (sample_color >> 8) & 0xFF
                    blue = sample_color & 0xFF
                    
                    # 薄い赤色（255,100,100付近）ならプレースホルダーと判定
                    if red > 200 and green < 150 and blue < 150:
                        is_placeholder = True
                        placeholder_count += 1
                    else:
                        normal_count += 1
                    
                    # QImageをPIL Imageに変換
                    qimg_rgba = qimg.convertToFormat(QImage.Format_RGBA8888)
                    w, h = qimg_rgba.width(), qimg_rgba.height()
                    
                    if w <= 0 or h <= 0:
                        print(f"[1枚スプライトシート] スキップ: スプライト {sprite_idx} (サイズ無効: {w}x{h})")
                        continue
                    
                    ptr = qimg_rgba.constBits()
                    ptr.setsize(qimg_rgba.byteCount())
                    
                    img_bytes = bytearray()
                    bytes_per_line = qimg_rgba.bytesPerLine()
                    for y in range(h):
                        line_start = y * bytes_per_line
                        line_end = line_start + w * 4
                        if line_end <= len(ptr):
                            img_bytes.extend(ptr[line_start:line_end])
                        else:
                            # バイト不足の場合は残りを0で埋める
                            img_bytes.extend(ptr[line_start:])
                            img_bytes.extend([0] * (line_end - len(ptr)))
                    
                    # PIL Image作成
                    if len(img_bytes) == w * h * 4:
                        pil_img = Image.frombytes('RGBA', (w, h), bytes(img_bytes))
                    else:
                        # バイト数が合わない場合はスキップ
                        print(f"[1枚スプライトシート] スキップ: スプライト {sprite_idx} バイト数不整合 (期待:{w*h*4}, 実際:{len(img_bytes)})")
                        continue
                    
                    # プレースホルダー画像はスキップ
                    if is_placeholder:
                        print(f"[1枚スプライトシート] スキップ: スプライト {sprite_idx} プレースホルダー画像")
                        continue
                    
                    # 正常な画像のみトリミング処理
                    trimmed_original = self._trim_single_image(pil_img)
                    sprite_images.append(trimmed_original)
                    sprite_info.append((sprite.get('group_no', 0), sprite.get('sprite_no', 0), True))
                    print(f"[1枚スプライトシート] スプライト {sprite_idx}: SFFグループ({sprite.get('group_no', 0)},{sprite.get('sprite_no', 0)}) サイズ{pil_img.size} → {trimmed_original.size}")
                    
                    # トリミング後のサイズで最大値を更新
                    final_img = sprite_images[-1]
                    max_width = max(max_width, final_img.width)
                    max_height = max(max_height, final_img.height)
                    
                    if len(sprite_images) % 50 == 0:  # 50個ごとに進捗表示
                        progress = int(len(sprite_images) * 100 / len(sprites))
                        print(f"[1枚スプライトシート] 処理済み: {len(sprite_images)} / {len(sprites)} ({progress}%) [正常:{normal_count}, 代替:{placeholder_count}]")
                
                except Exception as e:
                    print(f"[1枚スプライトシート] スキップ: スプライト {sprite_idx} 処理エラー: {e}")
                    # エラーが発生した場合はスキップ（プレースホルダーを追加しない）
                    continue
            
            # 最終統計を表示
            processed_count = len(sprite_images)
            total_count = len(sprites)
            success_rate = int(normal_count * 100 / total_count) if total_count > 0 else 0
            print(f"[1枚スプライトシート] 処理完了: {processed_count}/{total_count}個 (正常画像:{normal_count}, プレースホルダー:{placeholder_count}, 成功率:{success_rate}%)")
            
            if not sprite_images:
                print("[1枚スプライトシート] 警告: 有効な画像が無いため、空のスプライトシートを作成")
                # 空の場合でも最低限のスプライトシートを作成
                empty_img = Image.new('RGBA', (100, 50), (0, 0, 0, 0))
                return empty_img
            
            print(f"[1枚スプライトシート] 有効画像数: {len(sprite_images)}, 最大サイズ: {max_width}x{max_height}")
            
            # SFFグループ別レイアウト：group_no ごとに改行
            # sprite_info から各画像のSFFグループ情報を取得
            num_sprites = len(sprite_images)
            
            # SFFグループ別に行を構成
            rows_data = []  # [(row_width, row_height, [images_in_row]), ...]
            current_row = []
            current_row_width = 0
            current_row_max_height = 0
            current_sff_group = None
            
            for i, img in enumerate(sprite_images):
                img_width = img.width + padding * 2
                img_height = img.height + padding * 2
                
                # 対応するスプライト情報からSFFグループ番号を取得
                sff_group_no = sprite_info[i][0] if i < len(sprite_info) else 0
                sff_sprite_no = sprite_info[i][1] if i < len(sprite_info) else 0
                
                # SFFグループが変わったら強制改行
                sff_group_changed = current_sff_group is not None and sff_group_no != current_sff_group
                
                # 新しい行が必要かチェック（SFFグループ変更または列数制限）
                if sff_group_changed or len(current_row) >= max_columns:
                    if current_row:  # 現在の行が空でない場合のみ確定
                        rows_data.append((current_row_width, current_row_max_height, current_row))
                        print(f"[1枚スプライトシート] SFFグループ{current_sff_group}: {len(current_row)}画像, 行サイズ{current_row_width}x{current_row_max_height}")
                    current_row = []
                    current_row_width = 0
                    current_row_max_height = 0
                
                # 現在の行に画像を追加
                current_row.append((img, img_width, img_height, sff_group_no, sff_sprite_no))
                current_row_width += img_width
                current_row_max_height = max(current_row_max_height, img_height)
                current_sff_group = sff_group_no
            
            # 最後の行を追加
            if current_row:
                rows_data.append((current_row_width, current_row_max_height, current_row))
                print(f"[1枚スプライトシート] SFFグループ{current_sff_group}: {len(current_row)}画像, 行サイズ{current_row_width}x{current_row_max_height}")
            
            # 全体サイズを計算
            total_width = max(row_width for row_width, _, _ in rows_data) if rows_data else 0
            total_height = sum(row_height for _, row_height, _ in rows_data)
            
            print(f"[1枚スプライトシート] SFFグループ別レイアウト: {len(rows_data)}行, 全体: {total_width}x{total_height}")
            print(f"[1枚スプライトシート] SFFのgroup_noごとに改行: パディング{padding}px")
            
            # キャンバスエリアを2倍にする
            canvas_width = total_width * 2
            canvas_height = total_height * 2
            
            # 画像エリアの開始位置（キャンバス中央に配置）
            offset_x = (canvas_width - total_width) // 2
            offset_y = (canvas_height - total_height) // 2
            
            print(f"[1枚スプライトシート] 画像エリアサイズ: {total_width}x{total_height}")
            print(f"[1枚スプライトシート] キャンバスサイズ: {canvas_width}x{canvas_height}")
            
            # スプライトシートを作成（マゼンタ背景）
            spritesheet = Image.new('RGBA', (canvas_width, canvas_height), (255, 0, 255, 255))
            
            # SFFグループ別可変セルで画像を配置
            current_y = offset_y
            sprite_count = 0
            
            for row_idx, (row_width, row_height, images_in_row) in enumerate(rows_data):
                current_x = offset_x
                row_sff_group = None
                
                for img_data in images_in_row:
                    if len(img_data) == 5:  # SFFグループ情報付き
                        img, img_cell_width, img_cell_height, sff_group_no, sff_sprite_no = img_data
                        row_sff_group = sff_group_no
                    elif len(img_data) == 4:  # 従来のグループ情報付き（後方互換）
                        img, img_cell_width, img_cell_height, group_no = img_data
                        row_sff_group = group_no
                        sff_sprite_no = "?"
                    else:  # 従来形式対応
                        img, img_cell_width, img_cell_height = img_data
                        row_sff_group = "?"
                        sff_sprite_no = "?"
                    
                    # セル内で中央寄せ
                    x = current_x + (img_cell_width - img.width) // 2
                    y = current_y + (row_height - img.height) // 2
                    
                    # アルファマスク付きで貼り付け
                    mask = img.split()[3] if img.mode == 'RGBA' else None
                    spritesheet.paste(img, (x, y), mask)
                    
                    current_x += img_cell_width
                    sprite_count += 1
                    
                    if sprite_count % 100 == 0:  # 100個ごとに進捗表示
                        progress = int(sprite_count * 100 / len(sprite_images))
                        print(f"[1枚スプライトシート] 配置済み: {sprite_count} / {len(sprite_images)} ({progress}%) - SFFグループ({row_sff_group},{sff_sprite_no}), セル{img.width}x{img.height}")
                
                print(f"[1枚スプライトシート] 行{row_idx+1}完了: SFFグループ{row_sff_group}, {len(images_in_row)}画像, Y位置{current_y}")
                current_y += row_height
            
            # 出力用に画像部分のみを抽出する関数を作成
            def extract_image_area():
                """キャンバスから画像部分のみを抽出"""
                return spritesheet.crop((offset_x, offset_y, offset_x + total_width, offset_y + total_height))

            # キャンバス情報をシートオブジェクトに付加
            spritesheet.image_area_bounds = (offset_x, offset_y, offset_x + total_width, offset_y + total_height)
            spritesheet.extract_image_area = extract_image_area
            
            print(f"[1枚スプライトシート] 生成完了: キャンバス{canvas_width}x{canvas_height}, 画像エリア{total_width}x{total_height} ({len(sprite_images)}個のスプライト)")
            return spritesheet
            
        except Exception as e:
            print(f"[1枚スプライトシート] エラー: {e}")
            import traceback
            traceback.print_exc()
            return None

    def export_all_animations_gif(self):
        """全アニメーションをGIFで個別出力"""
        if not PIL_AVAILABLE:
            self._safe_set_label_text('エラー: PIL/Pillowライブラリが必要です')
            return
        
        if not self.reader or not hasattr(self.reader, 'sprites'):
            self._safe_set_label_text('エラー: SFFファイルが読み込まれていません')
            return
        
        if not self.animations:
            self._safe_set_label_text('エラー: アニメーションが読み込まれていません')
            return
        
        # 出力フォルダ選択
        output_dir = QFileDialog.getExistingDirectory(
            self,
            'GIF出力フォルダを選択',
            self.script_dir
        )
        
        if not output_dir:
            return
        
        self._safe_set_label_text('アニメーションGIF出力中...')
        QApplication.processEvents()
        
        try:
            anim_numbers = list(self.animations.keys())
            total = len(anim_numbers)
            
            for i, anim_no in enumerate(anim_numbers):
                output_path = os.path.join(output_dir, f'animation_{anim_no}.gif')
                self._export_single_animation_gif(anim_no, output_path)
                
                # 進捗更新
                progress = int((i + 1) * 100 / total)
                self._safe_set_label_text(f'アニメーションGIF出力中... {progress}%')
                QApplication.processEvents()
            
            self._safe_set_label_text(f'全アニメーション出力完了: {output_dir}')
            
        except Exception as e:
            self._safe_set_label_text(f'エラー: {str(e)}')

    def _export_single_animation_gif(self, anim_no: int, output_path: str):
        """単一アニメーションのGIF出力（内部用）"""
        if anim_no not in self.animations:
            return
        
        try:
            frames = self.animations[anim_no]
            if not frames:
                return
            
            # 既存のexport_animation_gifロジックを使用
            # ただし、ファイルパスは指定されたものを使用
            pil_frames = []
            durations = []
            
            # フレーム処理（簡略版）
            for frame in frames:
                if frame.get('loopstart'):
                    continue
                
                sprite_idx = self.find_sprite_index(frame.get('group', 0), frame.get('image', 0))
                if sprite_idx is None:
                    continue
                
                qimg, _ = self.render_sprite(sprite_idx)
                if qimg is None:
                    continue
                
                # QImageをPIL Imageに変換
                qimg_rgba = qimg.convertToFormat(QImage.Format_RGBA8888)
                w, h = qimg_rgba.width(), qimg_rgba.height()
                ptr = qimg_rgba.constBits()
                ptr.setsize(qimg_rgba.byteCount())
                
                img_bytes = bytearray()
                bytes_per_line = qimg_rgba.bytesPerLine()
                for y in range(h):
                    line_start = y * bytes_per_line
                    line_end = line_start + w * 4
                    img_bytes.extend(ptr[line_start:line_end])
                
                pil_img = Image.frombytes('RGBA', (w, h), bytes(img_bytes))
                pil_frames.append(pil_img)
                durations.append(max(1, int(frame.get('duration', 1))) * (1000 // 60))
            
            # GIF保存
            if pil_frames:
                # RGBAからPモードに変換
                converted_frames = []
                for frame in pil_frames:
                    if frame.mode == 'RGBA':
                        rgb_frame = Image.new('RGB', frame.size, (0, 0, 0))
                        rgb_frame.paste(frame, mask=frame.split()[3])
                        palette_frame = rgb_frame.quantize(colors=256)
                        converted_frames.append(palette_frame)
                    else:
                        converted_frames.append(frame.convert('P'))
                
                if converted_frames:
                    first_frame = converted_frames[0]
                    first_frame.save(output_path,
                        save_all=len(converted_frames) > 1,
                        append_images=converted_frames[1:] if len(converted_frames) > 1 else [],
                        duration=durations,
                        loop=0,
                        optimize=False)
            
        except Exception as e:
            print(f"[単一GIF出力] エラー - アニメ{anim_no}: {e}")

    def _export_all_groups_spritesheet(self):
        """全グループを個別にスプライトシートで出力"""
        # 出力フォルダ選択
        output_dir = QFileDialog.getExistingDirectory(
            self,
            'スプライトシート出力フォルダを選択',
            os.path.expanduser('~')
        )
        
        if not output_dir:
            return
        
        try:
            # グループ別にスプライトを分類
            groups = {}
            for i, sprite in enumerate(self.reader.sprites):
                group = sprite.get('group_no', 0)
                if group not in groups:
                    groups[group] = []
                groups[group].append((i, sprite))
            
            print(f"[スプライトシート] 検出されたグループ: {sorted(groups.keys())}")
            
            # 各グループごとにスプライトシートを作成
            created_count = 0
            for group_no in sorted(groups.keys()):
                sprites = sorted(groups[group_no], key=lambda x: x[1].get('sprite_no', 0))
                
                if not sprites:
                    continue
                
                print(f"[スプライトシート] グループ {group_no}: {len(sprites)} スプライト")
                
                output_path = os.path.join(output_dir, f'group_{group_no}.png')
                spritesheet = self._create_grid_spritesheet(sprites, max_columns=20, padding=3, max_width=4096)
                
                if spritesheet:
                    # キャンバスエリアを無視して画像部分のみを抽出
                    if hasattr(spritesheet, 'extract_image_area'):
                        output_sheet = spritesheet.extract_image_area()
                        print(f"[スプライトシート] グループ {group_no} 画像エリアのみ抽出: {output_sheet.size}")
                    else:
                        output_sheet = spritesheet
                    
                    # 不要な透過領域をトリミング
                    trimmed_spritesheet = self._trim_transparent_areas(output_sheet)
                    if trimmed_spritesheet:
                        output_sheet = trimmed_spritesheet
                        print(f"[スプライトシート] グループ {group_no} トリミング完了: {output_sheet.size}")
                    
                    output_sheet.save(output_path, 'PNG')
                    created_count += 1
                    print(f"[スプライトシート] 保存完了: {output_path}")
                else:
                    print(f"[スプライトシート] 生成失敗: グループ {group_no}")
            
            if created_count > 0:
                self._safe_set_label_text(f'{created_count} 個のスプライトシートを出力しました: {output_dir}')
            else:
                self._safe_set_label_text('エラー: スプライトシートを生成できませんでした')
                
        except Exception as e:
            self._safe_set_label_text(f'エラー: {str(e)}')
            print(f"[スプライトシート] エラー: {e}")
            import traceback
            traceback.print_exc()
    
    def _export_animation_group_spritesheet(self):
        """選択中のアニメーションのグループをスプライトシートで出力"""
        selected_rows = self.anim_list.selectionModel().selectedRows()
        
        if not selected_rows:
            self._safe_set_label_text('エラー: アニメーションが選択されていません')
            return
        
        # _anim_no_list から実際のアニメーション番号を取得
        row_index = selected_rows[0].row()
        if row_index >= len(self._anim_no_list):
            self._safe_set_label_text('エラー: 選択されたアニメーションが無効です')
            return
        
        anim_no = self._anim_no_list[row_index]
        if anim_no not in self.animations:
            self._safe_set_label_text('エラー: 選択されたアニメーションが無効です')
            return
        
        try:
            # アニメーションで使用されるグループを特定
            frames = self.animations[anim_no]
            used_groups = set()
            
            for frame in frames:
                if frame.get('loopstart'):
                    continue
                used_groups.add(frame.get('group', 0))
            
            if not used_groups:
                self._safe_set_label_text('エラー: アニメーションにスプライトがありません')
                return
            
            print(f"[アニメーションスプライトシート] 使用されるグループ: {sorted(used_groups)}")
            
            # ファイル保存ダイアログ
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                'アニメーションスプライトシートを保存',
                f'animation_{anim_no}_spritesheet.png',
                'PNG files (*.png)'
            )
            
            if not file_path:
                return
            
            # 使用されるグループのスプライトを収集
            sprites = []
            for group in sorted(used_groups):
                for i, sprite in enumerate(self.reader.sprites):
                    if sprite.get('group_no', 0) == group:
                        sprites.append((i, sprite))
            
            sprites = sorted(sprites, key=lambda x: (x[1].get('group_no', 0), x[1].get('sprite_no', 0)))
            
            print(f"[アニメーションスプライトシート] 収集されたスプライト: {len(sprites)} 個")
            
            if sprites:
                spritesheet = self._create_grid_spritesheet(sprites, max_columns=20, padding=3, max_width=4096)
                if spritesheet:
                    # キャンバスエリアを無視して画像部分のみを抽出
                    if hasattr(spritesheet, 'extract_image_area'):
                        output_sheet = spritesheet.extract_image_area()
                        print(f"[アニメーションスプライトシート] 画像エリアのみ抽出: {output_sheet.size}")
                    else:
                        output_sheet = spritesheet
                    
                    # 不要な透過領域をトリミング
                    trimmed_spritesheet = self._trim_transparent_areas(output_sheet)
                    if trimmed_spritesheet:
                        output_sheet = trimmed_spritesheet
                        print(f"[アニメーションスプライトシート] トリミング完了: {output_sheet.size}")
                    
                    output_sheet.save(file_path, 'PNG')
                    self._safe_set_label_text(f'アニメーションスプライトシートを保存しました: {file_path}')
                    print(f"[アニメーションスプライトシート] 保存完了: {file_path}")
                else:
                    self._safe_set_label_text('エラー: スプライトシートの生成に失敗しました')
                    print(f"[アニメーションスプライトシート] 生成失敗")
            else:
                self._safe_set_label_text('エラー: 有効なスプライトが見つかりませんでした')
                
        except Exception as e:
            self._safe_set_label_text(f'エラー: {str(e)}')
            print(f"[アニメーションスプライトシート] エラー: {e}")
            import traceback
            traceback.print_exc()
        """グループ別にスプライトを取得"""
        sprites = []
        groups = {}
        
        for i, sprite in enumerate(self.reader.sprites):
            group = sprite.get('group_no', 0)
            if group not in groups:
                groups[group] = []
            groups[group].append((i, sprite))
        
        # グループ順にソート
        for group in sorted(groups.keys()):
            # グループ内でスプライト番号順にソート
            sorted_sprites = sorted(groups[group], key=lambda x: x[1].get('sprite_no', 0))
            sprites.extend(sorted_sprites)
        
        return sprites

    def _create_grid_spritesheet(self, sprites, max_columns=20, padding=3, max_width=4096):
        """透明背景・グループ別段組みのスプライトシートを作る"""
        if not PIL_AVAILABLE:
            return None
        try:
            from PIL import Image

            # 1) スプライトをグループ別に分類して画像を収集
            groups = {}
            for sprite_idx, sprite in sprites:
                group_no = sprite.get('group_no', 0)
                if group_no not in groups:
                    groups[group_no] = []
                
                qimg, _ = self.render_sprite_raw(sprite_idx)
                if qimg is None or qimg.isNull():
                    continue
                    
                qimg = qimg.convertToFormat(QImage.Format_RGBA8888)
                w, h = qimg.width(), qimg.height()
                ptr = qimg.constBits(); ptr.setsize(qimg.byteCount())
                bpl = qimg.bytesPerLine()

                buf = bytearray()
                for y in range(h):
                    start = y * bpl
                    buf.extend(ptr[start:start + w*4])
                img = Image.frombytes('RGBA', (w, h), bytes(buf))

                img = self._trim_single_image(img)  # 透明縁を除去
                groups[group_no].append((img, sprite.get('sprite_no', 0), sprite_idx))

            if not groups:
                return None

            print(f"[グループ別スプライトシート] 検出グループ: {sorted(groups.keys())}")

            # 2) グループごとに段を作成（グループ番号順にソート）
            group_rows = []
            total_width = 0
            total_height = 0

            for group_no in sorted(groups.keys()):
                group_sprites = groups[group_no]
                # スプライト番号順にソート
                group_sprites.sort(key=lambda x: x[1])  # sprite_no でソート
                
                print(f"[グループ別スプライトシート] グループ {group_no}: {len(group_sprites)} スプライト")

                # このグループ内での棚詰め配置
                group_rows_data = []
                cur, row_w, row_h = [], 0, 0
                
                for img, sprite_no, sprite_idx in group_sprites:
                    iw, ih = img.size
                    need = (iw if not cur else (iw + padding))
                    if cur and row_w + need > max_width:
                        group_rows_data.append((cur, row_w, row_h))
                        cur, row_w, row_h = [], 0, 0
                    if cur:
                        row_w += padding
                    cur.append((img, sprite_no, sprite_idx))
                    row_w += iw
                    row_h = max(row_h, ih)
                
                if cur:
                    group_rows_data.append((cur, row_w, row_h))

                # このグループの幅と高さを計算
                group_width = max(w for _, w, _ in group_rows_data) if group_rows_data else 0
                group_height = sum(h for _, _, h in group_rows_data) + padding * (len(group_rows_data) - 1) if group_rows_data else 0
                
                group_rows.append((group_no, group_rows_data, group_width, group_height))
                total_width = max(total_width, group_width)
                total_height += group_height
                if len(group_rows) > 1:  # グループ間のパディング
                    total_height += padding * 2

            # ラベル用のスペースを追加
            label_space = 20  # 各グループラベル用のスペース
            total_height += len(group_rows) * label_space

            # キャンバスエリアを2倍にする
            canvas_width = total_width * 2
            canvas_height = total_height * 2

            print(f"[グループ別スプライトシート] 画像エリアサイズ: {total_width}x{total_height}")
            print(f"[グループ別スプライトシート] キャンバスサイズ: {canvas_width}x{canvas_height}")

            # 3) マゼンタ背景のキャンバス
            sheet = Image.new('RGBA', (canvas_width, canvas_height), (255, 0, 255, 255))

            # 画像エリアの開始位置（キャンバス中央に配置）
            offset_x = (canvas_width - total_width) // 2
            offset_y = (canvas_height - total_height) // 2

            # 4) グループごとに配置（アルファマスク付き、グループラベル付き）
            current_y = 20 + offset_y  # 最初のグループラベル用スペース + オフセット
            for group_no, group_rows_data, group_width, group_height in group_rows:
                print(f"[グループ別スプライトシート] グループ {group_no} 配置開始: y={current_y}")
                
                # グループラベルを描画（オプション）
                try:
                    from PIL import ImageDraw, ImageFont
                    draw = ImageDraw.Draw(sheet)
                    label_text = f"Group {group_no}"
                    
                    # デフォルトフォントを使用
                    try:
                        font = ImageFont.load_default()
                        text_bbox = draw.textbbox((0, 0), label_text, font=font)
                        text_width = text_bbox[2] - text_bbox[0]
                        text_height = text_bbox[3] - text_bbox[1]
                    except:
                        # フォントが利用できない場合はスキップ
                        text_width, text_height = 0, 0
                    
                    if text_width > 0 and current_y >= text_height + 2:
                        # グループの開始位置にラベルを描画（背景付き）
                        label_y = current_y - text_height - 2
                        # 半透明背景
                        bg_img = Image.new('RGBA', (text_width + 8, text_height + 4), (50, 50, 50, 180))
                        sheet.paste(bg_img, (4 + offset_x, label_y - 2), bg_img)
                        # テキスト描画
                        draw.text((8 + offset_x, label_y), label_text, fill=(255, 255, 255, 255), font=font)
                        print(f"[グループ別スプライトシート] グループ {group_no} ラベル描画: ({8 + offset_x}, {label_y})")
                
                except ImportError:
                    # PILのImageDrawが利用できない場合はラベルをスキップ
                    pass
                except Exception as e:
                    print(f"[グループ別スプライトシート] ラベル描画エラー: {e}")
                
                group_y = current_y
                for row_data, row_w, row_h in group_rows_data:
                    x = offset_x  # オフセットを適用
                    for img, sprite_no, sprite_idx in row_data:
                        yoff = (row_h - img.height) // 2
                        mask = img.split()[3] if img.mode == 'RGBA' else None
                        sheet.paste(img, (x, group_y + yoff), mask)
                        x += img.width + padding
                    group_y += row_h + padding
                
                current_y += group_height + padding * 2  # グループ間のパディング

            # 5) 出力用に画像部分のみを抽出する関数を作成
            def extract_image_area():
                """キャンバスから画像部分のみを抽出"""
                return sheet.crop((offset_x, offset_y, offset_x + total_width, offset_y + total_height))

            # キャンバス情報をシートオブジェクトに付加
            sheet.image_area_bounds = (offset_x, offset_y, offset_x + total_width, offset_y + total_height)
            sheet.extract_image_area = extract_image_area

            print(f"[グループ別スプライトシート] 生成完了: キャンバス{canvas_width}x{canvas_height}, 画像エリア{total_width}x{total_height}")
            return sheet

        except Exception as e:
            print(f"[グループ別スプライトシート] エラー: {e}")
            import traceback; traceback.print_exc()
            return None

    def render_sprite_raw(self, sprite_idx):
        """スプライトをフィルター適用なしで生成（実画像優先）"""
        if sprite_idx < 0 or sprite_idx >= len(self.reader.sprites):
            return None, None
        
        sprite = self.reader.sprites[sprite_idx]
        
        # 画像データの存在確認と詳細診断
        img_data = sprite.get('image_data')
        width = sprite.get('width', 0)
        height = sprite.get('height', 0)
        fmt = sprite.get('fmt', -1)
        offset = sprite.get('offset', 0)
        length = sprite.get('length', 0)
        
        # SFFv2の場合、image_dataがNoneでも遅延読み込みが可能
        if self.is_v2 and img_data is None and width > 0 and height > 0:
            try:
                # SFFv2の遅延読み込みを試行
                if decode_sprite_v2 is not None:
                    decoded_data, palette, w, h, mode = decode_sprite_v2(self.reader, sprite_idx)
                    if decoded_data and w > 0 and h > 0:
                        print(f"[render_sprite_raw] スプライト {sprite_idx}: SFFv2遅延読み込み成功 ({w}x{h})")
                        # decode_sprite_v2の結果から直接QImageを作成
                        qimg = self._create_qimage_from_decoded(decoded_data, palette, w, h, mode)
                        if qimg is not None:
                            print(f"[render_sprite_raw] スプライト {sprite_idx}: QImage作成成功")
                            return qimg, None
                else:
                    print(f"[render_sprite_raw] スプライト {sprite_idx}: decode_sprite_v2が利用できません")
            except Exception as e:
                print(f"[render_sprite_raw] スプライト {sprite_idx}: SFFv2遅延読み込み失敗: {e}")
        
        if not img_data or width <= 0 or height <= 0:
            # 詳細な診断情報を出力
            print(f"[render_sprite_raw] スプライト {sprite_idx}: 無効データ詳細")
            print(f"  - image_data: {type(img_data)} (長さ: {len(img_data) if img_data else 0})")
            print(f"  - サイズ: {width}x{height}")
            # リンクフレームの場合はリンク先fmtも表示
            link_idx = sprite.get('link_idx', None)
            if link_idx is not None and 0 <= link_idx < len(self.reader.sprites):
                link_fmt = self.reader.sprites[link_idx].get('fmt', -1)
                print(f"  - フォーマット: {fmt} (リンク先: {link_fmt})")
            else:
                print(f"  - フォーマット: {fmt}")
            print(f"  - オフセット: {offset}, 長さ: {length}")
            
            # 無効データの理由を分析
            if img_data is None:
                if self.is_v2:
                    reason = "SFFv2遅延読み込み対象（通常動作）"
                else:
                    reason = "画像データがNone（ファイル読み込みエラーまたは空データ）"
            elif len(img_data) == 0:
                reason = "画像データが空（長さ0）"
            elif width <= 0 or height <= 0:
                reason = f"無効なサイズ（{width}x{height}）"
            else:
                reason = "不明な理由"
            
            print(f"  - 無効理由: {reason}")
            
            # SFFファイル内でのこのスプライトの情報をさらに詳細に調査
            if hasattr(sprite, 'keys'):
                print(f"  - スプライト属性: {list(sprite.keys())}")
            
            # SFFv2の場合でサイズが有効なら、render_spriteに処理を委譲
            if self.is_v2 and width > 0 and height > 0:
                print(f"[render_sprite_raw] スプライト {sprite_idx}: SFFv2として標準レンダリングに委譲")
                # 無効データでもSFFv2なら処理を続行
            else:
                # 無効なデータの場合はプレースホルダー画像を作成
                placeholder_img = self._create_placeholder_image(max(32, width), max(32, height), f"SP{sprite_idx}")
                return placeholder_img, None
 
        # まず既存のrender_spriteメソッドを試行
        try:
            qimg, _ = self.render_sprite(sprite_idx)
            if qimg is not None and not qimg.isNull() and qimg.width() > 0 and qimg.height() > 0:
                print(f"[render_sprite_raw] スプライト {sprite_idx}: 正常レンダリング成功 ({qimg.width()}x{qimg.height()})")
                return qimg, None
            else:
                print(f"[render_sprite_raw] スプライト {sprite_idx}: render_sprite返り値無効")
        except Exception as e:
            print(f"[render_sprite_raw] スプライト {sprite_idx}: render_spriteエラー: {e}")
        
        # render_spriteが失敗した場合、直接レンダリングを試行
        try:
            qimg = self._direct_render_sprite(sprite_idx)
            if qimg is not None and not qimg.isNull():
                print(f"[render_sprite_raw] スプライト {sprite_idx}: 直接レンダリング成功 ({qimg.width()}x{qimg.height()})")
                return qimg, None
        except Exception as e:
            print(f"[render_sprite_raw] スプライト {sprite_idx}: 直接レンダリングエラー: {e}")
        
        # 全て失敗した場合はプレースホルダー
        print(f"[render_sprite_raw] スプライト {sprite_idx}: 全レンダリング失敗、プレースホルダー作成")
        return self._create_placeholder_image(width, height, f"ERR{sprite_idx}"), None

    def _create_qimage_from_decoded(self, decoded_data, palette, width, height, mode):
        """decode_sprite_v2の結果からQImageを作成"""
        try:
            if mode == 'rgba':
                # RGBA形式の場合
                img = QImage(width, height, QImage.Format_RGBA8888)
                stride = img.bytesPerLine()
                row_bytes = width * 4
                
                try:
                    ptr = img.bits()
                    ptr.setsize(stride * height)
                    mv = memoryview(ptr)
                    
                    if stride == row_bytes:
                        mv[:row_bytes * height] = decoded_data[:row_bytes * height]
                    else:
                        for y in range(height):
                            src_off = y * row_bytes
                            dst_off = y * stride
                            mv[dst_off:dst_off+row_bytes] = decoded_data[src_off:src_off+row_bytes]
                    return img
                except Exception as e:
                    print(f"[create_qimage] RGBA memoryview失敗、fallback: {e}")
                    # フォールバック: 手動設定
                    img = QImage(bytes(decoded_data[:width*height*4]), width, height, QImage.Format_RGBA8888)
                    return img
                    
            else:
                # インデックス形式の場合
                img = QImage(width, height, QImage.Format_Indexed8)
                
                if palette:
                    color_table = []
                    for r, g, b, a in palette:
                        color_table.append(QColor(r, g, b, a).rgba())
                    img.setColorTable(color_table)
                
                stride = img.bytesPerLine()
                try:
                    ptr = img.bits()
                    ptr.setsize(stride * height)
                    mv = memoryview(ptr)
                    
                    if stride == width:
                        mv[:width*height] = decoded_data[:width*height]
                    else:
                        for y in range(height):
                            src_off = y * width
                            dst_off = y * stride
                            mv[dst_off:dst_off+width] = decoded_data[src_off:src_off+width]
                    return img
                except Exception as e:
                    print(f"[create_qimage] インデックス memoryview失敗、RGBA fallback: {e}")
                    # RGBAフォールバック
                    rgba = bytearray()
                    for i in decoded_data[:width*height]:
                        if palette and 0 <= i < len(palette):
                            r, g, b, a = palette[i]
                        else:
                            r = g = b = 0; a = 0
                        rgba.extend([r, g, b, a])
                    
                    img_rgba = QImage(width, height, QImage.Format_RGBA8888)
                    stride_rgba = img_rgba.bytesPerLine()
                    row_bytes_rgba = width * 4
                    
                    try:
                        ptr_rgba = img_rgba.bits()
                        ptr_rgba.setsize(stride_rgba * height)
                        mv_rgba = memoryview(ptr_rgba)
                        
                        if stride_rgba == row_bytes_rgba:
                            mv_rgba[:row_bytes_rgba * height] = rgba[:row_bytes_rgba * height]
                        else:
                            for y in range(height):
                                src_off = y * row_bytes_rgba
                                dst_off = y * stride_rgba
                                mv_rgba[dst_off:dst_off+row_bytes_rgba] = rgba[src_off:src_off+row_bytes_rgba]
                        return img_rgba
                    except Exception as e2:
                        print(f"[create_qimage] RGBA fallback失敗: {e2}")
                        return None
                        
        except Exception as e:
            print(f"[create_qimage] 全般エラー: {e}")
            return None

    def _direct_render_sprite(self, sprite_idx):
        """スプライトを直接レンダリング（バックアップ方式）"""
        sprite = self.reader.sprites[sprite_idx]
        
        img_data = sprite.get('image_data')
        width = sprite.get('width', 0)
        height = sprite.get('height', 0)
        fmt = sprite.get('fmt', 0)
        
        if not img_data or width <= 0 or height <= 0:
            return None
        
        # フォーマットに応じた処理
        if fmt in [0, 1]:  # インデックスカラー
            return self._render_indexed_sprite(sprite_idx, sprite, img_data, width, height)
        elif fmt in [2, 3, 4, 11, 12]:  # 直接色（PNG fmt=10は除外）
            return self._render_direct_sprite(sprite_idx, sprite, img_data, width, height, fmt)
        elif fmt == 10:  # PNG形式 - SFFv2では遅延読み込みに委譲
            if self.is_v2:
                print(f"[direct_render] PNG形式(fmt=10)はSFFv2遅延読み込みで処理済み")
                return None  # 遅延読み込みで処理されるべき
            else:
                # SFFv1の場合は直接色として処理
                return self._render_direct_sprite(sprite_idx, sprite, img_data, width, height, fmt)
        else:
            print(f"[direct_render] 未対応フォーマット: {fmt}")
            return None

    def _render_indexed_sprite(self, sprite_idx, sprite, img_data, width, height):
        """インデックスカラースプライトのレンダリング"""
        try:
            # SFFv2の場合は専用のパレット取得方法を使用
            if self.is_v2:
                pal_idx = sprite.get('pal_idx', 0)
                if 0 <= pal_idx < len(self.reader.palettes):
                    palette_data = self.reader.palettes[pal_idx]
                    palette = []
                    for r, g, b, a in palette_data:
                        palette.extend([r, g, b])
                    print(f"[indexed_render] SFFv2パレット {pal_idx} を使用")
                else:
                    print(f"[indexed_render] SFFv2: 無効なパレットインデックス {pal_idx}")
                    # デフォルトパレット（グレースケール）
                    palette = []
                    for i in range(256):
                        palette.extend([i, i, i])
            else:
                # SFFv1の場合の既存処理
                pal_group = sprite.get('pal_group', 1)
                pal_item = sprite.get('pal_item', 0)
                pal_key = (pal_group, pal_item)
                
                if pal_key in self.reader.palettes:
                    palette = self.reader.palettes[pal_key]
                else:
                    # デフォルトパレット（グレースケール）
                    palette = []
                    for i in range(256):
                        palette.extend([i, i, i])
            
            # QImageを作成（インデックスカラー）
            qimg = QImage(width, height, QImage.Format_Indexed8)
            
            # パレット設定
            colors = []
            for i in range(0, min(len(palette), 768), 3):
                if i + 2 < len(palette):
                    r, g, b = palette[i], palette[i+1], palette[i+2]
                    colors.append(qRgb(r, g, b))
                else:
                    colors.append(qRgb(128, 128, 128))  # グレーで埋める
            
            # 256色まで埋める
            while len(colors) < 256:
                colors.append(qRgb(128, 128, 128))
            
            qimg.setColorTable(colors)
            
            # 画像データを設定
            for y in range(height):
                for x in range(width):
                    idx = y * width + x
                    if idx < len(img_data):
                        pixel_value = img_data[idx] if isinstance(img_data[idx], int) else ord(img_data[idx])
                        qimg.setPixel(x, y, pixel_value)
                    else:
                        qimg.setPixel(x, y, 0)
            
            # インデックス0を透明に設定
            if len(colors) > 0:
                colors[0] = colors[0] & 0x00FFFFFF
                qimg.setColorTable(colors)
            
            return qimg
            
        except Exception as e:
            print(f"[indexed_render] エラー: {e}")
            return None

    def _render_direct_sprite(self, sprite_idx, sprite, img_data, width, height, fmt):
        """直接色スプライトのレンダリング"""
        try:
            qimg = QImage(width, height, QImage.Format_ARGB32)
            
            if fmt == 2:  # 16bit RGB565
                # 16bitデータの処理
                for y in range(height):
                    for x in range(width):
                        idx = (y * width + x) * 2
                        if idx + 1 < len(img_data):
                            # リトルエンディアンで16bit値を構築
                            pixel16 = img_data[idx] | (img_data[idx + 1] << 8)
                            r = ((pixel16 >> 11) & 0x1F) << 3
                            g = ((pixel16 >> 5) & 0x3F) << 2
                            b = (pixel16 & 0x1F) << 3
                            qimg.setPixel(x, y, qRgb(r, g, b))
                        else:
                            qimg.setPixel(x, y, qRgb(255, 0, 255))  # マゼンタ
            
            elif fmt in [10, 11, 12]:  # 32bit RGBA
                for y in range(height):
                    for x in range(width):
                        idx = (y * width + x) * 4
                        if idx + 3 < len(img_data):
                            r = img_data[idx] if isinstance(img_data[idx], int) else ord(img_data[idx])
                            g = img_data[idx + 1] if isinstance(img_data[idx + 1], int) else ord(img_data[idx + 1])
                            b = img_data[idx + 2] if isinstance(img_data[idx + 2], int) else ord(img_data[idx + 2])
                            a = img_data[idx + 3] if isinstance(img_data[idx + 3], int) else ord(img_data[idx + 3])
                            color = qRgb(r, g, b) | (a << 24)
                            qimg.setPixel(x, y, color)
                        else:
                            qimg.setPixel(x, y, qRgb(255, 0, 255))  # マゼンタ
            
            else:
                # その他のフォーマット
                qimg.fill(qRgb(255, 0, 255))  # マゼンタで埋める
            
            return qimg
            
        except Exception as e:
            print(f"[direct_render] エラー: {e}")
            return None

    def _create_placeholder_image(self, width, height, text="?"):
        """プレースホルダー画像を作成"""
        # 最小サイズ確保
        width = max(16, min(width, 200))
        height = max(16, min(height, 200))
        
        # QImageを作成
        qimg = QImage(width, height, QImage.Format_RGBA8888)
        qimg.fill(qRgb(255, 100, 100))  # 薄い赤色で塗りつぶし
        
        # QPainterでテキストを描画
        painter = QPainter(qimg)
        painter.setPen(QPen(QColor(255, 255, 255)))  # 白色のペン
        
        # フォントサイズを画像サイズに応じて調整
        font_size = min(width, height) // 4
        font = painter.font()
        font.setPointSize(max(8, font_size))
        painter.setFont(font)
        
        # テキストを中央に描画
        painter.drawText(qimg.rect(), Qt.AlignCenter, text)
        painter.end()
        
        return qimg

    def _get_animation_sprites(self):
        """現在選択中のアニメーションのスプライトを取得"""
        sprites = []
        selected_rows = self.anim_list.selectionModel().selectedRows()
        
        if not selected_rows:
            return sprites
        
        # _anim_no_list から実際のアニメーション番号を取得
        row_index = selected_rows[0].row()
        if row_index >= len(self._anim_no_list):
            return sprites
        
        anim_no = self._anim_no_list[row_index]
        if anim_no not in self.animations:
            return sprites
        
        frames = self.animations[anim_no]
        sprite_indices = set()
        
        for frame in frames:
            if frame.get('loopstart'):
                continue
            
            sprite_idx = self.find_sprite_index(frame.get('group', 0), frame.get('image', 0))
            if sprite_idx is not None:
                sprite_indices.add(sprite_idx)
        
        # インデックス順にソート
        for idx in sorted(sprite_indices):
            sprites.append((idx, self.reader.sprites[idx]))
        
        return sprites

    def _create_spritesheet(self, sprites, padding):
        """スプライトシートを生成"""
        if not sprites:
            return None
        
        # 各スプライトの画像を取得
        sprite_images = []
        max_height = 0
        total_width = 0
        
        for sprite_idx, sprite in sprites:
            qimg, _ = self.render_sprite(sprite_idx)
            if qimg is None:
                continue
            
            # QImageをPIL Imageに変換
            qimg_rgba = qimg.convertToFormat(QImage.Format_RGBA8888)
            w, h = qimg_rgba.width(), qimg_rgba.height()
            ptr = qimg_rgba.constBits()
            ptr.setsize(qimg_rgba.byteCount())
            
            img_bytes = bytearray()
            bytes_per_line = qimg_rgba.bytesPerLine()
            for y in range(h):
                line_start = y * bytes_per_line
                line_end = line_start + w * 4
                img_bytes.extend(ptr[line_start:line_end])
            
            pil_img = Image.frombytes('RGBA', (w, h), bytes(img_bytes))
            sprite_images.append(pil_img)
            
            max_height = max(max_height, h)
            total_width += w + padding
        
        if not sprite_images:
            return None
        
        # 最後の余白は不要
        total_width -= padding
        
        # スプライトシートを作成
        spritesheet = Image.new('RGBA', (total_width, max_height), (0, 0, 0, 0))
        
        x_offset = 0
        for img in sprite_images:
            # 中央寄せで配置
            y_offset = (max_height - img.height) // 2
            
            # 常にマスク付きで貼り付け
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            mask = img.split()[3]  # αチャンネル
            spritesheet.paste(img, (x_offset, y_offset), mask)
            x_offset += img.width + padding
        
        return spritesheet

    def _trim_single_image(self, image):
        """単一画像の不要な透過領域をトリミング（キャンバスサイズを最小化）"""
        if not PIL_AVAILABLE:
            return image
            
        try:
            # アルファチャンネルが存在するかチェック
            if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
                # より厳密な境界検出：アルファチャンネルと色情報の両方を使用
                if image.mode == 'RGBA':
                    # RGBAの場合、ピクセル単位で詳細チェック
                    data = image.getdata()
                    width, height = image.size
                    
                    # 実際にコンテンツがあるピクセルを探す
                    min_x, min_y = width, height
                    max_x, max_y = -1, -1
                    
                    for y in range(height):
                        for x in range(width):
                            idx = y * width + x
                            r, g, b, a = data[idx]
                            
                            # アルファが閾値以上、または色が黒以外の場合
                            if a > 16 or (r > 8 or g > 8 or b > 8):  # より厳しい閾値
                                min_x = min(min_x, x)
                                min_y = min(min_y, y)
                                max_x = max(max_x, x)
                                max_y = max(max_y, y)
                    
                    if max_x >= min_x and max_y >= min_y:
                        # 見つかった境界で切り取り
                        bbox = (min_x, min_y, max_x + 1, max_y + 1)
                        trimmed = image.crop(bbox)
                        print(f"[キャンバス最小化] 詳細解析 {image.size} → {trimmed.size}")
                        return trimmed
                    else:
                        # フォールバック処理
                        print(f"[キャンバス最小化] 完全透明画像 → 1x1")
                        return image.crop((0, 0, 1, 1))
                        
                elif image.mode == 'LA':
                    alpha = image.getchannel('A')
                else:
                    # Pモードで透明度がある場合
                    alpha = image.convert('RGBA').getchannel('A')
                
                # 標準のアルファ境界検出
                bbox = alpha.getbbox()
                if bbox:
                    # キャンバスサイズを最小化（マージンなし）
                    left, top, right, bottom = bbox
                    
                    # トリミング実行（ピッタリサイズ）
                    trimmed = image.crop((left, top, right, bottom))
                    print(f"[キャンバス最小化] {image.size} → {trimmed.size}")
                    return trimmed
                else:
                    # 完全に透明な画像の場合は1x1に縮小
                    print(f"[キャンバス最小化] 完全透明画像 → 1x1")
                    return image.crop((0, 0, 1, 1))
            else:
                # 透明度がない場合、外周の同色領域をトリミング
                # 外周が単色の場合はそれを除去
                bbox = image.getbbox()
                if bbox and bbox != (0, 0, image.width, image.height):
                    trimmed = image.crop(bbox)
                    print(f"[キャンバス最小化] 単色外周除去: {image.size} → {trimmed.size}")
                    return trimmed
                else:
                    return image
                
        except Exception as e:
            print(f"[キャンバス最小化] エラー: {e}")
            return image

    def _trim_transparent_areas(self, image):
        """画像の不要な透過領域をトリミング"""
        if not PIL_AVAILABLE:
            return image
            
        try:
            # アルファチャンネルが存在するかチェック
            if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
                # アルファチャンネルを取得
                if image.mode == 'RGBA':
                    alpha = image.getchannel('A')
                elif image.mode == 'LA':
                    alpha = image.getchannel('A')
                else:
                    # Pモードで透明度がある場合
                    alpha = image.convert('RGBA').getchannel('A')
                
                # 非透明領域の境界を取得
                bbox = alpha.getbbox()
                if bbox:
                    # スプライトシート全体のトリミング（最小限のマージン）
                    margin = 1
                    left, top, right, bottom = bbox
                    left = max(0, left - margin)
                    top = max(0, top - margin)
                    right = min(image.width, right + margin)
                    bottom = min(image.height, bottom + margin)
                    
                    # トリミング実行
                    trimmed = image.crop((left, top, right, bottom))
                    print(f"[全体トリミング] 元サイズ: {image.size} → トリミング後: {trimmed.size}")
                    return trimmed
                else:
                    # 完全に透明な画像の場合
                    print(f"[トリミング] 完全透明画像のため、最小サイズに縮小")
                    return image.crop((0, 0, 1, 1))
            else:
                # 透明度がない場合はそのまま返す
                print(f"[トリミング] 透明度なし、トリミングスキップ")
                return image
                
        except Exception as e:
            print(f"[トリミング] エラー: {e}")
            return image

    def _export_single_animation_gif(self, anim_no, output_path):
        """単一アニメーションをGIFで出力（通常GIF出力と同じ処理）"""
        frames = self.animations[anim_no]
        if not frames:
            return

        try:
            print(f"[一括GIF] アニメーション {anim_no} 処理開始")

            # ====== 1) 全フレームのBBOXを事前計算（判定も含む） ======
            min_left = min_top = 10**9
            max_right = max_bottom = -10**9
            
            prepared = []  # 各フレームの必要情報を先に集める
            for fr in frames:
                if fr.get('loopstart'):  # ループマーカーはスキップ
                    continue
                
                # スプライト画像を取得
                sprite_idx = self.find_sprite_index(fr.get('group', 0), fr.get('image', 0))
                if sprite_idx is None:
                    continue
                
                qimg, _ = self.render_sprite(sprite_idx)
                if qimg is None:
                    continue
                
                w, h = qimg.width(), qimg.height()
                
                # 軸とAIRのオフセット
                spr = self.reader.sprites[sprite_idx]
                # SFFv1では 'axisx'/'axisy'、SFFv2では 'x_axis'/'y_axis' を使用
                ax = spr.get('axisx', spr.get('x_axis', 0))
                ay = spr.get('axisy', spr.get('y_axis', 0))
                dx, dy = fr.get('x', 0), fr.get('y', 0)
                
                # 画像のBBOX
                left = -ax + dx
                top = -ay + dy
                right = left + w
                bottom = top + h
                
                # 判定ボックスも考慮（表示設定に関係なく全体のサイズを計算）
                for clsn_key in ['clsn1', 'clsn2']:
                    clsn_boxes = fr.get(clsn_key, [])
                    for box in clsn_boxes:
                        if box:
                            x1, y1 = box.get('x1', 0), box.get('y1', 0)
                            x2, y2 = box.get('x2', 0), box.get('y2', 0)
                            
                            # 判定ボックスの位置計算
                            clsn_left = min(x1, x2) + dx
                            clsn_top = min(y1, y2) + dy  
                            clsn_right = max(x1, x2) + dx
                            clsn_bottom = max(y1, y2) + dy
                            
                            left = min(left, clsn_left)
                            top = min(top, clsn_top)
                            right = max(right, clsn_right)
                            bottom = max(bottom, clsn_bottom)
                
                min_left = min(min_left, left)
                min_top = min(min_top, top)
                max_right = max(max_right, right)
                max_bottom = max(max_bottom, bottom)
                
                prepared.append((qimg, ax, ay, dx, dy, w, h, fr))
            
            if not prepared:
                print(f"[一括GIF] アニメーション {anim_no}: 有効フレームなし")
                return

            margin = 20  # 余白サイズ
            canvas_w = int((max_right - min_left) + margin * 2)
            canvas_h = int((max_bottom - min_top) + margin * 2)
            
            origin_x = -min_left + margin
            origin_y = -min_top + margin
            
            print(f"[一括GIF] キャンバスサイズ: {canvas_w}x{canvas_h}, 原点: ({origin_x}, {origin_y})")

            # ====== 2) 各フレーム画像を同じ原点で作る ======
            pil_frames = []
            durations = []
            for qimg, ax, ay, dx, dy, w, h, fr in prepared:
                flip_h = fr.get('flip_h', False)
                flip_v = fr.get('flip_v', False)
                blend_mode = fr.get('blend_mode', 'normal')
                alpha_value = fr.get('alpha_value', 1.0)
                print(f"[一括GIF] フレーム処理: 軸({ax},{ay}), オフセット({dx},{dy}), サイズ({w},{h})")
                print(f"[一括GIF] 反転・合成: H={flip_h}, V={flip_v}, blend={blend_mode}, alpha={alpha_value}")
                
                # キャンバス作成
                base = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
                
                # QImage -> PIL変換
                qimg_rgba = qimg.convertToFormat(QImage.Format_RGBA8888)
                ptr = qimg_rgba.constBits()
                ptr.setsize(qimg_rgba.byteCount())
                
                # バイト配列を正しく取得
                img_bytes = bytearray()
                bytes_per_line = qimg_rgba.bytesPerLine()
                for y in range(h):
                    line_start = y * bytes_per_line
                    line_end = line_start + w * 4
                    img_bytes.extend(ptr[line_start:line_end])
                
                pil = Image.frombytes('RGBA', (w, h), bytes(img_bytes))
                
                # 反転処理
                if flip_h:
                    pil = pil.transpose(Image.FLIP_LEFT_RIGHT)
                    print(f"[一括GIF] 水平反転適用")
                if flip_v:
                    pil = pil.transpose(Image.FLIP_TOP_BOTTOM)
                    print(f"[一括GIF] 垂直反転適用")
                
                # 透明度処理
                if alpha_value < 1.0:
                    alpha_channel = pil.split()[-1]  # アルファチャンネル取得
                    alpha_channel = alpha_channel.point(lambda x: int(x * alpha_value))  # 透明度調整
                    pil.putalpha(alpha_channel)
                    print(f"[一括GIF] 透明度調整: {alpha_value}")
                
                # 画像配置位置の計算（通常時と同じロジック）
                effective_axis_x = ax + dx
                effective_axis_y = ay + dy
                img_x = origin_x - effective_axis_x
                img_y = origin_y - effective_axis_y
                
                print(f"[一括GIF] PIL配置: 原点({origin_x},{origin_y}), 軸({ax},{ay}), オフセット({dx},{dy}) → 配置位置({img_x},{img_y})")
                
                # 配置位置をキャンバス内に制限
                img_x = max(0, min(canvas_w - w, img_x))
                img_y = max(0, min(canvas_h - h, img_y))
                
                # 合成モードを考慮した配置
                if blend_mode == 'normal':
                    base.paste(pil, (img_x, img_y), pil)
                elif blend_mode == 'add':
                    # 加算合成（PIL）
                    temp = Image.new('RGBA', base.size, (0, 0, 0, 0))
                    temp.paste(pil, (img_x, img_y), pil)
                    base = Image.alpha_composite(base, temp)
                    print(f"[一括GIF] 加算合成適用")
                elif blend_mode == 'subtract':
                    # 減算合成（近似処理）
                    temp = Image.new('RGBA', base.size, (0, 0, 0, 0))
                    temp.paste(pil, (img_x, img_y), pil)
                    # 簡易減算として、元画像から新画像を引く（PIL制限による近似）
                    base = Image.alpha_composite(base, temp)
                    print(f"[一括GIF] 減算合成適用（近似）")
                else:
                    base.paste(pil, (img_x, img_y), pil)
                
                # 判定合成（config設定に基づく）
                show_clsn1 = self.config.show_clsn
                show_clsn2 = self.config.show_clsn
                
                print(f"[一括GIF] 判定表示設定: show_clsn={self.config.show_clsn}")
                
                # 判定データの存在確認
                has_clsn1 = fr.get('clsn1') and any(box for box in fr.get('clsn1', []) if box)
                has_clsn2 = fr.get('clsn2') and any(box for box in fr.get('clsn2', []) if box)
                print(f"[一括GIF] 判定データ存在: Clsn1={has_clsn1}, Clsn2={has_clsn2}")
                
                if self.config.show_clsn and (has_clsn1 or has_clsn2):
                    print(f"[一括GIF] 判定描画実行")
                    self._draw_clsn_on_pil(base, origin_x, origin_y, ax, ay, dx, dy, fr, show_clsn1, show_clsn2)
                else:
                    print(f"[一括GIF] 判定描画スキップ")
                
                pil_frames.append(base)
                durations.append(max(1, int(fr.get('duration', 1))) * (1000 // 60))  # ms

            # ====== 3) GIF保存 ======
            print(f"[一括GIF] フレーム数: {len(pil_frames)}")
            
            # デバッグ用：最初のフレームの内容確認
            if pil_frames:
                first_frame = pil_frames[0]
                print(f"[一括GIF] 最初のフレーム: サイズ{first_frame.size}, モード{first_frame.mode}")
                
                # フレームに画像データがあるかチェック
                bbox = first_frame.getbbox()
                if bbox:
                    print(f"[一括GIF] 画像データ範囲: {bbox}")
                else:
                    print(f"[一括GIF] 警告: 最初のフレームが空です")
            
            # RGBAからPモードに変換（透明度保持）
            converted_frames = []
            for i, frame in enumerate(pil_frames):
                if frame.mode == 'RGBA':
                    # 透明度を保持してパレット化
                    try:
                        # アルファチャンネルを分離
                        r, g, b, a = frame.split()
                        
                        # 完全に透明な部分にマゼンタ色(255,0,255)を設定（透明色として使用）
                        transparent_color = (255, 0, 255)  # マゼンタを透明色に
                        rgb_frame = Image.new('RGB', frame.size, transparent_color)
                        
                        # アルファ値が0でない部分のみ元の色を使用
                        mask = a.point(lambda x: 255 if x > 0 else 0)
                        rgb_frame.paste(frame.convert('RGB'), mask=mask)
                        
                        # パレット化（透明色を含む）
                        palette_frame = rgb_frame.quantize(colors=255)  # 255色（透明色用に1色残す）
                        
                        # パレットを取得・調整
                        palette = palette_frame.getpalette()
                        if palette:
                            # パレットサイズを768バイト（256色×3チャンネル）に調整
                            if len(palette) < 768:
                                palette.extend([0] * (768 - len(palette)))
                            elif len(palette) > 768:
                                palette = palette[:768]
                            
                            # 最後の色をマゼンタ（透明色）に設定
                            palette[765:768] = [255, 0, 255]  # インデックス255をマゼンタに
                            palette_frame.putpalette(palette)
                        
                        # マゼンタ色（インデックス255）を透明色として設定
                        palette_frame.info['transparency'] = 255
                        
                        # 透明部分をマゼンタ色に変換
                        pixels = list(palette_frame.getdata())
                        rgb_pixels = list(rgb_frame.getdata())
                        new_pixels = []
                        
                        for j, pixel in enumerate(pixels):
                            if rgb_pixels[j] == transparent_color:
                                new_pixels.append(255)  # マゼンタのインデックス
                            else:
                                new_pixels.append(pixel)
                        
                        palette_frame.putdata(new_pixels)
                        converted_frames.append(palette_frame)
                        
                    except Exception as e:
                        print(f"[一括GIF] 透明度処理失敗、フォールバック: {e}")
                        # フォールバック：単純なパレット化
                        rgb_frame = Image.new('RGB', frame.size, (0, 0, 0, 0))
                        rgb_frame.paste(frame.convert('RGB'), mask=frame.split()[-1])
                        palette_frame = rgb_frame.quantize(colors=256)
                        converted_frames.append(palette_frame)
                else:
                    # 非RGBA画像の処理
                    converted_frame = frame.quantize(colors=256)
                    converted_frames.append(converted_frame)
                
                print(f"[一括GIF] フレーム{i+1}変換完了: {converted_frames[-1].mode}")
            
            # GIF保存（透明度有効）
            if converted_frames:
                try:
                    # 最初のフレームの透明度設定をチェック
                    first_frame = converted_frames[0]
                    save_kwargs = {
                        'save_all': True,
                        'append_images': converted_frames[1:],
                        'duration': durations,
                        'loop': 0,
                        'disposal': 2,
                        'optimize': False  # パレット問題を避けるためoptimize無効
                    }
                    
                    # 透明度情報がある場合のみtransparencyを設定
                    if hasattr(first_frame, 'info') and 'transparency' in first_frame.info:
                        save_kwargs['transparency'] = first_frame.info['transparency']
                        print(f"[一括GIF] 透明度設定: {first_frame.info['transparency']}")
                    
                    first_frame.save(output_path, **save_kwargs)
                    print(f"[一括GIF] 保存完了: {output_path} ({len(pil_frames)} フレーム)")
                    
                except Exception as save_error:
                    print(f"[一括GIF] 保存エラー、フォールバック実行: {save_error}")
                    # フォールバック：透明度なしで保存
                    try:
                        # すべてのフレームをRGBに変換
                        rgb_frames = []
                        for frame in converted_frames:
                            if frame.mode != 'RGB':
                                rgb_frame = frame.convert('RGB')
                            else:
                                rgb_frame = frame
                            rgb_frames.append(rgb_frame)
                        
                        rgb_frames[0].save(output_path,
                            save_all=True,
                            append_images=rgb_frames[1:],
                            duration=durations,
                            loop=0,
                            optimize=False)
                        
                        print(f"[一括GIF] フォールバック保存完了: {output_path} ({len(rgb_frames)} フレーム, 透明度なし)")
                    except Exception as fallback_error:
                        print(f"[一括GIF] フォールバック保存も失敗: {fallback_error}")
                        raise fallback_error
            else:
                print(f"[一括GIF] エラー: フレームの変換に失敗")

        except Exception as e:
            print(f"[一括GIF] エラー (アニメ {anim_no}): {e}")
            import traceback
            traceback.print_exc()


def create_standalone_viewer(config: Optional[SFFViewerConfig] = None) -> SFFViewer:
    """スタンドアロンモードでSFFViewerを作成
    
    Args:
        config: ビューア設定。Noneの場合はデフォルト設定を使用
        
    Returns:
        設定されたSFFViewerインスタンス
    """
    viewer = SFFViewer(config)
    viewer._standalone_mode = True  # スタンドアロンモードフラグ
    
    # ウィンドウサイズと位置を強制設定
    viewer.resize(800, 600)
    viewer.move(100, 100)
    print(f"[DEBUG] ビューアウィンドウサイズ・位置設定完了: 800x600 at (100,100)")
    
    # 画像ウィンドウも確実に表示
    if hasattr(viewer, 'image_window'):
        viewer.image_window.resize(600, 400)
        viewer.image_window.move(300, 150)
        print(f"[DEBUG] 画像ウィンドウサイズ・位置設定完了: 600x400 at (300,150)")
    
    return viewer


def main():
    """メイン関数 - スタンドアロン実行用"""
    print(f"[DEBUG] main関数開始")
    
    logging.basicConfig(level=logging.INFO)
    print(f"[DEBUG] ログ設定完了")
    
    # コマンドライン引数の処理
    import argparse
    parser = argparse.ArgumentParser(description='SFF Viewer - 格闘ゲーム用スプライトビューア')
    parser.add_argument('file', nargs='?', help='開くSFFまたはDEFファイル')
    parser.add_argument('--debug', action='store_true', help='デバッグモードを有効にする')
    parser.add_argument('--scale', type=float, default=2.0, help='初期スケール倍率 (デフォルト: 2.0)')
    args = parser.parse_args()
    
    print(f"[DEBUG] 引数解析完了: file={args.file}, debug={args.debug}")
    
    # 設定作成
    config = SFFViewerConfig(
        debug_mode=args.debug,
        default_scale=args.scale
    )
    print(f"[DEBUG] 設定作成完了: debug_mode={config.debug_mode}")
    
    app = QApplication(sys.argv)
    print(f"[DEBUG] QApplication作成完了")
    
    viewer = create_standalone_viewer(config)
    print(f"[DEBUG] ビューア作成完了")
    
    # ファイルが指定されていれば開く
    if args.file:
        print(f"[DEBUG] ファイル読み込み開始: {args.file}")
        if args.file.lower().endswith('.def'):
            viewer.load_def_file(args.file)
        else:
            viewer.load_sff_file(args.file)
        print(f"[DEBUG] ファイル読み込み完了")
    
    print(f"[DEBUG] ウィンドウ表示開始")
    viewer.show()
    viewer.raise_()  # ウィンドウを前面に表示
    viewer.activateWindow()  # ウィンドウをアクティブにする
    
    # 画像ウィンドウも確実に表示
    if hasattr(viewer, 'image_window'):
        viewer.image_window.show()
        viewer.image_window.raise_()
        viewer.image_window.activateWindow()
        print(f"[DEBUG] 画像ウィンドウ表示完了")
    
    print(f"[DEBUG] メインループ開始")
    sys.exit(app.exec_())


# ===============================
# Library API Methods
# ===============================

class SFFViewerAPI:
    """
    High-level API for SFF Viewer library usage
    """
    
    @staticmethod
    def create_headless_reader(file_path):
        """
        Create a headless SFF reader without GUI.
        
        Args:
            file_path (str): Path to SFF file
            
        Returns:
            tuple: (reader, is_v2) - SFF reader object and version flag
        """
        # SFFファイルの形式を判定
        try:
            with open(file_path, 'rb') as f:
                sig = f.read(12)
                f.seek(0)
                if sig.startswith(b'ElecbyteSpr'):
                    f.seek(12)
                    ver = tuple(f.read(4))
                    f.seek(0)
                    if ver in [(0,0,0,2),(0,1,0,2)]:
                        # SFFv2
                        reader = SFFV2Reader(file_path)
                        with open(file_path, 'rb') as f2:
                            reader.read_header(f2)
                            reader.read_palettes(f2)
                            reader.read_sprites(f2)
                        return reader, True
                    else:
                        # SFFv1 (Elecbyte形式)
                        reader = SFFReader(file_path)
                        with open(file_path, 'rb') as f2:
                            reader.read_header(f2)
                            reader.read_sprites(f2)
                            reader.read_palettes(f2)
                        return reader, False
                else:
                    # SFFv1 (従来形式)
                    reader = SFFReader(file_path)
                    with open(file_path, 'rb') as f2:
                        reader.read_header(f2)
                        reader.read_sprites(f2)
                        reader.read_palettes(f2)
                    return reader, False
        except Exception as e:
            raise ValueError(f"Could not read SFF file: {e}")
    
    @staticmethod
    def get_sprite_info(file_path, sprite_index):
        """
        Get information about a specific sprite.
        
        Args:
            file_path (str): Path to SFF file
            sprite_index (int): Index of the sprite
            
        Returns:
            dict: Sprite information
        """
        reader, is_v2 = SFFViewerAPI.create_headless_reader(file_path)
        
        if sprite_index >= len(reader.sprites):
            raise IndexError(f"Sprite index {sprite_index} out of range")
        
        sprite = reader.sprites[sprite_index]
        return {
            'index': sprite_index,
            'group': sprite.get('group_no', 0),
            'image': sprite.get('sprite_no', 0),
            'width': sprite.get('width', 0),
            'height': sprite.get('height', 0),
            'x_axis': sprite.get('x_axis', 0),
            'y_axis': sprite.get('y_axis', 0),
            'format': 'SFFv2' if is_v2 else 'SFFv1'
        }
    
    @staticmethod
    def get_all_sprites_info(file_path):
        """
        Get information about all sprites in the file.
        
        Args:
            file_path (str): Path to SFF file
            
        Returns:
            list: List of sprite information dictionaries
        """
        reader, is_v2 = SFFViewerAPI.create_headless_reader(file_path)
        
        sprites_info = []
        for i, sprite in enumerate(reader.sprites):
            sprites_info.append({
                'index': i,
                'group': sprite.get('group_no', 0),
                'image': sprite.get('sprite_no', 0),
                'width': sprite.get('width', 0),
                'height': sprite.get('height', 0),
                'x_axis': sprite.get('x_axis', 0),
                'y_axis': sprite.get('y_axis', 0),
                'format': 'SFFv2' if is_v2 else 'SFFv1'
            })
        
        return sprites_info
    
    @staticmethod
    def extract_sprite_image(file_path, sprite_index, output_path=None):
        """
        Extract a sprite as an image file.
        
        Args:
            file_path (str): Path to SFF file
            sprite_index (int): Index of the sprite
            output_path (str, optional): Output image path. If None, returns QImage
            
        Returns:
            QImage or bool: QImage object if output_path is None, 
                           success status if output_path is provided
        """
        from PyQt5.QtGui import QImage
        
        reader, is_v2 = SFFViewerAPI.create_headless_reader(file_path)
        config = Config()
        renderer = SFFRenderer(config)
        
        if sprite_index >= len(reader.sprites):
            raise IndexError(f"Sprite index {sprite_index} out of range")
        
        # Render the sprite
        qimg, _ = renderer.render_sprite(reader, sprite_index, None, is_v2, [])
        
        if output_path:
            success = qimg.save(output_path)
            return success
        else:
            return qimg


def create_standalone_viewer(config=None):
    """スタンドアロンビューア作成"""
    from PyQt5.QtWidgets import QApplication
    
    if not QApplication.instance():
        app = QApplication(sys.argv)
    
    viewer = SFFViewer(config)
    viewer._standalone_mode = True
    return viewer


def main():
    """メイン関数"""
    import argparse
    from PyQt5.QtWidgets import QApplication
    
    parser = argparse.ArgumentParser(description='SffCharaViewer - SFF/AIR file viewer')
    parser.add_argument('file', nargs='?', help='SFF or DEF file to open')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--scale', type=float, default=2.0, help='Default scale factor')
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    
    # 設定を作成
    config = SFFViewerConfig(
        debug_mode=args.debug,
        default_scale=args.scale
    )
    
    viewer = create_standalone_viewer(config)
    viewer.show()
    
    # ファイルが指定されている場合は読み込み
    if args.file:
        if args.file.lower().endswith('.def'):
            viewer.load_def_file(args.file)
        else:
            viewer.load_sff_file(args.file)
    
    return app.exec_()


def create_standalone_app():
    """スタンドアロンアプリとして実行"""
    return main()


if __name__ == '__main__':
    main()
