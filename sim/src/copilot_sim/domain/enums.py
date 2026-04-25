"""Categorical labels used across the engine, sensors, historian and co-pilot."""

from __future__ import annotations

from enum import Enum


class OperationalStatus(Enum):
    FUNCTIONAL = "FUNCTIONAL"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    FAILED = "FAILED"
    # UNKNOWN is reserved for the observed view when no sensor reading is recoverable.
    # Never used in true (engine) state.
    UNKNOWN = "UNKNOWN"


class PrintOutcome(Enum):
    OK = "OK"
    QUALITY_DEGRADED = "QUALITY_DEGRADED"
    HALTED = "HALTED"


class Severity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class OperatorEventKind(Enum):
    TROUBLESHOOT = "TROUBLESHOOT"
    FIX = "FIX"
    REPLACE = "REPLACE"
