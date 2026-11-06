"""Bundle the shared repo-root core/ package into the build as cortex/core.

From a git checkout, ../core exists and is force-included. When building a wheel from an
sdist, cortex/core is already inside the unpacked tree and nothing needs to be added.
"""

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        core = (Path(self.root) / ".." / "core").resolve()
        if core.is_dir():
            build_data["force_include"][str(core)] = "cortex/core"
