import os
import struct
import json
import logging
from PIL import Image
from io import BytesIO
import tempfile

# =====================
# SFFv1 解析処理
# =====================
def analyze_sff_v1(f, output_file):
    f.seek(0)
    header = struct.unpack("<12s4B4I", f.read(32))
    subfile_offset = header[7]

    results = []
    while subfile_offset != 0:
        f.seek(subfile_offset)
        try:
            # SFF仕様に基づくサブヘッダー解析（32バイト）
            # next_offset, size, ax, ay, group, image, link_index, pal の順
            subheader = struct.unpack("<2I2h4hB11s", f.read(32))
        except struct.error:
            break

        next_offset, size, ax, ay, group, image, link_index, pal = subheader[:8]
        results.append({
            "index": len(results),  # 連続するインデックス
            "group_no": group,
            "image_no": image,
            "axisx": ax,
            "axisy": ay,
            "palette": pal,
            "link_index": link_index,  # リンクindexを追加
            "offset": subfile_offset,
            "size": size,
            "next_offset": next_offset
        })

        subfile_offset = next_offset

    with open(output_file, "w", encoding="utf-8") as f_out:
        json.dump(results, f_out, indent=2, ensure_ascii=False)

# =====================
# PCX → PIL画像
# =====================
def extract_pcx(bis, offset, size):
    bis.seek(offset)
    return bis.read(size)

def extract_palette_from_pcx_data(data):
    if len(data) >= 769 and data[-769] == 0x0C:
        return list(data[-768:])
    return None

def reverse_act_palette(palette):
    """ACTパレットを反転させる関数"""
    if len(palette) < 768:
        return palette
    reversed_palette = []
    for i in range(255, -1, -1):
        idx = i * 3
        if idx + 2 < len(palette):
            # BGR → RGB変換を行う
            b = palette[idx]
            g = palette[idx + 1]
            r = palette[idx + 2]
            reversed_palette.extend([r, g, b])  # RGB順に並び替え
        else:
            reversed_palette.extend([0, 0, 0])
    return reversed_palette

def convert_pcx_to_image(pcx_data, palette_data=None):
    try:
        img = Image.open(BytesIO(pcx_data))
        img.load()
        img = img.convert("P")

        extracted_palette = extract_palette_from_pcx_data(pcx_data)
        final_palette = palette_data or extracted_palette

        if final_palette and len(final_palette) >= 768:
            img.putpalette(final_palette[:768])
            logging.info("パレット適用成功")
        else:
            logging.warning("パレットが不足、または取得できません")

        return img, final_palette

    except Exception as e:
        logging.error(f"PCX→画像変換失敗: {e}")
        return None, None

