"""Ширина колонок таблицы привязок по содержимому (проверка 23.10: «Название» обрезалось, а «Параметры»
стояли с запасом - колонки делили ширину поровну). Без Qt, чтобы закон проверялся на любых числах."""


def fit_widths(needs: list[int], available: int, minimum: int = 60) -> list[int]:
    """Ширины колонок в сумме ровно available.

    Влезает всё - каждая колонка получает свою ширину по содержимому, остаток уходит последней.
    Не влезает - у каждой не меньше minimum, а сверх него место делится пропорционально тому,
    сколько колонке не хватает до minimum (длинное содержимое теряет столько же долей, сколько и короткое).
    """
    n = len(needs)
    if n == 0:
        return []
    available = max(0, int(available))
    want = [max(minimum, int(x)) for x in needs]
    total = sum(want)
    if total <= available:
        out = list(want)
        out[-1] += available - total
        return out
    if available <= minimum * n:
        out = [available // n] * n
        out[-1] += available - sum(out)
        return out
    extra = [w - minimum for w in want]
    k = (available - minimum * n) / sum(extra)
    out = [minimum + int(e * k) for e in extra]
    # остаток от округления - самой широкой, чтобы сумма была ровно available
    out[max(range(n), key=lambda i: want[i])] += available - sum(out)
    return out
