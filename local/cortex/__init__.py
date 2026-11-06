"""cortex local package."""

import os as _os

# Installed wheels bundle core/ as cortex/core (hatch force-include). In a source
# checkout (pip install -e, tests) it lives at <repo>/core — expose it as cortex.core.
_here = _os.path.dirname(__file__)
_repo_root = _os.path.normpath(_os.path.join(_here, "..", ".."))
if not _os.path.isdir(_os.path.join(_here, "core")) and _os.path.isdir(_os.path.join(_repo_root, "core")):
    __path__.append(_repo_root)  # type: ignore[name-defined]
