import struct
from PIL import Image
from io import BytesIO
from typing import Optional, Tuple, List

# デバッグフラグ
DEBUG_SFF = True
SYNTHESIZE_EMPTY_PALETTE = True  # 全黒/全透明パレット検出時に視覚化用パレットを生成

def debug_print(msg):
    if DEBUG_SFF:
        print(msg)

def is_png_data(data):
    """データがPNG形式かどうかを判定（シグネチャスニッフィング）"""
    if len(data) < 8:
        return False
    
    # PNG署名: 89 50 4E 47 0D 0A 1A 0A
    png_signature = b'\x89PNG\x0D\x0A\x1A\x0A'
    
    # 先頭から検索
    if data[:8] == png_signature:
        debug_print(f"[DEBUG] PNG signature found at offset 0: {' '.join(f'{b:02x}' for b in data[:8])}")
        return True
    
    # 4バイトオフセットから検索（圧縮データの場合）
    if len(data) >= 12 and data[4:12] == png_signature:
        debug_print(f"[DEBUG] PNG signature found at offset 4: {' '.join(f'{b:02x}' for b in data[4:12])}")
        return True
    
    # 他の一般的なオフセットもチェック
    for offset in [8, 16]:
        if len(data) >= offset + 8 and data[offset:offset+8] == png_signature:
            debug_print(f"[DEBUG] PNG signature found at offset {offset}: {' '.join(f'{b:02x}' for b in data[offset:offset+8])}")
            return True
    
    return False

def extract_png_data(data):
    """データからPNG部分を抽出"""
    if len(data) < 8:
        return None
    
    png_signature = b'\x89PNG\x0D\x0A\x1A\x0A'
    
    # 先頭から検索
    if data[:8] == png_signature:
        debug_print(f"[DEBUG] PNG data starts at offset 0")
        return data
    
    # 4バイトオフセットから検索（圧縮データの場合）
    if len(data) >= 12 and data[4:12] == png_signature:
        debug_print(f"[DEBUG] PNG data starts at offset 4")
        return data[4:]
    
    # 他のオフセットから検索
    for offset in [8, 16]:
        if len(data) >= offset + 8 and data[offset:offset+8] == png_signature:
            debug_print(f"[DEBUG] PNG data starts at offset {offset}")
            return data[offset:]
    
    return None

