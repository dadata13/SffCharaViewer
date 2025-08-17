# -*- coding: utf-8 -*-
"""
SffCharaViewer Module Usage Examples
===============================

This file demonstrates how to use the SffCharaViewer module both as a library
and as a standalone application.
"""

import sys
import os

# Add the current directory to Python path for import
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import the module
import SffCharaViewerModule as sffv


def example_1_simple_gui():
    """Example 1: Simple GUI usage"""
    print("Example 1: Simple GUI usage")
    print("-" * 30)
    
    # Create a simple viewer with default settings
    viewer = sffv.create_viewer(show=True)
    
    # You can load a file if you have one
    # viewer.load_sff_file("path/to/your/file.sff")
    
    print("GUI viewer created and shown")
    print("Close the window to continue to next example")
    
    # For this example, we won't run the event loop to continue
    return viewer


def example_2_custom_config():
    """Example 2: Custom configuration"""
    print("\nExample 2: Custom configuration")
    print("-" * 30)
    
    # Create custom configuration
    config = sffv.create_config(
        debug_mode=True,
        default_scale=3.0,
        window_width=1400,
        window_height=900
    )
    
    # Create viewer with custom config
    viewer = sffv.create_viewer(config, show=False)  # Don't show immediately
    
    print(f"Created viewer with custom config:")
    print(f"  Debug mode: {config.debug_mode}")
    print(f"  Default scale: {config.default_scale}")
    print(f"  Window size: {config.window_width}x{config.window_height}")
    
    return viewer


def example_3_api_usage():
    """Example 3: API usage (headless)"""
    print("\nExample 3: API usage (headless)")
    print("-" * 30)
    
    # This example requires an actual SFF file
    # Replace with path to a real SFF file for testing
    sample_file = "sample.sff"
    
    if os.path.exists(sample_file):
        try:
            # Get sprite information
            sprites = sffv.get_sprite_info(sample_file)
            print(f"Found {len(sprites)} sprites in {sample_file}")
            
            if sprites:
                print(f"First sprite info: {sprites[0]}")
                
                # Extract first sprite as image
                # This will return a QImage object
                image = sffv.extract_sprite(sample_file, 0)
                print(f"Extracted sprite 0: {image.width()}x{image.height()}")
                
                # Save sprite to file
                success = sffv.extract_sprite(sample_file, 0, "extracted_sprite_0.png")
                if success:
                    print("Sprite saved to extracted_sprite_0.png")
                
        except Exception as e:
            print(f"Error using API: {e}")
    else:
        print(f"Sample file {sample_file} not found.")
        print("Create a sample SFF file or modify the path to test API functionality.")


def example_4_advanced_module_usage():
    """Example 4: Advanced module usage"""
    print("\nExample 4: Advanced module usage")
    print("-" * 30)
    
    # Create module instance for more control
    module = sffv.SFFViewerModule()
    
    # Create GUI viewer but don't show yet
    viewer = module.create_gui_viewer(show_immediately=False)
    
    # Get API for headless operations
    api = module.get_api()
    
    print("Created module with both GUI and API access")
    print(f"Viewer instance: {viewer}")
    print(f"API instance: {api}")
    
    # Show the viewer when ready
    viewer.show()
    
    return module


def example_5_integration_with_existing_code():
    """Example 5: Integration with existing PyQt5 application"""
    print("\nExample 5: Integration with existing PyQt5 application")
    print("-" * 30)
    
    from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton
    
    # Your existing application
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Main Application with SffCharaViewer")
            self.setGeometry(100, 100, 400, 300)
            
            # Central widget
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            layout = QVBoxLayout(central_widget)
            
            # Button to open SFF viewer
            self.sff_viewer = None
            btn_open_sff = QPushButton("Open SffCharaViewer")
            btn_open_sff.clicked.connect(self.open_sff_viewer)
            layout.addWidget(btn_open_sff)
            
        def open_sff_viewer(self):
            if self.sff_viewer is None:
                # Create SFF viewer as part of existing application
                config = sffv.create_config(debug_mode=True)
                self.sff_viewer = sffv.create_viewer(config, show=False)
            
            self.sff_viewer.show()
            self.sff_viewer.raise_()
            self.sff_viewer.activateWindow()
    
    main_window = MainWindow()
    main_window.show()
    
    print("Created main application with integrated SffCharaViewer")
    print("Click 'Open SffCharaViewer' button to open the SffCharaViewer")
    
    return app, main_window


def run_examples():
    """Run all examples"""
    print("SffCharaViewer Module Examples")
    print("=" * 40)
    
    # Example 1: Simple GUI
    viewer1 = example_1_simple_gui()
    
    # Example 2: Custom config
    viewer2 = example_2_custom_config()
    
    # Example 3: API usage
    example_3_api_usage()
    
    # Example 4: Advanced module
    module = example_4_advanced_module_usage()
    
    # Example 5: Integration
    app, main_window = example_5_integration_with_existing_code()
    
    print("\n" + "=" * 40)
    print("All examples completed!")
    print("Note: GUI windows were created but event loop was not started.")
    print("To actually use the GUI, call app.exec_() or use sffv.run_standalone_app()")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='SffCharaViewer Module Examples')
    parser.add_argument('--example', type=int, choices=[1,2,3,4,5], help='Run specific example')
    parser.add_argument('--run-gui', action='store_true', help='Run GUI event loop')
    parser.add_argument('--standalone', action='store_true', help='Run as standalone app')
    args = parser.parse_args()
    
    if args.standalone:
        # Run as standalone application
        sffv.run_standalone_app()
    
    elif args.example:
        # Run specific example
        if args.example == 1:
            viewer = example_1_simple_gui()
        elif args.example == 2:
            viewer = example_2_custom_config()
        elif args.example == 3:
            example_3_api_usage()
        elif args.example == 4:
            module = example_4_advanced_module_usage()
        elif args.example == 5:
            app, main_window = example_5_integration_with_existing_code()
        
        if args.run_gui and args.example != 3:
            # Run GUI event loop for GUI examples
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                print("Starting GUI event loop...")
                sys.exit(app.exec_())
    
    else:
        # Run all examples
        run_examples()
