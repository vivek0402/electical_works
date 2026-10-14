"""Small helpers for text typed into forms, shared by the service modules."""


def clean_text(text):
    """Typed text that may run over several lines: NUL bytes dropped (Postgres rejects them), ends trimmed."""
    return (text or "").replace(chr(0), "").strip()