def decode_png(data, width, height):
    """PNG画像データをデコード"""
    try:
        debug_print(f"[DEBUG] PNG decoding: data_size={len(data)}, expected_size={width}x{height}")
        
        # PNG データを抽出
        png_data = extract_png_data(data)
        if png_data is None:
            debug_print(f"[ERROR] No PNG data found in provided data")
            return bytearray([0] * width * height), 'indexed', None
        
        debug_print(f"[DEBUG] Extracted PNG data size: {len(png_data)}")
        
        # PNG画像をPILで読み込み
        img = Image.open(BytesIO(png_data))
        img.load()

        def parse_png_chunks(raw: bytes):
            """最小限のPNGチャンク解析: PLTE / tRNS を抽出して返す"""
            if len(raw) < 8 or raw[:8] != b'\x89PNG\r\n\x1a\n':
                return None, None
            pos = 8
            plte = None
            trns = None
            while pos + 8 <= len(raw):
                try:
                    length = struct.unpack_from('>I', raw, pos)[0]
                    ctype = raw[pos+4:pos+8]
                except struct.error:
                    break
                pos += 8
                if pos + length + 4 > len(raw):
                    break
                cdata = raw[pos:pos+length]
                pos += length  # data終端
                crc = raw[pos:pos+4]
                pos += 4
                if ctype == b'PLTE':
                    plte = cdata  # 3*N bytes
                elif ctype == b'tRNS':
                    trns = cdata
                elif ctype == b'IEND':
                    break
            return plte, trns
        
        debug_print(f"[DEBUG] PNG image mode: {img.mode}, size: {img.size}")
        debug_print(f"[DEBUG] PNG info: {img.info}")
        
        # サイズ確認
        if img.size != (width, height):
            debug_print(f"[WARNING] PNG size mismatch: {img.size} vs expected {(width, height)}")
            # リサイズ
            img = img.resize((width, height), Image.NEAREST)
        
        # PNG内部がパレットモードの場合の詳細処理
        if img.mode == 'P':
            debug_print("[DEBUG] PNG: パレットモード検出、詳細解析開始")
            
            # 元の画像データを確認
            raw_data = img.tobytes()
            debug_print(f"[DEBUG] Raw indexed data size: {len(raw_data)}")
            if len(raw_data) >= 20:
                indices = list(raw_data[:20])
                debug_print(f"[DEBUG] First 20 pixel indices: {indices}")
                unique_indices = set(raw_data)
                debug_print(f"[DEBUG] Unique indices used: {sorted(unique_indices)[:20]}")  # 最初の20個
            
            # パレット情報をデバッグ出力
            palette_data = img.getpalette()
            transparency = img.info.get('transparency')
            all_black_palette = False
            if palette_data:
                debug_print(f"[DEBUG] Original PNG palette data length: {len(palette_data)}")
                # 使用されているインデックスのパレット色を確認
                first_colors = []
                for i in range(0, min(60, len(palette_data)), 3):
                    r = palette_data[i] if i < len(palette_data) else 0
                    g = palette_data[i+1] if i+1 < len(palette_data) else 0  
                    b = palette_data[i+2] if i+2 < len(palette_data) else 0
                    first_colors.append((r, g, b))
                debug_print(f"[DEBUG] Original palette first 20 colors: {first_colors}")
                
                # 非黒色をカウント
                non_black_count = 0
                for i in range(0, len(palette_data), 3):
                    r = palette_data[i] if i < len(palette_data) else 0
                    g = palette_data[i+1] if i+1 < len(palette_data) else 0  
                    b = palette_data[i+2] if i+2 < len(palette_data) else 0
                    if r > 0 or g > 0 or b > 0:
                        non_black_count += 1
                debug_print(f"[DEBUG] Non-black colors in original palette: {non_black_count}")
                
                # パレットが全て黒の場合の特別処理
                if non_black_count == 0:
                    debug_print("[WARNING] All palette colors are black -> PLTE再解析 & 合成試行")
                    plte_chunk, trns_chunk = parse_png_chunks(png_data)
                    if plte_chunk is not None:
                        debug_print(f"[DEBUG] Raw PLTE chunk length={len(plte_chunk)}")
                        # PLTEチャンクから直接パレット再構築
                        rebuilt = list(plte_chunk)
                        non_black_plte = 0
                        for i in range(0, len(rebuilt), 3):
                            if any(rebuilt[i+j] > 0 for j in range(3) if i+j < len(rebuilt)):
                                non_black_plte += 1
                        debug_print(f"[DEBUG] Non-black colors in PLTE chunk: {non_black_plte}")
                        if non_black_plte > 0:
                            # Pillow内部パレットを上書き（不足は0埋め）
                            if len(rebuilt) < 256*3:
                                rebuilt.extend([0]* (256*3 - len(rebuilt)))
                            img.putpalette(rebuilt)
                            palette_data = rebuilt
                            non_black_count = non_black_plte
                            debug_print("[DEBUG] Applied PLTE chunk palette override")
                    if non_black_count == 0:
                        all_black_palette = True
                    if non_black_count == 0 and SYNTHESIZE_EMPTY_PALETTE:
                        debug_print("[INFO] Still all black. Synthesizing debug palette")
                        synth = []
                        for i in range(256):
                            if i == 0:
                                synth += [0,0,0]
                            else:
                                # 彩度の高い擬似カラー (周期性で散らす)
                                r = (i * 37) & 0xFF
                                g = (i * 73) & 0xFF
                                b = (i * 151) & 0xFF
                                synth += [r, g, b]
                        img.putpalette(synth)
                        palette_data = synth
                        debug_print("[DEBUG] Synth palette applied")
            
            # すべて黒パレットの場合は SFF パレット適用前提でインデックスデータを返す
            if all_black_palette:
                # 透明度処理: 全 tRNS が 0 なら index0 のみ透明扱いにする
                if isinstance(transparency, (bytes, bytearray)):
                    if len(transparency) >= 1 and all(b == 0 for b in transparency):
                        debug_print("[DEBUG] Ignoring all-zero tRNS except index0")
                return bytearray(raw_data), 'indexed', None

            # 複数の変換方法を試行（正常パレット）
            conversion_methods = [
                ('RGB', lambda x: x.convert('RGB')),
                ('RGBA', lambda x: x.convert('RGBA')),
                ('L then RGB', lambda x: x.convert('L').convert('RGB')),
            ]
            
            for method_name, convert_func in conversion_methods:
                try:
                    debug_print(f"[DEBUG] Trying conversion method: {method_name}")
                    converted_img = convert_func(img)
                    
                    if method_name != 'RGBA':
                        converted_img = converted_img.convert('RGBA')
                    
                    rgba_data = converted_img.tobytes()
                    
                    # 最初の数ピクセルをチェック
                    if len(rgba_data) >= 16:
                        pixel_colors = []
                        for i in range(0, min(16, len(rgba_data)), 4):
                            r, g, b, a = rgba_data[i:i+4]
                            pixel_colors.append((r, g, b, a))
                        debug_print(f"[DEBUG] {method_name} - First 4 pixel colors: {pixel_colors[:4]}")
                        
                        # 非透明・非黒ピクセルをチェック
                        non_black_pixels = 0
                        for i in range(0, len(rgba_data), 4):
                            r, g, b, a = rgba_data[i:i+4]
                            if (r > 0 or g > 0 or b > 0) and a > 0:
                                non_black_pixels += 1
                        
                        debug_print(f"[DEBUG] {method_name} - Non-black visible pixels: {non_black_pixels}")
                        
                        # 有効なピクセルが見つかった場合はそれを使用
                        if non_black_pixels > 0:
                            debug_print(f"[DEBUG] Using {method_name} conversion (found valid pixels)")
                            # RGBA化した結果が有効
                            return bytearray(rgba_data), 'rgba', None
                        
                except Exception as e:
                    debug_print(f"[DEBUG] {method_name} conversion failed: {e}")
            
            # 全ての変換が失敗した場合はRGBA変換を使用
            debug_print("[WARNING] All conversion methods show black pixels, using RGBA anyway")
            img_rgba = img.convert('RGBA')
            rgba_data = img_rgba.tobytes()
            return bytearray(rgba_data), 'rgba', None
            
        else:
            # True Color / Alpha画像の場合
            debug_print(f"[DEBUG] PNG: {img.mode}モード、RGBAとして処理")
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            decoded = bytearray(img.tobytes())
            
            # 最初の数ピクセルをデバッグ出力
            if len(decoded) >= 16:
                pixel_colors = []
                for i in range(0, min(16, len(decoded)), 4):
                    r, g, b, a = decoded[i:i+4]
                    pixel_colors.append((r, g, b, a))
                debug_print(f"[DEBUG] First 4 pixel colors (RGBA): {pixel_colors[:4]}")
            
            return decoded, 'rgba', None
    except Exception as e:
        debug_print(f"[ERROR] PNG decoding failed: {e}")
        import traceback
        debug_print(f"[ERROR] Traceback: {traceback.format_exc()}")
        decoded = bytearray([0] * width * height)
        return decoded, 'indexed', None

