import logging
logging.basicConfig(level=logging.INFO)

def read_file(filename: str) -> str:
    try:
        with open(filename, 'r') as f:
            return f.read()
    except FileNotFoundError:
        logging.error(f"Файл {filename} не найден")
        return ""