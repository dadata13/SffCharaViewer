import struct
from PIL import Image
from io import BytesIO
from typing import Optional, Tuple, List, Dict
import sys
import os
import numpy as np
from pathlib import Path
# ikemen_rle8モジュールをインポート - 移植により不要
# sys.path.append(os.path.dirname(os.path.dirname(__file__)))
# from ikemen_rle8_true import rle8_decode

def rle8_decode(data: bytes, width: int, height: int) -> tuple:
    """
    Ikemen GO 互換のRLE8デコード関数 (移植版・高速化)
    
    IkemenGOのソースコードに基づく実装:
    - 0x40-0x7F: RLE (n = cmd & 0x3F, value = next byte)
    - その他: リテラル値 (cmd自体が出力値)
    
    Returns:
        tuple: (デコードされたピクセルデータ, 横縞パターン検出フラグ)
    """
    size = width * height
    out = bytearray(size)
    i = 0
    j = 0
    
    debug_print(f"[RLE8_TRUE] Ikemen RLE8開始: size={size}, data_len={len(data)}")
    
    while j < len(out) and i < len(data):
        n = 1
        d = data[i]
        i += 1
        
        # RLE圧縮の場合 (0x40-0x7F)
        if (d & 0xC0) == 0x40:
            n = int(d & 0x3F)
            if i < len(data):
                d = data[i]
                i += 1
            else:
                break
        
        # n回繰り返し（高速化）
        end_pos = min(j + n, len(out))
        if end_pos > j:
            out[j:end_pos] = [d] * (end_pos - j)
            j = end_pos
    
    debug_print(f"[RLE8_TRUE] デコード完了: 出力サイズ={len(out)}")
    
    # 簡略化した横縞パターン検出
    stripe_detected = False
    if width > 0 and height >= 5:
        # 最初の5行をチェック
        check_width = min(width, 20)
        patterns = set()
        for row in range(min(5, height)):
            row_start = row * width
            row_data = tuple(out[row_start:row_start + check_width])
            patterns.add(row_data)
        
        # パターン数が少ない場合は横縞の可能性
        if len(patterns) <= 2:
            stripe_detected = True
            debug_print(f"[RLE8_WARNING] 横縞パターン検出: パターン数={len(patterns)}")
    
    return out, stripe_detected

# デバッグフラグ（本番環境では無効化して高速化）
DEBUG_SFF = False  # 画像表示問題の修正完了
DEBUG_PALETTE_DETAILS = False  # パレット詳細デバッグ（修正後は無効化）
SYNTHESIZE_EMPTY_PALETTE = True  # 全黒/全透明パレット検出時に視覚化用パレットを生成
FIX_SFFV2_ALPHA_CHANNEL = True   # SFFv2パレットのアルファ値を修正（index0=透明、他=不透明）
DISABLE_BGRA_RGBA_CONVERSION = True  # BGRAからRGBAへの変換を無効化（色合い問題の修正）

def debug_print(msg):
    if DEBUG_SFF:
        print(msg)

def debug_palette(msg):
    if DEBUG_PALETTE_DETAILS:
        print(msg)

def is_png_data(data):
    """データがPNG形式かどうかを判定（最適化版）"""
    if len(data) < 8:
        return False
    
    # PNG署名: 89 50 4E 47 0D 0A 1A 0A（高速比較）
    png_signature = b'\x89PNG\x0D\x0A\x1A\x0A'
    
    # 先頭から検索（最も一般的）
    if data[:8] == png_signature:
        return True
    
    # 4バイトオフセットから検索（圧縮データの場合）
    if len(data) >= 12 and data[4:12] == png_signature:
        return True
    
    return False

def extract_png_data(data):
    """データからPNG部分を抽出（最適化版）"""
    if len(data) < 8:
        return None
    
    png_signature = b'\x89PNG\x0D\x0A\x1A\x0A'
    
    # 先頭から検索（最も一般的）
    if data[:8] == png_signature:
        return data
    
    # 4バイトオフセットから検索
    if len(data) >= 12 and data[4:12] == png_signature:
        return data[4:]
    
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

def _decode_elecbyte_rle8_enhanced(data: bytes, width: int, height: int) -> Optional[np.ndarray]:
    """
    Enhanced Elecbyte RLE8 decoder based on sff2_decode.py implementation.
    
    This is an improved version that follows the exact Elecbyte RLE8 specification
    as used in the standalone sff2_decode.py module.
    """
    expected_pixels = width * height
    debug_print(f"[ENHANCED_RLE8] Starting decode: w={width}, h={height}, expected_pixels={expected_pixels}")
    debug_print(f"[ENHANCED_RLE8] Input data size: {len(data)} bytes")
    
    if len(data) < 4:
        debug_print(f"[ENHANCED_RLE8] Data too short: {len(data)} < 4")
        return np.zeros(expected_pixels, dtype=np.uint8)
    
    # Log data header for debugging
    header_sample = data[:min(32, len(data))]
    header_hex = ' '.join(f'{b:02x}' for b in header_sample)
    debug_print(f"[ENHANCED_RLE8] Data header: {header_hex}")
    
    # Skip the first 4 bytes (uncompressed length in little-endian)
    uncompressed_length = struct.unpack('<I', data[:4])[0]
    debug_print(f"[ENHANCED_RLE8] Uncompressed length from header: {uncompressed_length}")
    
    i = 4  # skip uncompressed length
    out: List[int] = []
    run_len = -1
    iteration = 0
    
    # Process bytes until we've produced the required number of pixels
    while len(out) < expected_pixels and i < len(data):
        b = data[i]
        i += 1
        
        if iteration < 10:  # Debug first few iterations
            debug_print(f"[ENHANCED_RLE8] Iteration {iteration}: byte=0x{b:02x}, run_len={run_len}, out_len={len(out)}")
        
        # Top two bits 01 indicate a run header; only apply if no
        # run length is currently pending.
        if (b & 0xC0) == 0x40 and run_len == -1:
            run_len = b & 0x3F
            if iteration < 10:
                debug_print(f"[ENHANCED_RLE8]   RLE header detected: run_len={run_len}")
        else:
            count = run_len if run_len != -1 else 1
            out.extend([b] * count)
            if iteration < 10:
                debug_print(f"[ENHANCED_RLE8]   Output {count} copies of 0x{b:02x}, total_out={len(out)}")
            run_len = -1
        
        iteration += 1
        
        # Safety break to prevent infinite loops
        if iteration > expected_pixels * 3:
            debug_print(f"[ENHANCED_RLE8] Safety break at iteration {iteration}")
            break
    
    # Pad with zeros if we didn't emit enough pixels
    if len(out) < expected_pixels:
        padding_needed = expected_pixels - len(out)
        debug_print(f"[ENHANCED_RLE8] Padding with {padding_needed} zeros")
        out.extend([0] * padding_needed)
    
    # Truncate if we have too many pixels
    result = np.array(out[:expected_pixels], dtype=np.uint8)
    
    # Statistics for debugging
    non_zero_count = np.count_nonzero(result)
    unique_values = len(np.unique(result))
    debug_print(f"[ENHANCED_RLE8] Decode completed: {len(result)} pixels")
    debug_print(f"[ENHANCED_RLE8] Non-zero pixels: {non_zero_count}/{len(result)} ({non_zero_count/len(result)*100:.1f}%)")
    debug_print(f"[ENHANCED_RLE8] Unique values: {unique_values}")
    
    return result

