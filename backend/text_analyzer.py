import re

positive_words = {
    'хороший', 'отличный', 'прекрасный', 'замечательный', 'полезный',
    'понятно', 'ясно', 'спасибо', 'благодарю', 'молодец', 'верно',
    'правильно', 'успешно', 'эффективно', 'быстро', 'качественно'
}
negative_words = {
    'плохой', 'ужасный', 'неправильно', 'ошибка', 'баг', 'сложно',
    'непонятно', 'задержка', 'медленно', 'некачественно', 'проблема',
    'неудача', 'срыв', 'дедлайн', 'срочно'
}
polite_words = {
    'пожалуйста', 'будьте добры', 'извините', 'прошу', 'благодарю',
    'спасибо', 'пожалуй', 'разрешите'
}

def analyze_comments(text: str) -> dict:
    if not text or len(text.strip()) < 10:
        return {"communication_score": 50.0, "sentiment": "neutral", "details": "Недостаточно текста"}

    sentences = re.split(r'[.!?]', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 0]
    total_sentences = len(sentences)

    words = re.findall(r'\b[а-яё]+\b', text.lower())
    pos_count = sum(1 for w in words if w in positive_words)
    neg_count = sum(1 for w in words if w in negative_words)
    polite_count = sum(1 for w in words if w in polite_words)

    if pos_count > neg_count * 2:
        sentiment = "positive"
        base_score = 80
    elif neg_count > pos_count * 2:
        sentiment = "negative"
        base_score = 30
    else:
        sentiment = "neutral"
        base_score = 60

    base_score += min(10, polite_count * 2)
    volume_bonus = min(10, total_sentences // 3)
    constructive = 10 if any(word in text.lower() for word in ['предлагаю', 'нужно', 'следует', 'давайте', 'важно']) else 0
    score = min(100, base_score + volume_bonus + constructive)

    return {
        "communication_score": round(score, 2),
        "sentiment": sentiment,
        "details": f"Проанализировано {total_sentences} предложений, {len(words)} слов."
    }