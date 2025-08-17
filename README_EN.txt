# SffCharaViewer

A sprite file (.sff) and animation (.air) viewer for MUGEN and IkemenGO fighting games.
Probably supports all SFF versions.

## Overview

SffCharaViewer is an application for displaying and browsing SFF files in Python code.

### Key Features

- **SFF v1/v2 Support**: Compatible with both old and new SFF formats
- **Animation Playback**: Animation display using AIR files
- **Image Export**: Individual sprite, sprite sheet, and GIF animation export
- **Multi-language Support**: Japanese/English language switching
- **Advanced Display Features**: Zoom, collision box display, background transparency
- **DEF Integration Support**: Automatic loading from DEF files

## File Structure

```
SffCharaViewer_source/
├── SffCharaViewer.py          # Main application
├── SffCharaViewerModule.py    # Module interface
├── examples.py                # Usage examples
├── requirements.txt           # Required packages
├── config/
│   └── SffCharaViewer_config.json  # Configuration file
├── src/                       # Source modules
│   ├── air_parser.py         # AIR file parser
│   ├── sff_core.py           # SFF core functionality
│   ├── sff_parser.py         # SFFv1 parser
│   ├── sffv2_parser.py       # SFFv2 parser
│   └── ui_components.py      # UI components
```

## Usage

### 1. Using the Executable

Double-click `SffCharaViewer.exe` to launch

Command line arguments:
```bash
SffCharaViewer.exe [filename] [options]

Options:
  --debug        Launch in debug mode
  --scale SCALE  Specify initial scale factor
  --help         Show help message
```

### 2. Running as Python Script

```bash
# Basic execution
python SffCharaViewer.py

# Execute with file specified
python SffCharaViewer.py character.sff

# Execute with DEF file specified
python SffCharaViewer.py character.def

# Execute in debug mode
python SffCharaViewer.py --debug
```

### 3. Using as Python Module

#### 3.1 Basic Usage

```python
import SffCharaViewerModule as sffv

# Create and display GUI viewer
viewer = sffv.create_viewer(show=True)
viewer.load_sff_file("character.sff")

# Create viewer with custom configuration
config = sffv.create_config(
    debug_mode=True,
    default_scale=1.5,
    window_width=1400,
    window_height=900
)
viewer = sffv.create_viewer(config, show=True)
```

#### 3.2 Headless API Usage (No GUI)

```python
import SffCharaViewerModule as sffv

# Get sprite information
sprites = sffv.get_sprite_info("character.sff")
print(f"Number of sprites: {len(sprites)}")

# Get detailed sprite information
api = sffv.SFFViewerAPI()
sprite_info = api.get_sprite_info("character.sff", 0)
print(f"Size: {sprite_info['width']}x{sprite_info['height']}")

# Extract sprite image
success = sffv.extract_sprite("character.sff", 0, "sprite_0.png")
if success:
    print("Image extraction successful")

# Get as QImage object
qimage = sffv.extract_sprite("character.sff", 0)
```

#### 3.3 Advanced API Features

```python
from SffCharaViewerModule import SFFViewerAPI

# Create headless reader
reader, is_v2 = SFFViewerAPI.create_headless_reader("character.sff")
print(f"SFF Version: {'v2' if is_v2 else 'v1'}")

# Get all sprite information at once
all_sprites = SFFViewerAPI.get_all_sprites_info("character.sff")
for sprite in all_sprites[:5]:  # Display first 5
    print(f"Group: {sprite['group']}, Image: {sprite['image']}, "
          f"Size: {sprite['width']}x{sprite['height']}")

# Get specific sprite details
sprite_detail = SFFViewerAPI.get_sprite_info("character.sff", 10)
print(f"Axis position: ({sprite_detail['x_axis']}, {sprite_detail['y_axis']})")
```

#### 3.4 Detailed GUI Viewer Control

