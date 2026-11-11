def backoff_seconds(attempt: int) -> float:
    """Пауза после неудачной попытки: 1с, 2с, 4с."""
    return float(2 ** (attempt - 1))
