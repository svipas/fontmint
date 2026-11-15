"""fontmint — mint your own builds of the fonts you use.

Use the `fontmint` command, or the library:

    from fontmint import Options, mint

    files = mint(font_bytes, Options(features="ss02", name="Inter Clear", axes={"wght": "400,700"}))
"""

from importlib.metadata import PackageNotFoundError, version

from .common import FORMATS, FontmintError
from .core import FontInfo, Job, Options, Prepared, build_job, inspect, mint, prepare

try:
    __version__ = version("fontmint")
except PackageNotFoundError:  # running from a source tree that isn't installed
    __version__ = "0.0.0"

__all__ = [
    "FORMATS",
    "FontInfo",
    "FontmintError",
    "Job",
    "Options",
    "Prepared",
    "build_job",
    "inspect",
    "mint",
    "prepare",
]
