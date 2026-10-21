# Verificação dos exemplos do README

Data: **19/10/2026**, no horário de São Paulo. Escopo: revisão documental do README e seus recursos visuais, sobre a base `3078b230570aa55f6ed11483779fab3ee3d4b080`.

Este registro descreve um ensaio adicional em ambiente descartável. Os resultados históricos da entrega 1.4.5 permanecem na [matriz de hosts](../entrega/MATRIZ-HOSTS-E-VERIFICACOES.md). A verificação abaixo não representa uma instalação ou um teste no computador do leitor.

## Ambiente

- Linux x86_64.
- Python 3.12.14; SQLite 3.53.1.
- FTS5 com `unicode61 remove_diacritics 2`: disponível.
- SDK MCP: ausente no ambiente do ensaio funcional.
- Dados fictícios, identidade de laboratório e pastas temporárias.
- Sem chamadas reais a provedores ou alteração de perfis pessoais de hosts.

O instalador da skill calcula seu destino por `Path.home()`. Para conferir o script original sem alcançar um perfil real, o ensaio substituiu apenas essa resolução no processo filho, por meio de `unittest.mock.patch`, apontando-a para uma pasta descartável. Isso não adiciona uma opção `--perfil` ao instalador nem comprova descoberta da skill por qualquer host.

## Pacotes

| Pacote | Arquivos | SHA-256 | Divergências contra a árvore |
|---|---:|---|---:|
| `.skill` | 123 | `1134a4f1cea654778499091dfd52ffe3c622a13fb7e7af6d4981ed1b556a1ac9` | 0 |
| ZIP completo | 146 | `5a6013276820d709e61029a0d112064e01798bca6e6c2f64f42b7323cb06d3ad` | 0 |

Os hashes foram comparados com [`SHA256SUMS.txt`](../entrega/dist/SHA256SUMS.txt). O ZIP preparado para Claude.ai também foi conferido como idêntico ao `.skill`. Os pacotes não foram alterados nesta revisão.

## Exercícios dirigidos

Foram realizadas **28 chamadas de CLI**, todas com o código de saída esperado, incluindo as negativas. Também foi conferido o retorno manual de um arquivo do kit a partir da cópia anterior.

| Exercício | Resultado observado |
|---|---|
| Hash incorreto na instalação | Recusa com código 1, sem alteração |
| Instalar 1.4.4, verificar, atualizar para 1.4.5 e verificar | 123 arquivos na 1.4.5, nenhuma divergência |
| Retornar usando a pasta da versão anterior | Cópia resultante conferiu com o pacote 1.4.4 |
| Prévia de remoção e remoção confirmada | Prévia exigiu confirmação; remoção concluiu no perfil descartável |
| Simular e instalar o kit | Simulação sem escrita; instalação 1.4.1 com composição verificada |
| Inicializar e consultar sem identidade | Inicialização concluída; consulta negada com código 2 |
| Criar projeto e tarefa; consultar estado | Projeto visível à identidade; tarefa persistida em estado `pending` |
| Verificar eventos | Cadeia íntegra |
| Criar, verificar e restaurar backup em pasta nova | Cópia conferida, restauração com `released: true`, estado restaurado consultável |
| Atualizar kit com conflito local | Sem decisão: código 3 e nenhuma escrita; com `--atualizar`: código anterior guardado e configuração preservada |
| Verificar referências da skill | 258 conferidas, 0 ausentes |

O exercício de tarefa registra estado; não executa uma chamada a modelo. O retorno dos arquivos do kit não substitui uma restauração integral de banco e estado após uma migração.

## Suítes existentes

| Suíte | Coletados | Aprovados | Pulados | Falhas |
|---|---:|---:|---:|---:|
| Kit | 166 | 164 | 2 | 0 |
| Scripts da skill | 23 | 23 | 0 | 0 |
| Ferramentas de entrega | 40 | 36 | 4 | 0 |
| **Total** | **229** | **223** | **6** | **0** |

`unittest` inclui os testes pulados na contagem `Ran`. No kit, foram pulados o teste dependente do SDK MCP e um teste de caminho UNC exclusivo do Windows. Na entrega, foram pulados três testes de junções do Windows e um teste de exclusão de arquivo aberto específico desse sistema.

Comandos executados na raiz do repositório:

```bash
python -B fundacao-ia-multiprojetos/scripts/verificar_referencias.py
python -B -m unittest discover -s fundacao-ia-multiprojetos/scripts/tests -v
python -B -m unittest discover -s entrega/testes -v
```

Comando executado em `fundacao-ia-multiprojetos/assets/fundacao-kit/`:

```bash
python -B -m unittest discover -s tests -v
```

## Conferência da documentação e dos recursos visuais

O bloco POSIX final do laboratório foi extraído diretamente do README e executado com interrupção em caso de erro, em um destino novo. Todos os comandos terminaram com sucesso e a verificação dos eventos retornou `cadeia_integra: true`. O comando final de diagnóstico do FTS5 também foi executado com o tokenizador exigido pelo kit.

Os três blocos Mermaid foram extraídos do Markdown final, renderizados com Mermaid CLI 11.12.0 e inspecionados visualmente. O SVG de arquitetura foi validado como XML, renderizado e inspecionado; possui título e descrição acessíveis e não depende de fontes, scripts ou imagens externos. A capa conceitual foi gerada para o README e foi exportada em JPEG para reduzir o tamanho de download no repositório.

Os caminhos relativos e as âncoras do README foram conferidos, e `git diff --check` não apontou erros de espaçamento. A análise por revisores separados cobriu correspondência com o código, comandos, instruções oficiais de hosts e requisitos do pedido.

## Limites desta rodada

PowerShell e macOS não foram executados nesta rodada; os exemplos correspondentes foram conferidos contra a interface dos scripts. Claude Code, Codex e Claude.ai não foram instalados, autenticados ou acionados para ensaiar a skill. O servidor MCP real e o CAG com modelo real não foram testados.

Os cenários CEN-01–CEN-16 não foram repetidos. Eles possuem dependências próprias: CEN-11 utiliza PyYAML e verificadores externos, e CEN-15 depende do SDK MCP. Os números desses cenários no README estão explicitamente atribuídos ao registro histórico da entrega.

A revisão também comparou as instruções de instalação com as fontes oficiais dos hosts e conferiu o texto contra o código. As alterações ficaram restritas a documentação e recursos visuais; nenhum arquivo da skill, do kit ou dos pacotes distribuídos foi modificado.
