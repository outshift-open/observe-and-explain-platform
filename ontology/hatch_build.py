# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0

"""Hatch build hook: generate the SHACL shapes and the Pydantic KG models before packaging.

``src/oxp_ontology/mas-shapes.ttl`` and ``models/{nodes,edges}/`` are generated from the
ontology and not committed. CI generates them before it builds the published wheel; this
hook does the same whenever the package is built from a source checkout, so a git
dependency (``{ git = "...", subdirectory = "ontology" }``) or ``pip install ./ontology``
gets a complete package.

Built from an sdist, the ``scripts/`` directory is absent and the generated files are
already in the archive, so the hook does nothing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GenerateModelsHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        root = Path(self.root)
        scripts = root / "scripts"
        if not (scripts / "generate_models.py").exists():
            return

        # The shapes first: they are one of the files the models are generated from.
        shapes = _load(scripts / "generate_shacl_shapes.py")
        argv, sys.argv = sys.argv, ["generate_shacl_shapes.py"]
        try:
            shapes.main()
        finally:
            sys.argv = argv

        models = _load(scripts / "generate_models.py")
        ttl_files = sorted((root / "src" / "oxp_ontology").glob("*.ttl"))
        models.generate_robust_pydantic_models([str(p) for p in ttl_files])
