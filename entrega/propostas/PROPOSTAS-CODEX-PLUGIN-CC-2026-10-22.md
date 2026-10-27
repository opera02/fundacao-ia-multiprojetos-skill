# codex-plugin-cc — análise estática para a 1.7.9

Revisão `db52e28f4d9ded852ab3942cea316258ae4ef346`, consultada em 22/10/2026.
Foram conferidos os hashes das seis fontes fixadas no manifesto de pesquisa do
projeto. Nenhum script externo, plugin ou servidor foi executado ou instalado.
Dependências apontadas pelas fontes e não guardadas não foram auditadas.

## Evidências e limites

| Fonte | Leitura do código | Implicação |
|---|---|---|
| `plugins/codex/hooks/hooks.json` | Registra SessionStart, SessionEnd e Stop; o Stop chama o portão opcional de revisão. | Instalar altera o ciclo da sessão. Continua sendo decisão do titular no perfil. |
| `plugins/codex/scripts/lib/codex.mjs`, linhas 63–81 e 1002–1050 | Cria/retoma threads e inicia revisão pelo app server; a revisão pede sandbox `read-only` e política `never`. Captura resultado, arquivos e eventos. | Somente leitura restringe escrita; não prova que o processo deixa de enxergar arquivos fora da entrada da avaliação. |
| `plugins/codex/scripts/lib/app-server.mjs` | Implementa cliente de protocolo e clientes de processo/broker. | Não é só encaminhar uma mensagem: há processo, estado, ambiente e credencial a conferir. |
| `plugins/codex/scripts/lib/workspace.mjs` | Chama `ensureGitRepository(cwd)`; em erro, devolve `cwd`. O helper `git.mjs` não está entre as seis fontes auditadas. | Essa chamada não prova o isolamento da área. P7 deve receber pacote próprio e ambiente independente. |
| `plugins/codex/scripts/stop-review-gate-hook.mjs`, linhas 16–19 e 142–170 | Portão opcional com prazo de 15 minutos; falha, resposta inválida ou achado impede a conclusão normal do hook. | Revisão automática repetida pode consumir cota e criar um ciclo. A fundação precisa de teto separado e reconciliação antes de repetir. |
| `plugins/codex/schemas/review-output.schema.json` | Define formato estruturado para revisão. | Validar forma não autentica a autoria nem demonstra correção do veredito. |

Fontes: [hooks](https://github.com/openai/codex-plugin-cc/blob/db52e28f4d9ded852ab3942cea316258ae4ef346/plugins/codex/hooks/hooks.json),
[cliente Codex](https://github.com/openai/codex-plugin-cc/blob/db52e28f4d9ded852ab3942cea316258ae4ef346/plugins/codex/scripts/lib/codex.mjs),
[app server](https://github.com/openai/codex-plugin-cc/blob/db52e28f4d9ded852ab3942cea316258ae4ef346/plugins/codex/scripts/lib/app-server.mjs),
[workspace](https://github.com/openai/codex-plugin-cc/blob/db52e28f4d9ded852ab3942cea316258ae4ef346/plugins/codex/scripts/lib/workspace.mjs),
[portão Stop](https://github.com/openai/codex-plugin-cc/blob/db52e28f4d9ded852ab3942cea316258ae4ef346/plugins/codex/scripts/stop-review-gate-hook.mjs),
[schema](https://github.com/openai/codex-plugin-cc/blob/db52e28f4d9ded852ab3942cea316258ae4ef346/plugins/codex/schemas/review-output.schema.json).

O Stop usa um protocolo textual de permitir/bloquear, distinto do schema geral
de revisão. Se o portão estiver desligado ou faltar setup, o hook apenas avisa;
isso não é aprovação de uma entrega. Ao criar o filho ele herda o ambiente do
processo. Uma adoção futura exige conferir essa fronteira e as dependências não
lidas, além de custo, conta e visibilidade de arquivos.

## Desenho adotado para o preparo

1. P7 prepara e compara arquivos localmente. A futura avaliação recebe só rubrica
   sem notas e respostas com identificadores neutros; mapa, rastros e livro ficam fora.
2. O juiz não recebe o repositório inteiro. A conta/contêiner/VM deve enxergar só a
   entrada autorizada; pasta vazia e sandbox de escrita não demonstram esse isolamento.
3. Resultado e concordância são recibos ligados a hashes. A comparação local não
   comprova execução pelo Codex, nem aprovação humana, nem integração real.
4. A chamada futura tem livro e teto próprios, com modelo/esforço exatos, tentativas
   interrompidas contadas e custo ausente indicado. O livro P1 atual mede o rastro
   Claude; sua existência não fornece teto financeiro preventivo para Codex.
5. Instalação do plugin e revisão automática no Stop ficam adiadas. O preparo não
   precisa delas; nenhuma configuração ativa do host foi alterada.

P7 mede concordância entre avaliadores sobre a mesma rubrica, não verdade por
maioria. Divergências em segurança ou fatos críticos exigem revisão da evidência.
O texto das respostas ainda pode revelar autoria; anonimização não garante cegamento.
