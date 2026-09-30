#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pkgutil import extend_path

# Allow provider packages from separate distributions (e.g. mce-provider-native)
# to contribute modules under the shared `mce.providers` namespace.
__path__ = extend_path(__path__, __name__)
