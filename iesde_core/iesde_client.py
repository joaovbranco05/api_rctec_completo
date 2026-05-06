# iesde_core/iesde_client.py

import os
from typing import Any, Dict, List, Optional

import requests
import xmltodict
from dotenv import load_dotenv
from requests.auth import HTTPDigestAuth

# Carrega .env da raiz do projeto
load_dotenv()

BASE_URL = (os.getenv("BASE_URL") or "").rstrip("/")
EAD_API_KEY = os.getenv("EAD_API_KEY")
WS_USERNAME = os.getenv("WS_USERNAME")
WS_PASSWORD = os.getenv("WS_PASSWORD")

if not all([BASE_URL, EAD_API_KEY, WS_USERNAME, WS_PASSWORD]):
    raise RuntimeError(
        "Variáveis do .env não carregadas corretamente. "
        "Confira BASE_URL, EAD_API_KEY, WS_USERNAME, WS_PASSWORD."
    )


def _only_digits(s: str) -> str:
    return "".join(c for c in str(s) if c.isdigit())


def _to_float_or_none(x: Any) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if s == "":
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _extract_list_from_payload(payload: Any) -> List[Dict[str, Any]]:
    """
    Normaliza respostas para SEMPRE devolver List[Dict].
    Alguns endpoints retornam:
      - lista diretamente
      - dict com chave Info/data/items
      - dict com erro/status
    """
    if payload is None:
        return []

    # Caso 1: já é lista
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]

    # Caso 2: dict com lista dentro
    if isinstance(payload, dict):
        # chaves comuns
        for key in ("Info", "info", "Items", "items", "Data", "data", "Result", "result"):
            val = payload.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]

        # Às vezes vem algo como {"xml": {...}} etc — sem lista útil
        return []

    # Qualquer outro tipo (str, int...)
    return []