def decode_rle8(data, width, height):
    data = data[4:] if len(data) > 4 else data
    out = bytearray()
    i = 0
    while i < len(data):
        if data[i] & 0xC0 == 0x40:
            run = data[i] & 0x3F
            i += 1
            val = data[i] if i < len(data) else 0
            out.extend([val] * run)
            i += 1
        else:
            out.append(data[i])
            i += 1
    return out[:width * height]

def decode_rle5(data, width, height):
    out = bytearray()
    i = 0
    while i < len(data):
        if i + 1 >= len(data):
            break
        runlen = data[i] + 1
        i += 1
        ctrl = data[i]
        i += 1
        if ctrl & 0x80:
            if i >= len(data): break
            val = data[i]
            i += 1
            out.extend([val] * runlen)
        else:
            count = ctrl & 0x7F
            for _ in range(count):
                if i >= len(data): break
                b = data[i]
                i += 1
                r = (b >> 5) + 1
                val = b & 0x1F
                out.extend([val] * r)
    return out[:width * height]

def decode_lz5(data, width, height):
    if len(data) < 4:
        raise ValueError("LZ5 data too short")
    decompressed_size = struct.unpack_from('<I', data, 0)[0]
    dst = bytearray()
    srcpos = 4
    recycle_byte = 0
    recycle_count = 0
    while srcpos < len(data) and len(dst) < decompressed_size:
        ctrl = data[srcpos]
        srcpos += 1
        for bit in range(8):
            if srcpos >= len(data) or len(dst) >= decompressed_size:
                break
            is_lz = (ctrl >> bit) & 1
            if is_lz:
                b1 = data[srcpos]
                srcpos += 1
                if (b1 & 0x3F) == 0x00:
                    if srcpos + 1 >= len(data): break
                    b2 = data[srcpos]
                    b3 = data[srcpos + 1]
                    srcpos += 2
                    offset = (((b1 & 0xC0) << 2) | b2) + 1
                    length = b3 + 3
                else:
                    length = (b1 & 0x3F) + 1
                    recycle_byte |= ((b1 & 0xC0) >> 6) << (6 - 2 * recycle_count)
                    recycle_count += 1
                    if recycle_count == 4:
                        offset = recycle_byte + 1
                        recycle_byte = 0
                        recycle_count = 0
                    else:
                        if srcpos >= len(data): break
                        offset = data[srcpos] + 1
                        srcpos += 1
                for _ in range(length):
                    dst.append(dst[-offset] if offset <= len(dst) else 0)
            else:
                b1 = data[srcpos]
                srcpos += 1
                val = b1 & 0x1F
                count = b1 >> 5
                if count == 0:
                    if srcpos >= len(data): break
                    b2 = data[srcpos]
                    srcpos += 1
                    count = b2 + 8
                dst.extend([val] * count)
    return dst[:width * height]

