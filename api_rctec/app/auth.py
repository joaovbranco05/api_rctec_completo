import reflex as rx
import os


def load_professor_logins() -> dict[str, str]:
    """
    Lê do .env:
    PROFESSOR_LOGINS=65:123,70:abc456
    e retorna {"65":"123", "70":"abc456"}
    """
    raw = (os.getenv("PROFESSOR_LOGINS") or "").strip()
    d: dict[str, str] = {}
    if not raw:
        return d
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        pid, pwd = pair.split(":", 1)
        d[pid.strip()] = pwd.strip()
    return d


class AuthState(rx.State):
    professor_id_input: str = ""
    senha_input: str = ""

    logged_in: bool = False
    professor_id: int = 0

    auth_error: str = ""

    @rx.var
    def is_logged_in(self) -> bool:
        return self.logged_in

    def login(self):
        self.auth_error = ""
        logins = load_professor_logins()

        pid = self.professor_id_input.strip()
        pwd = self.senha_input

        if pid == "" or pwd == "":
            self.auth_error = "Preencha ID e senha."
            return

        if pid not in logins or logins[pid] != pwd:
            self.auth_error = "ID ou senha inválidos."
            return

        self.professor_id = (pid)
        self.logged_in = True

        self.senha_input = ""
        return rx.redirect("/")

    def logout(self):
        self.logged_in = False
        self.professor_id = 0
        self.professor_id_input = ""
        self.senha_input = ""
        self.auth_error = ""
        return rx.redirect("/login")
