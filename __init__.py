"""
SffCharaViewer Library
=================

A Python library for viewing and manipulating SFF (Sprite File Format) files.

Basic Usage (New Module Interface):
----------------------------------
```python
import SffCharaViewerModule as sffv

# GUI usage
viewer = sffv.create_viewer(show=True)
viewer.load_sff_file("character.sff")

# API usage (headless)
sprites = sffv.get_sprite_info("character.sff")
image = sffv.extract_sprite("character.sff", 0, "sprite_0.png")

# Advanced usage
config = sffv.create_config(debug_mode=True, default_scale=3.0)
viewer = sffv.create_viewer(config)
```

Legacy Usage:
------------
```python
from SffCharaViewer import SFFViewer, SFFReader

# Create a viewer instance
viewer = SFFViewer()

# Load an SFF file
viewer.load_sff_file("path/to/file.sff")

# Show the viewer window
viewer.show()
```

Classes:
--------
- SFFViewer: Main GUI application for viewing SFF files
- SFFViewerAPI: Headless API for programmatic access
- SFFViewerModule: High-level module interface
- SFFViewerConfig: Configuration management
"""

__version__ = "1.0.0"
__author__ = "SffCharaViewer Development Team"

# Import main classes for easy access
try:
    from .SffCharaViewer import SFFViewer, SFFViewerConfig, SFFViewerAPI
    from .SffCharaViewerModule import (
        SFFViewerModule, create_viewer, create_config,
        get_sprite_info, extract_sprite, run_standalone_app
    )
except ImportError:
    # Fallback for when running as standalone
    try:
        from SffCharaViewer import SFFViewer, SFFViewerConfig, SFFViewerAPI
        from SffCharaViewerModule import (
            SFFViewerModule, create_viewer, create_config,
            get_sprite_info, extract_sprite, run_standalone_app
        )
    except ImportError:
        # If all imports fail, define minimal interface
        def create_viewer(*args, **kwargs):
            raise ImportError("SffCharaViewer modules not available")
        
        def get_sprite_info(*args, **kwargs):
            raise ImportError("SffCharaViewer modules not available")

# Public API
__all__ = [
    'SFFViewer',
    'SFFViewerConfig',
    'SFFViewerAPI',
    'SFFViewerModule',
    'create_viewer',
    'create_config',
    'get_sprite_info',
    'extract_sprite',
    'run_standalone_app',
    'open_sff_file'
]

def open_sff_file(file_path, show_gui=True, config=None):
    """
    Open an SFF file with the viewer.
    
    Args:
        file_path (str): Path to the SFF file
        show_gui (bool): Whether to show the GUI window (default: True)
        config (SFFViewerConfig, optional): Configuration object
        
    Returns:
        SFFViewer: The viewer instance with the file loaded
    """
    if config is None:
        config = create_config()
    
    viewer = create_viewer(config, show=show_gui)
    
    success = viewer.load_sff_file(file_path)
    if not success:
        raise FileNotFoundError(f"Could not load SFF file: {file_path}")
    
    return viewer