def _decode_fmt2_rle8_strict(data: bytes, w: int, h: int) -> bytes | None:
    """SFFv2のRLE8をIkemen互換で復号する。"""
    debug_print(f"[RLE8_STRICT_DEBUG] 開始: w={w}, h={h}, data_len={len(data)}")
    
    # 先頭4Bが rawsize (w*h little-endian) の場合だけスキップ
    original_data = data
    if len(data) >= 4 and int.from_bytes(data[:4], "little") == w * h:
        debug_print(f"[RLE8_STRICT_DEBUG] 先頭4バイトがrawsizeヘッダー({w*h})のためスキップ")
        data = data[4:]
        debug_print(f"[RLE8_STRICT_DEBUG] ヘッダースキップ後のデータサイズ: {len(data)}")
    
    debug_print(f"[RLE8_STRICT_DEBUG] RLE8デコード前データ先頭: {' '.join(f'{b:02x}' for b in data[:20])}")
    
    result = rle8_decode(data, w, h)  # ★Ikemen互換のフル実装を呼ぶ
    
    # 戻り値の処理（タプルまたは単一値）
    if isinstance(result, tuple) and len(result) == 2:
        out, has_stripes = result
        if has_stripes:
            debug_print(f"[RLE8_STRICT_DEBUG] 横縞パターン検出 - フォールバック検討が必要")
    else:
        out = result
        has_stripes = False
    
    if out is None or len(out) != w * h:
        debug_print(f"[RLE8_STRICT_DEBUG] デコード失敗: out={len(out) if out else 'None'}, 期待={w*h}")
        return None
    
    debug_print(f"[RLE8_STRICT_DEBUG] デコード成功: 出力サイズ={len(out)}")
    debug_print(f"[RLE8_STRICT_DEBUG] 出力データ統計: 非ゼロ={sum(1 for x in out if x != 0)}, ユニーク値={len(set(out))}")
    
    return bytes(out), has_stripes  # パターン検出結果も返す

def decode_rle8(data, width, height):
    """SFFv2 RLE8デコード（IkemenGO準拠版・高速化）"""
    if len(data) == 0:
        return bytearray(data)
    
    expected_size = width * height
    p = bytearray(expected_size)  # 事前にサイズ確定
    i = 0
    j = 0
    
    debug_print(f"[DEBUG] RLE8デコード開始: データ={len(data)}バイト, 期待={expected_size}バイト")
    
    # IkemenGOのアルゴリズムを高速化
    while j < expected_size and i < len(data):
        d = data[i]
        i += 1
        
        # RLE判定と長さ取得
        if (d & 0xC0) == 0x40:
            n = d & 0x3F
            if i < len(data):
                d = data[i]
                i += 1
            else:
                # データ終端処理
                remaining = expected_size - j
                if remaining > 0:
                    p[j:j+remaining] = [0] * remaining
                break
        else:
            n = 1
        
        # 高速データコピー
        end_pos = min(j + n, expected_size)
        if end_pos > j:
            p[j:end_pos] = [d] * (end_pos - j)
            j = end_pos
    
    return p

def decode_rle8_pcx(data: bytes, width: int, height: int) -> bytearray:
    """PCX方式RLE8デコード（IkemenGO準拠版 - 正確な実装）"""
    expected_size = width * height
    debug_print(f"[DEBUG] PCX RLE8デコード開始: データサイズ={len(data)}, 期待サイズ={width}x{height}={expected_size}")
    
    # データが空の場合
    if len(data) == 0:
        debug_print(f"[WARNING] PCX RLE8データが空です")
        return bytearray([0] * expected_size)
    
    # データヘッダーをダンプ（デバッグ用）
    header_bytes = data[:min(32, len(data))]
    header_hex = ' '.join(f'{b:02x}' for b in header_bytes)
    debug_print(f"[DEBUG] PCX RLE8 データ先頭: {header_hex}")
    
    out = bytearray(expected_size)
    i = 0          # input index
    j = 0          # output index
    
    # IkemenGOのPCX RLE8アルゴリズムを厳密に再現
    while j < len(out) and i < len(data):
        d = data[i]
        i += 1
        
        # PCX RLEのエンコーディング判定
        if (d & 0xC0) == 0xC0:  # 上位2ビットが11の場合はRLEカウント
            count = d & 0x3F    # 下位6ビットがカウント
            if count == 0:
                count = 64      # 0の場合は64を意味する
            
            # 次のバイトが実際の値
            if i >= len(data):
                debug_print("[WARNING] PCX RLE8: データ不足（値バイトなし）")
                break
                
            value = data[i]
            i += 1
            
            # カウント分だけ値を出力
            for _ in range(count):
                if j >= len(out):
                    break
                out[j] = value
                j += 1
        else:
            # 通常のバイト（RLEでない）
            if j < len(out):
                out[j] = d
                j += 1
    
    # 不足分を0で埋める
    while j < len(out):
        out[j] = 0
        j += 1
    
    # 結果検証
    actual_size = len(out)
    debug_print(f"[DEBUG] PCX RLE8デコード完了: 入力={len(data)}バイト -> 出力={actual_size}バイト (期待={expected_size})")
    
    return out

