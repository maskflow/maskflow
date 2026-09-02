# PyInstaller spec for the standalone `maskflow` binary.
#
# The binary ships the pattern/checksum detection pass only -- Aadhaar, PAN,
# GSTIN, UPI, IFSC, email, phone, cards, and every other regex/checksum
# recognizer. spaCy and the NER model are deliberately EXCLUDED: bundling
# them turns a ~40 MB binary into a ~1 GB one that is fragile across the
# three OSes, and `maskflow_core.ner` already degrades cleanly when spaCy
# is absent (bare names/addresses are simply not counted, and `--deep`
# exits with a message pointing at the pip / Docker install).
#
# Build:  pyinstaller packages/maskflow-cli/packaging/maskflow.spec
# Output: dist/maskflow (dist/maskflow.exe on Windows) -- relative to CWD.

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

_ENTRY = os.path.join(SPECPATH, "_entry.py")  # noqa: F821 -- SPECPATH is PyInstaller-injected

datas = []
hiddenimports = []

# The recognizer packs register via import side effects and ship bundled
# reference data (IFSC/UPI/RTO code lists, name & place gazetteers) as
# package data -- collect both, for every submodule, so nothing is missed.
for pkg in ("maskflow_core", "maskflow_pack_intl", "maskflow_pack_india", "maskflow_cli"):
    datas += collect_data_files(pkg)
    hiddenimports += collect_submodules(pkg)

# Entry-point plugin discovery: the packs expose "maskflow.recognizers"
# entry points; the CLI imports them directly too, but keep the metadata.
datas += collect_data_files("maskflow_cli", include_py_files=False)

excludes = [
    "spacy",
    "thinc",
    "blis",
    "cymem",
    "preshed",
    "murmurhash",
    "wasabi",
    "srsly",
    "catalogue",
    "weasel",
    "en_core_web_sm",
    "numpy",
    "pandas",
    "matplotlib",
    "IPython",
    "pytest",
]

a = Analysis(
    [_ENTRY],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="maskflow",
    console=True,
    strip=False,
    upx=False,
    disable_windowed_traceback=False,
)
