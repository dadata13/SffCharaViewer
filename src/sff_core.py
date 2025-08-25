# -*- coding: utf-8 -*-
"""
sff_core.py  —  SFF v1/v2 共通読み込みコア
- 既存(SffCharaViewer等)の import 互換:  from src.sff_core import SFFParser, parse_sff
- 戻り値互換:  (sprites_dict, palettes_list)
    sprites_dict[(group, image)] -> SFFSprite
    palettes_list: [bytes(768), ...]  # 256*3 RGB
"""

from __future__ import annotations
import os
import io
import struct
import logging
from typing import Dict, Tuple, List, Optional

try:
    # 同一フォルダ内 or package 相対
    from .sffv2_parser import SFF2, decode_sprite  # type: ignore
except Exception:
    from sffv2_parser import SFF2, decode_sprite  # type: ignore

try:
    from .sff_parser import (
        analyze_sff_v1,
        extract_sffv1,
        convert_pcx_to_image,
        extract_palette_from_pcx_data,
        reverse_act_palette,
    )  # type: ignore
except Exception:
    from sff_parser import (
        analyze_sff_v1,
        extract_sffv1,
        convert_pcx_to_image,
        extract_palette_from_pcx_data,
        reverse_act_palette,
    )  # type: ignore

from PIL import Image


# ------------------------------
# Sprite object (互換インターフェース)
# ------------------------------
class SFFSprite:
    def __init__(
        self,
        group: int,
        image_no: int,
        axis_x: int = 0,
        axis_y: int = 0,
        pil_img: Optional[Image.Image] = None,
        raw_indexed: Optional[bytes] = None,
        palette: Optional[bytes] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ):
        self.group = group
        self.image = image_no
        self.x = axis_x
        self.y = axis_y
        self._pil = pil_img  # RGBA が望ましい
        self._raw_indexed = raw_indexed
        self._palette = palette  # 768 bytes (RGB) or None
        self.width = width if width is not None else (pil_img.width if pil_img else 0)
        self.height = height if height is not None else (pil_img.height if pil_img else 0)

    def get_pil_image(self, palette_data: Optional[bytes] = None) -> Optional[Image.Image]:
        """
        互換API: PIL.Image を返す。内部キャッシュがあればそれを返す。
        palette_data が渡された場合、インデックス画像を再合成してRGBAで返す。
        """
        if self._pil is not None:
            return self._pil

        # インデックス + パレットから再構成（v2のindexed保持などのため）
        if self._raw_indexed is not None and (palette_data or self._palette):
            pal = palette_data or self._palette
            if pal and len(pal) >= 768 and self.width and self.height:
                img = Image.frombytes("P", (self.width, self.height), self._raw_indexed)
                img.putpalette(list(pal[:768]))
                self._pil = img.convert("RGBA")
                return self._pil

        return None


# ------------------------------
# ユーティリティ
# ------------------------------
def _is_sff_v2(header: bytes) -> bool:
    # SFFv2: 先頭に "ElecbyteSFF" を含み、ヘッダ長 0x80、テーブルオフセットが妥当 など
    try:
        if len(header) >= 16 and b'Elecbyte' in header[:16] and b'SFF' in header[:16]:
            # v2ではオフセット類が 0x24 以降にある
            # 無茶な数値でないか軽くチェック
            return True
        return False
    except Exception:
        return False


def _is_sff_v1(header: bytes) -> bool:
    # v1は先頭12バイトに "ElecbyteSpr"（実装/派生で微妙に違うことがある）を含むのが一般的
    # 黒画面になっていたケースを拾うため、先頭 "Elec" を見たら v1 として扱う
    if len(header) >= 4 and header[:4] == b'Elec':
        return True
    if len(header) >= 12 and b'Elecbyte' in header[:12]:
        return True
    return False


