#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import logging
import os
from urllib.parse import (
    quote,
    urlsplit,
    urlunsplit,
)

DEFAULT_RABBITMQ_URL = "amqp://guest:guest@localhost/"
DEFAULT_RABBITMQ_URL_WITH_PORT = "amqp://guest:guest@localhost:5672/"
DEFAULT_RABBITMQ_PORT = "5672"


class ColoredFormatter(logging.Formatter):
    """ANSI-colored formatter for terminal logs."""

    GREY = "\033[90m"
    BLUE = "\033[34m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BOLD_RED = "\033[31;1m"
    RESET = "\033[0m"

    _BASE = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    _COLORED = {
        logging.DEBUG: GREY
        + "%(asctime)s - %(name)s - "
        + BLUE
        + "%(levelname)s"
        + GREY
        + " - "
        + RESET
        + "%(message)s",
        logging.INFO: GREY
        + "%(asctime)s - %(name)s - "
        + GREEN
        + "%(levelname)s"
        + GREY
        + " - "
        + RESET
        + "%(message)s",
        logging.WARNING: GREY
        + "%(asctime)s - %(name)s - "
        + YELLOW
        + "%(levelname)s"
        + GREY
        + " - "
        + RESET
        + "%(message)s",
        logging.ERROR: GREY
        + "%(asctime)s - %(name)s - "
        + RED
        + "%(levelname)s"
        + GREY
        + " - "
        + RESET
        + "%(message)s",
        logging.CRITICAL: GREY
        + "%(asctime)s - %(name)s - "
        + BOLD_RED
        + "%(levelname)s"
        + GREY
        + " - "
        + RESET
        + "%(message)s",
    }

    def format(self, record: logging.LogRecord) -> str:
        use_color = getattr(record, "_use_color", True)
        fmt = self._COLORED.get(record.levelno, self._BASE) if use_color else self._BASE
        return logging.Formatter(fmt).format(record)


def configure_worker_logging(*, debug: bool = False) -> None:
    """Configure root logging for workers with consistent colored output."""
    log_level = logging.DEBUG if debug else logging.INFO
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(ColoredFormatter())

    class _ColorFlagFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            record._use_color = True
            return True

    stream_handler.addFilter(_ColorFlagFilter())
    root_logger.addHandler(stream_handler)

    # Keep noisy Neo4j notifications suppressed globally.
    logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)


def mask_url_password(url: str) -> str:
    """Mask password in URLs for safe logging.

    Example: amqp://user:secret@host:5672/ -> amqp://user:***@host:5672/
    """
    try:
        parsed = urlsplit(url)
    except Exception:
        return url

    if parsed.password is None:
        return url

    username = parsed.username or ""
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    userinfo = f"{username}:***"
    netloc = f"{userinfo}@{host}{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def get_available_cpus() -> int:
    """Detect CPU capacity available to this process/container."""
    process_cpu_count = getattr(os, "process_cpu_count", None)
    if callable(process_cpu_count):
        return max(1, process_cpu_count())
    return max(1, os.cpu_count() or 1)


def resolve_max_inflight_messages(
    cli_value: int,
    *,
    error_subject: str,
) -> int:
    """Resolve max inflight message setting from env/CLI with auto support.

    `-1` means auto (= available CPU count), any non-positive value is rejected.
    """
    env_value = os.getenv("MAX_INFLIGHT_MESSAGES")
    raw = env_value if env_value not in (None, "") else str(cli_value)
    parsed = int(raw)
    if parsed == -1:
        return get_available_cpus()
    if parsed <= 0:
        raise ValueError(f"{error_subject} must be -1 (auto) or a positive integer")
    return parsed


def resolve_neo4j_auth(
    explicit_user: str | None = None,
    explicit_password: str | None = None,
    *,
    default_user: str = "",
    default_password: str = "",
) -> tuple[str, str]:
    """Resolve Neo4j credentials from CLI values and env vars.

    Supports either split env vars (`NEO4J_USERNAME`, `NEO4J_PASSWORD`) or
    combined `NEO4J_AUTH` in `username/password` format.

    Resolution order:
    1) Explicit CLI/user-provided values
    2) `NEO4J_AUTH` (`username/password`)
    3) Split env vars (`NEO4J_USERNAME`, `NEO4J_PASSWORD`)
    4) Optional defaults
    """

    auth_user: str | None = None
    auth_password: str | None = None
    auth_value = os.getenv("NEO4J_AUTH")
    if auth_value:
        if "/" not in auth_value:
            raise ValueError("NEO4J_AUTH must be formatted as 'username/password'")
        auth_user, auth_password = auth_value.split("/", 1)

    resolved_user = explicit_user or auth_user or os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER") or default_user
    resolved_password = explicit_password or auth_password or os.getenv("NEO4J_PASSWORD") or default_password

    return resolved_user, resolved_password


def resolve_rabbitmq_url(explicit_url: str | None = None) -> str:
    """Resolve RabbitMQ connection URL from either full URL or split env vars.

     Resolution order:
     1) Explicit URL argument (typically CLI `--rabbitmq-url`)
     2) `RABBITMQ_URL` env var
     3) Split env vars: `RABBITMQ_HOST`, `RABBITMQ_PORT`, `RABBITMQ_USER`,
         `RABBITMQ_PASSWORD`, and `RABBITMQ_VHOST`

    No implicit defaults are allowed for URL/user/password. If neither
    a full URL nor complete split credentials are provided, this raises.
    """

    placeholder_urls = {
        DEFAULT_RABBITMQ_URL.rstrip("/"),
        DEFAULT_RABBITMQ_URL_WITH_PORT.rstrip("/"),
    }

    env_full_url = os.getenv("RABBITMQ_URL")

    host = os.getenv("RABBITMQ_HOST")
    port = os.getenv("RABBITMQ_PORT")
    user = os.getenv("RABBITMQ_USER")
    password = os.getenv("RABBITMQ_PASSWORD")
    vhost = os.getenv("RABBITMQ_VHOST", "/")

    has_any_split_config = bool(user or password or port or host)
    has_complete_split_config = bool(host and user and password)

    explicit_is_placeholder = bool(explicit_url) and explicit_url.rstrip("/") in placeholder_urls
    env_full_is_placeholder = bool(env_full_url) and env_full_url.rstrip("/") in placeholder_urls

    if explicit_url and not (explicit_is_placeholder and has_complete_split_config):
        return explicit_url

    if env_full_url and not (env_full_is_placeholder and has_complete_split_config):
        return env_full_url

    if has_any_split_config:
        if not host:
            raise ValueError("RABBITMQ_HOST is required when using split RabbitMQ configuration")
        if not user:
            raise ValueError("RABBITMQ_USER is required when using split RabbitMQ configuration")
        if not password:
            raise ValueError("RABBITMQ_PASSWORD is required when using split RabbitMQ configuration")

        try:
            port_value = int(port or DEFAULT_RABBITMQ_PORT)
        except ValueError:
            raise ValueError("RABBITMQ_PORT must be an integer")

        # RabbitMQ URL format: amqp://user:pass@host:port/vhost
        if not vhost.startswith("/"):
            vhost = f"/{vhost}"

        user_enc = quote(user, safe="")
        pass_enc = quote(password, safe="")
        return f"amqp://{user_enc}:{pass_enc}@{host}:{port_value}{vhost}"

    raise ValueError(
        "RabbitMQ connection is not configured. Provide either RABBITMQ_URL "
        "or split env vars: RABBITMQ_HOST, RABBITMQ_USER, "
        "RABBITMQ_PASSWORD (and optional RABBITMQ_PORT, RABBITMQ_VHOST)."
    )
