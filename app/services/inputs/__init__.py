"""Pluggable input layer.

    connector (excel | csv | pdf | image_ocr | web_crawler | http_api)
        │  .fetch() ──► ConnectorResult (rows | docs)
        ▼
    sink.route_result  ──►  TimescaleDB (rows)  |  Qdrant (docs)

Add a source once (via the API / ``input_sources`` table) and pick or swap the
connector later — nothing downstream changes.
"""

from app.services.inputs.base import (
    ConfigError,
    ConnectorKind,
    ConnectorResult,
    DocItem,
    InputConnector,
)
from app.services.inputs.registry import get_connector, list_connectors
from app.services.inputs.sink import route_result, run_connector

__all__ = [
    "InputConnector",
    "ConnectorResult",
    "ConnectorKind",
    "DocItem",
    "ConfigError",
    "get_connector",
    "list_connectors",
    "route_result",
    "run_connector",
]
