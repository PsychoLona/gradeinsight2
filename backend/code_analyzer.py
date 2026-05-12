import os
import tempfile
import subprocess
import re
from pylint.lint import Run
from radon.complexity import cc_visit
from radon.metrics import mi_visit

def analyze_code_from_text(code_text: str) -> dict:
    """
    Анализирует код и возвращает:
    - pylint_score (0-10)
    - avg_complexity (средняя цикломатическая сложность)
    - comment_ratio (%)
    - code_quality_score (0-100)
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(code_text)
        temp_file = f.name

    # 1. pylint (оценка 0-10)
    try:
        # Запускаем pylint через командную строку, чтобы получить оценку
        result = subprocess.run(
            ['pylint', temp_file, '--score=y', '--exit-zero'],
            capture_output=True, text=True
        )
        output = result.stdout
        # Ищем строку "Your code has been rated at X.XX/10"
        match = re.search(r'rated at (\d+\.\d+)/10', output)
        if match:
            pylint_score = float(match.group(1))
        else:
            pylint_score = 0.0
    except Exception:
        pylint_score = 0.0

    # 2. radon (цикломатическая сложность)
    try:
        with open(temp_file, 'r') as f:
            code = f.read()
        blocks = cc_visit(code)
        if blocks:
            avg_complexity = sum(b.complexity for b in blocks) / len(blocks)
        else:
            avg_complexity = 0
        # Сложность > 15 считается плохой, > 25 – очень плохой
        complexity_score = max(0, 100 - avg_complexity * 3)
        if complexity_score < 0:
            complexity_score = 0
    except Exception:
        avg_complexity = 0
        complexity_score = 50  # нейтральное значение

    # 3. Процент комментариев
    try:
        lines = code_text.split('\n')
        total_lines = len([l for l in lines if l.strip()])
        comment_lines = sum(1 for l in lines if l.strip().startswith('#'))
        comment_ratio = (comment_lines / total_lines * 100) if total_lines > 0 else 0
        # Максимум 30% комментариев считается идеальным
        comment_score = min(100, comment_ratio * 3)
    except Exception:
        comment_ratio = 0
        comment_score = 0

    # 4. Итоговый балл (взвешенный)
    # pylint весит 50%, сложность 30%, комментарии 20%
    final_score = (pylint_score / 10) * 50 + (complexity_score * 0.3) + (comment_score * 0.2)
    final_score = min(100, max(0, final_score))

    os.unlink(temp_file)

    return {
        "pylint_score": round(pylint_score, 2),
        "avg_complexity": round(avg_complexity, 2),
        "comment_ratio": round(comment_ratio, 2),
        "code_quality_score": round(final_score, 2)
    }