# =====================
# SFF画像の抽出処理
# =====================
def extract_sffv1(bis, analysis_json, image_objects, image_info_list, act_palette=None, palette_list=None):
    with open(analysis_json, 'r', encoding='utf-8') as f:
        analysis_results = json.load(f)

    last_valid_palette = None
    applied_act_once = False
    first_palette = None  # 先頭画像のパレットのみを保持
    group9000_palettes = []  # グループ9000の独立パレットを保持
    palette_mapping = {}  # 各画像のパレットインデックスを記録

    for img in analysis_results:
        offset = img['offset']
        size = img['size']
        palflag = img['palette']
        group = img['group_no']
        image_no = img['image_no']

        if size == 0:
            # SFF仕様に従い、サイズ0の画像の場合はリンクindexを使って実際の画像データを参照
            link_index = img.get('link_index', None)
            link_resolved = False
            
            # 現在のインデックス位置
            current_index = len(image_objects)
            
            # まずリンクindexが有効かチェック
            if link_index is not None and 0 <= link_index < len(analysis_results):
                # リンク先の画像情報を取得
                linked_img_info = analysis_results[link_index]
                linked_group = linked_img_info['group_no']
                linked_image_no = linked_img_info['image_no']
                linked_size = linked_img_info['size']
                
                if linked_size > 0:
                    try:
                        # リンク先の画像データを取得
                        linked_offset = linked_img_info['offset']
                        linked_pcx_data = extract_pcx(bis, linked_offset + 32, linked_size)
                        
                        # パレット処理
                        linked_palette_data = extract_palette_from_pcx_data(linked_pcx_data)
                        if not linked_palette_data:
                            linked_palette_data = last_valid_palette
                        
                        # 画像変換
                        linked_img, used_palette = convert_pcx_to_image(linked_pcx_data, linked_palette_data)
                        
                        if linked_img:
                            image_objects.append(linked_img)
                            
                            # 元の画像情報を保持し、リンク情報を追加
                            img_copy = img.copy()
                            img_copy['is_linked'] = True
                            img_copy['linked_from'] = f"index({link_index}):({linked_group},{linked_image_no})"
                            img_copy['link_index'] = link_index
                            image_info_list.append(img_copy)
                            
                            palette_mapping[current_index] = -1
                            logging.info(f"画像({group},{image_no}): リンクindex {link_index}→({linked_group},{linked_image_no})から解決")
                            link_resolved = True
                            
                    except Exception as e:
                        logging.warning(f"リンクindex処理エラー ({group},{image_no}) -> index {link_index}: {e}")
            
            # リンク解決に失敗した場合は空画像を作成
            if not link_resolved:
                from PIL import Image
                empty_img = Image.new('P', (1, 1), 0)  # 1x1の透明画像
                empty_img.putpalette([0] * 768)  # 黒いパレット
                
                image_objects.append(empty_img)
                img_copy = img.copy()
                img_copy['is_zero_size'] = True
                img_copy['original_width'] = 0
                img_copy['original_height'] = 0
                image_info_list.append(img_copy)
                
                # パレットマッピングは継承予定として設定
                palette_mapping[len(image_objects) - 1] = -1
                logging.info(f"画像({group},{image_no}): リンク解決失敗またはリンクindexなし、空画像を作成")
            continue

        pcx_data = extract_pcx(bis, offset + 32, size)

        # ACT適用条件: ACTパレットが指定されている場合のみ適用
        # ただし、defファイルで開いた場合はACTパレットは無視する
        if False:  # ACTパレットは個別画像処理では使用しない（後で共有パレットとして処理）
            pass
        elif group == 9000 and image_no != 0 and palflag == 1:
            palette_data = extract_palette_from_pcx_data(pcx_data)
            logging.info(f"Group 9000 image {image_no}: 強制的に個別パレットを抽出")
            if palette_data:
                last_valid_palette = palette_data
        elif group == 9000:
            # グループ9000の画像は常に個別パレットを抽出を試みる
            palette_data = extract_palette_from_pcx_data(pcx_data)
            if palette_data:
                last_valid_palette = palette_data
                logging.info(f"Group 9000 image {image_no}: 個別パレットを抽出")
            else:
                palette_data = last_valid_palette
        elif (6000 <= group < 7000 or 8000 <= group < 9000):
            # 特殊グループの画像も個別パレットを抽出を試みる
            palette_data = extract_palette_from_pcx_data(pcx_data)
            if palette_data:
                last_valid_palette = palette_data
                logging.info(f"Group {group} image {image_no}: 個別パレットを抽出")
            else:
                palette_data = last_valid_palette
        elif palflag == 1:
            # palflag=1は独立パレットを持たないので、直前のパレットを継承
            if last_valid_palette:
                palette_data = last_valid_palette
                logging.info(f"画像({group},{image_no}): palflag=1のため、直前のパレットを継承")
            else:
                # 前のパレットがない場合は自分からパレット抽出を試みる
                palette_data = extract_palette_from_pcx_data(pcx_data)
                logging.warning(f"画像({group},{image_no}): palflag=1だが、直前のパレットがないため自分からパレット抽出を試みる")
                if palette_data:
                    last_valid_palette = palette_data
        elif palflag == 0:
            # palflag=0は独立パレットを持つ可能性があるので、まず自分からパレット抽出を試みる
            palette_data = extract_palette_from_pcx_data(pcx_data)
            if palette_data:
                last_valid_palette = palette_data
                logging.info(f"画像({group},{image_no}): palflag=0で独立パレットを抽出成功")
            else:
                # パレット抽出に失敗した場合は直前のパレットを使用
                palette_data = last_valid_palette
                logging.info(f"画像({group},{image_no}): palflag=0だがパレット抽出失敗、直前のパレットを使用")
        else:
            palette_data = None

        img_obj, used_palette = convert_pcx_to_image(pcx_data, palette_data)

        if img_obj:
            image_objects.append(img_obj)
            image_info_list.append(img)

            # 画像のインデックスを取得
            current_img_idx = len(image_objects) - 1
            
            # 独立パレットを持つ画像を検出（内部的な処理用）
            is_independent_palette = False
            
            # パレットフラグとパレット抽出結果に基づいて独立パレットかどうかを判定
            extracted_own_palette = extract_palette_from_pcx_data(pcx_data)
            
            if used_palette and extracted_own_palette:
                # 条件1: グループ9000の画像でPCXにパレットがある場合は独立パレット
                if group == 9000:
                    is_independent_palette = True
                    logging.info(f"画像({group},{image_no}): グループ9000で独自パレットあり")
                # 条件2: 特殊グループ（6000番台、8000番台）でPCXにパレットがある場合は独立パレット
                elif (6000 <= group < 7000 or 8000 <= group < 9000):
                    is_independent_palette = True
                    logging.info(f"画像({group},{image_no}): 特殊グループで独自パレットあり")
                # 条件3: (0,0)画像でPCXにパレットがある場合は独立パレット
                elif group == 0 and image_no == 0:
                    is_independent_palette = True
                    logging.info(f"画像(0,0): 先頭画像で独自パレットあり")
                # 条件4: その他のグループでpalflag=0かつPCXにパレットがある場合
                elif palflag == 0:
                    is_independent_palette = True
                    logging.info(f"画像({group},{image_no}): palflag=0で独自パレットあり")
            
            if is_independent_palette:
                # 独立パレットを持つ画像の処理（内部的なパレット保存用）
                group9000_palettes.append(used_palette)
                logging.info(f"画像({group},{image_no}): 内部パレット{len(group9000_palettes)}を保存")
            
            # 表示用パレットマッピングは後で統一するため、一旦-1に設定
            palette_mapping[current_img_idx] = -1

            if palflag == 0 and used_palette:
                last_valid_palette = used_palette

    # パレットリストを更新（9000,0のパレットのみ）
    if palette_list is not None:
        palette_list.clear()
        
        # 9000,0のパレットまたは最初の独立パレットを使用
        group9000_0_palette = None
        
        # 9000,0の画像を探してそのパレットを取得
        for i, info in enumerate(image_info_list):
            if info.get('group_no') == 9000 and info.get('image_no') == 0:
                # group9000_palettesから適切なパレットを探す
                for palette in group9000_palettes:
                    if palette:  # パレットが存在する場合
                        group9000_0_palette = palette
                        logging.info(f"(9000,0)パレット発見")
                        break
                break
        
        # ACTパレットが指定されている場合は、それで(9000,0)パレットを上書きする
        # （ACTパレットは共有パレットとして扱う）
        if act_palette:
            # ACTパレットを(9000,0)パレットとして使用
            act_palette_rgb = reverse_act_palette(act_palette)
            group9000_0_palette = act_palette_rgb
            logging.info(f"ACTパレットを(9000,0)パレットとして使用")
        
        if group9000_0_palette:
            palette_list.append(group9000_0_palette)
            logging.info(f"(9000,0)パレット追加: インデックス0 (RGB値数: {len(group9000_0_palette)//3})")
            logging.info(f"総パレット数: 1 ((9000,0)パレットのみ)")
        else:
            # (9000,0)が見つからない場合
            if act_palette:
                # ACTパレットが指定されている場合はACTパレットを使用
                act_palette_rgb = reverse_act_palette(act_palette)
                palette_list.append(act_palette_rgb)
                logging.info(f"ACTパレット追加: インデックス0 (RGB値数: {len(act_palette_rgb)//3})")
                logging.info(f"総パレット数: 1 (ACTパレットのみ)")
            elif group9000_palettes:
                # 最初の独立パレットを使用
                palette_list.append(group9000_palettes[0])
                logging.info(f"最初の独立パレット追加: インデックス0 (RGB値数: {len(group9000_palettes[0])//3})")
                logging.info(f"総パレット数: 1 (最初の独立パレットのみ)")
            else:
                # パレットが一つもない場合はデフォルトパレット
                default_palette = []
                for i in range(256):
                    default_palette.extend([i, i, i])  # RGB同値でグレースケール
                palette_list.append(default_palette)
                logging.warning("パレットが見つからないため、デフォルトグレースケールパレットを使用")
                logging.info(f"総パレット数: 1 (デフォルトパレットのみ)")
    
    # パレット適用範囲を決定
    # 9000,0と0,0から次の独立パレットまでの範囲を特定
    shared_palette_range = set()
    
    # 9000,0と0,0の画像インデックスを取得
    group9000_0_index = None
    group0_0_index = None
    
    for i, info in enumerate(image_info_list):
        if info.get('group_no') == 9000 and info.get('image_no') == 0:
            group9000_0_index = i
        elif info.get('group_no') == 0 and info.get('image_no') == 0:
            group0_0_index = i
    
    # 共有パレット範囲を決定
    if group9000_0_index is not None:
        shared_palette_range.add(group9000_0_index)
        
        # 9000,0から次の独立パレットまでの範囲を追加
        for i in range(group9000_0_index + 1, len(image_info_list)):
            info = image_info_list[i]
            group = info.get('group_no', 0)
            image_no = info.get('image_no', 0)
            
            # 次の独立パレットかどうかをチェック
            has_own_palette = False
            if i < len(image_objects):
                pcx_offset = info.get('offset', 0) + 32
                pcx_size = info.get('size', 0)
                if pcx_size > 0:
                    bis.seek(pcx_offset)
                    pcx_data = bis.read(pcx_size)
                    extracted_palette = extract_palette_from_pcx_data(pcx_data)
                    if extracted_palette and (group == 9000 or (6000 <= group < 7000 or 8000 <= group < 9000) or info.get('palette', 0) == 0):
                        has_own_palette = True
            
            if has_own_palette:
                # 独立パレットが見つかったので範囲終了
                break
            else:
                # 共有パレット範囲に追加
                shared_palette_range.add(i)
    
    if group0_0_index is not None:
        shared_palette_range.add(group0_0_index)
        
        # 0,0から次の独立パレットまでの範囲を追加
        for i in range(group0_0_index + 1, len(image_info_list)):
            if i in shared_palette_range:
                continue  # 既に追加済み
                
            info = image_info_list[i]
            group = info.get('group_no', 0)
            image_no = info.get('image_no', 0)
            
            # 次の独立パレットかどうかをチェック
            has_own_palette = False
            if i < len(image_objects):
                pcx_offset = info.get('offset', 0) + 32
                pcx_size = info.get('size', 0)
                if pcx_size > 0:
                    bis.seek(pcx_offset)
                    pcx_data = bis.read(pcx_size)
                    extracted_palette = extract_palette_from_pcx_data(pcx_data)
                    if extracted_palette and (group == 9000 or (6000 <= group < 7000 or 8000 <= group < 9000) or info.get('palette', 0) == 0):
                        has_own_palette = True
            
            if has_own_palette:
                # 独立パレットが見つかったので範囲終了
                break
            else:
                # 共有パレット範囲に追加
                shared_palette_range.add(i)
    
    logging.info(f"共有パレット適用範囲: {sorted(shared_palette_range)}")
    
    # 2回目のパス: 共有パレット範囲の画像のみパレットマッピングを0に設定
    # その他の画像は独自のパレットを使用
    for i, info in enumerate(image_info_list):
        group = info.get('group_no', 0)
        image_no = info.get('image_no', 0)
        
        if i in shared_palette_range:
            # 共有パレット範囲の画像はパレットリストのパレット（インデックス0）を使用
            palette_mapping[i] = 0
            logging.info(f"画像({group},{image_no}) @ index {i}: 共有パレット0を適用")
        else:
            # 共有パレット範囲外の画像は独自のパレットを使用（-1で無効化）
            palette_mapping[i] = -1
            logging.info(f"画像({group},{image_no}) @ index {i}: 独自パレットを使用（共有パレット無効）")
    
    # デバッグ用に最終的なパレットマッピング一覧を出力
    logging.info("=== パレットマッピング最終状態 ===")
    for i, info in enumerate(image_info_list):
        group = info.get('group_no', 0)
        image_no = info.get('image_no', 0)
        final_palette_idx = palette_mapping.get(i, 0)
        logging.info(f"画像({group},{image_no}) @ index {i}: パレット{final_palette_idx}")
    
    return palette_mapping, shared_palette_range