```python
import SffCharaViewerModule as sffv
from SffCharaViewer import SFFViewerConfig

# Create detailed configuration object
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

# Detailed control using module object
module = sffv.SFFViewerModule(config)
viewer = module.create_gui_viewer(show_immediately=True)

# Load file
viewer.load_sff_file("character.sff")

# Select sprite
viewer.set_sprite_index(5)

# Start animation
animation_list = viewer.get_animation_list()
if animation_list:
    viewer.start_animation(animation_list[0])

# Export image
viewer.export_current_sprite("output.png")

# Run event loop
module.run_event_loop()
```

#### 3.5 Batch Processing Usage

```python
import os
import SffCharaViewerModule as sffv
from SffCharaViewer import SFFViewerAPI

def batch_process_sff_files(directory):
    """Process all SFF files in specified directory"""
    
    for filename in os.listdir(directory):
        if filename.lower().endswith('.sff'):
            filepath = os.path.join(directory, filename)
            print(f"\nProcessing: {filename}")
            
            try:
                # Get sprite information
                sprites = SFFViewerAPI.get_all_sprites_info(filepath)
                print(f"  Number of sprites: {len(sprites)}")
                
                # Create output directory
                output_dir = os.path.join(directory, f"{os.path.splitext(filename)[0]}_sprites")
                os.makedirs(output_dir, exist_ok=True)
                
                # Export all sprites
                for i, sprite in enumerate(sprites):
                    output_path = os.path.join(output_dir, f"sprite_{i:03d}.png")
                    success = SFFViewerAPI.extract_sprite_image(filepath, i, output_path)
                    if success:
                        print(f"  Exported: sprite_{i:03d}.png")
                
            except Exception as e:
                print(f"  Error: {e}")

# Usage example
batch_process_sff_files("./characters")
```

#### 3.6 Module Integration Example (DEF File Support)

```python
import SffCharaViewerModule as sffv
import os

def load_character_complete(def_file_path):
    """Load complete character data from DEF file"""
    
    # Create viewer
    viewer = sffv.create_viewer(show=True)
    
    # Load DEF file
    success = viewer.load_def_file(def_file_path)
    if success:
        print(f"Character load successful: {os.path.basename(def_file_path)}")
        
        # Get animation list
        animations = viewer.get_animation_list()
        print(f"Available animations: {len(animations)}")
        
        # Play first animation
        if animations:
            viewer.start_animation(animations[0])
            print(f"Started animation {animations[0]}")
        
        return viewer
    else:
        print("Character loading failed")
        return None

# Usage example
viewer = load_character_complete("character.def")
if viewer:
    # Further operations...
    pass
```

## API Feature Details

### SFFViewerAPI Class

Low-level API for operating on SFF files without GUI (headless).

#### Main Methods

```python
from SffCharaViewer import SFFViewerAPI

# Create headless reader
reader, is_v2 = SFFViewerAPI.create_headless_reader(file_path)
```
- **Function**: Load SFF file without GUI
- **Returns**: (reader_object, is_v2_format) tuple
- **Use case**: Batch processing, server-side processing

```python
# Get sprite information
sprite_info = SFFViewerAPI.get_sprite_info(file_path, sprite_index)
```
- **Returns**: Dictionary with sprite details
- **Information included**: index, group, image, width, height, x_axis, y_axis, format

```python
# Get all sprite information
all_sprites = SFFViewerAPI.get_all_sprites_info(file_path)
```
- **Returns**: List of all sprite information
- **Use case**: Generate sprite lists, get statistics

```python
# Extract sprite image
qimage = SFFViewerAPI.extract_sprite_image(file_path, sprite_index)
success = SFFViewerAPI.extract_sprite_image(file_path, sprite_index, output_path)
```
- **Function**: Extract sprite as QImage or file
- **Supported formats**: PNG, JPG, BMP, etc. (Qt-supported formats)

### SFFViewerModule Class

High-level interface integrating GUI viewer and API.

#### Basic Methods