def decode_rle5(data, width, height):
    """SFFv2 RLE5デコード（IkemenGO準拠版）"""
    expected_size = width * height
    debug_print(f"[DEBUG] RLE5デコード開始: データサイズ={len(data)}, 期待サイズ={expected_size}")
    
    if len(data) == 0:
        return bytearray([0] * expected_size)
    
    out = bytearray(expected_size)
    i = 0
    j = 0
    
    while j < len(out) and i < len(data):
        # rl (run length) を読み取り
        rl = data[i]
        if i < len(data) - 1:
            i += 1
        
        if i >= len(data):
            break
            
        # dl (data length) と c (color) を読み取り
        dl = data[i] & 0x7F
        c = 0
        
        if (data[i] >> 7) != 0:
            if i < len(data) - 1:
                i += 1
            if i < len(data):
                c = data[i]
        
        if i < len(data) - 1:
            i += 1
        
        # データを出力
        while True:
            if j < len(out):
                out[j] = c
                j += 1
            
            rl -= 1
            if rl < 0:
                dl -= 1
                if dl < 0:
                    break
                
                if i < len(data):
                    c = data[i] & 0x1F
                    rl = (data[i] >> 5)
                    if i < len(data) - 1:
                        i += 1
                else:
                    break
    
    # サイズ調整
    if len(out) < expected_size:
        debug_print(f"[WARNING] RLE5: 出力不足、0で埋めます: {len(out)} -> {expected_size}")
        out.extend([0] * (expected_size - len(out)))
    elif len(out) > expected_size:
        debug_print(f"[WARNING] RLE5: 出力過多、切り詰めます: {len(out)} -> {expected_size}")
        out = out[:expected_size]
    
    debug_print(f"[DEBUG] RLE5デコード完了: 出力サイズ={len(out)}")
    return out

def decode_lz5(data, width, height):
    """SFFv2 LZ5デコード（IkemenGO準拠版）"""
    if len(data) < 4:
        debug_print("[ERROR] LZ5 data too short")
        return bytearray([0] * width * height)
    
    decompressed_size = struct.unpack_from('<I', data, 0)[0]
    debug_print(f"[DEBUG] LZ5デコード: 期待サイズ={decompressed_size}, 実際={width*height}")
    
    dst = bytearray()
    srcpos = 4
    recycle_byte = 0
    recycle_count = 0
    
    while srcpos < len(data) and len(dst) < decompressed_size:
        if srcpos >= len(data):
            break
            
        ctrl = data[srcpos]
        srcpos += 1
        
        for bit in range(8):
            if srcpos >= len(data) or len(dst) >= decompressed_size:
                break
                
            is_lz = (ctrl >> bit) & 1
            
            if is_lz:
                # 辞書参照
                if srcpos >= len(data):
                    break
                    
                b1 = data[srcpos]
                srcpos += 1
                
                if (b1 & 0x3F) == 0x00:
                    # 長い距離・長い長さ
                    if srcpos + 1 >= len(data):
                        break
                    b2 = data[srcpos]
                    b3 = data[srcpos + 1]
                    srcpos += 2
                    offset = (((b1 & 0xC0) << 2) | b2) + 1
                    length = b3 + 3
                else:
                    # 短い距離・短い長さ
                    length = (b1 & 0x3F) + 1
                    recycle_byte |= ((b1 & 0xC0) >> 6) << (6 - 2 * recycle_count)
                    recycle_count += 1
                    
                    if recycle_count == 4:
                        offset = recycle_byte + 1
                        recycle_byte = 0
                        recycle_count = 0
                    else:
                        if srcpos >= len(data):
                            break
                        offset = data[srcpos] + 1
                        srcpos += 1
                
                # 辞書データをコピー
                for _ in range(length):
                    if len(dst) >= decompressed_size:
                        break
                    if offset <= len(dst):
                        dst.append(dst[-offset])
                    else:
                        dst.append(0)
            else:
                # リテラル
                if srcpos >= len(data):
                    break
                    
                b1 = data[srcpos]
                srcpos += 1
                val = b1 & 0x1F
                count = b1 >> 5
                
                if count == 0:
                    if srcpos >= len(data):
                        break
                    b2 = data[srcpos]
                    srcpos += 1
                    count = b2 + 8
                
                # リテラル値を追加
                for _ in range(count):
                    if len(dst) >= decompressed_size:
                        break
                    dst.append(val)
    
    # サイズ調整
    result = dst[:width * height]
    if len(result) < width * height:
        result.extend([0] * (width * height - len(result)))
    
    debug_print(f"[DEBUG] LZ5デコード完了: 出力サイズ={len(result)}")
    return result

