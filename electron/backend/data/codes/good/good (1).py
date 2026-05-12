def safe_divide(a: float, b: float) -> float:
    """Безопасное деление с проверкой на ноль."""
    if b == 0:
        raise ValueError("Деление на ноль запрещено")
    return a / b