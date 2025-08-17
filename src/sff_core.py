# -*- coding: utf-8 -*-
"""
SFFファイルパーサーモジュール
SFF（Sprite File Format）ファイルの読み込みと処理を行う
"""

import os
import struct
import logging
from typing import Dict, List, Optional, Tuple, Any
from PIL import Image, ImageDraw
import io


class SFFSprite:
    """SFFスプライトデータクラス"""
    
    def __init__(self, group: int, image: int, x: int, y: int, 
                 image_data: bytes, palette_data: Optional[bytes] = None):
        self.group = group
        self.image = image
        self.x = x
        self.y = y
        self.image_data = image_data
        self.palette_data = palette_data
        self.width = 0
        self.height = 0
        self.cached_pil_image = None
        
    def get_pil_image(self, palette_data: Optional[bytes] = None) -> Optional[Image.Image]:
        """PIL Imageオブジェクトを取得（キャッシュ対応）"""
        if self.cached_pil_image is not None:
            return self.cached_pil_image
            
        try:
            # PCXまたはPNG形式の判定と読み込み
            if self.image_data.startswith(b'\x89PNG'):
                # PNG形式
                self.cached_pil_image = Image.open(io.BytesIO(self.image_data))
            else:
                # PCX形式の場合の処理
                self.cached_pil_image = self._parse_pcx_data(palette_data or self.palette_data)
                
            if self.cached_pil_image:
                self.width = self.cached_pil_image.width
                self.height = self.cached_pil_image.height
                
            return self.cached_pil_image
        except Exception as e:
            logging.error(f"Error creating PIL image for sprite {self.group},{self.image}: {e}")
            return None
    
    def _parse_pcx_data(self, palette_data: Optional[bytes]) -> Optional[Image.Image]:
        """PCXデータをパース"""
        # PCX解析のロジックを実装
        # ここでは簡略化
        try:
            if len(self.image_data) < 128:
                return None
                
            # PCXヘッダーの解析
            header = struct.unpack('<BBBBIHHHHH64s', self.image_data[:128])
            manufacturer = header[0]
            version = header[1]
            encoding = header[2]
            bits_per_pixel = header[3]
            
            if manufacturer != 10:  # PCXマジックナンバー
                return None
                
            xmin, ymin, xmax, ymax = header[4:8]
            width = xmax - xmin + 1
            height = ymax - ymin + 1
            
            if width <= 0 or height <= 0:
                return None
                
            # 色深度に応じた処理
            if bits_per_pixel == 8:
                return self._parse_pcx_8bit(width, height, palette_data)
            else:
                # その他の色深度は未実装
                return None
                
        except Exception as e:
            logging.error(f"PCX parsing error: {e}")
            return None
    
    def _parse_pcx_8bit(self, width: int, height: int, palette_data: Optional[bytes]) -> Optional[Image.Image]:
        """8bit PCXデータをパース"""
        try:
            data_start = 128
            pixel_data = []
            pos = data_start
            
            # RLE展開
            while pos < len(self.image_data) and len(pixel_data) < width * height:
                byte = self.image_data[pos]
                pos += 1
                
                if byte >= 192:  # RLEマーカー
                    count = byte - 192
                    if pos < len(self.image_data):
                        value = self.image_data[pos]
                        pos += 1
                        pixel_data.extend([value] * count)
                else:
                    pixel_data.append(byte)
            
            if len(pixel_data) != width * height:
                return None
                
            # 8bitインデックスカラー画像を作成
            img = Image.new('P', (width, height))
            img.putdata(pixel_data)
            
            # パレット設定
            if palette_data and len(palette_data) >= 768:
                img.putpalette(palette_data[:768])
            else:
                # デフォルトグレースケールパレット
                palette = []
                for i in range(256):
                    palette.extend([i, i, i])
                img.putpalette(palette)
            
            return img.convert('RGBA')
            
        except Exception as e:
            logging.error(f"8bit PCX parsing error: {e}")
            return None


class SFFParser:
    """SFFファイルパーサークラス"""
    
    @staticmethod
    def parse_sff(file_path: str) -> Tuple[Dict[Tuple[int, int], SFFSprite], List[bytes]]:
        """SFFファイルを解析"""
        sprites = {}
        palettes = []
        
        if not os.path.exists(file_path):
            return sprites, palettes
            
        try:
            with open(file_path, 'rb') as f:
                # ヘッダー読み込み
                header = f.read(16)
                if len(header) < 16:
                    return sprites, palettes
                    
                signature = header[:4]
                if signature == b'ElcD':
                    # SFF v2
                    return SFFParser._parse_sff_v2(f, file_path)
                elif signature[:3] == b'Elc':
                    # SFF v1
                    return SFFParser._parse_sff_v1(f, file_path)
                else:
                    logging.error(f"Unknown SFF format: {signature}")
                    return sprites, palettes
                    
        except Exception as e:
            logging.error(f"Error parsing SFF file {file_path}: {e}")
            return sprites, palettes
    
    @staticmethod
    def _parse_sff_v1(f, file_path: str) -> Tuple[Dict[Tuple[int, int], SFFSprite], List[bytes]]:
        """SFF v1形式を解析"""
        sprites = {}
        palettes = []
        
        try:
            f.seek(0)
            header = f.read(32)
            
            if len(header) < 32:
                return sprites, palettes
                
            # ヘッダー解析
            signature = header[:4]
            version = struct.unpack('<I', header[4:8])[0]
            groups = struct.unpack('<I', header[8:12])[0]
            images = struct.unpack('<I', header[12:16])[0]
            next_offset = struct.unpack('<I', header[16:20])[0]
            subheader_size = struct.unpack('<I', header[20:24])[0]
            
            # パレット読み込み（デフォルト）
            palette_data = f.read(768)
            if len(palette_data) == 768:
                palettes.append(palette_data)
            
            # スプライトデータ読み込み
            for i in range(images):
                f.seek(32 + 768 + i * 32)  # スプライトヘッダー位置
                sprite_header = f.read(32)
                
                if len(sprite_header) < 32:
                    break
                    
                next_file = struct.unpack('<I', sprite_header[0:4])[0]
                length = struct.unpack('<I', sprite_header[4:8])[0]
                x = struct.unpack('<h', sprite_header[8:10])[0]
                y = struct.unpack('<h', sprite_header[10:12])[0]
                group = struct.unpack('<H', sprite_header[12:14])[0]
                image = struct.unpack('<H', sprite_header[14:16])[0]
                
                if length > 0:
                    f.seek(next_file)
                    image_data = f.read(length)
                    
                    sprite = SFFSprite(group, image, x, y, image_data, palette_data)
                    sprites[(group, image)] = sprite
                    
        except Exception as e:
            logging.error(f"Error parsing SFF v1: {e}")
            
        return sprites, palettes
    
    @staticmethod
    def _parse_sff_v2(f, file_path: str) -> Tuple[Dict[Tuple[int, int], SFFSprite], List[bytes]]:
        """SFF v2形式を解析"""
        # SFF v2の実装は複雑なため、既存のsffv2_parser.pyを使用
        try:
            from sffv2_parser import parse_sff as parse_sff_v2
            return parse_sff_v2(file_path)
        except ImportError:
            logging.error("sffv2_parser module not found")
            return {}, []


def parse_sff(file_path: str) -> Tuple[Dict[Tuple[int, int], SFFSprite], List[bytes]]:
    """SFFファイルを解析（互換性関数）"""
    return SFFParser.parse_sff(file_path)
