# -*- coding: utf-8 -*-
"""
SFFファイルパーサーモジュール
SFF（Sprite File Format）ファイルの読み込みと処理を行う

- SFF v1 / v2 自動判別
- v1: サブヘッダ連鎖の正確な走査、リンク(size=0)解決、PCX/PNG読込、パレット継承
- v2: 既存の sffv2_parser に委譲
"""

from __future__ import annotations

import os
import io
import struct
import logging
from typing import Dict, List, Optional, Tuple, Any

from PIL import Image

__all__ = [
    "SFFSprite",
    "SFFParser",
    "parse_sff",
    "get_sprite_pil",
    "get_sprite_rgba",
]

# ------------------------------------------------------------
# スプライトコンテナ
# ------------------------------------------------------------

class SFFSprite:
    """SFFスプライトデータ（共通）"""
    def __init__(
        self,
        group: int,
        image: int,
        axis_x: int,
        axis_y: int,
        image_data: bytes,
        *,
        is_link: bool = False,
        link_index: int = -1,
        pal_flag: int = 0,
        embedded_palette: Optional[bytes] = None,
    ):
        self.group = group
        self.image = image
        self.axis_x = axis_x
        self.axis_y = axis_y
        self.image_data = image_data  # PCX/PNG バイト列想定
        self.pal_flag = pal_flag      # v1 subheader の palette フラグ
        self.is_link = is_link
        self.link_index = link_index

        # 解析時に見つかった PCX 末尾の 768B パレット（RGB×256）
        self.embedded_palette = embedded_palette

        # キャッシュ
        self._pil_cache: Optional[Image.Image] = None

    # --- 表示用ヘルパ ---
    def get_pil(self, fallback_palette: Optional[bytes] = None) -> Optional[Image.Image]:
        """PIL Image を返す（PCX/PNG 自動判定・パレット適用）"""
        if self._pil_cache is not None:
            return self._pil_cache
        try:
            data = self.image_data or b""
            if not data:
                return None

            if data.startswith(b"\x89PNG"):
                img = Image.open(io.BytesIO(data))
                img.load()
                self._pil_cache = img.convert("RGBA")
                return self._pil_cache

            # PCX 想定（Pillow は PCX 読める）
            img = Image.open(io.BytesIO(data))
            img.load()

            # PCX は P モードで読み出し → 必要ならパレット適用
            if img.mode != "P":
                self._pil_cache = img.convert("RGBA")
                return self._pil_cache

            # パレット決定（優先順：埋め込み > 引数 > 現在の画像の既存パレット > グレースケール）
            palette = None
            if self.embedded_palette and len(self.embedded_palette) >= 768:
                palette = list(self.embedded_palette[:768])
            elif fallback_palette and len(fallback_palette) >= 768:
                palette = list(fallback_palette[:768])
            else:
                # Pillow が持っているパレットを使えるならそのまま
                p = img.getpalette()
                if p and len(p) >= 768:
                    palette = p[:768]
                else:
                    # 最低限のグレースケール
                    palette = []
                    for i in range(256):
                        palette.extend([i, i, i])

            img = img.convert("P")
            img.putpalette(palette)
            self._pil_cache = img.convert("RGBA")
            return self._pil_cache

        except Exception as e:
            logging.error(f"Sprite({self.group},{self.image}) PIL化失敗: {e}")
            return None


# ------------------------------------------------------------
# v1 ユーティリティ
# ------------------------------------------------------------

def _extract_pcx_tail_palette(data: bytes) -> Optional[bytes]:
    """
    PCX 末尾のパレット（0x0C + 768B）を抽出して返す。
    """
    if len(data) >= 769 and data[-769] == 0x0C:
        return data[-768:]
    return None


