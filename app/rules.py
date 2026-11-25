"""Validation of a daily report (§5.6). The rules are data: an administrator can add one without touching the code.

A rule is a comparison of the reported figures, for example  beds_flu <= beds_total.  An "error" blocks the report,
a "warning" is shown and the person may send it anyway. Expressions are parsed, checked against a small whitelist and
evaluated here; nothing from the database is ever executed as code."""
import ast
import operator
from datetime import date, timedelta

from .translit import lat

CMP = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne}
BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


class RuleError(ValueError):
    pass


def parse(expr: str, codes: set[str] | None = None) -> ast.AST:
    """The syntax tree of a rule, or RuleError saying what is wrong with it."""
    if not expr or len(expr) > 300:
        raise RuleError("Пустое или слишком длинное выражение")
    try:
        tree = ast.parse(expr.strip(), mode="eval").body
    except SyntaxError:
        raise RuleError("Не удалось разобрать выражение. Пример: beds_flu <= beds_total")
    names = set()

    def check(n, top=False):
        if isinstance(n, ast.BoolOp) and isinstance(n.op, (ast.And, ast.Or)):
            return all(check(v, top) for v in n.values)
        if isinstance(n, ast.Compare):
            if not all(type(o) in CMP for o in n.ops):
                raise RuleError("Допустимы сравнения < <= > >= == !=")
            return check(n.left) and all(check(x) for x in n.comparators)
        if top:
            raise RuleError("Правило должно быть сравнением, например: severe <= visits")
        if isinstance(n, ast.BinOp) and type(n.op) in BIN:
            return check(n.left) and check(n.right)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            return check(n.operand)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return True
        if isinstance(n, ast.Name):
            names.add(n.id)
            return True
        raise RuleError("В выражении допустимы только показатели, числа, + − * / и сравнения")

    check(tree, True)
    if codes is not None and not names <= codes:
        raise RuleError("Неизвестные показатели: " + ", ".join(sorted(names - codes)))
    tree._names = names  # type: ignore[attr-defined]
    return tree


def evaluate(tree: ast.AST, values: dict) -> bool | None:
    """True/False, or None when a figure the rule needs is missing or a division by zero happens (the rule then does not apply)."""
    def ev(n):
        if isinstance(n, ast.BoolOp):
            res = [ev(v) for v in n.values]
            if any(r is None for r in res):
                return None
            return all(res) if isinstance(n.op, ast.And) else any(res)
        if isinstance(n, ast.Compare):
            left = ev(n.left)
            for op, comp in zip(n.ops, n.comparators):
                right = ev(comp)
                if left is None or right is None:
                    return None
                if not CMP[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(n, ast.BinOp):
            a, b = ev(n.left), ev(n.right)
            if a is None or b is None:
                return None
            try:
                return BIN[type(n.op)](a, b)
            except ZeroDivisionError:
                return None
        if isinstance(n, ast.UnaryOp):
            v = ev(n.operand)
            return None if v is None else -v
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.Name):
            return values.get(n.id)
    return ev(tree)


class _Safe(dict):
    def __missing__(self, key):
        return "?"


def validate(c, values: dict, lang: str = "ru", facility_id: int | None = None, report_date: str | None = None, partial: bool = False) -> dict:
    """{'errors': [...], 'warnings': [...], 'fields': {code: message}} for the entered figures."""
    ind = c.execute("SELECT code, name_ru, name_uz FROM indicators WHERE active=1 ORDER BY sort").fetchall()
    errors, warnings, fields = [], [], {}
    msg = (lambda r, k: (lat(r[f"{k}_uz"]) if lang == "uz" and r[f"{k}_uz"] else r[f"{k}_ru"]))     # Uzbek is written in Latin
    for i in ind:
        v = values.get(i["code"])
        name = msg(i, "name")
        if v is None and partial:
            continue   # an import may carry only part of the figures; the rules below skip what is absent
        if v is None:
            text = f"Не заполнено: {name}" if lang != "uz" else f"To‘ldirilmagan: {name}"
        elif isinstance(v, bool) or not isinstance(v, int):
            text = f"Нужно целое число: {name}" if lang != "uz" else f"Butun son kerak: {name}"
        elif v < 0:
            text = f"Отрицательные значения запрещены: {name}" if lang != "uz" else f"Manfiy qiymatlar taqiqlanadi: {name}"
        else:
            continue
        errors.append(text)
        fields[i["code"]] = text
    if fields:
        return {"errors": errors, "warnings": warnings, "fields": fields}   # the rules are meaningless on broken figures
    safe = _Safe(values)
    for r in c.execute("SELECT * FROM rules WHERE active=1 ORDER BY sort, id").fetchall():
        try:
            tree = parse(r["expr"])
        except RuleError:
            continue
        if not tree._names <= set(values):  # type: ignore[attr-defined]
            continue
        if evaluate(tree, values) is False:
            text = msg(r, "message").format_map(safe)
            (errors if r["kind"] == "error" else warnings).append(text)
    if facility_id and report_date:
        warnings.extend(history_warnings(c, facility_id, report_date, values, lang))
    return {"errors": errors, "warnings": warnings, "fields": fields}


def history_warnings(c, facility_id: int, report_date: str, values: dict, lang: str) -> list[str]:
    """Unusual compared with the previous report of the same facility: not an error, a hint to double-check."""
    prev = c.execute("SELECT id FROM reports WHERE facility_id=? AND report_date < ? ORDER BY report_date DESC LIMIT 1", (facility_id, report_date)).fetchone()
    if not prev:
        return []
    old = {r["code"]: r["value"] for r in c.execute("SELECT code, value FROM report_values WHERE report_id=?", (prev["id"],))}
    out, uz = [], lang == "uz"
    for code, floor, ru, uzt in (("visits", 20, "Обращений", "Murojaatlar"), ("hosp", 10, "Госпитализаций", "Yotqizilganlar")):
        a, b = values.get(code), old.get(code)
        if a is not None and b and a >= 3 * b and a >= floor:
            out.append(f"{uzt} avvalgi hisobotdan 3 baravar ko‘p ({b} → {a}). Tekshiring." if uz else f"{ru} в 3 и более раз больше, чем в прошлом отчёте ({b} → {a}). Проверьте.")
    a, b = values.get("beds_total"), old.get("beds_total")
    if a is not None and b and abs(a - b) > 0.3 * b:
        out.append(f"Jami o‘rinlar soni keskin o‘zgargan ({b} → {a}). Tekshiring." if uz else f"Общее число коек резко изменилось ({b} → {a}). Проверьте.")
    return out