def decode_sprite(fmt, data, width, height):
    debug_print(f"[DEBUG] decode_sprite: fmt={fmt}, data_size={len(data)}, size={width}x{height}")
    
    # データの先頭をデバッグ出力
    if len(data) >= 16:
        debug_print(f"[DEBUG] Data header: {' '.join(f'{b:02x}' for b in data[:16])}")
    
    try:
        # 初期化
        decoded = None
        mode = 'indexed'
        
        # PNG形式の場合（fmt=10 かつ 署名で確認）
        if fmt == 10:
            debug_print(f"[DEBUG] fmt=10 detected, checking PNG signature...")
            if is_png_data(data):
                debug_print(f"[DEBUG] Valid PNG signature confirmed, processing as PNG")
                decoded, mode, png_palette = decode_png(data, width, height)
                return decoded, mode
            else:
                debug_print(f"[WARNING] fmt=10 but invalid PNG signature, treating as unknown format")
                # PNG署名がない場合は空データとして処理
                decoded = bytearray([0] * width * height)
        
        # 署名による自動PNG検出（fmt=10以外でも）
        elif is_png_data(data):
            debug_print(f"[DEBUG] PNG signature detected in fmt={fmt}, processing as PNG")
            decoded, mode, png_palette = decode_png(data, width, height)
            return decoded, mode
            
        elif fmt in (0, 1):
            decoded = bytearray(data[:width * height])
        elif fmt == 2:
            decoded = decode_rle8(data, width, height)
        elif fmt == 3:
            decoded = decode_rle5(data, width, height)
        elif fmt in (4, 25):
            decoded = decode_lz5(data, width, height)
        else:
            # 未知のフォーマットの場合、データの特徴から推測を試行
            debug_print(f"[WARNING] Unknown format {fmt}, attempting auto-detection")
            
            # データサイズから推測
            expected_indexed = width * height
            expected_rgba = width * height * 4
            
            if len(data) == expected_indexed:
                debug_print(f"[INFO] Auto-detected as raw indexed (fmt=0/1)")
                decoded = bytearray(data)
            elif len(data) == expected_rgba:
                debug_print(f"[INFO] Auto-detected as raw RGBA")
                decoded = bytearray(data)
            elif len(data) > 4 and data[:4] == struct.pack('<I', expected_indexed):
                debug_print(f"[INFO] Auto-detected as LZ5 compression (fmt=4)")
                decoded = decode_lz5(data, width, height)
            elif len(data) > 0:
                # RLE8を試行
                try:
                    debug_print(f"[INFO] Attempting RLE8 decoding (fmt=2)")
                    decoded = decode_rle8(data, width, height)
                    if len(decoded) != expected_indexed:
                        raise ValueError("RLE8 size mismatch")
                except:
                    # RLE5を試行
                    try:
                        debug_print(f"[INFO] Attempting RLE5 decoding (fmt=3)")
                        decoded = decode_rle5(data, width, height)
                        if len(decoded) != expected_indexed:
                            raise ValueError("RLE5 size mismatch")
                    except:
                        # 最後の手段として生データとして扱う
                        debug_print(f"[WARNING] All decompression failed, using raw data")
                        decoded = bytearray(data[:expected_indexed])
                        while len(decoded) < expected_indexed:
                            decoded.append(0)
            else:
                # 空のデータの場合
                decoded = bytearray([0] * width * height)
    
    except Exception as e:
        debug_print(f"[ERROR] decode_sprite failed: {e}")
        # フォールバック: 透明な画像を作成
        decoded = bytearray([0] * width * height)
        mode = 'indexed'
    
    # decoded変数の確認（安全性のため）
    if decoded is None:
        debug_print(f"[ERROR] decoded is None, creating fallback data")
        decoded = bytearray([0] * width * height)
        mode = 'indexed'
    
    # モード判定
    if len(decoded) == width * height * 4:
        mode = 'rgba'
    elif len(decoded) == width * height:
        mode = 'indexed'
    else:
        debug_print(f"[WARNING] Unexpected decoded size: {len(decoded)} vs {width}x{height}, padding/truncating")
        # サイズ調整
        expected_size = width * height
        if len(decoded) > expected_size:
            decoded = decoded[:expected_size]
        else:
            while len(decoded) < expected_size:
                decoded.append(0)
        mode = 'indexed'
    
    return decoded, mode

