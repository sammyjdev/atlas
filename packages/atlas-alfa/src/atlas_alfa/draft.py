"""Grounded reply draft. The user sends it. Alfa does not."""

import os
import re

# playbook-vs-cv.md canonical table, baked in so a draft does not depend on the docs repo.
CANON = """
Carreira, obrigatorio:
- Software: cerca de 7 anos desde TJPB set/2019. Proibido: Six years, 6 years, 6 anos.
- AWS: cerca de 4 anos, explicito no CV desde 2022. Proibido: 6 anos de AWS.
- LLM em producao: Avangrid mar/2025. Proibido: 2 anos de LLM, 1,5 ano, GenAI antes de 2025.
- Databricks: skill. Nao amarrar a empregador ou cliente.
- Trabalho atual: assistente clinico / medical reference, nivel de CV.
  Proibido nomear Afya, produto ou dado confidencial.
- Nao inventar LinkedIn, metrica obsoleta, nem ferramenta adjacente como experiencia.
Voz: curta, ativa, sem travessao, sem tom motivacional. Comeca pela resposta.
Forma: interesse em 1 linha, cobertura com artefato ou metrica, gap se faltar must-have,
uma pergunta (faixa, modelo, cliente, duracao), assinatura curta.
Sourcer: 1-2 linhas. Nao escreva piso salarial. Nao diga que a mensagem foi enviada.
""".strip()

# ponytail: substring guard, not a parser. Tighten if it blocks a JD quote the user meant to keep.
_BANNED = (
    re.compile(r"afya", re.I),
    re.compile(r"six years", re.I),
    re.compile(r"\b6 years\b", re.I),
    re.compile(r"\b6 anos\b", re.I),
    re.compile(r"\b2 anos\b", re.I),
    re.compile(r"1[,.]5", re.I),
)

AUTO = object()

NO_MODEL = "Sem modelo nesta máquina. O rascunho não foi inventado."
NO_THREAD = "Cole a thread antes do rascunho."
BLOCKED = "Rascunho bloqueado: fere o canônico de carreira."


def prompt_for(thread: str, *, title: str | None, company: str | None) -> str:
    role = title or "-"
    org = company or "-"
    return (
        "Escreva um rascunho que o usuario envia. Voce nao envia.\n"
        f"Vaga: {role}\nEmpresa: {org}\n\n"
        f"{CANON}\n\n"
        "Se a thread estiver em ingles, o rascunho em ingles. Se em portugues, em portugues.\n"
        "Responda so com estes titulos, nesta ordem:\n"
        "Resumo:\nPrazos:\nProximo passo:\nRascunho:\n\n"
        f"Thread:\n{thread}"
    )


def vet(text: str) -> str | None:
    if any(pattern.search(text) for pattern in _BANNED):
        return None
    return text


def complete_from_env():
    if not os.environ.get("MERIT_API_KEY"):
        return None

    def complete(prompt: str) -> str:
        from atlas_merit.models import build_writer

        result = build_writer().invoke(prompt)
        content = getattr(result, "content", result)
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    parts.append(part.get("text", ""))
                else:
                    parts.append(str(part))
            return "".join(parts)
        return str(content)

    return complete
