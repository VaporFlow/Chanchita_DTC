# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['Chanchita_DTC.pyw'],
    pathex=[],
    binaries=[('C:\\Users\\fmang\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\site-packages\\libmgrs.cp313-win_amd64.pyd', '.')],
    datas=[('airport_names.db', '.')],
    hiddenimports=['mgrs'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Chanchita_DTC',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['G:\\Chanchita_DTC\\chanchita.ico'],
)
# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['Chanchita_DTC.pyw'],
    pathex=[],
    binaries=[('C:\\Users\\fmang\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\site-packages\\libmgrs.cp313-win_amd64.pyd', '.')],
    datas=[('airport_names.db', '.')],
    hiddenimports=['mgrs'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Chanchita_DTC',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['G:\\Chanchita_DTC\\chanchita.ico'],
)
