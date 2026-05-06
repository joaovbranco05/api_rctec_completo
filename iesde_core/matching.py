# app/matching.py
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional
from rapidfuzz import fuzz


# -----------------------------
# Normalização de texto
# -----------------------------
def norm(s: Any) -> str:
    s = ("" if s is None else str(s)).strip().lower()
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    s = " ".join(s.split())
    return s


def only_alnum_space(s: str) -> str:
    # remove quase tudo exceto letras/numeros/espacos
    return re.sub(r"[^a-z0-9 ]+", " ", norm(s))


# -----------------------------
# Heurísticas para avaliação
# -----------------------------
def _avaliacao_synonyms(av: str) -> List[str]:
    """
    Expande sinônimos comuns de "nome da avaliacao" da planilha.
    Mapeia nomes do iScholar para nomes da IESDE:
    - Prova Presencial (iScholar) → ACF (IESDE)
    - Prova Online (iScholar) → PO (IESDE)
    """
    a = only_alnum_space(av)

    # padrões comuns
    base = [a]

    # ✅ MAPEAMENTO ISCHOLAR → IESDE
    # Prova Online → PO
    if a in {"po", "prova online"} or "prova online" in a or "online" in a:
        base += ["prova online", "online", "po"]
    
    # Prova Presencial → ACF
    if a in {"pp", "prova presencial", "acf"} or "prova presencial" in a or "presencial" in a:
        base += ["prova presencial", "presencial", "pp", "acf"]
    
    # Outros padrões comuns
    if "rec" == a or "recuperacao" in a or "reavaliacao" in a:
        base += ["recuperacao", "reavaliacao", "rec"]
    if "atividade" in a or "trabalho" in a or "tde" in a:
        base += ["atividade", "trabalho", "tde"]

    # remove duplicados mantendo ordem
    out = []
    for x in base:
        x = only_alnum_space(x)
        if x and x not in out:
            out.append(x)
    return out


def _avaliacao_match(item: Dict[str, Any], avaliacao_planilha: str) -> int:
    """
    Retorna um score 0..100 de quão bem o item casa com a avaliação.
    Usa item['avaliacao'] e item['sigla_avaliacao'] (se existirem).
    """
    alvo_variants = _avaliacao_synonyms(avaliacao_planilha)
    if not alvo_variants:
        return 0

    item_av = only_alnum_space(item.get("avaliacao", ""))
    item_sigla = only_alnum_space(item.get("sigla_avaliacao", ""))

    # se não tem nada no item, não casa
    if not item_av and not item_sigla:
        return 0

    best = 0
    for alvo in alvo_variants:
        # exato/contém
        if alvo and item_av and (alvo == item_av or alvo in item_av or item_av in alvo):
            best = max(best, 100)
        if alvo and item_sigla and (alvo == item_sigla or alvo in item_sigla or item_sigla in alvo):
            best = max(best, 100)

        # fuzzy
        if item_av:
            best = max(best, fuzz.token_sort_ratio(alvo, item_av))
            best = max(best, fuzz.partial_ratio(alvo, item_av))
        if item_sigla:
            best = max(best, fuzz.token_sort_ratio(alvo, item_sigla))
            best = max(best, fuzz.partial_ratio(alvo, item_sigla))

    return int(best)


# -----------------------------
# Heurísticas para disciplina
# -----------------------------
def _disciplina_match(item: Dict[str, Any], materia_planilha: str) -> int:
    """
    Score 0..100 de match da disciplina.
    """
    alvo = only_alnum_space(materia_planilha)
    if not alvo:
        return 0

    disc = only_alnum_space(item.get("disciplina", ""))
    if not disc:
        return 0

    # exato/contém primeiro
    if alvo == disc:
        return 100
    if alvo in disc or disc in alvo:
        return 98

    # fuzzy
    return int(max(
        fuzz.token_sort_ratio(alvo, disc),
        fuzz.token_set_ratio(alvo, disc),
        fuzz.partial_ratio(alvo, disc),
    ))


# -----------------------------
# Função principal
# -----------------------------
def encontrar_nota_por_disciplina_e_avaliacao(
    notas: List[Dict[str, Any]],
    materia_planilha: str,
    avaliacao_planilha: str,
    limiar_avaliacao: int = 85,
    limiar_disciplina: int = 88,
) -> Optional[Dict[str, Any]]:
    """
    Retorna o item da IESDE (um dict dentro de 'notas') que melhor casa com:
      - disciplina ~ materia_planilha
      - avaliacao/sigla ~ avaliacao_planilha

    Estratégia:
      1) calcula score de avaliação; filtra por limiar
      2) dentro dos filtrados, escolhe o melhor por disciplina
      3) se disciplina não passar limiar, retorna None (para não lançar errado)

    Observação: 'notas' é a lista que você já devolve em get_notas_por_matricula()
    """
    if not notas:
        return None

    # 1) filtra por avaliação
    candidatos = []
    for it in notas:
        if not isinstance(it, dict):
            continue
        sc_av = _avaliacao_match(it, avaliacao_planilha)
        if sc_av >= limiar_avaliacao:
            candidatos.append((sc_av, it))

    if not candidatos:
        return None

    # ordena melhores avaliações primeiro (em caso de empate, disciplina decide)
    candidatos.sort(key=lambda t: t[0], reverse=True)

    # 2) escolhe melhor disciplina entre os candidatos (pondera avaliação + disciplina)
    best_item = None
    best_score = -1

    for sc_av, it in candidatos:
        sc_disc = _disciplina_match(it, materia_planilha)

        # precisa passar o limiar de disciplina
        if sc_disc < limiar_disciplina:
            continue

        # score combinado (prioriza avaliação, mas exige disciplina boa)
        combined = sc_av * 0.55 + sc_disc * 0.45

        # bônus se tiver ProvaID (geralmente é item de avaliação mesmo)
        if (it.get("prova_id") or "").strip():
            combined += 2

        if combined > best_score:
            best_score = combined
            best_item = it

    return best_item
