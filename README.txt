# SffCharaViewer

mugen、IkemenGO用スプライトファイル(.sff)とアニメーション(.air)のビューア
多分、各sffバージョン対応済み

## 概要

SffCharaViewerは、SFFファイルをPythonコード上で表示・閲覧するためのアプリケーションです。

### 主な機能

- **SFF v1/v2 対応**: 新旧両方のSFFフォーマットに対応
- **アニメーション再生**: AIRファイルによるアニメーション表示
- **画像出力**: 個別スプライト、スプライトシート、GIFアニメーション出力
- **多言語対応**: 日本語・英語切り替え可能
- **高度な表示機能**: 拡大縮小、当たり判定表示、背景透明化
- **DEF統合サポート**: DEFファイルからの自動読み込み

## ファイル構成

```
SffCharaViewer_source/
├── SffCharaViewer.py          # メインアプリケーション
├── SffCharaViewerModule.py    # モジュールインターフェース
├── examples.py                # 使用例
├── requirements.txt           # 必要パッケージ
├── config/
│   └── SffCharaViewer_config.json  # 設定ファイル
├── src/                       # ソースモジュール
│   ├── air_parser.py         # AIRファイル解析
│   ├── sff_core.py           # SFFコア機能
│   ├── sff_parser.py         # SFFv1パーサー
│   ├── sffv2_parser.py       # SFFv2パーサー
│   └── ui_components.py      # UI部品
├── dist/                      # ビルド済み実行ファイル
│   └── SffCharaViewer.exe    # 単体実行ファイル

```

## 使用方法

### 1. 実行ファイルを使用する場合

`SffCharaViewer.exe` をダブルクリックして起動

コマンドライン引数:
```bash
SffCharaViewer.exe [ファイル名] [オプション]

オプション:
  --debug        デバッグモードで起動
  --scale SCALE  初期スケール倍率を指定
  --help         ヘルプを表示
```

### 2. Pythonスクリプトとして実行する場合

```bash
# 基本実行
python SffCharaViewer.py

# ファイルを指定して実行
python SffCharaViewer.py character.sff

# DEFファイルを指定して実行
python SffCharaViewer.py character.def

# デバッグモードで実行
python SffCharaViewer.py --debug
```

### 3. Pythonモジュールとして使用する場合

#### 3.1 基本的な使用方法

```python
import SffCharaViewerModule as sffv

# GUI版ビューアの作成と表示
viewer = sffv.create_viewer(show=True)
viewer.load_sff_file("character.sff")

# カスタム設定でビューアを作成
config = sffv.create_config(
    debug_mode=True,
    default_scale=1.5,
    window_width=1400,
    window_height=900
)
viewer = sffv.create_viewer(config, show=True)
```

#### 3.2 ヘッドレス API使用（GUIなし）

```python
import SffCharaViewerModule as sffv

# スプライト情報の取得
sprites = sffv.get_sprite_info("character.sff")
print(f"スプライト数: {len(sprites)}")

# 個別スプライトの詳細情報
api = sffv.SFFViewerAPI()
sprite_info = api.get_sprite_info("character.sff", 0)
print(f"サイズ: {sprite_info['width']}x{sprite_info['height']}")

# スプライト画像の抽出
success = sffv.extract_sprite("character.sff", 0, "sprite_0.png")
if success:
    print("画像の抽出に成功しました")

# QImageオブジェクトとして取得
qimage = sffv.extract_sprite("character.sff", 0)
```

#### 3.3 高度なAPI機能

```python
from SffCharaViewerModule import SFFViewerAPI

# ヘッドレスリーダーの作成
reader, is_v2 = SFFViewerAPI.create_headless_reader("character.sff")
print(f"SFFバージョン: {'v2' if is_v2 else 'v1'}")

# 全スプライト情報の一括取得
all_sprites = SFFViewerAPI.get_all_sprites_info("character.sff")
for sprite in all_sprites[:5]:  # 最初の5個を表示
    print(f"Group: {sprite['group']}, Image: {sprite['image']}, "
          f"Size: {sprite['width']}x{sprite['height']}")

# 特定スプライトの詳細情報
sprite_detail = SFFViewerAPI.get_sprite_info("character.sff", 10)
print(f"軸位置: ({sprite_detail['x_axis']}, {sprite_detail['y_axis']})")
```

#### 3.4 GUI ビューアの詳細制御