```python
from SffCharaViewerModule import SFFViewerModule

# Create module instance
module = SFFViewerModule(config)

# Create GUI viewer
viewer = module.create_gui_viewer(show_immediately=True)

# Get API instance
api = module.get_api()

# Run event loop
module.run_event_loop()
```

#### Configuration Object (SFFViewerConfig)

```python
from SffCharaViewer import SFFViewerConfig

config = SFFViewerConfig(
    # Window size
    window_width=1200,
    window_height=800,
    image_window_width=1000,
    image_window_height=700,
    
    # Display settings
    default_scale=2.0,
    min_scale=25,
    max_scale=500,
    
    # Canvas settings
    canvas_margin=4,
    min_canvas_size=(200, 150),
    max_canvas_size=(4096, 4096),
    
    # Animation settings
    animation_fps=60,
    auto_fit_sprite=False,
    
    # Collision box display settings
    show_clsn=True,
    clsn1_color=(255, 0, 0, 128),    # Defense collision (red)
    clsn2_color=(0, 0, 255, 128),    # Attack collision (blue)
    clsn_line_width=2,
    
    # Debug settings
    debug_mode=True
)
```

### Convenience Functions

```python
import SffCharaViewerModule as sffv

# Simple viewer creation
viewer = sffv.create_viewer(config=None, show=False)

# Simple configuration object creation
config = sffv.create_config(
    debug_mode=False,
    default_scale=2.0,
    window_width=1200,
    window_height=800
)

# Simple sprite information retrieval
sprites = sffv.get_sprite_info(file_path)

# Simple sprite extraction
result = sffv.extract_sprite(file_path, sprite_index, output_path)

# Run standalone app
sffv.run_standalone_app()
```

## Practical Usage Examples

### Web Application Usage

```python
# Flask web app sprite serving example
from flask import Flask, send_file, jsonify
import SffCharaViewerModule as sffv
import io
import base64

app = Flask(__name__)

@app.route('/api/sprites/<path:sff_file>')
def get_sprite_list(sff_file):
    """Return sprite list in JSON format"""
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
    """Serve specified sprite as image"""
    try:
        qimage = sffv.extract_sprite(sff_file, index)
        
        # Convert QImage to byte array
        buffer = io.BytesIO()
        qimage.save(buffer, 'PNG')
        buffer.seek(0)
        
        return send_file(buffer, mimetype='image/png')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
```

### Data Analysis Usage

```python
# Character data statistical analysis
import SffCharaViewerModule as sffv
import matplotlib.pyplot as plt
import pandas as pd

def analyze_character_sprites(sff_file):
    """Statistical analysis of character sprites"""
    
    # Get all sprite information
    sprites = sffv.get_sprite_info(sff_file)
    
    # Convert to DataFrame
    df = pd.DataFrame(sprites)
    
    # Basic statistics
    print("=== Sprite Statistics ===")
    print(f"Total: {len(sprites)}")
    print(f"Average size: {df['width'].mean():.1f} x {df['height'].mean():.1f}")
    print(f"Maximum size: {df['width'].max()} x {df['height'].max()}")
    print(f"Minimum size: {df['width'].min()} x {df['height'].min()}")
    
    # Group-wise aggregation
    group_stats = df.groupby('group').size()
    print(f"\nSprites per group:")
    for group, count in group_stats.items():
        print(f"  Group {group}: {count} sprites")
    
    # Size distribution graphs
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

# Usage example
df = analyze_character_sprites("character.sff")
```

### Game Development Usage

