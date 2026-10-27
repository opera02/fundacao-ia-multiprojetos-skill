# Migração 5 e retorno da 1.7.9

Preparação técnica; nenhuma migração foi aplicada à fundação em uso nesta retomada.
O kit novo declara versão 1.7.9 e cinco migrações. Versão da skill, do kit e
`user_version` do banco são medidas distintas.

## Compatibilidade

| Recurso | Comportamento |
|---|---|
| Memórias anteriores | Conservam tipo, corpo, revisões e aprovações. Procedimento antigo não vira lição automaticamente. |
| Lição nova | Tipo `licao`, somente no projeto e sem caso; corpo estruturado com gatilho, lição, evidência e confiança. Propor não aprova. Consulta por gatilho entrega só revisão vigente aprovada e autorizada. |
| Banco anterior | A migração 5 reconstrói `memory_item`, conserva índices/triggers, confere chaves estrangeiras e cria `lesson_trigger` FTS5. Alteração de esquema e `user_version` confirmam na mesma transação; falha desfaz ambos. |
| Banco migrado com kit antigo | O kit anterior recusa versão futura. Repor somente o código antigo não é um retorno válido. |
| Rotas `/1` e `/2` | `/1` preserva seleção por rota; `/2` acrescenta alvos explícitos por tarefa. Validação local não liga rota nem promove R13. |
| Livro de cópias legado | Continua legível com seu limite de confiança documentado. Adoção do modo estrito é escolha explícita. |

Mudança intencional mais restritiva: com `max_usd`, a recusa de provedor sem
mecanismo preventivo por chamada também vale no formato `/1`. A compatibilidade
de leitura não conserva esse caminho de consumo sem limite preventivo.

## Atualização futura

1. Concluir testes, revisão, pacote e saneamento; guardar referência recuperável
   anterior, incluindo código, banco, configuração e registros de retiradas.
2. Aplicar C6 com uma única sessão operando o banco: backup ANTES verificado,
   restauração em pasta nova, ensaio de migração e comparação dos contratos.
3. Conferir que memórias/revisões/aprovações/ACL e vínculos existentes permanecem;
   conferir negativas de projeto/caso e rollback da migração em erro.
4. Só promover após os critérios da versão. A conexão do kit novo aplica migrações;
   não abrir o banco vivo com esse código durante o preparo.
5. Guardar backup DEPOIS e os hashes. Novos registros posteriores à promoção
   precisam ser reconciliados antes de qualquer retorno à cópia anterior.

## Retorno

Se o esquema ainda não mudou, vale o `desfazer` de C6 com registro autêntico e
verificações do atualizador. Depois da migração 5, restaurar a cópia ANTES em
**pasta nova**, com o kit correspondente e reaplicação do registro de retiradas,
seguindo C9. Conferir perdas e efeitos posteriores com o titular antes de trocar
o ambiente em uso. Nunca reduzir `PRAGMA user_version` nem substituir só o código.

## Livro assinado: adoção separada

`copia-assinatura preparar` prepara o documento a partir da entrada original do
livro; o titular confere o hash da cópia por fonte independente e assina o arquivo
com a chave existente, no namespace `fundacao-copia`. O executor só registra a
assinatura validada contra a âncora protegida. Uma assinatura nova não torna
verdadeira uma entrada antiga que não foi conferida.

Depois do registro, invocar `backup verificar --exigir-livro-assinado` ou
`backup restaurar --exigir-livro-assinado` exige assinatura válida do manifesto;
ausência ou alteração recusa. Registrar a assinatura não ativa esse modo automaticamente.
Hash externo guardado
pelo titular continua sendo caminho de verificação independente. Preparar não
assina; não houve solicitação ou uso da chave do titular nesta retomada.
