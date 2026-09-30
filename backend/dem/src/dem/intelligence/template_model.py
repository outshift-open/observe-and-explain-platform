#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Pydantic model for insight templates."""

import hashlib
from pydantic import BaseModel, Field


class InsightTemplateModel(BaseModel):
    """Represents an insight template with metadata and query."""

    nameTemplate: str
    descriptionTemplate: str
    kgQuery: str
    labels: list[str] = Field(default_factory=list)
    scope: str | None = None
    priority: str | None = None
    targetNodeId: str | None = None

    @property
    def templateId(self) -> str:
        """Generate a unique ID based on template name hash."""
        return hashlib.sha256(self.nameTemplate.encode()).hexdigest()
