from __future__ import annotations


def parse_nota(value) -> float:
    """
    Aceita nota 0..10 (inclui 0), com ponto ou vírgula.
    Retorna float.
    """
    
    if value is None:
        raise ValueError("Nota vazia (None).")

    s = str(value).strip()
    if s == "":
        raise ValueError("Nota vazia.")

    s = s.replace(",", ".")

    try:
        nota = float(s)
    except Exception:
        raise ValueError(f"Nota inválida: {value!r}")

    if nota < 0 or nota > 10:
        raise ValueError(f"Nota deve estar entre 0 e 10. Recebido: {nota}")

    return nota