```python
# Sprite loading for game engines
import SffCharaViewerModule as sffv
from PyQt5.QtGui import QPixmap

class SpriteManager:
    """Game sprite management class"""
    
    def __init__(self):
        self.sprite_cache = {}
        self.sprite_info_cache = {}
    
    def load_character(self, sff_file):
        """Load character data"""
        # Cache sprite information
        self.sprite_info_cache[sff_file] = sffv.get_sprite_info(sff_file)
        print(f"Loaded {len(self.sprite_info_cache[sff_file])} sprites from {sff_file}")
    
    def get_sprite(self, sff_file, group, image):
        """Get sprite by group and image number"""
        cache_key = f"{sff_file}:{group}:{image}"
        
        if cache_key in self.sprite_cache:
            return self.sprite_cache[cache_key]
        
        # Search for sprite
        sprites = self.sprite_info_cache.get(sff_file, [])
        for sprite in sprites:
            if sprite['group'] == group and sprite['image'] == image:
                # Get QImage and convert to QPixmap
                qimage = sffv.extract_sprite(sff_file, sprite['index'])
                qpixmap = QPixmap.fromImage(qimage)
                
                # Save to cache
                self.sprite_cache[cache_key] = qpixmap
                return qpixmap
        
        return None  # Not found
    
    def get_sprite_info(self, sff_file, group, image):
        """Get sprite information"""
        sprites = self.sprite_info_cache.get(sff_file, [])
        for sprite in sprites:
            if sprite['group'] == group and sprite['image'] == image:
                return sprite
        return None

# Usage example
sprite_mgr = SpriteManager()
sprite_mgr.load_character("character.sff")

# Get standing pose sprite
standing_sprite = sprite_mgr.get_sprite("character.sff", 0, 0)
if standing_sprite:
    print("Standing pose sprite acquired")
```

## Error Handling and Troubleshooting

### Common Errors and Solutions

```python
import SffCharaViewerModule as sffv

def safe_load_sff(file_path):
    """Safe SFF file loading"""
    try:
        # Check file existence
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"SFF file not found: {file_path}")
        
        # Check file size
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            raise ValueError("SFF file is empty")
        
        if file_size > 100 * 1024 * 1024:  # Over 100MB
            print(f"Warning: Large file ({file_size/1024/1024:.1f}MB)")
        
        # Get sprite information
        sprites = sffv.get_sprite_info(file_path)
        
        if not sprites:
            raise ValueError("No valid sprites found")
        
        print(f"Successfully loaded: {len(sprites)} sprites")
        return sprites
        
    except FileNotFoundError as e:
        print(f"File error: {e}")
    except ValueError as e:
        print(f"Format error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
    
    return None

def safe_extract_sprite(file_path, sprite_index, output_path):
    """Safe sprite extraction"""
    try:
        # Check index range
        sprites = sffv.get_sprite_info(file_path)
        if sprite_index >= len(sprites):
            raise IndexError(f"Sprite index {sprite_index} out of range (0-{len(sprites)-1})")
        
        # Check output directory
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Execute extraction
        success = sffv.extract_sprite(file_path, sprite_index, output_path)
        
        if success:
            print(f"Sprite {sprite_index} exported to {output_path}")
            return True
        else:
            print(f"Failed to export sprite {sprite_index}")
            return False
            
    except Exception as e:
        print(f"Sprite extraction error: {e}")
        return False
```

### Performance Optimization

```python
# Memory efficiency for large-scale processing
import gc
import SffCharaViewerModule as sffv

def process_large_sff_efficiently(file_path, output_dir):
    """Efficient processing of large SFF files"""
    
    # Get sprite information only once
    sprites = sffv.get_sprite_info(file_path)
    total = len(sprites)
    
    print(f"Processing started: {total} sprites")
    
    # Batch processing (limit memory usage)
    batch_size = 50
    for i in range(0, total, batch_size):
        batch_end = min(i + batch_size, total)
        
        print(f"Processing: {i+1}-{batch_end}/{total}")
        
        for j in range(i, batch_end):
            try:
                output_path = os.path.join(output_dir, f"sprite_{j:04d}.png")
                sffv.extract_sprite(file_path, j, output_path)
            except Exception as e:
                print(f"  Error (sprite {j}): {e}")
        
        # Memory cleanup
        if i > 0 and i % (batch_size * 4) == 0:
            gc.collect()
            print("  Memory cleanup executed")
    
    print("Processing complete")
```

## Build Instructions

### Requirements
- Python 3.7 or higher
- PyQt5
- Pillow
- PyInstaller