def _read_sff_v1(path: str) -> Tuple[Dict[Tuple[int, int], SFFSprite], List[bytes]]:
    """
    SFF v1 を読み込む。
    仕様に基づき、ヘッダ→subfile 連鎖を辿って各 PCX/PNG を抜き出す。
    """
    sprites: Dict[Tuple[int, int], SFFSprite] = {}
    palettes: List[bytes] = []  # 共有/参照用に 768B RGB を入れておく（index0優先）

    if not os.path.isfile(path):
        return sprites, palettes

    with open(path, "rb") as f:
        # 32B ヘッダ
        # signature(12s), ver(4B), nb_groups(I), nb_images(I),
        # subfile_offset(I), subheader_size(I), palette_type(I), reserved(I*3)
        hdr = f.read(32)
        if len(hdr) < 32:
            return sprites, palettes

        sig = hdr[:12]                      # b'ElecbyteSpr'
        ver1, ver2, ver3, ver4 = hdr[12:16]
        nb_groups = struct.unpack_from("<I", hdr, 16)[0]
        nb_images = struct.unpack_from("<I", hdr, 20)[0]
        first_sub_offset = struct.unpack_from("<I", hdr, 24)[0]
        subheader_size = struct.unpack_from("<I", hdr, 28)[0]

        # v1 はサブヘッダ 32B
        if subheader_size != 32:
            # 一部派生で違う値のケースもあるが、基本 32
            subheader_size = 32

        # 連鎖を辿る
        index = 0
        offset = first_sub_offset

        # リンク解決用に subfile 情報を一次保管
        # （size=0 の時、link_index で参照）
        sub_infos: List[Dict[str, Any]] = []

        while offset != 0:
            f.seek(offset)
            raw = f.read(subheader_size)
            if len(raw) < subheader_size:
                break

            # サブヘッダ構造（32B）
            # next(I), size(I), ax(h), ay(h), group(h), image(h), link_index(H), palette(B), reserved(??)
            next_off = struct.unpack_from("<I", raw, 0)[0]
            size = struct.unpack_from("<I", raw, 4)[0]
            ax = struct.unpack_from("<h", raw, 8)[0]
            ay = struct.unpack_from("<h", raw, 10)[0]
            group = struct.unpack_from("<H", raw, 12)[0]
            image_no = struct.unpack_from("<H", raw, 14)[0]
            link_index = struct.unpack_from("<H", raw, 16)[0]
            pal_flag = raw[18] if len(raw) > 18 else 0

            img_data = b""
            embedded_pal = None
            is_link = False

            if size > 0:
                # 直後に画像データ
                f.seek(offset + subheader_size)
                img_data = f.read(size)

                # PNG 直判
                if img_data.startswith(b"\x89PNG"):
                    pass
                else:
                    # PCX 末尾パレット
                    embedded_pal = _extract_pcx_tail_palette(img_data)
            else:
                # リンク
                is_link = True

            sub_infos.append(
                dict(
                    index=index,
                    offset=offset,
                    next=next_off,
                    size=size,
                    axis_x=ax,
                    axis_y=ay,
                    group=group,
                    image=image_no,
                    link_index=link_index,
                    pal_flag=pal_flag,
                    data=img_data,
                    embedded_palette=embedded_pal,
                )
            )

            index += 1
            offset = next_off

        # リンク解決（size=0 は link_index の data を使う）
        for info in sub_infos:
            if info["size"] == 0:
                li = info.get("link_index", -1)
                if 0 <= li < len(sub_infos):
                    src = sub_infos[li]
                    # 参照元の画像データ・埋め込みパレットを拝借
                    info["data"] = src["data"]
                    info["embedded_palette"] = src.get("embedded_palette", None)
                else:
                    # 無効リンク → 空画像にしておく
                    info["data"] = b""
                    info["embedded_palette"] = None
                    logging.warning(
                        f"SFFv1 link unresolved: idx {info['index']} -> {li}"
                    )

        # 「直近の有効パレット」を作っておく（パレット継承）
        last_valid_palette: Optional[bytes] = None

        for info in sub_infos:
            data = info["data"]
            group = info["group"]
            image_no = info["image"]
            pal_flag = info["pal_flag"]

            # パレット更新（PCX 末尾 or PNG パレットはここでは扱わない）
            if data and not data.startswith(b"\x89PNG"):
                pal = info.get("embedded_palette")
                if pal and len(pal) >= 768:
                    last_valid_palette = pal

            spr = SFFSprite(
                group=group,
                image=image_no,
                axis_x=info["axis_x"],
                axis_y=info["axis_y"],
                image_data=data,
                is_link=(info["size"] == 0),
                link_index=info.get("link_index", -1),
                pal_flag=pal_flag,
                embedded_palette=info.get("embedded_palette"),
            )

            sprites[(group, image_no)] = spr

        # 最終的な共有パレットを palettes[0] に入れておく
        if last_valid_palette is not None:
            palettes.append(bytes(last_valid_palette))
        else:
            # 無い場合はグレースケールを 1 本
            gray = bytearray()
            for i in range(256):
                gray += bytes([i, i, i])
            palettes.append(bytes(gray))

    return sprites, palettes


# ------------------------------------------------------------
# v2 デリゲート
# ------------------------------------------------------------