```python
import SffCharaViewerModule as sffv
from SffCharaViewer import SFFViewerConfig

# 詳細設定オブジェクトの作成
config = SFFViewerConfig(
    window_width=1200,
    window_height=800,
    image_window_width=1000,
    image_window_height=700,
    default_scale=2.0,
    min_scale=25,
    max_scale=500,
    animation_fps=60,
    show_clsn=True,
    debug_mode=True
)

# モジュールオブジェクトを使用した詳細制御
module = sffv.SFFViewerModule(config)
viewer = module.create_gui_viewer(show_immediately=True)

# ファイルの読み込み
viewer.load_sff_file("character.sff")

# スプライトの選択
viewer.set_sprite_index(5)

# アニメーションの開始
animation_list = viewer.get_animation_list()
if animation_list:
    viewer.start_animation(animation_list[0])

# 画像の出力
viewer.export_current_sprite("output.png")

# イベントループの実行
module.run_event_loop()
```

#### 3.5 バッチ処理での活用

```python
import os
import SffCharaViewerModule as sffv
from SffCharaViewer import SFFViewerAPI

def batch_process_sff_files(directory):
    """指定ディレクトリ内の全SFFファイルを処理"""
    
    for filename in os.listdir(directory):
        if filename.lower().endswith('.sff'):
            filepath = os.path.join(directory, filename)
            print(f"\n処理中: {filename}")
            
            try:
                # スプライト情報の取得
                sprites = SFFViewerAPI.get_all_sprites_info(filepath)
                print(f"  スプライト数: {len(sprites)}")
                
                # 出力ディレクトリの作成
                output_dir = os.path.join(directory, f"{os.path.splitext(filename)[0]}_sprites")
                os.makedirs(output_dir, exist_ok=True)
                
                # 全スプライトの出力
                for i, sprite in enumerate(sprites):
                    output_path = os.path.join(output_dir, f"sprite_{i:03d}.png")
                    success = SFFViewerAPI.extract_sprite_image(filepath, i, output_path)
                    if success:
                        print(f"  出力: sprite_{i:03d}.png")
                
            except Exception as e:
                print(f"  エラー: {e}")

# 使用例
batch_process_sff_files("./characters")
```

#### 3.6 モジュール統合例（DEFファイル対応）

```python
import SffCharaViewerModule as sffv
import os

def load_character_complete(def_file_path):
    """DEFファイルから完全なキャラクターデータを読み込み"""
    
    # ビューアの作成
    viewer = sffv.create_viewer(show=True)
    
    # DEFファイルの読み込み
    success = viewer.load_def_file(def_file_path)
    if success:
        print(f"キャラクター読み込み成功: {os.path.basename(def_file_path)}")
        
        # アニメーション一覧の取得
        animations = viewer.get_animation_list()
        print(f"利用可能なアニメーション: {len(animations)}個")
        
        # 最初のアニメーションを再生
        if animations:
            viewer.start_animation(animations[0])
            print(f"アニメーション {animations[0]} を開始")
        
        return viewer
    else:
        print("キャラクターの読み込みに失敗しました")
        return None

# 使用例
viewer = load_character_complete("character.def")
if viewer:
    # さらなる操作...
    pass
```

## API機能詳細

### SFFViewerAPI クラス

ヘッドレス（GUIなし）でSFFファイルを操作するための低レベルAPIです。

#### 主要メソッド

```python
from SffCharaViewer import SFFViewerAPI

# ヘッドレスリーダーの作成
reader, is_v2 = SFFViewerAPI.create_headless_reader(file_path)
```
- **機能**: GUIなしでSFFファイルを読み込み
- **戻り値**: (reader_object, is_v2_format)のタプル
- **用途**: バッチ処理、サーバーサイド処理

```python
# スプライト情報の取得
sprite_info = SFFViewerAPI.get_sprite_info(file_path, sprite_index)
```
- **戻り値**: スプライト詳細情報の辞書
- **含まれる情報**: index, group, image, width, height, x_axis, y_axis, format

```python
# 全スプライト情報の取得
all_sprites = SFFViewerAPI.get_all_sprites_info(file_path)
```
- **戻り値**: 全スプライトの情報リスト
- **用途**: スプライト一覧の生成、統計情報の取得

```python
# スプライト画像の抽出
qimage = SFFViewerAPI.extract_sprite_image(file_path, sprite_index)
success = SFFViewerAPI.extract_sprite_image(file_path, sprite_index, output_path)
```
- **機能**: スプライトをQImageまたはファイルとして抽出
- **対応形式**: PNG, JPG, BMP等（Qt対応形式）