class SFFv1Reader:
    def __init__(self, file_path, act_palette=None):
        self.file_path = file_path
        self.image_objects = []
        self.image_info_list = []
        self.palette_list = []
        self.palette_mapping = {}  # 画像インデックスからパレットインデックスへのマッピング
        self.shared_palette_range = set()  # 共有パレット適用範囲
        self.act_palette = act_palette
        self.sprites = []  # spritesリストを追加
        self.palettes = [None]  # ← ここを追加
        self.last_image_uses_embedded_palette = False  # 最後に取得した画像が独自パレットを使用するかのフラグ

    def read_header(self, f):
        pass  # ヘッダ読み込み不要（内部で行う）

    def read_palettes(self, f):
        pass  # パレットは get_image 時に処理される

    def read_sprites(self, f):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp_json:
            analyze_sff_v1(f, tmp_json.name)

        with open(self.file_path, 'rb') as bis:
            result = extract_sffv1(
                bis,
                tmp_json.name,
                self.image_objects,
                self.image_info_list,
                self.act_palette,
                self.palette_list
            )
            self.palette_mapping, self.shared_palette_range = result

        if self.palette_list:
            self.palettes = self.palette_list
        else:
            self.palettes = [None]

        # spritesリストを構築（viewer.pyが期待する形式）
        self.sprites = []
        for i, info in enumerate(self.image_info_list):
            # 対応する画像から実際のサイズを取得
            width = 1  # デフォルト値を1に設定（0だと表示されない可能性）
            height = 1
            image_data = None  # image_dataフィールドを追加
            
            if i < len(self.image_objects) and self.image_objects[i]:
                width = self.image_objects[i].width
                height = self.image_objects[i].height
                # PIL画像からRGBAバイトデータを取得
                try:
                    img = self.image_objects[i]
                    if img.mode != 'RGBA':
                        img = img.convert('RGBA')
                    image_data = img.tobytes()
                except Exception as e:
                    print(f"[SFFv1] 警告: スプライト{i}のimage_data変換失敗: {e}")
                    image_data = None
            
            # サイズ0の場合でも最低限のサイズを確保
            if width == 0:
                width = 1
            if height == 0:
                height = 1
            
            # パレットインデックスを適切に設定
            pal_idx = self.palette_mapping.get(i, 0)
            sprite = {
                'index': i,
                'group_no': info.get('group_no', 0),
                'sprite_no': info.get('image_no', 0),
                'axisx': info.get('axisx', 0),
                'axisy': info.get('axisy', 0),
                'x_axis': info.get('axisx', 0),  # viewer.pyで使われる可能性
                'y_axis': info.get('axisy', 0),  # viewer.pyで使われる可能性
                'link_idx': info.get('link_index', None),  # リンクindex情報を追加
                'fmt': 0,
                'pal_idx': pal_idx,
                'width': width,
                'height': height,
                'data_ofs': info.get('offset', 0),
                'data_len': info.get('size', 0),
                'image_data': image_data,  # image_dataフィールドを追加
            }
            self.sprites.append(sprite)

    def get_image(self, index, palette_index=0, palette_override=None):
        from PIL import Image
        if index >= len(self.image_objects):
            raise ValueError(f"画像インデックス{index}が範囲外です（最大{len(self.image_objects)-1}）")
        
        img = self.image_objects[index]
        width, height = img.size
        
        sprite_info = self.sprites[index] if index < len(self.sprites) else None
        
        # パレットオーバーライドが指定されている場合は最優先で使用
        if palette_override is not None:
            raw_palette = self._convert_palette_to_flat(palette_override)
            if sprite_info:
                print(f"[DEBUG] get_image: 画像({sprite_info['group_no']},{sprite_info['sprite_no']}) -> オーバーライドパレット使用")
            else:
                print(f"[DEBUG] get_image: 画像index{index} -> オーバーライドパレット使用")
        # SFFv1の仕様に厳密に従う：
        # 共有パレット範囲の画像のみ共有パレット（9000,0またはACT）を使用
        # それ以外は画像埋め込みパレットを強制使用
        elif index in self.shared_palette_range:
            # 共有パレット範囲の画像はパレットリストのパレットを使用
            if len(self.palette_list) == 0:
                # パレットが存在しない場合はデフォルトパレットを作成
                default_palette = []
                for i in range(256):
                    default_palette.extend([i, i, i])  # RGB同値でグレースケール
                raw_palette = default_palette
            else:
                raw_palette = self.palette_list[0]  # 常にインデックス0
            
            if sprite_info:
                print(f"[DEBUG] get_image: 画像({sprite_info['group_no']},{sprite_info['sprite_no']}) -> 共有パレット0使用")
            else:
                print(f"[DEBUG] get_image: 画像index{index} -> 共有パレット0使用")
        else:
            # 共有パレット範囲外の画像は**必ず**独自のパレットを使用
            # ACTパレットや他の外部パレットは一切使用しない
            if index < len(self.image_objects):
                # 画像から直接パレットを取得
                img_palette = img.getpalette()
                if img_palette:
                    raw_palette = img_palette
                    if sprite_info:
                        print(f"[DEBUG] get_image: 画像({sprite_info['group_no']},{sprite_info['sprite_no']}) -> 独自パレット使用（埋め込みパレット）")
                    else:
                        print(f"[DEBUG] get_image: 画像index{index} -> 独自パレット使用（埋め込みパレット）")
                else:
                    # パレットがない場合はデフォルト
                    default_palette = []
                    for i in range(256):
                        default_palette.extend([i, i, i])
                    raw_palette = default_palette
                    if sprite_info:
                        print(f"[DEBUG] get_image: 画像({sprite_info['group_no']},{sprite_info['sprite_no']}) -> デフォルトパレット使用（埋め込みパレットなし）")
                    else:
                        print(f"[DEBUG] get_image: 画像index{index} -> デフォルトパレット使用（埋め込みパレットなし）")
            else:
                default_palette = []
                for i in range(256):
                    default_palette.extend([i, i, i])
                raw_palette = default_palette
        # フラットな 768 長のリストを [(r, g, b, a)] に変換
        palette = []
        for i in range(0, min(len(raw_palette), 768), 3):
            try:
                r, g, b = raw_palette[i], raw_palette[i+1], raw_palette[i+2]
            except IndexError:
                r, g, b = 0, 0, 0
            # インデックス0は透明、それ以外は不透明
            color_index = i // 3
            a = 0 if color_index == 0 else 255
            palette.append((r, g, b, a))

        data = img.tobytes()
        
        # 独自パレット使用フラグをインスタンス変数に保存（呼び出し元で参照可能）
        self.last_image_uses_embedded_palette = index not in self.shared_palette_range
        
        return data, palette, width, height

    def _convert_palette_to_flat(self, palette_rgba):
        """RGBA形式のパレット[(r,g,b,a), ...]をフラット形式[r,g,b,r,g,b,...]に変換"""
        flat_palette = []
        for r, g, b, a in palette_rgba:
            flat_palette.extend([r, g, b])
        # 768バイト（256色×3）まで埋める
        while len(flat_palette) < 768:
            flat_palette.append(0)
        return flat_palette[:768]

    def is_independent_palette_image(self, index):
        """
        SFFv1では独立パレット表示は行わない
        常にFalseを返す
        """
        return False