def decode_sprite(fmt, data, width, height):
    debug_print(f"[DEBUG] decode_sprite: fmt={fmt}, data_size={len(data)}, size={width}x{height}")
    
    try:
        # 初期化
        decoded = None
        mode = 'indexed'
        
        # PNG形式の場合（fmt=10 かつ 署名で確認）
        if fmt == 10:
            if is_png_data(data):
                debug_print(f"[DEBUG] Valid PNG signature confirmed, processing as PNG")
                decoded, mode, png_palette = decode_png(data, width, height)
                return decoded, mode
            else:
                debug_print(f"[WARNING] fmt=10 but invalid PNG signature, treating as unknown format")
                decoded = bytearray([0] * width * height)
        
        # 署名による自動PNG検出（fmt=10以外でも）
        elif is_png_data(data):
            debug_print(f"[DEBUG] PNG signature detected in fmt={fmt}, processing as PNG")
            decoded, mode, png_palette = decode_png(data, width, height)
            return decoded, mode
            
        elif fmt in (0, 1):
            decoded = bytearray(data[:width * height])
        elif fmt == 2:
            # fmt=2は RLE8圧縮（SFFv2仕様）- 高速化版
            expected_size = width * height
            
            if len(data) == expected_size:
                # 非圧縮データ
                decoded = bytearray(data)
            else:
                # RLE8圧縮データ - 最も高速な方法を優先
                try:
                    decoded_array = _decode_elecbyte_rle8_enhanced(data, width, height)
                    if decoded_array is not None and len(decoded_array) == expected_size:
                        decoded = bytearray(decoded_array.astype(np.uint8))
                    else:
                        # フォールバック
                        decode_result = _decode_fmt2_rle8_strict(data, width, height)
                        if decode_result is not None:
                            if isinstance(decode_result, tuple):
                                decoded, _ = decode_result
                            else:
                                decoded = decode_result
                            decoded = bytearray(decoded) if decoded else None
                        
                        if decoded is None or len(decoded) != expected_size:
                            decoded = decode_rle8(data, width, height)
                except Exception:
                    decoded = decode_rle8(data, width, height)
                    
        elif fmt == 3:
            decoded = decode_rle5(data, width, height)
        elif fmt in (4, 25):
            decoded = decode_lz5(data, width, height)
        else:
            # 未知のフォーマット - 簡単な推測のみ
            expected_indexed = width * height
            if len(data) == expected_indexed:
                decoded = bytearray(data)
            else:
                decoded = bytearray([0] * expected_indexed)
    
    except Exception as e:
        debug_print(f"[ERROR] decode_sprite failed: {e}")
        decoded = bytearray([0] * width * height)
        mode = 'indexed'
    
    # decoded変数の確認
    if decoded is None:
        decoded = bytearray([0] * width * height)
        mode = 'indexed'
    
    # モード判定
    if len(decoded) == width * height * 4:
        mode = 'rgba'
    elif len(decoded) == width * height:
        mode = 'indexed'
    else:
        # サイズ調整
        expected_size = width * height
        if len(decoded) > expected_size:
            decoded = decoded[:expected_size]
        else:
            decoded.extend([0] * (expected_size - len(decoded)))
        mode = 'indexed'
    
    return decoded, mode

