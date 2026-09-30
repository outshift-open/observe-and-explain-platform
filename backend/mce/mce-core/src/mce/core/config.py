#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class MceSettings(BaseSettings):
    """
    Configuration for the MCE library.
    Settings can be overridden by environment variables with the prefix MCE_.

    Provider availability is determined automatically: if a package is importable
    (e.g. deepeval, ragas, opik) its metrics are discovered and registered.
    Install the metapackage to get everything, or install individual provider
    packages to pick only what you need.
    """

    strict_fail_fast: bool = Field(
        default=False, description="Raise exceptions on provider initialization failure"
    )

    model_config = SettingsConfigDict(
        env_prefix="MCE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Global settings instance
settings = MceSettings()
