# sync_planilha_sem_cpf.py
import os
import pandas as pd
from collections import defaultdict

from app.iesde_client import IESDEClient
from app.matching import encontrar_nota_por_disciplina_e_avaliacao
from app.name_utils import norm_text


ARQUIVO_ENTRADA = "modelo importação exemplo.xlsx"
ARQUIVO_SAIDA = "planilha_preenchida_iesde.xlsx"
RELATORIO_SAIDA = "relatorio_sync.csv"

COL_ALUNO = "nome do aluno"
COL_TURMA = "nome da turma"
COL_PROF = "nome do professor"
COL_MATERIA = "nome da materia"
COL_AVALIACAO = "nome da avaliacao"
COL_NOTA = "nota"


def carregar_matriculas_indice(
    client,
    ano_inicio: int = 2022,
    ano_fim: int = 2030,
    situacao=None,
    registros_pagina: int = 200,
) -> dict:
    """
    Baixa matrículas paginadas SEM CPF em janelas de 1 ano (regra da API).
    Cria índice: aluno_normalizado -> lista de matrículas
    """
    indice = defaultdict(list)

    for ano in range(ano_inicio, ano_fim + 1):
        dt_inicio = f"01/01/{ano}"
        dt_fim = f"31/12/{ano}"

        print(f"\n📆 Janela: {dt_inicio} -> {dt_fim}")

        pagina = 1
        while True:
            mats = client.get_matriculas_paginado(
            pagina=pagina,
            registros_pagina=registros_pagina,
            dt_inicio=dt_inicio,
            dt_fim=dt_fim,
            situacao=situacao,
            debug=(ano == ano_inicio and pagina == 1),  # ✅ só 1 vez
        )

            if mats and pagina == 1 and ano == ano_inicio:
                print("DEBUG mats[0] keys:", list(mats[0].keys()))
                print("DEBUG mats[0]:", mats[0])

            for m in mats:
                if not isinstance(m, dict):
                    continue

                # tenta várias chaves possíveis para o nome do aluno
                nome_raw = (
                    m.get("Aluno")
                    or m.get("NomeAluno")
                    or m.get("Nome")
                    or m.get("NomeCompleto")
                    or m.get("AlunoNome")
                    or ""
                )

                nome_raw = (
                    m.get("Aluno")
                    or m.get("NomeAluno")
                    or m.get("Nome")
                    or m.get("NomeCompleto")
                    or m.get("AlunoNome")
                    or ""
                )
                aluno = norm_text(nome_raw)
                if aluno:
                    indice[aluno].append(m)

            print(f"📥 Matrículas: ano {ano} | página {pagina} -> {len(mats)} registros")
            pagina += 1

            if len(mats) < registros_pagina:
                break

    return indice


def main():
    print(">>> ENTROU NO MAIN <<<")
    print("CWD:", os.getcwd())
    print("Arquivos na pasta:", os.listdir("."))

    if not os.path.exists(ARQUIVO_ENTRADA):
        raise FileNotFoundError(
            f"Não achei '{ARQUIVO_ENTRADA}' na pasta atual ({os.getcwd()}). "
            f"Coloque a planilha na raiz do projeto ou ajuste ARQUIVO_ENTRADA."
        )

    df = pd.read_excel(ARQUIVO_ENTRADA)

    # valida colunas
    for c in [COL_ALUNO, COL_TURMA, COL_PROF, COL_MATERIA, COL_AVALIACAO, COL_NOTA]:
        if c not in df.columns:
            raise RuntimeError(
                f"Coluna ausente na planilha: '{c}'. Colunas atuais: {list(df.columns)}"
            )

    client = IESDEClient()

    print("🔎 Baixando e indexando matrículas (paginado)...")
    indice_mats = carregar_matriculas_indice(
        client, ano_inicio=2022, ano_fim=2030, situacao=None, registros_pagina=200
    )
    teste_nome = norm_text("MIRIAN MARIA GOULART")
    print("DEBUG - MIRIAN no índice?", teste_nome in indice_mats)
    if teste_nome in indice_mats:
        print("DEBUG - qtd matrículas:", len(indice_mats[teste_nome]))
        print("DEBUG - MatriculaIDs:", [m.get("MatriculaID") for m in indice_mats[teste_nome]][:20])

    cache_notas = {}  # MatriculaID -> lista de notas já normalizadas
    relatorio = []

    for idx, row in df.iterrows():
        aluno_planilha = str(row[COL_ALUNO]).strip()
        turma_planilha = str(row[COL_TURMA]).strip()
        materia_planilha = str(row[COL_MATERIA]).strip()
        avaliacao_planilha = str(row[COL_AVALIACAO]).strip()

        # pula se já tem nota preenchida
        nota_atual = row.get(COL_NOTA)
        if pd.notna(nota_atual) and str(nota_atual).strip() != "":
            relatorio.append({"linha": idx, "status": "SKIP", "motivo": "nota ja preenchida"})
            continue

        aluno_key = norm_text(aluno_planilha)

        if not aluno_key or not materia_planilha or not avaliacao_planilha:
            relatorio.append({"linha": idx, "status": "SKIP", "motivo": "campos vazios (aluno/materia/avaliacao)"})
            continue

        mats = indice_mats.get(aluno_key, [])
        if not mats:
            relatorio.append({"linha": idx, "status": "ERRO", "motivo": "aluno nao encontrado nas matriculas", "aluno": aluno_planilha})
            continue

        nota_encontrada = None
        usado_matricula = None
        usado_disciplina = None

        # tenta cada matrícula até achar a matéria+avaliação com nota
        for m in mats:
            mat_id = str(m.get("MatriculaID", "")).strip()
            if not mat_id:
                continue

            if mat_id not in cache_notas:
                try:
                    cache_notas[mat_id] = client.get_notas_por_matricula(mat_id)
                except Exception as e:
                    relatorio.append({"linha": idx, "status": "WARN", "motivo": f"falha ao buscar notas MatriculaID={mat_id}: {e}"})
                    continue

            notas = cache_notas[mat_id]

            item = encontrar_nota_por_disciplina_e_avaliacao(
                notas,
                materia_planilha=materia_planilha,
                avaliacao_planilha=avaliacao_planilha,
            )

            if item and item.get("nota_para_lancar") is not None:
                nota_encontrada = item["nota_para_lancar"]
                usado_matricula = mat_id
                usado_disciplina = item.get("disciplina")
                break

        if nota_encontrada is None:
            relatorio.append({
                "linha": idx,
                "status": "NAO_ENCONTRADO",
                "motivo": "materia+avaliacao sem nota ou nao casou",
                "aluno": aluno_planilha,
                "turma": turma_planilha,
                "materia": materia_planilha,
                "avaliacao": avaliacao_planilha,
            })
        else:
            df.at[idx, COL_NOTA] = nota_encontrada
            relatorio.append({
                "linha": idx,
                "status": "OK",
                "aluno": aluno_planilha,
                "turma": turma_planilha,
                "materia": materia_planilha,
                "avaliacao": avaliacao_planilha,
                "nota": nota_encontrada,
                "matricula_id": usado_matricula,
                "disciplina_iesde": usado_disciplina,
            })

    print("💾 Salvando planilha preenchida...")
    df.to_excel(ARQUIVO_SAIDA, index=False)

    print("🧾 Salvando relatório...")
    pd.DataFrame(relatorio).to_csv(RELATORIO_SAIDA, index=False, encoding="utf-8-sig")

    print(f"✅ Pronto! Saídas:\n- {ARQUIVO_SAIDA}\n- {RELATORIO_SAIDA}")


if __name__ == "__main__":
    main()
