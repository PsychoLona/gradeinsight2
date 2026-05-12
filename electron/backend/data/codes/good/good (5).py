class User:
    """Модель пользователя."""
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age

    def is_adult(self) -> bool:
        return self.age >= 18