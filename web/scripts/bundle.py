"""Packs all Python code the site runs into one zip of bytecode, as compiling it takes most of
Python's start. Runs in Pyodide (scripts/assets.ts)."""

from __future__ import annotations

import py_compile
import tempfile
import zipfile
from collections.abc import Iterable
from pathlib import Path

# Nothing the site runs reaches these.
UNUSED = (
    "_pyrepl/",
    "bdb.py",
    "doctest.py",
    "fontTools/merge/",
    "fontTools/mtiLib/",
    "fontTools/ufoLib/",
    "fontTools/voltLib/",
    "imaplib.py",
    "mailbox.py",
    "multiprocessing/",
    "pdb.py",
    "pickletools.py",
    "pydoc.py",
    "pydoc_data/",
    "smtplib.py",
    "unittest/",
    "wsgiref/",
    "xmlrpc/",
)


def bundle(archives: Iterable[str], output: str) -> None:
    """Write the modules, licenses and versions in `archives` (zips and wheels) to one zip."""
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zipped:
        for archive in archives:
            with zipfile.ZipFile(archive) as files:
                for name in sorted(files.namelist()):
                    if name.startswith(UNUSED):
                        continue
                    if name.endswith(".py"):
                        _write(zipped, f"{name}c", _bytecode(name, files.read(name)))
                    elif ".dist-info/" in name:
                        _write(zipped, name, files.read(name))


def _bytecode(name: str, source: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as folder:
        module = Path(folder, "module.py")
        module.write_bytes(source)
        py_compile.compile(
            str(module),
            cfile=f"{module}c",
            dfile=name,
            doraise=True,
            optimize=0,  # assertions stay in: fontTools relies on them to reject damaged fonts
            invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
        )
        return Path(f"{module}c").read_bytes()


def _write(zipped: zipfile.ZipFile, name: str, data: bytes) -> None:
    # ZipInfo's fixed date makes the zip reproducible.
    zipped.writestr(zipfile.ZipInfo(name), data, zipfile.ZIP_DEFLATED, compresslevel=9)
