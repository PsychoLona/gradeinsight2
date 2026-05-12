"""
Модуль для расчёта среднего арифметического.
Содержит функции для обработки списков чисел.
"""

def calculate_average(numbers):
    """
    Вычисляет среднее арифметическое списка чисел.

    Args:
        numbers (list): Список чисел (int или float).

    Returns:
        float: Среднее арифметическое.
    """
    if not numbers:
        return 0.0
    total = sum(numbers)
    count = len(numbers)
    return total / count


def main():
    """Основная функция для демонстрации."""
    data = [10, 20, 30, 40, 50]
    avg = calculate_average(data)
    print(f"Среднее: {avg}")


if __name__ == "__main__":
    main()