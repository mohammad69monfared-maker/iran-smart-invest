"""Human-readable reporting. Numbers originate only from the analysis engine."""
from .narrative import build_narrative, optional_ollama
from .details import technical, fundamental_note

__all__ = ["build_narrative", "optional_ollama", "technical", "fundamental_note"]