class SFF2:
    """
    Enhanced SFFv2 reader with improved RLE8 support based on sff2_decode.py
    
    This class provides a more robust SFFv2 implementation specifically
    designed for handling RLE8 compression (format code 2, colour depth 8).
    """

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.data = file_path.read_bytes()
        # Parse header fields
        header = self.data[:0x80]
        try:
            self.spr_offset = struct.unpack_from('<I', header, 0x24)[0]
            self.spr_count = struct.unpack_from('<I', header, 0x28)[0]
            self.pal_offset = struct.unpack_from('<I', header, 0x2C)[0]
            self.pal_count = struct.unpack_from('<I', header, 0x30)[0]
            self.ldata_offset = struct.unpack_from('<I', header, 0x34)[0]
            self.tdata_offset = struct.unpack_from('<I', header, 0x3C)[0]
        except struct.error as e:
            raise ValueError(f"Invalid SFF2 header: {e}") from e
        
        # Parse palette and sprite tables
        self.palettes: List[Dict] = []
        self._load_palettes()
        self.sprites: Dict[Tuple[int, int], Dict] = {}
        self._load_sprites()

    def _load_palettes(self) -> None:
        """Load palette records from the palette table."""
        for i in range(self.pal_count):
            base = self.pal_offset + i * 16
            if base + 16 > len(self.data):
                break
            # Layout: uint16 groupid, uint16 palid, uint16 numcol,
            # uint16 linkid, uint32 file_off, uint32 file_len
            groupid, palid, numcol, linkid, file_off, file_len = struct.unpack_from(
                '<HHHHII', self.data, base
            )
            self.palettes.append(
                {
                    'groupid': groupid,
                    'palid': palid,
                    'numcol': numcol,
                    'linkid': linkid,
                    'file_off': file_off,
                    'file_len': file_len,
                    'data': None,  # will be filled on demand
                }
            )
        # Post‑process palette links to copy the referenced palette data
        for idx, rec in enumerate(self.palettes):
            link = rec['linkid']
            if link != 0xFFFF and 0 <= link < len(self.palettes):
                linked = self.palettes[link]
                if linked['data'] is not None:
                    rec['data'] = linked['data']

    def _load_sprites(self) -> None:
        """Load sprite records into a dictionary keyed by (group, number)."""
        for i in range(self.spr_count):
            base = self.spr_offset + i * 28
            if base + 28 > len(self.data):
                break
            group, number = struct.unpack_from('<hh', self.data, base)
            width, height = struct.unpack_from('<HH', self.data, base + 4)
            axis_x, axis_y = struct.unpack_from('<hh', self.data, base + 8)
            index_next = struct.unpack_from('<H', self.data, base + 12)[0]
            fmt = self.data[base + 14]
            coldepth = self.data[base + 15]
            file_off = struct.unpack_from('<I', self.data, base + 16)[0]
            file_len = struct.unpack_from('<I', self.data, base + 20)[0]
            pal_index = struct.unpack_from('<H', self.data, base + 24)[0]
            flags = struct.unpack_from('<H', self.data, base + 26)[0]
            # Compute the absolute data offset
            rel_tdata = bool(flags & 0x0001)
            actual_off = file_off + (self.tdata_offset if rel_tdata else self.ldata_offset)
            self.sprites[(group, number)] = {
                'width': width,
                'height': height,
                'fmt': fmt,
                'coldepth': coldepth,
                'file_off': actual_off,
                'file_len': file_len,
                'pal_index': pal_index,
                'flags': flags,
            }

    def _get_palette(self, index: int) -> np.ndarray:
        """Return palette as an array of shape (256,4) in RGBA order with fixed alpha values."""
        if index >= len(self.palettes) or index < 0:
            # Return a default palette (all opaque magenta) if out of range.
            return np.tile(np.array([255, 0, 255, 255], dtype=np.uint8), (256, 1))
        rec = self.palettes[index]
        if rec['data'] is not None:
            return rec['data']
        # The palette data in SFFv2 files is stored in the ldata section.
        file_off = rec['file_off'] + self.ldata_offset
        file_len = rec['file_len']
        pal_data = self.data[file_off : file_off + file_len]
        # Ensure at least 256*4 bytes; pad with zeros if necessary.
        if len(pal_data) < 1024:
            pal_data += bytes(1024 - len(pal_data))
        
        # Debug: パレットの最初の数色をBGRA形式で確認
        if len(pal_data) >= 16:
            debug_palette(f"[PALETTE_DEBUG] Raw palette data (first 4 colors in BGRA):")
            for i in range(4):
                offset = i * 4
                if offset + 3 < len(pal_data):
                    b, g, r, a = pal_data[offset:offset+4]
                    debug_palette(f"[PALETTE_DEBUG]   Color {i}: B={b:02x} G={g:02x} R={r:02x} A={a:02x}")
        
        pal = np.frombuffer(pal_data, dtype=np.uint8).reshape(-1, 4)[:256]
        
        # Convert BGRA → RGBA (条件付き変換)
        # 注意：SFFv2パレットがBGRA順序で保存されていることを前提としている
        # もしパレットが既にRGBA順序の場合、この変換は間違った結果を生成する
        pal_original = pal.copy()
        
        if not DISABLE_BGRA_RGBA_CONVERSION:
            pal = pal[:, [2, 1, 0, 3]].copy()
            conversion_applied = True
        else:
            conversion_applied = False
            debug_palette(f"[PALETTE_DEBUG] BGRA→RGBA conversion disabled for testing")
        
        # Debug: 変換前後のパレット比較
        if DEBUG_PALETTE_DETAILS:
            debug_palette(f"[PALETTE_DEBUG] Palette conversion ({'BGRA → RGBA' if conversion_applied else 'No conversion'}) for first 4 colors:")
            for i in range(min(4, len(pal))):
                orig = pal_original[i]
                conv = pal[i]
                if conversion_applied:
                    debug_palette(f"[PALETTE_DEBUG]   Color {i}: BGRA({orig[0]:02x},{orig[1]:02x},{orig[2]:02x},{orig[3]:02x}) → RGBA({conv[0]:02x},{conv[1]:02x},{conv[2]:02x},{conv[3]:02x})")
                else:
                    debug_palette(f"[PALETTE_DEBUG]   Color {i}: Original({orig[0]:02x},{orig[1]:02x},{orig[2]:02x},{orig[3]:02x}) = Used({conv[0]:02x},{conv[1]:02x},{conv[2]:02x},{conv[3]:02x})")
        
        
        # Fix alpha channel: index 0 = transparent (0), others = opaque (255)
        # Many SFFv2 palettes have incorrect alpha values (0 or 1) which make sprites invisible
        if FIX_SFFV2_ALPHA_CHANNEL:
            pal[0, 3] = 0      # Index 0 (background) = transparent
            pal[1:, 3] = 255   # All other indices = opaque
            debug_print(f"[ENHANCED_RLE8] Fixed palette alpha: index0=transparent, others=opaque")
        else:
            debug_print(f"[ENHANCED_RLE8] Using original palette alpha values")
        
        rec['data'] = pal
        return pal

    def decode_sprite(self, group: int, number: int) -> Optional[np.ndarray]:
        """Decode a sprite to an RGBA array and return it."""
        key = (group, number)
        rec = self.sprites.get(key)
        if not rec:
            return None
        if rec['fmt'] != 2 or rec['coldepth'] != 8:
            return None
        w, h = rec['width'], rec['height']
        file_off = rec['file_off']
        file_len = rec['file_len']
        rle = self.data[file_off : file_off + file_len]
        pixels = self._decode_rle8(rle, w * h)
        pal = self._get_palette(rec['pal_index'])
        # Map indices to palette
        rgba = pal[pixels].reshape(h, w, 4)
        return rgba

    @staticmethod
    def _decode_rle8(data: bytes, expected_pixels: int) -> np.ndarray:
        """Decode Elecbyte RLE8 data (fmt=2) into a 1‑D index array (高速化版)."""
        if len(data) < 4:
            return np.zeros(expected_pixels, dtype=np.uint8)
        
        i = 4  # skip uncompressed length
        out = np.zeros(expected_pixels, dtype=np.uint8)  # NumPy配列で高速化
        out_idx = 0
        run_len = -1
        
        # Process bytes until we've produced the required number of pixels
        while out_idx < expected_pixels and i < len(data):
            b = data[i]
            i += 1
            # Top two bits 01 indicate a run header; only apply if no
            # run length is currently pending.
            if (b & 0xC0) == 0x40 and run_len == -1:
                run_len = b & 0x3F
            else:
                count = run_len if run_len != -1 else 1
                end_idx = min(out_idx + count, expected_pixels)  # 配列境界チェック
                out[out_idx:end_idx] = b  # NumPy スライス代入で高速化
                out_idx = end_idx
                run_len = -1
        
        return out

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
        
        # Read header fields at correct positions
        f.seek(0x24)  # 36: sprite offset
        self.header['sprite_offset'] = struct.unpack('<I', f.read(4))[0]
        
        f.seek(0x28)  # 40: sprite count
        self.header['num_sprites'] = struct.unpack('<I', f.read(4))[0]
        
        f.seek(0x2C)  # 44: palette offset  
        self.header['palette_offset'] = struct.unpack('<I', f.read(4))[0]
        
        f.seek(0x30)  # 48: palette count
        self.header['num_palettes'] = struct.unpack('<I', f.read(4))[0]
        
        f.seek(0x34)  # 52: ldata offset
        self.header['l_offset'] = struct.unpack('<I', f.read(4))[0]
        
        f.seek(0x38)  # 56: ldata length
        self.header['l_len'] = struct.unpack('<I', f.read(4))[0]
        
        f.seek(0x3C)  # 60: tdata offset
        self.header['t_offset'] = struct.unpack('<I', f.read(4))[0]
        
        f.seek(0x40)  # 64: tdata length
        self.header['t_len'] = struct.unpack('<I', f.read(4))[0]
        
        debug_print(f"[DEBUG] SFF header info:")
        debug_print(f"  - sprite_offset: 0x{self.header['sprite_offset']:x}")
        debug_print(f"  - num_sprites: {self.header['num_sprites']}")
        debug_print(f"  - palette_offset: 0x{self.header['palette_offset']:x}")
        debug_print(f"  - num_palettes: {self.header['num_palettes']}")
        debug_print(f"  - l_offset: 0x{self.header['l_offset']:x}")
        debug_print(f"  - t_offset: 0x{self.header['t_offset']:x}")
        debug_print(f"  - l_len: {self.header['l_len']}")
        debug_print(f"  - t_len: {self.header['t_len']}")

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
            
            # Fix alpha channel values: ignore stored alpha, set index 0 = transparent, others = opaque
            palette = []
            if FIX_SFFV2_ALPHA_CHANNEL:
                for idx, (r, g, b, a) in enumerate(struct.iter_unpack('BBBB', data)):
                    if idx == 0:
                        # Index 0 = transparent background
                        palette.append((r, g, b, 0))
                    else:
                        # All other indices = opaque (ignore stored alpha value)
                        palette.append((r, g, b, 255))
                debug_print(f"[DEBUG] Palette {i}: Fixed alpha values (index0=transparent, others=opaque)")
            else:
                # Use original alpha values from file
                for idx, (r, g, b, a) in enumerate(struct.iter_unpack('BBBB', data)):
                    palette.append((r, g, b, a))
                debug_print(f"[DEBUG] Palette {i}: Using original alpha values from file")
            
            while len(palette) < 256:
                palette.append((0, 0, 0, 255))
            
            # Ensure index 0 transparency (always apply this)
            if len(palette) > 0:
                r, g, b, _ = palette[0]
                palette[0] = (r, g, b, 0)
                
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
            
            # flags の bit0 で領域を選ぶ
            rel_offset = data_ofs  # 元の相対オフセットを保存
            if (flags & 1) == 0:
                base = self.header['l_offset']
                data_ofs += base
                debug_print(f"[DEBUG] Sprite {sprite_index}: flags bit0=0 → using ldata (l_offset=0x{base:x})")
            else:
                base = self.header['t_offset']
                data_ofs += base
                debug_print(f"[DEBUG] Sprite {sprite_index}: flags bit0=1 → using tdata (t_offset=0x{base:x})")
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
                'flags': flags,
                'rel_offset': rel_offset,  # 相対オフセットも保存
                'image_data': None  # SFFv2では遅延読み込み（必要時にdecode_sprite_v2で取得）
            })
            # パレット使用回数カウント
            if 0 <= pal_idx < len(self.palette_usage_count):
                self.palette_usage_count[pal_idx] += 1

        # 専用パレット集合作成（使用1回）
        self.dedicated_palette_indices = {i for i, c in enumerate(self.palette_usage_count) if c == 1}
        debug_print(f"[DEBUG] Dedicated palette indices: {sorted(self.dedicated_palette_indices)}")

