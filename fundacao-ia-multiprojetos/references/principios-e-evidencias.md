# Princípios, evidências e estados honestos

Use este arquivo para decidir **o que se pode afirmar** sobre qualquer componente,
requisito ou projeto. Ele vale para os três fluxos.

## 1. Rótulos de origem (use nos relatórios)

| Rótulo | Significado |
|---|---|
| [Livro pX] | Conteúdo extraído do livro 2.0 (página do PDF) |
| [3.0] | Proposta de correção/acréscimo do documento 2.0→3.0 |
| [Verificado 2026-10-18] | Fato conferido em documentação oficial (ver `references/fontes-verificadas.md`) |
| [Decisão] | Escolha de projeto desta skill, com justificativa |
| [Didático] | Exemplo, nome, número ou caso inventado para ensinar; não descreve o ambiente do usuário |

## 2. Quatro níveis de evidência [Livro p8]

| Estado da conclusão | Evidência suficiente | Conclusão permitida |
|---|---|---|
| Documentado | Documento identificado e datado | Alguém registrou aquela informação |
| Código presente | Arquivo e versão examinados | Existe uma implementação candidata |
| Executado | Operação, saída e ambiente registrados | A operação ocorreu naquele ambiente |
| Validado | Resultado comparado com critério | O comportamento passou no cenário testado |

Os níveis qualificam **as suas conclusões**, não o fornecedor. Uma função bem
escrita pode nunca ser chamada; um programa pode rodar com outra configuração;
uma resposta certa pode não ter usado a fonte que se queria testar [Livro p8].
Exemplos de excesso a evitar: "`claude --version` respondeu, logo a assinatura e a
integração funcionam" (só prova o executável) [Livro p11]; "existe a pasta memory/,
logo a memória funciona" (prova estrutura) [Livro p35].

Separe sempre três camadas: dependência **declarada** (manifesto), instalação
**detectada** e comportamento **verificado** [Livro p9].

## 3. Estados de requisito [Livro p178, p187]

| Estado | Quando | O que permite avançar |
|---|---|---|
| `em_desenvolvimento` | planejado, em construção ou demonstração incompleta | implementação, integração e testes que cubram o requisito |
| `implementado_ativo` | passou nos testes e está habilitado na configuração avaliada | revalidar quando dependências relevantes mudarem |
| `implementado_inativo` | funcionamento **já demonstrado** e componente desabilitado de forma verificável | procedimento de ativação documentado e nova conferência das condições |
| `bloqueado` | falta acesso, recurso, autorização, capacidade ou decisão indispensável | resolução identificável do bloqueio + os testes que faltavam |

Regras:
- Não existe "concluído com ressalvas". Uma capacidade pode ficar bloqueada
  enquanto as outras avançam; o requisito **não some** da matriz porque a primeira
  forma de implementá-lo falhou [Livro p4].
- `implementado_inativo` exige registrar a demonstração anterior **e** a
  verificação atual de que o desligamento impede novos disparos e consumo [Livro p187].
- Código concluído com integração bloqueada: registre as duas coisas [Livro p178].
- Mock, plano ou configuração sem funcionamento real ficam identificados como tais;
  um mock de provedor não demonstra participação daquele provedor; um cache de
  respostas não satisfaz a prova de CAG [Livro p178].
- Atualização que invalida um teste anterior reabre a linha e indica a
  verificação a repetir [Livro p193].
- [3.0] Cada requisito pode ganhar `limiar` e `validade_evidencia` (ex.: 90 dias
  ou até mudar a versão da CLI/modelo). A skill registra esses campos na matriz.

Ferramenta: `python <skill>/scripts/matriz.py validar --matriz <arquivo>` aplica essas regras.
A saída separa `schema_ok` (estados, campos, identificadores, `simulado` explícito sim/nao) de
`evidencias` (para cada linha implementada: o caminho existe — relativo à raiz da fundação quando
a matriz está em `<raiz>/registry/`, ou ao `--base` —, não está vazio, cita a `versao_avaliada` e,
com a coluna opcional `sha256_evidencia`, confere o hash). "Matriz válida" não é capacidade
demonstrada: o mérito da evidência continua com a revisão humana [Decisão; auditoria externa da 1.3.4].

## 4. Registro de cada requisito [Livro p187]

Campos: finalidade, implementação, integração, verificação, caminho da evidência,
versão avaliada, estado, bloqueio, **impacto do bloqueio**, condição de resolução e
responsável pelo próximo passo, ligados a um `run_id` (requisito `bloqueado` sem
bloqueio, impacto ou condição é recusado pela validação). Uma evidência pode servir a vários requisitos se demonstrar cada
comportamento exigido. Atualize só as linhas afetadas; o log fica no artefato, a
matriz aponta para ele [Livro p193]. Na revisão final, examine primeiro os
bloqueios, depois os inativos, por último os ativos, perguntando: "Qual
comportamento foi observado, em qual versão, com que acesso e onde está a prova?"

## 5. Medição honesta

- "Não medido" ≠ 0. Contadores ausentes são `null`/`unknown`; nunca um zero por
  conveniência [Livro p111, p163].
- Separe **contagem exata**, **estimativa** (com método e incerteza) e
  **faturamento observado** [Livro p111].
- "Custo R$ 0" numa assinatura deve virar "sem cobrança adicional observada nesta
  modalidade", com consumo, duração e limites registrados [Livro p19].
- Tempo menor numa segunda execução não prova CAG nem cache; identifique o
  mecanismo reutilizado [Livro p106].
- Concordância entre agentes não é prova: três agentes podem repetir o mesmo erro;
  vale a sustentação na fonte [Livro p51].

## 6. Princípios de arquitetura (resumo operacional)

1. **Núcleo independente de domínio** [Livro p20, p32]: conhece tarefas,
   autorização, resultados, estado e evidências; adaptadores conhecem provedores e
   ferramentas; projetos conhecem regras de domínio; casos contêm dados particulares.
2. **Separação fundação/projeto/caso** [Livro p76]: comum (aprovado para
   reutilização), projeto (objetivos, decisões, documentos), caso (dados de uma
   necessidade específica). Autorização no projeto não dá acesso a todos os casos.
3. **Reutilização controlada** [Livro p36, p39, p133]: novos projetos herdam
   componentes e conhecimento **aprovado** por referência e começam com dados,
   memória e estado próprios. Copiar a pasta de outro projeto transporta históricos,
   caches e instruções indevidas.
4. **Implementação progressiva** [Livro p2–p3]: marcos pequenos, executáveis e
   verificáveis, com retomada documentada entre sessões; o núcleo pequeno é o primeiro
   marco, não a conclusão.
5. **Evolução por contratos e versões** [Livro p20, p33, p38, p167]: interfaces
   estáveis e pontos de troca; `schema_version` (estrutura do registro) ≠ `version`
   (componente); modelo de projeto é receita de criação, migração de instância é
   procedimento explícito; versionamento semântico ajuda mas não substitui testes.

## 7. Distinções que o relatório final deve manter

Documentado · código presente · executado · validado [Livro p4]. E, para entregas:
fundação implementada · projeto criado pelo modelo · projeto existente efetivamente
adaptado · integração real com dois provedores · capacidade inativa demonstrada.
"Um laboratório descrito no livro não equivale a uma implantação na sua máquina" [Livro p4].
