# -*- coding: utf-8 -*-
"""
AIRファイルパーサーモジュール
AIR（Animation Information Resource）ファイルの読み込みと処理を行う
"""

import os
import re
import logging
from typing import Dict, List, Optional, Any


class AIRFrame:
    """AIRフレームデータクラス"""
    
    def __init__(self, group: int, image: int, x: int = 0, y: int = 0, 
                 duration: int = 1, flip: int = 0, **kwargs):
        self.group = group
        self.image = image
        self.x = x
        self.y = y
        self.duration = duration  # フレーム持続時間
        self.time = duration      # 時間情報（互換性のため）
        self.flip = flip
        
        # 拡張属性
        self.flip_h = kwargs.get('flip_h', False)
        self.flip_v = kwargs.get('flip_v', False)
        self.blend_mode = kwargs.get('blend_mode', 'normal')
        self.alpha_value = kwargs.get('alpha_value', 1.0)
        self.clsn1 = kwargs.get('clsn1', [])
        self.clsn2 = kwargs.get('clsn2', [])
        self.loopstart = kwargs.get('loopstart', False)
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式で返す（既存コードとの互換性）"""
        return {
            'group': self.group,
            'image': self.image,
            'x': self.x,
            'y': self.y,
            'duration': self.duration,
            'time': self.time,  # update_anim_infoで使用される
            'flip': self.flip,
            'flip_h': self.flip_h,
            'flip_v': self.flip_v,
            'blend_mode': self.blend_mode,
            'alpha_value': self.alpha_value,
            'clsn1': self.clsn1,
            'clsn2': self.clsn2,
            'loopstart': self.loopstart
        }


class AIRAnimation:
    """AIRアニメーションデータクラス"""
    
    def __init__(self, animation_no: int):
        self.animation_no = animation_no
        self.frames: List[AIRFrame] = []
        self.loop_start_index = -1
    
    def add_frame(self, frame: AIRFrame):
        """フレームを追加"""
        if frame.loopstart:
            self.loop_start_index = len(self.frames)
        self.frames.append(frame)
    
    def get_frame(self, index: int) -> Optional[AIRFrame]:
        """指定インデックスのフレームを取得"""
        if 0 <= index < len(self.frames):
            return self.frames[index]
        return None
    
    def get_total_frames(self) -> int:
        """総フレーム数を取得"""
        return len(self.frames)
    
    def get_frame_list(self) -> List[Dict[str, Any]]:
        """フレームリストを辞書形式で取得（既存コードとの互換性）"""
        return [frame.to_dict() for frame in self.frames]


class AIRParser:
    """AIRファイルパーサークラス"""
    
    @staticmethod
    def parse_air(path: str) -> Dict[int, List[Dict[str, int]]]:
        """AIRファイルを解析（既存インターフェース互換）"""
        animations = AIRParser.parse_air_full(path)
        
        # 既存形式に変換
        result = {}
        for anim_no, animation in animations.items():
            result[anim_no] = animation.get_frame_list()
        
        return result
    
    @staticmethod
    def parse_air_full(path: str) -> Dict[int, AIRAnimation]:
        """AIRファイルを完全解析"""
        animations: Dict[int, AIRAnimation] = {}
        current_animation: Optional[AIRAnimation] = None
        current_clsn1_default = []
        current_clsn2_default = []
        current_clsn1_default_count = 0
        current_clsn2_default_count = 0
        
        # フレーム専用の一時リスト
        frame_clsn1 = None
        frame_clsn2 = None
        
        if not os.path.isfile(path):
            logging.warning(f"AIR file not found: {path}")
            return animations
        
        try:
            with open(path, 'r', encoding='utf-8-sig', errors='ignore') as f:
                for line_no, raw_line in enumerate(f, 1):
                    line = raw_line.strip()
                    if not line or line.startswith(';'):
                        continue
                    
                    # Begin Action の検出
                    m = re.match(r'^\[?\s*begin\s+action\s+(-?\d+)\s*\]?$', line, re.I)
                    if m:
                        anim_no = int(m.group(1))
                        current_animation = AIRAnimation(anim_no)
                        animations[anim_no] = current_animation
                        
                        # 新しいアニメーション開始時にリセット
                        current_clsn1_default = []
                        current_clsn2_default = []
                        frame_clsn1 = None
                        frame_clsn2 = None
                        continue
                    
                    if current_animation is None:
                        continue
                    
                    # 当たり判定情報の処理
                    # CLSNキーワードの場合は直接処理
                    if 'clsn' in line.lower():
                        try:
                            current_clsn1_default_count, current_clsn2_default_count, frame_clsn1, frame_clsn2 = \
                                AIRParser._parse_clsn_line(
                                    line, current_animation.frames, current_clsn1_default, current_clsn2_default,
                                    current_clsn1_default_count, current_clsn2_default_count,
                                    frame_clsn1, frame_clsn2
                                )
                            continue
                        except Exception as e:
                            logging.warning(f"Error parsing clsn line {line_no}: {e}")
                            continue
                    
                    # 座標データの可能性がある行の処理
                    # - CLSN宣言の後に座標待ちの状態
                    # - 行が数値のみ（4つの座標値）または Clsn1[n] = / Clsn2[n] = 形式
                    coords = re.findall(r'-?\d+', line)
                    parts = [p.strip() for p in line.split(',')]
                    
                    # Clsn1[n] = または Clsn2[n] = 形式かどうか
                    is_clsn_format = bool(re.search(r'clsn[12]\[\d+\]\s*=', line.lower()))
                    
                    # 座標データかどうかの判定：
                    # 1. 4つの数値がある
                    # 2. CLSN待ちの状態である、またはClsn形式
                    # 3. パラメータが4つまでかつすべて数値、またはClsn形式
                    is_coords = (len(coords) >= 4 and 
                                (is_clsn_format or 
                                 (len(parts) <= 4 and 
                                  all(p.strip().lstrip('-').isdigit() or p.strip() == '' for p in parts) and
                                  (current_clsn1_default_count > 0 or current_clsn2_default_count > 0 or 
                                   frame_clsn1 is not None or frame_clsn2 is not None))))
                    
                    if is_coords:
                        try:
                            current_clsn1_default_count, current_clsn2_default_count, frame_clsn1, frame_clsn2 = \
                                AIRParser._parse_clsn_line(
                                    line, current_animation.frames, current_clsn1_default, current_clsn2_default,
                                    current_clsn1_default_count, current_clsn2_default_count,
                                    frame_clsn1, frame_clsn2
                                )
                            continue
                        except Exception as e:
                            logging.warning(f"Error parsing coords line {line_no}: {e}")
                            continue
                    
                    # LoopStart の検出
                    if line.lower().strip() in ('loopstart', 'loop start'):
                        final_clsn1 = frame_clsn1 if frame_clsn1 is not None else current_clsn1_default
                        final_clsn2 = frame_clsn2 if frame_clsn2 is not None else current_clsn2_default
                        
                        loop_frame = AIRFrame(-1, -1, 0, 0, 1, 0,
                                            clsn1=final_clsn1.copy(),
                                            clsn2=final_clsn2.copy(),
                                            loopstart=True)
                        current_animation.add_frame(loop_frame)
                        
                        frame_clsn1 = None
                        frame_clsn2 = None
                        continue
                    
                    # フレームデータの解析
                    parts = [p.strip() for p in line.split(',')]
                    if len(parts) < 3:
                        continue
                    
                    try:
                        group = int(parts[0])
                        image = int(parts[1])
                        x = int(parts[2]) if len(parts) > 2 and parts[2] else 0
                        y = int(parts[3]) if len(parts) > 3 and parts[3] else 0
                        duration = int(parts[4]) if len(parts) > 4 and parts[4] else 1
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
                        
                        # 従来のflip値も保持
                        flip_legacy = 0
                        if flip_h and flip_v:
                            flip_legacy = 3
                        elif flip_h:
                            flip_legacy = 1
                        elif flip_v:
                            flip_legacy = 2
                        
                        # フレームオブジェクト作成
                        # Clsn1/Clsn2の優先順位：個別指定があればそれを、なければDefault
                        if frame_clsn1 is not None:
                            final_clsn1 = frame_clsn1
                        else:
                            final_clsn1 = current_clsn1_default
                        if frame_clsn2 is not None:
                            final_clsn2 = frame_clsn2
                        else:
                            final_clsn2 = current_clsn2_default

                        frame = AIRFrame(group, image, x, y, duration, flip_legacy,
                                       flip_h=flip_h, flip_v=flip_v,
                                       blend_mode=blend_mode, alpha_value=alpha_value,
                                       clsn1=final_clsn1.copy(),
                                       clsn2=final_clsn2.copy())

                        current_animation.add_frame(frame)

                        # 個別指定は1フレームのみ有効なのでクリア
                        frame_clsn1 = None
                        frame_clsn2 = None
                        
                    except (ValueError, IndexError) as e:
                        logging.warning(f"Error parsing frame data line {line_no}: {e}")
                        continue
                        
        except Exception as e:
            logging.error(f"Error parsing AIR file {path}: {e}")
        
        return animations
    
    @staticmethod
    def _parse_clsn_line(line: str, current_frames: List[AIRFrame],
                        current_clsn1_default: List[Dict], 
                        current_clsn2_default: List[Dict],
                        current_clsn1_default_count: int,
                        current_clsn2_default_count: int,
                        frame_clsn1: Optional[List],
                        frame_clsn2: Optional[List]) -> tuple:
        """当たり判定行を解析"""
        
        line_lower = line.lower().strip()
        line_orig = line.strip()
        
        # Clsn1Defaultの処理
        if line_lower.startswith('clsn1default'):
            match = re.search(r'clsn1default\s*:\s*(\d+)', line_lower)
            if match:
                count = int(match.group(1))
                current_clsn1_default_count = count
                current_clsn1_default.clear()
                logging.debug(f"Clsn1Default: {count}個")
        
        # Clsn2Defaultの処理
        elif line_lower.startswith('clsn2default'):
            match = re.search(r'clsn2default\s*:\s*(\d+)', line_lower)
            if match:
                count = int(match.group(1))
                current_clsn2_default_count = count
                current_clsn2_default.clear()
                logging.debug(f"Clsn2Default: {count}個")
        
        # Clsn1の処理
        elif line_lower.startswith('clsn1'):
            if 'default' not in line_lower:
                match = re.search(r'clsn1\s*:\s*(\d+)', line_lower)
                if match:
                    count = int(match.group(1))
                    if frame_clsn1 is None:
                        frame_clsn1 = []
                    logging.debug(f"Clsn1: {count}個")
                else:
                    # Clsn1[n] = 形式の座標データの場合
                    eq_pos = line_orig.find('=')
                    if eq_pos > 0:
                        coord_part = line_orig[eq_pos + 1:].strip()
                        coords = re.findall(r'-?\d+', coord_part)
                        if len(coords) >= 4:
                            try:
                                clsn_data = {
                                    'x1': int(coords[0]),
                                    'y1': int(coords[1]),
                                    'x2': int(coords[2]),
                                    'y2': int(coords[3])
                                }
                                if frame_clsn1 is not None:
                                    frame_clsn1.append(clsn_data)
                                    logging.debug(f"Clsn1座標追加（個別）: {clsn_data}")
                                elif current_clsn1_default_count > 0 and len(current_clsn1_default) < current_clsn1_default_count:
                                    current_clsn1_default.append(clsn_data)
                                    logging.debug(f"Clsn1Default座標追加: {clsn_data}")
                            except (ValueError, IndexError) as e:
                                logging.warning(f"Clsn1座標データ解析エラー: {e}")
        
        # Clsn2の処理
        elif line_lower.startswith('clsn2'):
            if 'default' not in line_lower:
                match = re.search(r'clsn2\s*:\s*(\d+)', line_lower)
                if match:
                    count = int(match.group(1))
                    if frame_clsn2 is None:
                        frame_clsn2 = []
                    logging.debug(f"Clsn2: {count}個")
                else:
                    # Clsn2[n] = 形式の座標データの場合
                    eq_pos = line_orig.find('=')
                    if eq_pos > 0:
                        coord_part = line_orig[eq_pos + 1:].strip()
                        coords = re.findall(r'-?\d+', coord_part)
                        if len(coords) >= 4:
                            try:
                                clsn_data = {
                                    'x1': int(coords[0]),
                                    'y1': int(coords[1]),
                                    'x2': int(coords[2]),
                                    'y2': int(coords[3])
                                }
                                if frame_clsn2 is not None:
                                    frame_clsn2.append(clsn_data)
                                    logging.debug(f"Clsn2座標追加（個別）: {clsn_data}")
                                elif current_clsn2_default_count > 0 and len(current_clsn2_default) < current_clsn2_default_count:
                                    current_clsn2_default.append(clsn_data)
                                    logging.debug(f"Clsn2Default座標追加: {clsn_data}")
                            except (ValueError, IndexError) as e:
                                logging.warning(f"Clsn2座標データ解析エラー: {e}")
        
        # 座標データの処理（様々な形式に対応）
        else:
            # Clsn形式の判定（Clsn1[n] = x1,y1, x2, y2 または単純な x1, y1, x2, y2）
            is_clsn_format = bool(re.search(r'clsn[12]\[\d+\]\s*=', line_lower))
            
            if is_clsn_format:
                # Clsn1[n] = または Clsn2[n] = 形式の場合、= 以降の座標データを抽出
                eq_pos = line_orig.find('=')
                if eq_pos > 0:
                    coord_part = line_orig[eq_pos + 1:].strip()
                    coords = re.findall(r'-?\d+', coord_part)
                else:
                    coords = []
            else:
                # 通常の座標データ形式
                coords = re.findall(r'-?\d+', line_orig)
            
            if len(coords) >= 4:
                try:
                    clsn_data = {
                        'x1': int(coords[0]),
                        'y1': int(coords[1]),
                        'x2': int(coords[2]),
                        'y2': int(coords[3])
                    }
                    
                    # Clsn1[n] = またはClsn2[n] = 形式の場合、どちらに追加するか判定
                    if is_clsn_format:
                        if 'clsn2' in line_lower:
                            if frame_clsn2 is not None:
                                frame_clsn2.append(clsn_data)
                                logging.debug(f"Clsn2座標追加（個別）: {clsn_data}")
                            elif current_clsn2_default_count > 0 and len(current_clsn2_default) < current_clsn2_default_count:
                                current_clsn2_default.append(clsn_data)
                                logging.debug(f"Clsn2Default座標追加: {clsn_data}")
                        elif 'clsn1' in line_lower:
                            if frame_clsn1 is not None:
                                frame_clsn1.append(clsn_data)
                                logging.debug(f"Clsn1座標追加（個別）: {clsn_data}")
                            elif current_clsn1_default_count > 0 and len(current_clsn1_default) < current_clsn1_default_count:
                                current_clsn1_default.append(clsn_data)
                                logging.debug(f"Clsn1Default座標追加: {clsn_data}")
                    else:
                        # 通常の座標データ形式の場合（優先順位順）
                        if frame_clsn2 is not None:
                            frame_clsn2.append(clsn_data)
                            logging.debug(f"Clsn2座標追加: {clsn_data}")
                        elif frame_clsn1 is not None:
                            frame_clsn1.append(clsn_data)
                            logging.debug(f"Clsn1座標追加: {clsn_data}")
                        elif current_clsn2_default_count > 0 and len(current_clsn2_default) < current_clsn2_default_count:
                            current_clsn2_default.append(clsn_data)
                            logging.debug(f"Clsn2Default座標追加: {clsn_data}")
                        elif current_clsn1_default_count > 0 and len(current_clsn1_default) < current_clsn1_default_count:
                            current_clsn1_default.append(clsn_data)
                            logging.debug(f"Clsn1Default座標追加: {clsn_data}")
                        
                except (ValueError, IndexError) as e:
                    logging.warning(f"座標データ解析エラー: {e}")
        
        return current_clsn1_default_count, current_clsn2_default_count, frame_clsn1, frame_clsn2


def parse_air(path: str) -> Dict[int, List[Dict[str, int]]]:
    """AIRファイルを解析（互換性関数）"""
    return AIRParser.parse_air(path)
