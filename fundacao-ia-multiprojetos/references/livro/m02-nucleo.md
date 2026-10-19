# Módulo 02 — Núcleo reutilizável e recuperação (A05–A07, p28–39)

## Ideia central
Primeiro um ponto de retorno **restaurado de verdade**; depois um núcleo pequeno que
reconhece projetos e persiste tarefas; então um modelo que cria projetos isolados de
forma previsível e repetível.

## Frameworks do livro
- **Quatro grupos de preservação** (A05 p28): código e regras (histórico e cópia) · dados
  de projeto (cópia por escopo) · estado operacional (exportação consistente) · ambiente
  (receita de recriação). Credenciais têm procedimento próprio, fora do pacote.
- **Prova negativa da restauração** (A05 p29): alterar um arquivo e remover outro só na
  cópia de teste; a comparação aponta os dois.
- **Inventário que não confunde intenção com funcionamento** (A06 p32): planejado · em
  desenvolvimento · bloqueado · implementado e ativo · implementado e inativo.
- **`schema_version` × `version`** (A06 p33).
- **Modelo × instância × configuração** (A07 p36) e **lista positiva** do modelo.
- **Identidade antes da resposta** (A07 p36): `project_id` estável; `case_id`; principal
  autenticado; a IA pode sugerir projeto, mas a sugestão não dá acesso.

## Conceitos-chave
Estado de referência · bundle Git (não leva arquivos soltos, alterações, configuração local
nem hooks) · `Connection.backup()` do sqlite3 · venv recriável (não copiável) · núcleo ·
interface/contrato · adaptador · atomicidade (transações) · contenção de caminhos
(`Path.resolve()` não autentica) · colisão de nomes no Windows · migração explícita de instâncias.

## Antipadrões
- "Criei a versão antes da migração" sem restaurar: faltou `caso-demo.txt` fora do Git (p29).
- Copiar banco enquanto é alterado (p29); restaurar sobre a origem (p29).
- Hashes dos PDFs conferem, mas a lista de tarefas restaurada está vazia → aula não
  concluída (p31).
- Pasta `memory/` + "memória pronta" no inventário (p35).
- Gerador que exige editar o núcleo para cada projeto; "isolado porque cada pasta tem
  nome diferente" (p38).
- Skill genérica cujo exemplo traz nome de cliente promovida ao modelo (p39).

## Referência — contratos didáticos
Registro de componente (A06 p33): `{"schema_version":1,"component_id":"local_task_store",
"version":"0.1.0","scope":"foundation","status":"in_development","entrypoint":
"components.local_task_store","permissions":["task_state:read","task_state:write"],
"evidence":[]}`. Configuração de projeto (A07 p37): `schema_version`, `project_id`,
`display_name`, `template_version`, `allowed_principals`, `enabled_components`,
`data_root`, `memory_root` (no kit, os principais ficam na ACL do serviço, não no arquivo).

## Exemplo trabalhado
Laboratório A05 (p28–30): origem fictícia com `instrucoes.md`, `caso-demo.txt` e tabela de
tarefas; identificador `baseline-a05-001`; restauração em `restauracao-a05/`; comparação
de contagem de arquivos, hashes e consulta à tabela de tarefas (dados lógicos, não bytes).
Laboratório A06 (p33): tarefa fictícia "listar documentos necessários do caso Aurora",
processo encerrado e consultado em processo novo; negativa ao consultar o mesmo id sob
`reversa-lab`. Laboratório A07 (p37): `juridico-lab` com marcador AURORA-381 e
`reversa-lab` com REVERSA-624; "mostre o caso Aurora" com reversa-lab selecionado →
item indisponível naquele escopo, sem troca silenciosa de projeto; segunda criação de
`juridico-lab` informa que existe.

## Verificações de aceite derivadas
- A05: frase e tarefa fictícias recuperadas com identificadores originais; duas
  divergências provocadas detectadas sem "conserto silencioso" (p30).
- A06: operação mínima reproduzível; persistência após reinício; erros negativos corretos
  (projeto inexistente, configuração inválida, componente desconhecido, tarefa de outro
  projeto); inventário fiel (p34).
- A07: repetição preserva o existente; negativa antes da leitura de dados alheios; teste
  atravessa a mesma função de leitura do sistema (p38).

## Adaptação para a skill
Etapas A4–A6 do Fluxo A e B6 do Fluxo B; kit de referência implementa núcleo, modelo e
backup (`assets/fundacao-kit/`), com testes de conformidade equivalentes aos laboratórios.

## Conecta com
`../capacidades/11-manutencao-recuperacao.md`, `../seguranca-isolamento.md`,
`../fluxo-a-implantar.md` (A4–A7).