class SFFv2Reader:
    def __init__(self, file_path):
        # 基本コンテナ
        self.file_path = file_path
        self.header = {}
        self.sprites = []
        self.palettes = []
        # パレット使用状況
        self.palette_usage_count = []
        self.dedicated_palette_indices = set()  # 使用回数1回のパレット = 専用パレット

    def read_header(self, f):
        f.seek(0)
        sig = f.read(12)
        debug_print(f"[DEBUG] SFF signature: {sig}")
        if sig != b'ElecbyteSpr\x00':
            raise ValueError("Invalid SFF file signature")
        self.header['version'] = struct.unpack('<4B', f.read(4))
        debug_print(f"[DEBUG] SFF version: {self.header['version']}")
        if self.header['version'] not in [(0, 0, 0, 2), (0, 1, 0, 2)]:
            raise ValueError("Not an SFFv2 file")
        f.seek(36)
        (
            self.header['sprite_offset'],
            self.header['num_sprites'],
            self.header['palette_offset'],
            self.header['num_palettes'],
            self.header['l_offset'],
            self.header['t_offset']
        ) = struct.unpack('<IIIIII', f.read(24))
        
        debug_print(f"[DEBUG] SFF header info:")
        debug_print(f"  - sprite_offset: {self.header['sprite_offset']}")
        debug_print(f"  - num_sprites: {self.header['num_sprites']}")
        debug_print(f"  - palette_offset: {self.header['palette_offset']}")
        debug_print(f"  - num_palettes: {self.header['num_palettes']}")
        debug_print(f"  - l_offset: {self.header['l_offset']}")
        debug_print(f"  - t_offset: {self.header['t_offset']}")

    def read_palettes(self, f):
        self.palettes = []
        for i in range(self.header['num_palettes']):
            f.seek(self.header['palette_offset'] + i * 16)
            _, _, _ = struct.unpack('<3h', f.read(6))  # group no, index no, _
            link = struct.unpack('<H', f.read(2))[0]
            ofs, siz = struct.unpack('<II', f.read(8))
            if siz == 0:
                self.palettes.append(None)
                continue
            f.seek(self.header['l_offset'] + ofs)
            data = f.read(siz)
            palette = [(r, g, b, 255) for r, g, b, a in struct.iter_unpack('BBBB', data)]
            while len(palette) < 256:
                palette.append((0, 0, 0, 255))
            palette[0] = (0, 0, 0, 0)
            self.palettes.append(palette)
        for i, p in enumerate(self.palettes):
            if p is None:
                self.palettes[i] = self.palettes[link]

    def read_sprites(self, f):
        self.sprites = []
        f.seek(self.header['sprite_offset'])
        # 使用回数カウンタ初期化
        self.palette_usage_count = [0] * self.header.get('num_palettes', 0)
        for sprite_index in range(self.header['num_sprites']):
            d = f.read(28)
            if len(d) < 28:
                break
            
            # デバッグ: バイナリデータをダンプ
            debug_hex = ' '.join(f'{b:02x}' for b in d)
            debug_print(f"[DEBUG] Sprite {sprite_index} raw data: {debug_hex}")
            
            (
                group_no, sprite_no, width, height,
                x_axis, y_axis, link_idx, fmt, coldepth,
                data_ofs, data_len, pal_idx, flags
            ) = struct.unpack('<HHHHhhHBBIIHH', d)
            
            # デバッグ: 解析結果を出力
            debug_print(f"[DEBUG] Sprite {sprite_index}: group={group_no}, sprite={sprite_no}, "
                  f"size={width}x{height}, fmt={fmt}, pal_idx={pal_idx}")
            
            # fmt値の妥当性チェック
            if fmt > 100:  # 異常に大きな値の場合
                debug_print(f"[WARNING] Suspicious fmt value {fmt} for sprite {sprite_index} "
                      f"(group {group_no}, sprite {sprite_no})")
                # バイト順を試してみる
                alt_unpack = struct.unpack('>HHHHhhHBBIIHH', d)
                debug_print(f"[DEBUG] Alternative big-endian unpack: fmt={alt_unpack[7]}")
            
            if (flags & 1) == 0:
                data_ofs += self.header['l_offset']
            else:
                data_ofs += self.header['t_offset']
            self.sprites.append({
                'group_no': group_no,
                'sprite_no': sprite_no,
                'width': width,
                'height': height,
                'x_axis': x_axis,
                'y_axis': y_axis,
                'link_idx': link_idx,
                'data_ofs': data_ofs,
                'data_len': data_len,
                'coldepth': coldepth,
                'pal_idx': pal_idx,
                'fmt': fmt,
                'image_data': None  # SFFv2では遅延読み込み（必要時にdecode_sprite_v2で取得）
            })
            # パレット使用回数カウント
            if 0 <= pal_idx < len(self.palette_usage_count):
                self.palette_usage_count[pal_idx] += 1

        # 専用パレット集合作成（使用1回）
        self.dedicated_palette_indices = {i for i, c in enumerate(self.palette_usage_count) if c == 1}
        debug_print(f"[DEBUG] Dedicated palette indices: {sorted(self.dedicated_palette_indices)}")

