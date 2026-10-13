#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Parse complete JSON values, allowing only omitted closing delimiters at EOF."""

import json


def loads_json_response(text: str, *, allow_eof_close: bool = False):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        if not allow_eof_close or error.pos != len(text) or not text or text[-1] in "{[:,":
            raise
        stack, quoted, escaped = [], False, False
        for char in text:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "{[":
                stack.append("}" if char == "{" else "]")
            elif char in "}]" and (not stack or stack.pop() != char):
                raise error
        if quoted or not stack:
            raise
        return json.loads(text + "".join(reversed(stack)))