# ------------------------------
# v1 読み込み（旧ロジックをそのまま活用）
# ------------------------------
def _load_sff_v1(path: str) -> Tuple[Dict[Tuple[int, int], SFFSprite], List[bytes]]:
    """
    sff_parser.py の analyze_sff_v1 / extract_sffv1 を使って
    旧挙動（正しくパレットを適用）で復元する。
    """
    sprites: Dict[Tuple[int, int], SFFSprite] = {}
    palettes: List[bytes] = []

    if not os.path.isfile(path):
        return sprites, palettes

    # 一時 JSON（解析結果）をメモリに持ちたいので BytesIO を使う実装に変更
    # ただし sff_parser.analyze_sff_v1 はファイル出力を前提なので小さなテンポラリを使う
    import tempfile, json
    with open(path, "rb") as f:
        # 解析結果を temp json へ
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
            analysis_json = tmp.name
        try:
            analyze_sff_v1(f, analysis_json)
        except Exception as e:
            logging.error(f"SFFv1 analyze error: {e}")
            os.unlink(analysis_json)
            return sprites, palettes

    # 画像群を復元
    image_objects: List[Image.Image] = []
    image_info_list: List[dict] = []
    try:
        with open(path, "rb") as f2:
            # extract_sffv1 は palettes を引数で受け取り、(9000,0) 等から共有パレットを構築する
            extract_sffv1(
                f2,                 # バイナリストリーム
                analysis_json,      # 上で作成した解析JSON
                image_objects,      # 出力: PIL画像（Pモード or 既にパレット適用済）
                image_info_list,    # 出力: 画像メタ
                act_palette=None,   # ACTは外部から与えられない想定
                palette_list=palettes
            )
    except Exception as e:
        logging.error(f"SFFv1 extract error: {e}")
    finally:
        try:
            os.unlink(analysis_json)
        except Exception:
            pass

    # マッピング作成
    for pil_img, info in zip(image_objects, image_info_list):
        try:
            group = int(info.get("group_no", 0))
            image_no = int(info.get("image_no", 0))
            ax = int(info.get("axisx", 0))
            ay = int(info.get("axisy", 0))
        except Exception:
            group = info.get("group_no", 0)
            image_no = info.get("image_no", 0)
            ax = info.get("axisx", 0)
            ay = info.get("axisy", 0)

        # 可能なら RGBA 化（Viewerでの合成を安定させる）
        try:
            pil_rgba = pil_img.convert("RGBA") if pil_img.mode != "RGBA" else pil_img
        except Exception:
            pil_rgba = pil_img

        sp = SFFSprite(group, image_no, ax, ay, pil_img=pil_rgba)
        sprites[(group, image_no)] = sp

    # palettes は 768 bytes RGB のみ（extract_sffv1 が整備済）
    return sprites, palettes


# ------------------------------
# v2 読み込み（sffv2_parser.SFF2 を使用）
# ------------------------------
def _load_sff_v2(path: str) -> Tuple[Dict[Tuple[int, int], SFFSprite], List[bytes]]:
    sprites: Dict[Tuple[int, int], SFFSprite] = {}
    palettes: List[bytes] = []

    s2 = SFF2(os.path.abspath(path))

    # パレットテーブル → 768bytes(RGB) に整形して格納
    for idx in range(len(s2.palettes)):
        pal_rgba = s2._get_palette(idx)  # (256,4) RGBA (sffv2_parser 側で整備)
        # 768bytes(RGB) に落とす（アルファは無視）
        rgb = bytearray()
        for r, g, b, a in pal_rgba:
            rgb += bytes((int(r), int(g), int(b)))
        palettes.append(bytes(rgb))

    # スプライトの復元
    for (g, n), rec in s2.sprites.items():
        w = rec["width"]
        h = rec["height"]
        fmt = rec["fmt"]
        off = rec["file_off"]
        ln = rec["file_len"]
        pal_index = rec["pal_index"]

        blob = s2.data[off : off + ln]
        decoded, mode = decode_sprite(fmt, blob, w, h)

        # インデックスならパレットを当ててRGBA化
        if mode == "indexed":
            pal = palettes[pal_index] if 0 <= pal_index < len(palettes) else None
            if pal and len(decoded) == w * h:
                img = Image.frombytes("P", (w, h), bytes(decoded))
                img.putpalette(list(pal[:768]))
                img = img.convert("RGBA")
                sp = SFFSprite(g, n, 0, 0, pil_img=img, width=w, height=h)
            else:
                # 失敗時は透明
                img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                sp = SFFSprite(g, n, 0, 0, pil_img=img, width=w, height=h)
        else:
            # RGBA 直
            img = Image.frombytes("RGBA", (w, h), bytes(decoded))
            sp = SFFSprite(g, n, 0, 0, pil_img=img, width=w, height=h)

        sprites[(g, n)] = sp

    return sprites, palettes


# ------------------------------
# 公開API（既存互換）
# ------------------------------
class SFFParser:
    """既存互換のパーサークラス（静的メソッドのみ）"""

    @staticmethod
    def parse_sff(file_path: str) -> Tuple[Dict[Tuple[int, int], SFFSprite], List[bytes]]:
        return parse_sff(file_path)


def parse_sff(file_path: str) -> Tuple[Dict[Tuple[int, int], SFFSprite], List[bytes]]:
    """
    既存互換のトップレベル関数。
    SffCharaViewer / ステージプレビュー側はこれを呼ぶ前提。
    """
    sprites: Dict[Tuple[int, int], SFFSprite] = {}
    palettes: List[bytes] = []

    if not os.path.isfile(file_path):
        logging.error(f"SFF file not found: {file_path}")
        return sprites, palettes

    # 先頭で判別し、確実にフォールバック
    try:
        with open(file_path, "rb") as f:
            head = f.read(64)
    except Exception as e:
        logging.error(f"Failed to read header: {e}")
        return sprites, palettes

    try:
        if _is_sff_v2(head):
            try:
                return _load_sff_v2(file_path)
            except Exception as e:
                logging.warning(f"SFFv2 parse failed, fallback to v1: {e}")

        if _is_sff_v1(head):
            return _load_sff_v1(file_path)

        # 不明でも v1 側に投げてみる（旧ファイル互換のため）
        logging.warning("Unknown SFF signature, trying v1 parser as fallback.")
        return _load_sff_v1(file_path)

    except Exception as e:
        logging.error(f"SFF parse error: {e}")
        return sprites, palettes