def decode_sprite_v2(reader, index, palette_override=None, visited_indices=None):
    if visited_indices is None:
        visited_indices = set()
    
    if index in visited_indices:
        # 循環参照の場合は1x1の透明画像を返す
        return bytearray([0]), [(0, 0, 0, 0)] * 256, 1, 1, 'indexed'
    
    visited_indices.add(index)
    sprite = reader.sprites[index]
    
    # リンク判定
    # SFFv2 では data_len==0 かつ link_idx 指定、もしくは互換的対応で width/height==0 の場合にリンク扱い
    if sprite.get('data_len', 0) == 0 or sprite['width'] == 0 or sprite['height'] == 0:
        link_idx = sprite.get('link_idx', None)
        if link_idx is not None and 0 <= link_idx < len(reader.sprites) and link_idx not in visited_indices:
            # リンク先を再帰取得
            decoded, palette, lw, lh, mode = decode_sprite_v2(reader, link_idx, palette_override, visited_indices)
            # 幅高さが 0 の場合はリンク元の値で補完（軸はリンク元独自なのでそのまま viewer 側で利用）
            if sprite['width'] > 0 and sprite['height'] > 0 and (lw != sprite['width'] or lh != sprite['height']):
                # 基本的には同じはず。異なるならサイズはリンク元の情報を尊重せずリンク先データをそのまま返す
                pass
            return decoded, palette, sprite['width'] if sprite['width']>0 else lw, sprite['height'] if sprite['height']>0 else lh, mode
        else:
            # 無効リンク → 透明 1x1
            return bytearray([0]), [(0,0,0,0)]*256, 1, 1, 'indexed'
    
    with open(reader.file_path, 'rb') as f:
        f.seek(sprite['data_ofs'])
        data = f.read(sprite['data_len'])
    
    # PNG形式の判定をより厳密に行う
    is_fmt10 = (sprite['fmt'] == 10)
    has_png_signature = is_png_data(data)
    
    debug_print(f"[DEBUG] Sprite {index}: fmt={sprite['fmt']}, is_fmt10={is_fmt10}, has_png_signature={has_png_signature}")
    
    # PNG形式の場合は特別な処理
    if is_fmt10 and has_png_signature:
        debug_print(f"[DEBUG] Processing confirmed PNG sprite at index {index}")
        decoded, mode, png_palette = decode_png(data, sprite['width'], sprite['height'])
        
        # PNG画像は常にRGBAモードで処理（パレット問題を回避）
        if mode == 'rgba':
            palette = []  # viewer側でNone扱いエラー回避
            debug_print(f"[DEBUG] PNG processed as RGBA (palette unused)")
        elif mode == 'indexed' and png_palette:
            # 旧形式の場合のみパレット使用
            palette = png_palette
            debug_print(f"[DEBUG] Using PNG internal palette with {len(png_palette)} colors")
            # PNG内部パレットの最初の数色をデバッグ出力
            debug_print(f"[DEBUG] PNG palette preview: {png_palette[:3]}")
            
            # 画像データの整合性チェック
            if len(decoded) > 0:
                max_index = max(decoded) if decoded else 0
                debug_print(f"[DEBUG] PNG image data: size={len(decoded)}, max_index={max_index}")
                if max_index >= len(png_palette):
                    debug_print(f"[WARNING] PNG index {max_index} exceeds palette size {len(png_palette)}")
        else:
            # indexed かつ png_palette なし → 全黒パレットだったので SFF パレット採用
            if mode == 'indexed':
                # 専用パレットなら override を無視
                sprite_pal = sprite['pal_idx']
                if sprite_pal in getattr(reader, 'dedicated_palette_indices', set()):
                    pal_idx = sprite_pal
                    debug_print(f"[DEBUG] Forcing dedicated palette {pal_idx} (PNG indexed)")
                else:
                    pal_idx = palette_override if palette_override is not None else sprite_pal
                palette = reader.palettes[pal_idx] if pal_idx < len(reader.palettes) else []
                debug_print(f"[DEBUG] PNG indexed fallback using SFF palette index {pal_idx}")
            else:
                # PNG処理に失敗
                debug_print(f"[WARNING] PNG processing failed, falling back to SFF palette")
                pal_idx = palette_override if palette_override is not None else sprite['pal_idx']
                palette = reader.palettes[pal_idx] if pal_idx < len(reader.palettes) else []
                debug_print(f"[DEBUG] PNG fallback to SFF palette index {pal_idx}")
    else:
        # 従来形式の処理（fmt=10でもPNG署名がない場合を含む）
        if is_fmt10 and not has_png_signature:
            debug_print(f"[WARNING] fmt=10 but no PNG signature, treating as standard format")
        
        decoded, mode = decode_sprite(sprite['fmt'], data, sprite['width'], sprite['height'])
        # 専用パレットは強制適用
        sprite_pal = sprite['pal_idx']
        if sprite_pal in getattr(reader, 'dedicated_palette_indices', set()):
            pal_idx = sprite_pal
            debug_print(f"[DEBUG] Forcing dedicated palette {pal_idx} (standard decode)")
        else:
            pal_idx = palette_override if palette_override is not None else sprite_pal
        palette = reader.palettes[pal_idx] if pal_idx < len(reader.palettes) else None
    
    return decoded, palette, sprite['width'], sprite['height'], mode
