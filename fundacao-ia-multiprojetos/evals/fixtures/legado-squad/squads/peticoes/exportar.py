"""Exportador (cópia 2 de 2): idêntico ao comum, mas acrescenta campo de assinatura.

Diferença intencional ou acidental? Investigar antes de unificar (livro A02, p15).
"""


def exportar(case_id, fatos, pendencias):
    linhas = [f"# Rascunho {case_id} (FICTÍCIO)", "", "## Fatos"]
    linhas += [f"- {f['text']} [{f['doc']}]" for f in fatos] or ["- (nenhum fato documentado)"]
    linhas += ["", "## Pendências"]
    linhas += [f"- {p}" for p in pendencias] or ["- nenhuma"]
    linhas += ["", "Assinatura: (pendente de revisão profissional)"]
    return "\n".join(linhas) + "\n"
