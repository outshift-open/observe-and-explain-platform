#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import json
from typing import Any, Tuple

from metrics_computation_engine.models.eval import BinaryGrading


def stringify_payload(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=True, default=str)
    except Exception:
        return str(value)


async def judge_binary(jury: Any, prompt: str) -> Tuple[float, str]:
    if hasattr(jury, "ajudge"):
        return await jury.ajudge(prompt, BinaryGrading)
    return jury.judge(prompt, BinaryGrading)