# グローバルキャッシュ for Enhanced SFF2 readers（最大10ファイルまで）
_enhanced_sff2_cache = {}
_cache_max_size = 10

def create_enhanced_sff2_reader(file_path):
    """
    Create an enhanced SFF2 reader that provides better RLE8 support.
    Uses LRU cache for performance optimization.
    """
    # キャッシュキーとして絶対パスを使用
    cache_key = os.path.abspath(file_path)
    
    if cache_key in _enhanced_sff2_cache:
        # LRU: アクセスしたアイテムを最後に移動
        value = _enhanced_sff2_cache.pop(cache_key)
        _enhanced_sff2_cache[cache_key] = value
        debug_print(f"[DEBUG] Using cached Enhanced SFF2 reader for {file_path}")
        return value
    
    try:
        sff2 = SFF2(Path(file_path))
        debug_print(f"[DEBUG] Enhanced SFF2 reader created for {file_path}")
        debug_print(f"[DEBUG] Found {len(sff2.sprites)} sprites and {len(sff2.palettes)} palettes")
        
        # キャッシュサイズ管理（LRU削除）
        if len(_enhanced_sff2_cache) >= _cache_max_size:
            # 最も古いアイテムを削除
            oldest_key = next(iter(_enhanced_sff2_cache))
            del _enhanced_sff2_cache[oldest_key]
            debug_print(f"[DEBUG] Removed oldest cache entry: {oldest_key}")
        
        # キャッシュに保存
        _enhanced_sff2_cache[cache_key] = sff2
        return sff2
    except Exception as e:
        debug_print(f"[WARNING] Failed to create enhanced SFF2 reader: {e}")
        return None

def clear_enhanced_sff2_cache():
    """Clear the Enhanced SFF2 reader cache to free memory"""
    global _enhanced_sff2_cache
    _enhanced_sff2_cache.clear()
    debug_print(f"[DEBUG] Enhanced SFF2 cache cleared")

