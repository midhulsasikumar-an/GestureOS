# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for GestureOS.
# STUB — fully built out in Checkpoint 10 (Packaging & Deployment).
# This stub exists so the file is present at the location TRD §8 requires
# from Checkpoint 0 onward, allowing later code to reference it without
# a structural change to the project layout.

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)
pyz = PYZ(a.pure)

# Placeholder; replaced with COLLECT()/EXE() at Checkpoint 10.