### SFFViewerModule クラス

GUI版ビューアとAPIを統合したハイレベルインターフェースです。

#### 基本メソッド

```python
from SffCharaViewerModule import SFFViewerModule

# モジュールインスタンスの作成
module = SFFViewerModule(config)

# GUIビューアの作成
viewer = module.create_gui_viewer(show_immediately=True)

# APIインスタンスの取得
api = module.get_api()

# イベントループの実行
module.run_event_loop()
```

#### 設定オブジェクト (SFFViewerConfig)

```python
from SffCharaViewer import SFFViewerConfig

config = SFFViewerConfig(
    # ウィンドウサイズ
    window_width=1200,
    window_height=800,
    image_window_width=1000,
    image_window_height=700,
    
    # 表示設定
    default_scale=2.0,
    min_scale=25,
    max_scale=500,
    
    # キャンバス設定
    canvas_margin=4,
    min_canvas_size=(200, 150),
    max_canvas_size=(4096, 4096),
    
    # アニメーション設定
    animation_fps=60,
    auto_fit_sprite=False,
    
    # 当たり判定表示設定
    show_clsn=True,
    clsn1_color=(255, 0, 0, 128),    # 防御判定（赤）
    clsn2_color=(0, 0, 255, 128),    # 攻撃判定（青）
    clsn_line_width=2,
    
    # デバッグ設定
    debug_mode=True
)
```

### 便利関数

```python
import SffCharaViewerModule as sffv

# 簡単なビューア作成
viewer = sffv.create_viewer(config=None, show=False)

# 設定オブジェクトの簡単作成
config = sffv.create_config(
    debug_mode=False,
    default_scale=2.0,
    window_width=1200,
    window_height=800
)

# スプライト情報の簡単取得
sprites = sffv.get_sprite_info(file_path)

# スプライト抽出の簡単実行
result = sffv.extract_sprite(file_path, sprite_index, output_path)

# スタンドアロンアプリの実行
sffv.run_standalone_app()
```

## ビルド方法

### 必要な環境
- Python 3.7以上
- PyQt5
- Pillow
- PyInstaller

### 自動ビルド
```bash
build.bat
```

### 手動ビルド
```bash
# 必要パッケージのインストール
pip install -r requirements.txt

# 実行ファイルをビルド
pyinstaller --onefile --windowed --name SffCharaViewer --add-data "config;config" --add-data "src;src" SffCharaViewer.py
```

## 対応ファイル形式

- **SFF (Sprite File Format)**: v1, v2
- **AIR (Animation)**: M.U.G.E.N アニメーションファイル
- **DEF (Definition)**: キャラクター定義ファイル
- **ACT (Palette)**: パレットファイル

## 機能詳細

### 表示機能
- スプライト一覧表示
- パレット切り替え
- 拡大縮小 (25%〜500%)
- 背景透明化表示
- 当たり判定ボックス表示

### 出力機能
- PNG画像出力（個別スプライト）
- スプライトシート出力（全体・アニメーション別）
- GIFアニメーション出力（個別・全体）

### アニメーション機能
- 60FPS再生
- LoopStart対応
- フレーム情報表示


## 実践的な使用例

### Webアプリケーションでの活用

```python
# Flask Webアプリでのスプライト配信例
from flask import Flask, send_file, jsonify
import SffCharaViewerModule as sffv
import io
import base64

app = Flask(__name__)

@app.route('/api/sprites/<path:sff_file>')
def get_sprite_list(sff_file):
    """スプライト一覧をJSON形式で返す"""
    try:
        sprites = sffv.get_sprite_info(sff_file)
        return jsonify({
            'success': True,
            'count': len(sprites),
            'sprites': sprites
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/sprite/<path:sff_file>/<int:index>')
def get_sprite_image(sff_file, index):
    """指定スプライトを画像として配信"""
    try:
        qimage = sffv.extract_sprite(sff_file, index)
        
        # QImageをバイト配列に変換
        buffer = io.BytesIO()
        qimage.save(buffer, 'PNG')
        buffer.seek(0)
        
        return send_file(buffer, mimetype='image/png')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
```

### データ分析での活用