def decode_sprite_with_sff2(sff2_reader, group, number, palette_override=None):
    """
    Decode a sprite using the enhanced SFF2 reader.
    Returns the decoded RGBA data ready for display in the GUI.
    
    Args:
        sff2_reader: Enhanced SFF2 reader instance
        group: Sprite group number
        number: Sprite number
        palette_override: If provided, use this palette index instead of the sprite's default
    
    Returns:
        tuple: (rgba_bytes, None, width, height, 'rgba') or None if failed
    """
    try:
        # Get sprite info first
        sprite_key = (group, number)
        if sprite_key not in sff2_reader.sprites:
            debug_print(f"[DEBUG] Sprite ({group}, {number}) not found in Enhanced SFF2")
            return None
        
        sprite_info = sff2_reader.sprites[sprite_key]
        original_pal_index = sprite_info['pal_index']
        
        if palette_override is not None:
            debug_print(f"[DEBUG] Enhanced SFF2 palette override: {original_pal_index} -> {palette_override}")
            
            # Get sprite dimensions and RLE data
            w, h = sprite_info['width'], sprite_info['height']
            file_off = sprite_info['file_off']
            file_len = sprite_info['file_len']
            rle_data = sff2_reader.data[file_off : file_off + file_len]
            
            # Decode RLE8 to get index data
            pixels = sff2_reader._decode_rle8(rle_data, w * h)
            
            # Use override palette instead of original
            if palette_override < len(sff2_reader.palettes):
                override_palette = sff2_reader._get_palette(palette_override)
                
                # Apply palette to pixels
                rgba_array = override_palette[pixels].reshape(h, w, 4)
                
                # Apply alpha channel fix if enabled
                if FIX_SFFV2_ALPHA_CHANNEL:
                    alpha_channel = rgba_array[:, :, 3]
                    non_transparent_pixels = np.count_nonzero(alpha_channel)
                    total_pixels = h * w
                    transparency_ratio = non_transparent_pixels / total_pixels
                    
                    debug_print(f"[ENHANCED_RLE8] Sprite {group},{number} with palette {palette_override} transparency ratio: {transparency_ratio:.3f}")
                    
                    if transparency_ratio < 0.1:
                        debug_print(f"[ENHANCED_RLE8] Fixing excessive transparency for sprite {group},{number} with palette override")
                        # Create a writable copy to avoid read-only assignment errors
                        rgba_array = rgba_array.copy()
                        rgb_sum = rgba_array[:, :, 0] + rgba_array[:, :, 1] + rgba_array[:, :, 2]
                        non_black_mask = rgb_sum > 0
                        rgba_array[non_black_mask, 3] = 255
                        debug_print(f"[ENHANCED_RLE8] Fixed alpha for {np.count_nonzero(non_black_mask)} non-black pixels")
                
                # Convert to bytes
                rgba_bytes = rgba_array.flatten().tobytes()
                debug_print(f"[DEBUG] Enhanced SFF2 with palette override decoded sprite {group},{number}: {w}x{h}, {len(rgba_bytes)} bytes")
                
                # パレット表示のため、パレット情報も返す
                palette_for_display = [(r, g, b, a) for r, g, b, a in override_palette.tolist()]
                return bytearray(rgba_bytes), palette_for_display, w, h, 'rgba'
            else:
                debug_print(f"[ERROR] Invalid palette override index: {palette_override} (max: {len(sff2_reader.palettes)-1})")
                # Fall back to original palette
                palette_override = None
        
        # Use standard Enhanced SFF2 decoding (no palette override)
        rgba_array = sff2_reader.decode_sprite(group, number)
        if rgba_array is not None:
            # Convert numpy array to format expected by GUI
            height, width, channels = rgba_array.shape
            
            # Additional alpha channel fix: ensure proper visibility
            if FIX_SFFV2_ALPHA_CHANNEL:
                alpha_channel = rgba_array[:, :, 3]
                non_transparent_pixels = np.count_nonzero(alpha_channel)
                total_pixels = height * width
                transparency_ratio = non_transparent_pixels / total_pixels
                
                debug_print(f"[ENHANCED_RLE8] Sprite {group},{number} transparency ratio: {transparency_ratio:.3f}")
                
                # If more than 90% of pixels are transparent, it's likely a palette alpha issue
                if transparency_ratio < 0.1:
                    debug_print(f"[ENHANCED_RLE8] Fixing excessive transparency for sprite {group},{number}")
                    # Create a writable copy to avoid read-only assignment errors
                    rgba_array = rgba_array.copy()
                    # Fix alpha: set all non-index-0 pixels to opaque
                    # We need to identify which pixels should be background (index 0)
                    # For now, we'll set all pixels with non-zero RGB values to opaque
                    rgb_sum = rgba_array[:, :, 0] + rgba_array[:, :, 1] + rgba_array[:, :, 2]
                    non_black_mask = rgb_sum > 0
                    rgba_array[non_black_mask, 3] = 255  # Set non-black pixels to opaque
                    debug_print(f"[ENHANCED_RLE8] Fixed alpha for {np.count_nonzero(non_black_mask)} non-black pixels")
            else:
                debug_print(f"[ENHANCED_RLE8] Alpha fix disabled, using original values")
            
            # Flatten the array and convert to bytes
            rgba_bytes = rgba_array.flatten().tobytes()
            debug_print(f"[DEBUG] SFF2 decoded sprite {group},{number}: {width}x{height}, {len(rgba_bytes)} bytes")
            
            # パレット表示のため、使用されたパレット情報も返す
            sprite_key = (group, number)
            if sprite_key in sff2_reader.sprites:
                pal_index = sff2_reader.sprites[sprite_key]['pal_index']
                if pal_index < len(sff2_reader.palettes):
                    used_palette = sff2_reader._get_palette(pal_index)
                    palette_for_display = [(r, g, b, a) for r, g, b, a in used_palette.tolist()]
                    return bytearray(rgba_bytes), palette_for_display, width, height, 'rgba'
            
            return bytearray(rgba_bytes), None, width, height, 'rgba'
        else:
            debug_print(f"[DEBUG] SFF2 could not decode sprite {group},{number}")
            return None
    except Exception as e:
        debug_print(f"[ERROR] SFF2 decoding failed for sprite {group},{number}: {e}")
        return None

def _try_enhanced_sff2_decode(reader, sprite, palette_override=None):
    """Enhanced SFF2デコーダーでスプライトをデコードを試行"""
    if not hasattr(reader, 'file_path') or not reader.file_path:
        debug_print(f"[DEBUG] Enhanced SFF2: file_path not available")
        return None
        
    try:
        group_no = sprite['group_no']
        sprite_no = sprite['sprite_no']
        debug_print(f"[DEBUG] Enhanced SFF2: attempting decode for sprite {group_no},{sprite_no}")
        
        sff2_reader = create_enhanced_sff2_reader(reader.file_path)
        if sff2_reader is not None:
            result = decode_sprite_with_sff2(sff2_reader, group_no, sprite_no, palette_override)
            if result is not None:
                decoded, palette, width, height, mode = result
                if decoded is not None and len(decoded) > 0:
                    if palette_override is not None:
                        debug_print(f"[DEBUG] Enhanced SFF2: success with palette override {palette_override}, size={width}x{height}")
                    else:
                        debug_print(f"[DEBUG] Enhanced SFF2: success, size={width}x{height}")
                    return decoded, palette, width, height, mode
                else:
                    debug_print(f"[DEBUG] Enhanced SFF2: decoded data is empty or None")
            else:
                debug_print(f"[DEBUG] Enhanced SFF2: decode_sprite_with_sff2 returned None")
        else:
            debug_print(f"[DEBUG] Enhanced SFF2: create_enhanced_sff2_reader returned None")
        return None
    except Exception as e:
        debug_print(f"[WARNING] Enhanced SFF2 decoder error: {e}")
        return None