class IESDEClient:
    def __init__(self):
        self.base_url = BASE_URL
        self.session = requests.Session()
        self.session.headers.update(
            {
                "EAD-API-KEY": EAD_API_KEY,
                # Aceita JSON ou XML (alguns endpoints devolvem XML mesmo)
                "Accept": "application/json, text/xml, application/xml, */*",
            }
        )
        self.auth = HTTPDigestAuth(WS_USERNAME, WS_PASSWORD)

    def post_raw(self, path: str, data: Dict[str, Any] | None = None) -> requests.Response:
        url = f"{self.base_url}/{path.lstrip('/')}"
        return self.session.post(url, auth=self.auth, data=data or {}, timeout=60)

    # -----------------------------
    # MATRÍCULAS (por CPF)
    # -----------------------------
    def get_matriculas_por_cpf(self, cpf: str) -> List[Dict[str, Any]]:
        cpf = _only_digits(cpf)

        r = self.post_raw("/web_service/getMatriculas/format/json", {"CPF": cpf})
        if r.status_code >= 400:
            raise RuntimeError(f"Erro HTTP {r.status_code}: {r.text[:500]}")

        payload = r.json()
        # esse endpoint normalmente retorna lista diretamente
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return _extract_list_from_payload(payload)
        return []

    # -----------------------------
    # MATRÍCULAS (paginado, sem CPF)
    # -----------------------------
    def get_matriculas_paginado(
        self,
        pagina: int,
        registros_pagina: int = 200,
        dt_inicio: Optional[str] = None,  # "DD/MM/AAAA"
        dt_fim: Optional[str] = None,     # "DD/MM/AAAA"
        situacao: Optional[str] = None,   # "A" ou "I" ou None
        debug: bool = False,
    ) -> List[Dict[str, Any]]:

        data: Dict[str, Any] = {
            "registros_pagina": int(registros_pagina),
            "pagina": int(pagina),
        }
        if dt_inicio:
            data["DtInicio"] = dt_inicio
        if dt_fim:
            data["DtFim"] = dt_fim
        if situacao is not None:
            data["Situacao"] = situacao

        r = self.post_raw("/web_servicePg/getMatriculas/format/json", data)

        if debug:
            print("\n--- DEBUG get_matriculas_paginado ---")
            print("URL:", f"{self.base_url}/web_servicePg/getMatriculas/format/json")
            print("STATUS:", r.status_code)
            print("REQ DATA:", data)
            print("RESP HEADERS Content-Type:", r.headers.get("Content-Type"))
            print("RESP TEXT (500):", (r.text or "")[:500])

        # Eles às vezes usam 400 para "Nenhum registro encontrado"
        if r.status_code == 400:
            try:
                payload = r.json()
                msg = str(payload.get("mensagem", "")).lower()
                if "nenhum registro" in msg:
                    return []
            except Exception:
                pass
            raise RuntimeError(f"Erro HTTP 400: {r.text[:500]}")

        if r.status_code >= 400:
            raise RuntimeError(f"Erro HTTP {r.status_code}: {r.text[:500]}")

        payload = r.json()

        if isinstance(payload, dict) and payload:
            mats = []
            for k, v in payload.items():
                if str(k).isdigit() and isinstance(v, dict):
                    mats.append(v)
            if mats:
                return mats

        # fallback: se vier lista normal
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]

        # fallback: tenta achar lista dentro de dicts aninhados
        if isinstance(payload, dict):
            for k in ("Info", "info", "Items", "items", "Data", "data", "Result", "result", "Matriculas", "matriculas"):
                v = payload.get(k)
                if isinstance(v, list):
                    return [x for x in v if isinstance(x, dict)]
                if isinstance(v, dict):
                    mats = []
                    for kk, vv in v.items():
                        if str(kk).isdigit() and isinstance(vv, dict):
                            mats.append(vv)
                    if mats:
                        return mats

        return []

    # -----------------------------
    # NOTAS (por matrícula)
    # -----------------------------
    def get_notas_por_matricula(self, matricula_id: str) -> List[Dict[str, Any]]:
        r = self.post_raw("/web_service/notas", {"MatriculaID": str(matricula_id).strip()})

        if r.status_code >= 400:
            raise RuntimeError(f"Erro HTTP {r.status_code}: {r.text[:500]}")

        text = (r.text or "").strip()

        # Normalmente vem XML
        if text.startswith("<?xml") or "<xml" in text[:200].lower():
            parsed = xmltodict.parse(text)
            xml_root = parsed.get("xml", {})
            items = xml_root.get("item", [])

            # quando vem só 1 item, xmltodict retorna dict
            if isinstance(items, dict):
                items = [items]

            out: List[Dict[str, Any]] = []
            for it in items:
                if not isinstance(it, dict):
                    continue

                nota = _to_float_or_none(it.get("Nota"))
                media_final = _to_float_or_none(it.get("MediaFinal"))
                nota_para_lancar = media_final if media_final is not None else nota

                out.append(
                    {
                        "matricula_id": str(it.get("MatriculaID", "")).strip(),
                        "curso_id": str(it.get("CursoID", "")).strip(),
                        "disciplina_id": str(it.get("DisciplinaID", "")).strip(),
                        "disciplina": (it.get("Disciplina") or "").strip(),
                        "prova_id": str(it.get("ProvaID", "")).strip(),
                        "sigla_avaliacao": (it.get("SiglaAvaliacao") or "").strip(),
                        "avaliacao": (it.get("Avaliacao") or "").strip(),
                        "nota": nota,
                        "media_final": media_final,
                        "nota_para_lancar": nota_para_lancar,
                        "dt_aprovacao": (it.get("DtAprovacao") or "").strip() or None,
                        "dt_cad_nota": (it.get("DtCadNota") or "").strip() or None,
                        "dt_alt_nota": (it.get("DtAltNota") or "").strip() or None,
                    }
                )

            return out

        # Se algum dia vier JSON
        try:
            payload = r.json()
            if isinstance(payload, dict) and payload:
                keys = list(payload.keys())
                if all(str(k).isdigit() for k in keys):
                    vals = list(payload.values())
                    # filtra só dicts (cada matrícula é dict)
                    mats = [v for v in vals if isinstance(v, dict)]
                    return mats
            # tenta extrair algo útil
            if isinstance(payload, list):
                return [{"raw": x} for x in payload]
            if isinstance(payload, dict):
                return [{"raw": x} for x in _extract_list_from_payload(payload)] or [{"raw": payload}]
            return [{"raw": payload}]
        except Exception:
            raise RuntimeError(f"Resposta inesperada (não XML/JSON): {text[:500]}")