```python
# キャラクターデータの統計分析
import SffCharaViewerModule as sffv
import matplotlib.pyplot as plt
import pandas as pd

def analyze_character_sprites(sff_file):
    """キャラクタースプライトの統計分析"""
    
    # 全スプライト情報を取得
    sprites = sffv.get_sprite_info(sff_file)
    
    # DataFrameに変換
    df = pd.DataFrame(sprites)
    
    # 基本統計
    print("=== スプライト統計 ===")
    print(f"総数: {len(sprites)}")
    print(f"平均サイズ: {df['width'].mean():.1f} x {df['height'].mean():.1f}")
    print(f"最大サイズ: {df['width'].max()} x {df['height'].max()}")
    print(f"最小サイズ: {df['width'].min()} x {df['height'].min()}")
    
    # グループ別集計
    group_stats = df.groupby('group').size()
    print(f"\nグループ別スプライト数:")
    for group, count in group_stats.items():
        print(f"  Group {group}: {count}個")
    
    # サイズ分布のグラフ化
    plt.figure(figsize=(12, 4))
    
    plt.subplot(1, 3, 1)
    plt.hist(df['width'], bins=20, alpha=0.7)
    plt.title('Width Distribution')
    plt.xlabel('Width (pixels)')
    
    plt.subplot(1, 3, 2)
    plt.hist(df['height'], bins=20, alpha=0.7)
    plt.title('Height Distribution')
    plt.xlabel('Height (pixels)')
    
    plt.subplot(1, 3, 3)
    plt.scatter(df['width'], df['height'], alpha=0.6)
    plt.title('Size Correlation')
    plt.xlabel('Width')
    plt.ylabel('Height')
    
    plt.tight_layout()
    plt.savefig('sprite_analysis.png')
    plt.show()
    
    return df

# 使用例
df = analyze_character_sprites("character.sff")
```

### ゲーム開発での活用

```python
# ゲームエンジンでのスプライト読み込み
import SffCharaViewerModule as sffv
from PyQt5.QtGui import QPixmap

class SpriteManager:
    """ゲーム用スプライト管理クラス"""
    
    def __init__(self):
        self.sprite_cache = {}
        self.sprite_info_cache = {}
    
    def load_character(self, sff_file):
        """キャラクターデータの読み込み"""
        # スプライト情報をキャッシュ
        self.sprite_info_cache[sff_file] = sffv.get_sprite_info(sff_file)
        print(f"Loaded {len(self.sprite_info_cache[sff_file])} sprites from {sff_file}")
    
    def get_sprite(self, sff_file, group, image):
        """グループ・画像番号からスプライトを取得"""
        cache_key = f"{sff_file}:{group}:{image}"
        
        if cache_key in self.sprite_cache:
            return self.sprite_cache[cache_key]
        
        # スプライトを検索
        sprites = self.sprite_info_cache.get(sff_file, [])
        for sprite in sprites:
            if sprite['group'] == group and sprite['image'] == image:
                # QImageを取得してQPixmapに変換
                qimage = sffv.extract_sprite(sff_file, sprite['index'])
                qpixmap = QPixmap.fromImage(qimage)
                
                # キャッシュに保存
                self.sprite_cache[cache_key] = qpixmap
                return qpixmap
        
        return None  # 見つからない場合
    
    def get_sprite_info(self, sff_file, group, image):
        """スプライト情報を取得"""
        sprites = self.sprite_info_cache.get(sff_file, [])
        for sprite in sprites:
            if sprite['group'] == group and sprite['image'] == image:
                return sprite
        return None

# 使用例
sprite_mgr = SpriteManager()
sprite_mgr.load_character("character.sff")

# 立ちポーズのスプライト取得
standing_sprite = sprite_mgr.get_sprite("character.sff", 0, 0)
if standing_sprite:
    print("立ちポーズスプライトを取得しました")
```

## エラー処理とトラブルシューティング

### 一般的なエラーと対策

