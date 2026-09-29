# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0

"""Hand-written base classes for the generated KG node/edge Pydantic models.

Everything else under ``oxp_ontology.models`` (``nodes/``, ``edges/``) is
produced by ``scripts/generate_models.py`` from the bundled ontology TTL
files and is not committed to source control. This module is the one
exception: the generator imports ``KGNode``/``KGEdge`` from it, so it has to
exist before generation runs.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

MAS_CONTEXT = {
    "mas": "https://outshift-open.github.io/oxp-ontology/mas#",
    "source_id": {"@id": "mas:source", "@type": "@id"},
    "target_id": {"@id": "mas:target", "@type": "@id"},
}


class KGBase(BaseModel):
    """Base Pydantic contract shared by all KG nodes and edges."""

    model_config = ConfigDict(extra="forbid")

    @property
    def kg_type(self) -> str:
        """Return the ontology type name represented by this model class."""
        return self.__class__.__name__

    def to_json(self) -> dict[str, Any]:
        """Serialize the KG object to a JSON-compatible dictionary."""
        return self.model_dump(mode="json", exclude_none=True)

    def to_jsonld(self) -> dict[str, Any]:
        """Serialize the KG object to a compact JSON-LD dictionary."""
        payload = self.to_json()
        jsonld: dict[str, Any] = {
            "@context": MAS_CONTEXT,
            "@type": f"mas:{self.kg_type}",
        }
        item_id = self.kg_id
        if item_id:
            jsonld["@id"] = item_id
        jsonld.update(payload)
        return jsonld

    @property
    def kg_id(self) -> str | None:
        """Return the best available stable identifier for this KG object."""
        for field_name in ("id", "canonicalId", "callId", "agentId"):
            value = getattr(self, field_name, None)
            if value:
                return str(value)
        return None


class KGNode(KGBase):
    """Base class for ontology node models."""

    def to_json(self) -> dict[str, Any]:
        """Serialize a node and include its ontology node type."""
        payload = super().to_json()
        if self.kg_id:
            payload.setdefault("id", self.kg_id)
        payload.setdefault("node_type", self.kg_type)
        return payload


class KGEdge(KGBase):
    """Base class for ontology edge models."""

    source_id: str
    target_id: str

    @property
    def kg_id(self) -> str | None:
        """Return a deterministic edge identifier from type and endpoints."""
        return f"{self.kg_type}:{self.source_id}:{self.target_id}"

    def to_json(self) -> dict[str, Any]:
        """Serialize an edge and include its ontology edge type."""
        payload = super().to_json()
        payload.setdefault("from_id", self.source_id)
        payload.setdefault("to_id", self.target_id)
        payload.setdefault("edge_type", self.kg_type)
        return payload

    def to_jsonld(self) -> dict[str, Any]:
        """Serialize an edge to JSON-LD with explicit source and target IRIs."""
        payload = super().to_jsonld()
        payload["source"] = {"@id": self.source_id}
        payload["target"] = {"@id": self.target_id}
        return payload
