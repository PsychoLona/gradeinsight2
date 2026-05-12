def calculate_grade(employee_data, competency_weights, grade_levels):
    """
    employee_data: dict с метриками сотрудника
    competency_weights: dict {competency_name: weight}
    grade_levels: list of dict с min_score, max_score, name
    """
    # Нормализуем метрики (0-1)
    normalized = {}
    normalized['tasks'] = min(employee_data.get('tasks_completed', 0) / 100, 1.0)
    normalized['deadlines'] = employee_data.get('deadlines_met', 0) / 100
    normalized['code_quality'] = employee_data.get('code_quality_score', 0) / 100
    normalized['communication'] = employee_data.get('communication_score', 0) / 100
    
    # Расчёт итогового балла
    total_score = sum(
        normalized[key] * competency_weights.get(key, 0.25) 
        for key in ['tasks', 'deadlines', 'code_quality', 'communication']
    )
    
    # Определение грейда по порогам
    grade = "Не определен"
    for gl in grade_levels:
        if gl['min_score'] <= total_score < gl['max_score']:
            grade = gl['name']
            break
    if total_score >= grade_levels[-1]['max_score']:
        grade = grade_levels[-1]['name']
    
    return {
        "total_score": round(total_score, 2),
        "grade": grade,
        "normalized_metrics": normalized
    }

def get_recommendation(calculated_grade: str, formal_grade: str) -> str:
    if not formal_grade:
        return ""
    grades = ["Junior", "Middle", "Senior"]
    if formal_grade not in grades or calculated_grade not in grades:
        return ""
    formal_idx = grades.index(formal_grade)
    calc_idx = grades.index(calculated_grade)
    if calc_idx > formal_idx:
        return "Повысить"
    elif calc_idx < formal_idx:
        return "Понизить"
    else:
        return "Оставить"
