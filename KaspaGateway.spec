# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from importlib.metadata import distribution # <-- Import this

# --- Add project root to sys.path ---
sys.path.append(os.getcwd())

from src.config.config import APP_VERSION

# --- Find duckdb metadata path (FIXED for Python 3.12) ---
# This is the fix for 'No package metadata was found for duckdb'
try:
    duckdb_dist = distribution('duckdb')
    
    # NEW FIX: Find the directory containing the .dist-info folder
    duckdb_metadata_path = None
    
    # Iterate through the files provided by the distribution object
    for file in duckdb_dist.files:
        # We are looking for the directory that holds the top-level files (like 'duckdb-X.X.X.dist-info')
        # This usually corresponds to the site-packages root path.
        if '.dist-info' in str(file) and file.locate() is not None:
            # Get the physical path of the file
            full_path = str(file.locate())
            # Go up two levels to get the folder containing the site-packages
            # (e.g., C:\...\site-packages\duckdb-X.X.X.dist-info\METADATA -> C:\...\site-packages)
            metadata_dir_root = os.path.dirname(os.path.dirname(full_path))
            
            # Now we look for the .dist-info folder inside this root
            for item in os.listdir(metadata_dir_root):
                if 'duckdb' in item and item.endswith('.dist-info'):
                    duckdb_metadata_path = os.path.join(metadata_dir_root, item)
                    break
            if duckdb_metadata_path:
                break

    if not duckdb_metadata_path:
        raise Exception("Could not locate duckdb .dist-info folder in site-packages.")

    # The 'datas' tuple format is (source_on_disk, destination_in_bundle)
    # We want to copy the entire '.dist-info' folder to the root of the bundle
    # under the *same name* it has on disk.
    duckdb_datas = (duckdb_metadata_path, os.path.basename(duckdb_metadata_path))
    print(f"Found duckdb metadata at: {duckdb_metadata_path}")
    print(f"Bundling as: {duckdb_datas[1]}")

except Exception as e:
    # Changed error logging to be more descriptive
    print(f"FATAL: Could not resolve duckdb metadata path for bundling. Error: {e}")
    duckdb_datas = None

if duckdb_datas is None:
    raise Exception("Stopping build: duckdb metadata path discovery failed after attempting advanced fixes.")

# --- Main Variables ---
APP_NAME = 'KaspaGateway'
MAIN_SCRIPT = 'src/main.py'
ICON_PATH = 'assets/kaspa-white.ico'
ASSETS_DIR = 'assets'
TRANSLATIONS_DIR = 'src/translations'

# --- Analysis Settings ---
a = Analysis(
    [MAIN_SCRIPT],
    # Paths: Add project root and 'src' folder for PyInstaller's analysis
    pathex=['.', 'src'],
    
    binaries=[],
    
    # Data Files: (source_on_disk, destination_in_bundle)
    datas=[
        (TRANSLATIONS_DIR, 'translations'), # Bundle translation files
        (ASSETS_DIR, 'assets'),             # Bundle fonts and icons
        duckdb_datas                        # <-- Add the metadata path here
    ],
    
    # Hidden Imports: Modules PyInstaller might not find
    hiddenimports=[
        'pywin32',
        'win32timezone',
        'keyring.backends.Windows',
        'psutil',
        'duckdb',
        'babel.numbers',
        'reportlab.fonts'
    ],
    
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher_block_size=16
)

# --- PYZ Archive Settings ---
pyz = PYZ(a.pure, a.zipped_data, cipher_block_size=16)

# --- EXE File Settings ---
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=APP_NAME,
    
    # --- Windowed GUI App (no console) ---
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    
    console=False, # True = opens a black console (for debugging)
    windowed=True, # True = GUI application
    
    # --- Icon ---
    icon=ICON_PATH,
    
    # --- Version Info ---
    version_file=None,
    
    # --- Build Mode ---
    onefile=False  # False = One-Dir (faster startup)
)

# --- App Bundle Settings (for onefile=False) ---
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME  # The name of the output folder in 'dist'
)
