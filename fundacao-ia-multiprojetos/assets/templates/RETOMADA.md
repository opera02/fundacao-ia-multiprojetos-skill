# RETOMADA

> Índice de estado e evidências para continuar em outra sessão ou outro provedor — não é
> fonte de autorização: quem escreve na pasta pode alterá-lo, e
> `python scripts/retomada.py validar --arquivo RETOMADA.md` confere só o preenchimento.
> A IA seguinte confere os arquivos citados antes de agir; ação que exige decisão do usuário
> só vale se confirmada na conversa atual ou pela origem verificável registrada abaixo.
> Não copie credenciais, conversas integrais nem documentos de outros projetos.
> Índice enxuto (até ~12 KB e 150 linhas): estado atual e uma linha por efeito já realizado. O histórico
> vai para `evidence/retomada/` com `python scripts/retomada.py arquivar --arquivo RETOMADA.md --historico
> evidence/retomada`, que confere a cópia e deixa aqui a linha `Histórico arquivado: <caminho> (sha256 ...)`.

project_id: (preencher)
run_id de referência: (preencher)
Fluxo da skill: (A implantar | B adaptar | C operar)
Versão da skill e do kit: (preencher)

Objetivo atual: (preencher)
Resultado aceito até aqui: (preencher)

Estado confirmado: (preencher — o que foi observado, não o que foi planejado)
Versão do código/configuração: (preencher — commit, hash do manifesto ou versão)
Versão ou hash dos artefatos relevantes: (preencher)
Permissões e limites registrados: (preencher — histórico; valem só com a origem abaixo)
Origem das autorizações: (preencher — por autorização: autor, ação, recurso, limites e vigência, num registro verificável fora do alcance de quem edita este arquivo, ex.: approval_id gravado pelo serviço da fundação; "conversa de <data>" é histórico: em outra sessão, ação que exige decisão pede nova confirmação; ou "nenhuma")

Evidências: (preencher — caminhos em evidence/, um por linha)

Arquivos mínimos para leitura:
1. (preencher)

Pendência prioritária: (preencher)
Próxima ação autorizada: (preencher — sem origem verificável, é proposta a confirmar)
Verificação necessária para aceitá-la: (preencher)

Ações já realizadas que não devem ser repetidas: (preencher — efeitos externos, chamadas pagas, envios, migrações aplicadas; use "nenhum" se não houver)
Aprovações que precisam ser revalidadas: (preencher ou "nenhum")
Bloqueios de acesso, custo ou decisão: (preencher ou "nenhum" — para cada um: impacto e condição de resolução)
Recursos em uso: (preencher ou "nenhum" — processos e servidores abertos, pastas temporárias, banco aberto no Windows ou no WSL)

Última conferência do registro: (preencher data/hora com fuso)
Responsável pela conferência: (preencher)
