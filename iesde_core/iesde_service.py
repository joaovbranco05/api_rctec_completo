# app/iesde_service.py
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .iesde_client import IESDEClient

# O IESDEClient agora será importado via __init__.py
from .matching import encontrar_nota_por_disciplina_e_avaliacao
from .name_utils import norm_text


Matricula = Dict[str, Any]
NotaItem = Dict[str, Any]


def build_indice_matriculas(
    client: IESDEClient,
    ano_inicio: int = 2022,
    ano_fim: int = 2030,
    situacao: Optional[str] = None,   # None = todas
    registros_pagina: int = 200,
    verbose: bool = False,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Índice: nome_normalizado -> lista de matrículas (dict)
    """
    indice = defaultdict(list)

    for ano in range(ano_inicio, ano_fim + 1):
        dt_inicio = f"01/01/{ano}"
        dt_fim = f"31/12/{ano}"
        
        if verbose:
            print(f"📅 Indexando ano {ano}...")

        pagina = 1
        while True:
            mats = client.get_matriculas_paginado(
                pagina=pagina,
                registros_pagina=registros_pagina,
                dt_inicio=dt_inicio,
                dt_fim=dt_fim,
                situacao=situacao,
            )
            if not mats:
                break

            for m in mats:
                nome_raw = (
                    m.get("Aluno")
                    or m.get("NomeAluno")
                    or m.get("Nome")
                    or m.get("NomeCompleto")
                    or ""
                )
                key = norm_text(nome_raw)
                if key:
                    indice[key].append(m)

            if verbose:
                print(f"  📥 Página {pagina}: {len(mats)} matrículas")

            if len(mats) < registros_pagina:
                break
            pagina += 1

    if verbose:
        print(f"✅ Total de alunos indexados: {len(indice)}")

    return dict(indice)


def buscar_nota_iesde(
    *,
    client: IESDEClient,
    indice_matriculas: Dict[str, List[Dict[str, Any]]],
    cache_notas: Dict[str, List[Dict[str, Any]]],
    aluno_nome: str,
    materia_nome: str,
    avaliacao_nome: str,
) -> Optional[float]:
    """
    Retorna a nota (float) ou None.
    - usa nome (sem CPF) -> lista de MatriculaIDs
    - para cada MatriculaID: get_notas_por_matricula (cacheado)
    - encontra item por disciplina+avaliacao
    """
    print(f"\n🔍 BUSCAR_NOTA_IESDE:")
    print(f"  Aluno: {aluno_nome}")
    print(f"  Matéria: {materia_nome}")
    print(f"  Avaliação: {avaliacao_nome}")
    
    aluno_key = norm_text(aluno_nome)
    mats = indice_matriculas.get(aluno_key, [])
    if not mats:
        print(f"  ❌ Aluno não encontrado no índice")
        return None

    print(f"  ✅ Encontradas {len(mats)} matrículas para este aluno")

    for m in mats:
        mat_id = str(m.get("MatriculaID", "")).strip()
        if not mat_id:
            continue

        if mat_id not in cache_notas:
            print(f"  📥 Buscando notas da matrícula {mat_id}...")
            cache_notas[mat_id] = client.get_notas_por_matricula(mat_id)
            print(f"  📊 Total de notas retornadas: {len(cache_notas[mat_id])}")

        item = encontrar_nota_por_disciplina_e_avaliacao(
            cache_notas[mat_id],
            materia_planilha=materia_nome,
            avaliacao_planilha=avaliacao_nome,
        )
        if item and item.get("nota_para_lancar") is not None:
            nota = float(item["nota_para_lancar"])
            print(f"  ✅ NOTA ENCONTRADA: {nota}")
            print(f"     Disciplina IESDE: {item.get('disciplina', 'N/A')}")
            print(f"     Avaliação IESDE: {item.get('avaliacao', 'N/A')} / {item.get('sigla_avaliacao', 'N/A')}")
            return nota

    print(f"  ❌ Nota não encontrada")
    return None
