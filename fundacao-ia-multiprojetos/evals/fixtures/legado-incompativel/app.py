"""Aplicativo legado FICTÍCIO com sinais de incompatibilidade (para avaliação).

- Lê documentos de TODOS os clientes numa pasta compartilhada fora do projeto.
- Guarda credencial no código.
- Depende de um serviço da intranet que não existe neste ambiente.
"""
import json
import urllib.request

PASTA_CLIENTES = "C:/escritorio/clientes/todos/"
MODELOS = "../../modelos-compartilhados/"
CHAVE_SERVICO = "chave-embutida-ficticia-123456"


def gerar(caso_id):
    dados = open(PASTA_CLIENTES + caso_id + ".json", encoding="utf-8").read()
    req = urllib.request.Request("http://intranet.local/gerar", data=dados.encode(),
                                 headers={"Authorization": CHAVE_SERVICO})
    return json.loads(urllib.request.urlopen(req).read())


if __name__ == "__main__":
    import sys
    print(gerar(sys.argv[1]))