```python
import SffCharaViewerModule as sffv

def safe_load_sff(file_path):
    """安全なSFFファイル読み込み"""
    try:
        # ファイル存在確認
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"SFFファイルが見つかりません: {file_path}")
        
        # ファイルサイズ確認
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            raise ValueError("SFFファイルが空です")
        
        if file_size > 100 * 1024 * 1024:  # 100MB以上
            print(f"警告: 大きなファイルです ({file_size/1024/1024:.1f}MB)")
        
        # スプライト情報取得
        sprites = sffv.get_sprite_info(file_path)
        
        if not sprites:
            raise ValueError("有効なスプライトが見つかりません")
        
        print(f"正常に読み込まれました: {len(sprites)}個のスプライト")
        return sprites
        
    except FileNotFoundError as e:
        print(f"ファイルエラー: {e}")
    except ValueError as e:
        print(f"フォーマットエラー: {e}")
    except Exception as e:
        print(f"予期しないエラー: {e}")
    
    return None

def safe_extract_sprite(file_path, sprite_index, output_path):
    """安全なスプライト抽出"""
    try:
        # インデックス範囲確認
        sprites = sffv.get_sprite_info(file_path)
        if sprite_index >= len(sprites):
            raise IndexError(f"スプライトインデックス {sprite_index} は範囲外です (0-{len(sprites)-1})")
        
        # 出力ディレクトリ確認
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # 抽出実行
        success = sffv.extract_sprite(file_path, sprite_index, output_path)
        
        if success:
            print(f"スプライト {sprite_index} を {output_path} に出力しました")
            return True
        else:
            print(f"スプライト {sprite_index} の出力に失敗しました")
            return False
            
    except Exception as e:
        print(f"スプライト抽出エラー: {e}")
        return False
```

### パフォーマンス最適化

```python
# 大量処理時のメモリ効率化
import gc
import SffCharaViewerModule as sffv

def process_large_sff_efficiently(file_path, output_dir):
    """大きなSFFファイルの効率的処理"""
    
    # スプライト情報を一度だけ取得
    sprites = sffv.get_sprite_info(file_path)
    total = len(sprites)
    
    print(f"処理開始: {total}個のスプライト")
    
    # バッチ処理（メモリ使用量を制限）
    batch_size = 50
    for i in range(0, total, batch_size):
        batch_end = min(i + batch_size, total)
        
        print(f"処理中: {i+1}-{batch_end}/{total}")
        
        for j in range(i, batch_end):
            try:
                output_path = os.path.join(output_dir, f"sprite_{j:04d}.png")
                sffv.extract_sprite(file_path, j, output_path)
            except Exception as e:
                print(f"  エラー (sprite {j}): {e}")
        
        # メモリ解放
        if i > 0 and i % (batch_size * 4) == 0:
            gc.collect()
            print("  メモリクリーンアップ実行")
    
    print("処理完了")
```

## ライセンス

オープンソースソフトウェア。好きにしよう。

## 更新履歴

### v1.0.0 (2025年8月17日)
- **初回リリース**
- SFFv1/v2形式完全対応
- AIRアニメーション再生機能
- 多言語対応（日本語・英語）
- 単体実行ファイル(.exe)対応

#### 主要機能
- **表示機能**
  - スプライト一覧表示
  - パレット切り替え対応
  - 拡大縮小表示 (25%〜500%)
  - 背景透明化表示
  - 当たり判定ボックス表示
  - 高品質画像レンダリング

- **アニメーション機能**
  - 60FPS滑らかな再生
  - LoopStart/LoopEnd対応
  - フレーム情報詳細表示
  - 再生制御（再生/停止/一時停止）

- **出力機能**
  - PNG画像出力（個別スプライト）
  - スプライトシート出力（全体・アニメーション別）
  - GIFアニメーション出力（個別・全体一括）
  - 高解像度出力対応

- **統合機能**
  - DEFファイル自動認識・読み込み
  - ACTパレットファイル対応
  - localcoord自動スケーリング
  - STファイル連動

#### 技術仕様
- **対応SFFバージョン**: v1.01, v2.00, v2.01
- **対応画像形式**: RLE5, RLE8, RAW, PNG
- **出力形式**: PNG, JPG, BMP, GIF
- **アニメーション**: M.U.G.E.N AIR形式

#### モジュール機能
- **SFFViewerAPI**: ヘッドレス操作API
- **SFFViewerModule**: 統合モジュールインターフェース
- **バッチ処理対応**: 大量ファイル自動処理
- **Webアプリ連携**: Flask/Django等での活用
- **ゲーム開発支援**: リアルタイムスプライト管理

#### ビルド・配布
- **PyInstaller**: 単一実行ファイル化
- **依存関係内蔵**: Python環境不要
- **クロスプラットフォーム**: Windows対応（Linux/Mac予定）
- **軽量化**: 不要コンポーネント除去

#### アーキテクチャ
- **モジュラー設計**: 機能別分離
- **プラグイン対応**: 拡張機能追加可能
- **キャッシュ機能**: 高速表示最適化
- **エラーハンドリング**: 堅牢な例外処理


ですからー