from app.iesde_client import IESDEClient
from app.matching import encontrar_disciplina

CPF_TESTE = "12868997961"  # coloca o seu pra testar
MATERIA_TESTE = "MÉTODOS E TÉCNICAS DE PESQUISA"

client = IESDEClient()

matriculas = client.get_matriculas_por_cpf(CPF_TESTE)
print(f"Encontrou {len(matriculas)} matrículas")

# pega a primeira matrícula só pra teste (depois vamos escolher por curso/periodo)
mat = matriculas[0]
matricula_id = mat["MatriculaID"]
print("Usando MatriculaID:", matricula_id, "| Curso:", mat.get("Curso"))

notas = client.get_notas_por_matricula(matricula_id)
item = encontrar_disciplina(notas, MATERIA_TESTE)

if not item:
    print("❌ Matéria não encontrada nas notas dessa matrícula.")
else:
    print("✅ Matéria encontrada:", item["disciplina"])
    print("Nota para lançar:", item["nota_para_lancar"])
