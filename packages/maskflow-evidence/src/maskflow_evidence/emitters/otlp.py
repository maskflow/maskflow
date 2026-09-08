"""Ship events as OpenTelemetry log records to an OTLP/HTTP endpoint.

Requires the ``otlp`` extra (``pip install maskflow-evidence[otlp]``). Each
event becomes one OTel log record: the message is the compact JSON line and
the metadata fields are also attached as record attributes, so an existing
OTel pipeline can route and retain evidence alongside other telemetry.

Implemented over the SDK's stdlib ``LoggingHandler`` bridge -- the stable,
documented integration point -- driven directly (its own private logger,
not attached to the root) so evidence never mixes with app logs.
"""

from __future__ import annotations

import logging

from ..schema import EvidenceEvent


class OTLPEmitter:
    def __init__(self, endpoint: str) -> None:
        if not endpoint:
            raise ValueError("otlp sink requires [evidence] url (the OTLP/HTTP logs endpoint)")
        try:
            from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
            from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
            from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        except ModuleNotFoundError as exc:  # pragma: no cover - import guard
            raise ModuleNotFoundError(
                "the otlp evidence sink needs the OpenTelemetry SDK -- "
                "install maskflow-evidence[otlp]"
            ) from exc

        self._provider = LoggerProvider()
        self._provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint))
        )
        self._logger = logging.getLogger("maskflow.evidence.otlp")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        self._handler = LoggingHandler(level=logging.INFO, logger_provider=self._provider)
        self._logger.addHandler(self._handler)

    def emit(self, event: EvidenceEvent) -> None:
        self._logger.info(event.to_json(), extra=event.to_dict())

    def close(self) -> None:
        self._logger.removeHandler(self._handler)
        self._provider.shutdown()
