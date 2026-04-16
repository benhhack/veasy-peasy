# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ["src/veasy_peasy/vzpz_cli.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=(
        collect_submodules("typer")
        + collect_submodules("rich")
        + collect_submodules("click")
        + ["veasy_peasy"]
    ),
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "passporteye",
        "easyocr",
        "pymupdf",
        "torch",
        "torchvision",
        "scipy",
        "numpy",
        "PIL",
        "cv2",
        "sklearn",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="vzpz",
    debug=False,
    strip=False,
    upx=True,
    console=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