def _read_sff_v2(path: str) -> Tuple[Dict[Tuple[int, int], SFFSprite], List[bytes]]:
    """
    SFF v2 は sffv2_parser に委譲。戻りを SFFSprite に詰め替える。
    sffv2_parser.parse_sff は (dict, palettes) を返す前提。
    """
    try:
        from sffv2_parser import parse_sff as parse_sff_v2  # 同梱モジュール
    except Exception as e:
        logging.error(f"sffv2_parser の読み込みに失敗: {e}")
        return {}, []

    sprites_out: Dict[Tuple[int, int], SFFSprite] = {}
    palettes_out: List[bytes] = []

    try:
        parsed_sprites, parsed_palettes = parse_sff_v2(path)
        # parsed_sprites は {(group,image): {'data': bytes, 'x': int, 'y': int, ...}} 想定
        for (g, i), meta in parsed_sprites.items():
            data = meta.get("data", b"")
            ax = meta.get("x", 0)
            ay = meta.get("y", 0)
            spr = SFFSprite(
                group=g,
                image=i,
                axis_x=ax,
                axis_y=ay,
                image_data=data,
                is_link=False,
                link_index=-1,
                pal_flag=0,
                embedded_palette=None,
            )
            sprites_out[(g, i)] = spr

        # v2 側のパレット（RGBA/PLTE）→ 768B RGB 想定または None
        for pal in parsed_palettes or []:
            if pal and len(pal) >= 768:
                palettes_out.append(bytes(pal[:768]))
    except Exception as e:
        logging.error(f"SFF v2 解析中にエラー: {e}")
        return {}, []

    # パレットが 0 本なら最低 1 本は用意
    if not palettes_out:
        gray = bytearray()
        for v in range(256):
            gray += bytes([v, v, v])
        palettes_out.append(bytes(gray))

    return sprites_out, palettes_out


# ------------------------------------------------------------
# 署名判定 & パブリック API
# ------------------------------------------------------------

class SFFParser:
    """SFF v1/v2 統合パーサ"""

    @staticmethod
    def parse_sff(file_path: str) -> Tuple[Dict[Tuple[int, int], SFFSprite], List[bytes]]:
        """
        SFF を解析して (sprites, palettes) を返す。
        sprites: {(group,image): SFFSprite}
        palettes: [768B RGB, ...]（少なくとも 1 本は入れる）
        """
        sprites: Dict[Tuple[int, int], SFFSprite] = {}
        palettes: List[bytes] = []

        if not os.path.isfile(file_path):
            logging.error(f"SFF file not found: {file_path}")
            return sprites, palettes

        try:
            with open(file_path, "rb") as f:
                head = f.read(64)  # 署名判定用に少し多めに読む
        except Exception as e:
            logging.error(f"SFF 読み込み失敗: {e}")
            return sprites, palettes

        # 既存の「b'Elec' を Unknown として弾いてしまう」問題を修正
        # v2 判定：ヘッダ中に 'SFF2' の文字が見える（ElecbyteSFF2）
        if b"SFF2" in head or b"ElecbyteSFF2" in head:
            return _read_sff_v2(file_path)
        else:
            # それ以外は v1 として読む（ElecbyteSpr ...）
            return _read_sff_v1(file_path)


def parse_sff(file_path: str) -> Tuple[Dict[Tuple[int, int], SFFSprite], List[bytes]]:
    """互換関数（従来API維持）"""
    return SFFParser.parse_sff(file_path)


# ------------------------------------------------------------
# 画像取り出しヘルパ（SffCharaViewer から使いやすい形）
# ------------------------------------------------------------

def get_sprite_pil(
    sprites: Dict[Tuple[int, int], SFFSprite],
    palettes: List[bytes],
    group: int,
    image: int,
    *,
    palette_index: int = 0,
) -> Optional[Image.Image]:
    """
    指定 (group, image) の PIL.Image を返す（RGBA）。
    パレットは palettes[palette_index] をフォールバックとして使用。
    """
    spr = sprites.get((group, image))
    if not spr:
        return None

    fallback = None
    if 0 <= palette_index < len(palettes):
        fallback = palettes[palette_index]

    return spr.get_pil(fallback_palette=fallback)


def get_sprite_rgba(
    sprites: Dict[Tuple[int, int], SFFSprite],
    palettes: List[bytes],
    group: int,
    image: int,
    *,
    palette_index: int = 0,
) -> Optional[bytes]:
    """
    指定 (group, image) の RGBA バイト列（width*height*4）を返す。
    Qt で QImage(QImage.Format_RGBA8888) に渡す用途など向け。
    """
    img = get_sprite_pil(sprites, palettes, group, image, palette_index=palette_index)
    if img is None:
        return None
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img.tobytes()
