# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('C:\\\\Users\\\\Khalid\\\\Documents\\\\Projects\\\\NeuralAgent\\\\neuralagent-desktop\\\\aiagent\\\\venv\\\\Lib\\\\site-packages\\\\browser_use\\\\agent\\\\system_prompt.md', 'browser_use/agent'), ('C:\\\\Users\\\\Khalid\\\\Documents\\\\Projects\\\\NeuralAgent\\\\neuralagent-desktop\\\\aiagent\\\\venv\\\\Lib\\\\site-packages\\\\browser_use\\\\dom\\\\buildDomTree.js', 'browser_use/dom')]
binaries = []
hiddenimports = ['mem0.configs.vector_stores', 'mem0.configs.vector_stores.qdrant', 'mem0.configs.vector_stores.faiss', 'mem0.configs.vector_stores.chroma']
tmp_ret = collect_all('playwright')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['aiagent\\main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['aiagent\\\\pyi_playwright_hook.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='agent.exe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='agent.exe',
)
