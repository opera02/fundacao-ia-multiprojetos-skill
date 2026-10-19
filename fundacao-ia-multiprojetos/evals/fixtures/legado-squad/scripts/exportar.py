"""Exportador comum (cópia 1 de 2). A cópia em squads/peticoes/ acrescenta assinatura."""


def exportar(case_id, fatos, pendencias):
    linhas = [f"# Rascunho {case_id} (FICTÍCIO)", "", "## Fatos"]
    linhas += [f"- {f['text']} [{f['doc']}]" for f in fatos] or ["- (nenhum fato documentado)"]
    linhas += ["", "## Pendências"]
    linhas += [f"- {p}" for p in pendencias] or ["- nenhuma"]
    return "\n".join(linhas) + "\n"