### Automatic Build
```bash
# For Windows users
.\build_exe.bat

# For Python users
python build_exe.py
```

### Manual Build
```bash
# Install required packages
pip install -r requirements.txt

# Build executable with basic options
pyinstaller --onefile --windowed --name SffCharaViewer --add-data "config;config" --add-data "src;src" SffCharaViewer.py

# Build executable with detailed options
pyinstaller --onefile --windowed --name SffCharaViewer ^
    --add-data "config;config" ^
    --add-data "src;src" ^
    --hidden-import "PyQt5.QtCore" ^
    --hidden-import "PyQt5.QtGui" ^
    --hidden-import "PyQt5.QtWidgets" ^
    --hidden-import "PIL.Image" ^
    --hidden-import "PIL.ImageQt" ^
    --hidden-import "src.ui_components" ^
    --hidden-import "src.air_parser" ^
    --hidden-import "src.sff_core" ^
    --hidden-import "src.sff_parser" ^
    --hidden-import "src.sffv2_parser" ^
    SffCharaViewer.py
```

## Supported File Formats

- **SFF (Sprite File Format)**: v1.01, v2.00, v2.01
- **AIR (Animation)**: M.U.G.E.N animation files
- **DEF (Definition)**: Character definition files
- **ACT (Palette)**: Palette files

## Feature Details

### Display Features
- Sprite list display with detailed information
- Palette switching support
- Zoom display (25%〜500%)
- Background transparency display
- Collision box display (Clsn1/Clsn2)
- High-quality image rendering

### Export Features
- PNG image export (individual sprites)
- Sprite sheet export (all sprites/per animation)
- GIF animation export (individual/batch export)
- High-resolution output support

### Animation Features
- Smooth 60FPS playback
- LoopStart/LoopEnd support
- Detailed frame information display
- Playback control (play/stop/pause)

### Integration Features
- DEF file automatic recognition and loading
- ACT palette file support
- localcoord automatic scaling
- ST file integration

## License

Open Source Software. Use as you like.

## Version History

### v1.0.0 (August 17, 2025)
- **Initial Release**
- Complete SFFv1/v2 format support
- AIR animation playback functionality
- Multi-language support (Japanese/English)
- Standalone executable (.exe) support

#### Key Features
- **Display Functions**
  - Sprite list display
  - Palette switching support
  - Zoom display (25%〜500%)
  - Background transparency display
  - Collision box display
  - High-quality image rendering

- **Animation Functions**
  - Smooth 60FPS playback
  - LoopStart/LoopEnd support
  - Detailed frame information display
  - Playback control (play/stop/pause)

- **Export Functions**
  - PNG image export (individual sprites)
  - Sprite sheet export (all/per animation)
  - GIF animation export (individual/batch)
  - High-resolution output support

- **Integration Functions**
  - DEF file automatic recognition and loading
  - ACT palette file support
  - localcoord automatic scaling
  - ST file integration

#### Technical Specifications
- **Supported SFF Versions**: v1.01, v2.00, v2.01
- **Supported Image Formats**: RLE5, RLE8, RAW, PNG
- **Output Formats**: PNG, JPG, BMP, GIF
- **Animation**: M.U.G.E.N AIR format

#### Module Functions
- **SFFViewerAPI**: Headless operation API
- **SFFViewerModule**: Integrated module interface
- **Batch Processing Support**: Automated processing of large file sets
- **Web App Integration**: Usage with Flask/Django etc.
- **Game Development Support**: Real-time sprite management

#### Build & Distribution
- **PyInstaller**: Single executable file creation
- **Embedded Dependencies**: No Python environment required
- **Cross-platform**: Windows support (Linux/Mac planned)
- **Lightweight**: Unnecessary components removed

#### Architecture
- **Modular Design**: Function-based separation
- **Plugin Support**: Extensible functionality
- **Cache System**: High-speed display optimization
- **Error Handling**: Robust exception handling

That's all!

descolor