def decode_sprite_v2(reader, index, palette_override=None, visited_indices=None):
    if visited_indices is None:
        visited_indices = set()
    
    if index in visited_indices:
        # 循環参照の場合は1x1の透明画像を返す
        return bytearray([0]), [(0, 0, 0, 0)] * 256, 1, 1, 'indexed'
    
    visited_indices.add(index)
    sprite = reader.sprites[index]
    
    # パレットオーバーライドが指定された場合は必ずEnhanced SFF2を使用
    if palette_override is not None:
        debug_print(f"[DEBUG] Palette override {palette_override} specified, forcing Enhanced SFF2 decoder")
        result = _try_enhanced_sff2_decode(reader, sprite, palette_override)
        if result is not None:
            return result
        else:
            debug_print(f"[ERROR] Enhanced SFF2 decoder failed with palette override, falling back to standard decode")
            # フォールバック: 標準デコードを続行
    
    # Enhanced SFF2 reader を使用するか判定 (fmt=2 かつ coldepth=8)
    if sprite.get('fmt') == 2 and sprite.get('coldepth') == 8:
        result = _try_enhanced_sff2_decode(reader, sprite)
        if result is not None:
            return result
        debug_print(f"[DEBUG] Enhanced SFF2 decoder failed, falling back to standard decoder")
    
    # ファイルパスとスプライト情報を出力
    debug_print(f"[DEBUG] 処理中のSFFファイル: {reader.file_path}")
    
    # SFFv1とSFFv2で異なるキー名に対応
    offset_info = ""
    if 'absolute_offset' in sprite:
        offset_info = f"absolute offset 0x{sprite['absolute_offset']:x}"
    elif 'offset' in sprite:
        offset_info = f"offset 0x{sprite['offset']:x}"
    elif 'data_offset' in sprite:
        offset_info = f"data offset 0x{sprite['data_offset']:x}"
    else:
        offset_info = "offset unknown"
    
    debug_print(f"[DEBUG] Sprite {index}: Reading from {offset_info}, size={sprite.get('data_len', sprite.get('data_size', 0))}")
    
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
    
    # データ読み取り（高速化版）
    with open(reader.file_path, 'rb') as f:
        f.seek(sprite['data_ofs'])
        data = f.read(sprite['data_len'])
        
        debug_print(f"[DEBUG] Sprite {index}: Reading from absolute offset 0x{sprite['data_ofs']:x}, size={sprite['data_len']}")
        
        # fmt=2でデータが疑わしい場合のみフォールバック試行
        if sprite['fmt'] == 2 and len(data) >= 16:
            first_16_zeros = data[:16].count(b'\x00')
            
            # より簡単な判定：先頭16バイトの14個以上が0x00
            if first_16_zeros >= 14:
                debug_print(f"[DEBUG] Suspicious data detected, trying fallback...")
                # 逆の領域を試行
                flags = sprite.get('flags', 0)
                rel_offset = sprite.get('rel_offset', 0)
                if (flags & 1) == 0:
                    # 現在ldata、tdataを試行
                    alt_offset = reader.header['t_offset'] + rel_offset
                else:
                    # 現在tdata、ldataを試行
                    alt_offset = reader.header['l_offset'] + rel_offset
                
                f.seek(alt_offset)
                fallback_data = f.read(sprite['data_len'])
                
                # 簡単な妥当性チェック
                fallback_zeros = fallback_data[:16].count(b'\x00')
                if fallback_zeros < first_16_zeros:
                    debug_print(f"[DEBUG] Using fallback data (fewer zeros: {fallback_zeros} < {first_16_zeros})")
                    data = fallback_data
    
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
        
        # デコード結果のNoneチェック
        if decoded is None:
            debug_print(f"[ERROR] decode_sprite returned None, creating fallback")
            decoded = bytearray([0] * sprite['width'] * sprite['height'])
            mode = 'indexed'
        
        # 専用パレットは強制適用
        sprite_pal = sprite['pal_idx']
        if sprite_pal in getattr(reader, 'dedicated_palette_indices', set()):
            pal_idx = sprite_pal
            debug_print(f"[DEBUG] Forcing dedicated palette {pal_idx} (standard decode)")
        else:
            pal_idx = palette_override if palette_override is not None else sprite_pal
        
        # パレット取得の確実性を向上
        palette = None
        if pal_idx is not None and pal_idx < len(reader.palettes):
            palette = reader.palettes[pal_idx]
            debug_print(f"[DEBUG] Using palette {pal_idx} with {len(palette)} colors (fmt={sprite['fmt']})")
        else:
            debug_print(f"[WARNING] Invalid palette index {pal_idx}, available palettes: {len(reader.palettes) if hasattr(reader, 'palettes') else 0}")
            # フォールバック：最初のパレットを使用
            if hasattr(reader, 'palettes') and len(reader.palettes) > 0:
                palette = reader.palettes[0]
                debug_print(f"[FALLBACK] Using palette 0 as fallback with {len(palette)} colors")
    
    # 最終的なNoneチェック
    if decoded is None:
        debug_print(f"[ERROR] Final decoded data is None, creating fallback")
        width, height = sprite['width'], sprite['height']
        decoded = bytearray([0] * width * height)  # 透明データ
        mode = 'indexed'
        if palette is None:
            palette = [(0, 0, 0, 0)] * 256  # 透明パレット
    
    return decoded, palette, sprite['width'], sprite['height'], mode
