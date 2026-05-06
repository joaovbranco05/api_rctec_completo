from __future__ import annotations
import requests
from unidecode import unidecode
from difflib import get_close_matches

def norm(s: str) -> str:
    return unidecode(str(s or "").strip().lower())

class IScholarResolver:
    def __init__(self, codigo_escola: str, token: str, unidade: str):
        self.codigo_escola = codigo_escola
        self.token = token
        self.unidade = unidade

        self._cache_matriculas: list[dict] | None = None
        self._cache_disciplinas_por_turma: dict[int, list[dict]] = {}
        self._cache_avaliacoes_por_turma: dict[int, dict[str, list[tuple[str,int]]]] = {}
        self._cache_prof_por_matricula: dict[int, list[dict]] = {}

    def _headers(self):
        return {"X-Codigo-Escola": self.codigo_escola, "X-Autorizacao": self.token}

    def _get(self, url: str, params: dict | None = None) -> dict:
        r = requests.get(url, headers=self._headers(), params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "sucesso":
            raise ValueError(f"API erro em {url}: {data}")
        return data

    def _best_key(self, target: str, keys: list[str], cutoff: float = 0.88) -> str | None:
        t = norm(target)
        if t in keys:
            return t
        close = get_close_matches(t, keys, n=1, cutoff=cutoff)
        return close[0] if close else None

    
    def _load_matriculas(self):
        if self._cache_matriculas is not None:
            return
        url = "https://api.ischolar.app/aluno/pega_alunos"
        data = self._get(url, params={"unidade": self.unidade})
        self._cache_matriculas = data.get("dados", [])

    def resolve_matricula_e_turma(self, aluno_nome: str, turma_nome: str) -> tuple[int, int]:
        self._load_matriculas()
        mats = self._cache_matriculas or []

        
        aluno_map: dict[str, list[dict]] = {}
        for m in mats:
            aluno_map.setdefault(norm(m.get("nome_aluno","")), []).append(m)

        aluno_key = self._best_key(aluno_nome, list(aluno_map.keys()), cutoff=0.86)
        if not aluno_key:
            raise ValueError(f"Aluno não encontrado (unidade={self.unidade}): {aluno_nome}")

        cand = aluno_map[aluno_key]
        turma_map = {norm(c.get("turma","")): c for c in cand}
        turma_key = self._best_key(turma_nome, list(turma_map.keys()), cutoff=0.86)
        if not turma_key:
            
            poss = [c.get("turma","") for c in cand]
            raise ValueError(f"Turma não encontrada para aluno '{aluno_nome}'. Possíveis: {poss}")

        c = turma_map[turma_key]
        return int(c["id_matricula"]), int(c["id_turma"])

    
    def resolve_disciplina(self, id_turma: int, materia_nome: str) -> dict:
        if id_turma not in self._cache_disciplinas_por_turma:
            url = "https://api.ischolar.app/turma/disciplinas"
            data = self._get(url, params={"id_turma": id_turma})
            self._cache_disciplinas_por_turma[id_turma] = data.get("dados", [])

        disciplinas = self._cache_disciplinas_por_turma[id_turma]
        mapping = {norm(d.get("disciplina_nome","")): d for d in disciplinas}
        key = self._best_key(materia_nome, list(mapping.keys()), cutoff=0.86)
        if not key:
            poss = [d.get("disciplina_nome","") for d in disciplinas]
            raise ValueError(f"Disciplina não encontrada na turma {id_turma}: {materia_nome}. Possíveis: {poss}")
        return mapping[key]

    
    def _load_avaliacoes_turma(self, id_turma: int):
        if id_turma in self._cache_avaliacoes_por_turma:
            return

        url = "https://api.ischolar.app/turma/sistema_avaliativo"
        data = self._get(url, params={"id_turma": id_turma})

        
        out: dict[str, list[tuple[str,int]]] = {}

        turmas = (((data.get("data") or {}).get("turma")) or [])
        if not turmas:
            self._cache_avaliacoes_por_turma[id_turma] = out
            return

        
        sistema = (turmas[0].get("sistema_avaliativo") or {})
        divs = sistema.get("divisoes") or []
        for div in divs:
            div_desc = div.get("descricao","")
            for ava in (div.get("avaliacoes") or []):
                name = norm(ava.get("nome_avaliacao",""))
                if not name:
                    continue
                out.setdefault(name, []).append((div_desc, int(ava["id_avaliacao"])))

        self._cache_avaliacoes_por_turma[id_turma] = out

    def resolve_avaliacao_id(self, id_turma: int, avaliacao_nome: str) -> int:
        self._load_avaliacoes_turma(id_turma)
        mapping = self._cache_avaliacoes_por_turma[id_turma]

        key = self._best_key(avaliacao_nome, list(mapping.keys()), cutoff=0.86)
        if not key:
            poss = list(mapping.keys())
            raise ValueError(f"Avaliação não encontrada na turma {id_turma}: {avaliacao_nome}. Possíveis (normalizados): {poss[:20]}...")

        hits = mapping[key]  
        ids = sorted(set(i for _, i in hits))

        
        if len(ids) > 1:
            raise ValueError(f"Avaliação '{avaliacao_nome}' é ambígua na turma {id_turma}. IDs encontrados: {hits}")

        return ids[0]

    
    def resolve_professor_id_por_matricula(self, id_matricula: int, professor_nome: str) -> int:
        if id_matricula not in self._cache_prof_por_matricula:
            url = "https://api.ischolar.app/funcionarios/professores"
            data = self._get(url, params={"id_matricula": id_matricula})
            self._cache_prof_por_matricula[id_matricula] = data.get("dados", [])

        profs = self._cache_prof_por_matricula[id_matricula]
        mapping = {norm(p.get("nome_professor","")): int(p["id_professor"]) for p in profs}
        key = self._best_key(professor_nome, list(mapping.keys()), cutoff=0.86)
        if not key:
            poss = [p.get("nome_professor","") for p in profs]
            raise ValueError(f"Professor não encontrado p/ matrícula {id_matricula}: {professor_nome}. Possíveis: {poss}")
        return mapping[key]
