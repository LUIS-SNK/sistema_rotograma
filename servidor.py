"""Inicialização padrão: migração, verificação inicial e servidor com rotina interna."""
import os
from waitress import serve
from app import criar_aplicacao

if __name__ == "__main__":
    aplicacao = criar_aplicacao()
    host = os.getenv("HOST", "127.0.0.1")
    porta = int(os.getenv("PORT", "5000"))
    print(f"Sistema disponível em http://{host}:{porta}", flush=True)
    print("Verificação interna de validade ativa; mantenha esta janela aberta.", flush=True)
    serve(aplicacao, host=host, port=porta, threads=4)
