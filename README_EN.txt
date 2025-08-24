# SffCharaViewer

A sprite file (.sff) and animation (.air) viewer for MUGEN and IkemenGO
Supports all SFF versions

## Overview

SffCharaViewer is an application for displaying and viewing SFF files in Python code.

### Main Features

- **SFF v1/v2 Support**: Compatible with both old and new SFF formats
- **Enhanced RLE8 Decoder**: High-precision RLE8 compressed sprite analysis
- **Animation Playback**: Animation display using AIR files
- **Image Export**: Individual sprites, sprite sheets, and GIF animation output
- **Multi-language Support**: Japanese/English language switching
- **Advanced Display Features**: Zoom in/out, collision box display, background transparency
- **DEF Integration Support**: Automatic loading from DEF files

## Enhanced RLE8 Decoder

The enhanced RLE8 decoder provides high-precision sprite decoding with automatic color correction.

### Features

1. **High-precision Decoding**: RLE8 decoder compliant with Elecbyte specifications
2. **Performance Optimization**: Efficient processing using NumPy
3. **Automatic Fallback**: Maintains compatibility with legacy decoders
4. **Cache Functionality**: Fast re-loading of the same files

### Alpha Value Correction

Many SFFv2 files have inappropriate alpha values which cause sprites to become transparent.
The Enhanced RLE8 decoder automatically corrects these issues:

- **Background color (Index 0)**: Transparent (alpha=0)
- **Other colors**: Opaque (alpha=255)
- **Auto-correction**: Makes non-black pixels visible

## Usage

### 1. Using the Executable File

Double-click `SffCharaViewer.exe` to start

Command line arguments:
```bash
SffCharaViewer.exe [filename] [options]

Options:
  --debug        Start in debug mode
  --scale SCALE  Specify initial scale factor
  --help         Show help
```

### 2. Running as Python Script

```bash
# Basic execution
python SffCharaViewer.py

# Execute with file specified
python SffCharaViewer.py character.sff

# Execute with DEF file specified
python SffCharaViewer.py character.def
```

### 3. Using as Python Module

```python
import SffCharaViewerModule as sffv

# Create and display GUI viewer
viewer = sffv.create_viewer(show=True)
viewer.load_sff_file("character.sff")

# Get sprite information
sprites = sffv.get_sprite_info("character.sff")
print(f"Number of sprites: {len(sprites)}")

# Extract sprite image
success = sffv.extract_sprite("character.sff", 0, "sprite_0.png")
```

## Build Instructions

### Required Environment
- Python 3.7 or higher
- PyQt5
- Pillow
- PyInstaller

### Manual Build
```bash
# Install required packages
pip install -r requirements.txt

# Build executable file
pyinstaller --onefile --windowed --name SffCharaViewer SffCharaViewer.py
```

## Supported File Formats

- **SFF (Sprite File Format)**: v1, v2
- **AIR (Animation)**: M.U.G.E.N animation files
- **DEF (Definition)**: Character definition files
- **ACT (Palette)**: Palette files

## Feature Details

### Display Features
- Sprite list display
- Palette switching
- Zoom in/out (25%~500%)
- Background transparency display
- Collision box display

### Export Features
- PNG image output (individual sprites)
- Sprite sheet output (complete & per-animation)
- GIF animation output (individual & complete)

### Animation Features
- 60FPS playback
- LoopStart support
- Frame information display

## API Reference

### SFFViewerAPI Class

```python
from SffCharaViewer import SFFViewerAPI

# Create headless reader
reader, is_v2 = SFFViewerAPI.create_headless_reader(file_path)

# Get sprite information
sprite_info = SFFViewerAPI.get_sprite_info(file_path, sprite_index)

# Extract sprite image
qimage = SFFViewerAPI.extract_sprite_image(file_path, sprite_index)
```

## License

Open source software. Use freely.

## Update History

### v1.0.2 (August 17, 2025)
- Fixed RLE8 decode processing
- Split output for long sprite sheets

### v1.0.1 (August 20, 2025)
- Bug fixes

### v1.0.0 (August 17, 2025)
- **Initial Release**
- Complete SFFv1/v2 format support
- AIR animation playback functionality
- Multi-language support (Japanese/English)
- Standalone executable (.exe) support

MUGEN DESU KARA~
