import sys

import structlog


def configure_logging() -> None:
    """Configure JSON-capable structured logging for the whole process."""
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(),
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    # Route Uvicorn/FastAPI and third-party standard logs through structlog.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        named_logger = logging.getLogger(logger_name)
        named_logger.handlers.clear()
        named_logger.propagate = True


def get_logger(name: str):
    return structlog.get_logger(name)
