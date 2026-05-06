import requests
from dataclasses import dataclass

@dataclass
class IScholarConfig:
    codigo_escola: str
    token_acesso: str

class IScholarClient:
    def __init__(self, cfg: IScholarConfig):
        self.cfg = cfg
        self.base_url = "https://api.ischolar.app"

    def _headers(self) -> dict:
        return {
            "X-Codigo-Escola": self.cfg.codigo_escola,
            "X-Autorizacao": self.cfg.token_acesso,
            "Content-Type": "application/json",
        }

    def lancar_nota(
        self,
        *,
        id_matricula: int,
        id_disciplina: int,
        id_avaliacao: int,
        id_professor: int,
        valor: float,
    ) -> dict:
        url = f"{self.base_url}/notas/lanca_nota"

        
        if valor is None:
            raise ValueError("valor é obrigatório (use 0 se for zero).")

        payload = {
            "id_matricula": int(id_matricula),
            "id_disciplina": int(id_disciplina),
            "id_avaliacao": int(id_avaliacao),
            "id_professor": int(id_professor),
            "valor": "0.0" if float(valor) == 0.0 else float(valor),
        }
        
        r = requests.post(url, headers=self._headers(), json=payload, timeout=30)
        
        r.raise_for_status()
        return r.json()
