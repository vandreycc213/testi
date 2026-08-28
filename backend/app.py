"""
app.py
------
Servidor principal do sistema "Escolha sua cadeira".

Tecnologias escolhidas:
    - Flask: framework web minimalista, fácil de rodar em rede local sem
      configuração complexa, e integra muito bem com Flask-SocketIO.
    - Flask-SocketIO: fornece WebSockets (com fallback automático para
      long-polling caso o WebSocket puro não esteja disponível na rede),
      permitindo emitir eventos em tempo real para TODOS os clientes
      conectados assim que uma cadeira muda de estado. Isso evita usar
      `setInterval` fazendo polling HTTP constante, conforme pedido.
    - SQLite (via backend/database.py): persistência simples em arquivo,
      com transações atômicas para proteger contra condições de corrida.

O próprio Flask serve os arquivos estáticos do frontend (pasta
../frontend), então basta rodar este servidor e acessar
http://<ip-do-servidor>:5000 de qualquer computador da rede local.
"""

import os
import sys

from flask import Flask, jsonify, send_from_directory
from flask_socketio import SocketIO, emit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database
import models

# ---------------------------------------------------------------------
# Configuração do Flask
# ---------------------------------------------------------------------
FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend"
)

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
app.config["SECRET_KEY"] = "cadeiras-online-secret-key"  # uso apenas local/teste

# async_mode="threading" evita depender de eventlet/gevent (que às vezes
# dão problema de instalação no Windows) e funciona muito bem para o
# volume de conexões deste projeto (poucas dezenas de clientes).
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


# ---------------------------------------------------------------------
# Rotas HTTP (frontend estático)
# ---------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(FRONTEND_DIR, path)


@app.route("/api/status")
def api_status():
    """Endpoint HTTP simples, útil para depuração e para o frontend
    buscar o estado inicial mesmo antes do WebSocket conectar."""
    cadeiras = database.get_all_cadeiras()
    return jsonify(models.estado_completo(cadeiras))


# ---------------------------------------------------------------------
# Eventos WebSocket (Socket.IO)
# ---------------------------------------------------------------------
@socketio.on("connect")
def handle_connect():
    """Ao conectar, o cliente recebe imediatamente o estado atual e
    correto das 4 cadeiras — inclusive se estiver entrando depois que
    outras pessoas já ocuparam cadeiras."""
    cadeiras = database.get_all_cadeiras()
    emit("estado_inicial", models.estado_completo(cadeiras))
    print("[socket] Cliente conectado.")


@socketio.on("disconnect")
def handle_disconnect():
    print("[socket] Cliente desconectado.")


@socketio.on("solicitar_estado")
def handle_solicitar_estado():
    """Usado na reconexão: o cliente pede o estado atual para corrigir
    a interface caso tenha ficado desatualizada."""
    cadeiras = database.get_all_cadeiras()
    emit("estado_inicial", models.estado_completo(cadeiras))


@socketio.on("ocupar_cadeira")
def handle_ocupar_cadeira(data):
    """Evento disparado quando um usuário clica em uma cadeira disponível.

    Fluxo (conforme especificação):
        1. Receber solicitação para ocupar a cadeira.
        2. Verificar no banco se ela ainda está disponível.
        3. Se disponível: reservar dentro de transação segura e confirmar.
        4. Se já ocupada: recusar e avisar o solicitante.
        5. Transmitir o novo estado para todos os clientes conectados.
    """
    data = data or {}
    cadeira_id = models.validar_cadeira_id(data.get("cadeira_id"))
    user_id = data.get("user_id")
    user_name = models.validar_nome_usuario(data.get("user_name"))

    if cadeira_id is None:
        emit("erro", {"codigo": "cadeira_invalida", "mensagem": "ID de cadeira inválido."})
        return
    if not user_id or not isinstance(user_id, str):
        emit("erro", {"codigo": "usuario_invalido", "mensagem": "Identificação de usuário inválida."})
        return
    if not user_name:
        emit("erro", {"codigo": "nome_invalido", "mensagem": "Informe um nome válido."})
        return

    sucesso, motivo, cadeira = database.ocupar_cadeira(cadeira_id, user_id, user_name)

    if sucesso:
        # Notifica TODOS os clientes conectados (inclusive quem clicou)
        socketio.emit("cadeira_atualizada", models.cadeira_para_dict(cadeira))
        emit("sucesso", {
            "codigo": "cadeira_ocupada",
            "mensagem": f"Cadeira {cadeira_id} reservada com sucesso.",
            "cadeira_id": cadeira_id,
        })
    else:
        mensagens = {
            "cadeira_ja_ocupada": "Essa cadeira acabou de ser ocupada por outra pessoa.",
            "voce_ja_possui_cadeira": "Você já possui uma cadeira. Libere-a antes de escolher outra.",
            "cadeira_inexistente": "Cadeira inexistente.",
        }
        mensagem = mensagens.get(motivo, "Não foi possível reservar a cadeira.")
        emit("erro", {"codigo": motivo, "mensagem": mensagem, "cadeira_id": cadeira_id})

        # Reenvia o estado real dessa cadeira para o solicitante, para
        # garantir que a tela dele fique consistente mesmo em caso de erro.
        cadeira_atual = database.get_cadeira(cadeira_id)
        if cadeira_atual:
            emit("cadeira_atualizada", models.cadeira_para_dict(cadeira_atual))


@socketio.on("liberar_cadeira")
def handle_liberar_cadeira(data):
    """Libera uma cadeira, somente se pertencer ao usuário que solicitou."""
    data = data or {}
    cadeira_id = models.validar_cadeira_id(data.get("cadeira_id"))
    user_id = data.get("user_id")

    if cadeira_id is None:
        emit("erro", {"codigo": "cadeira_invalida", "mensagem": "ID de cadeira inválido."})
        return
    if not user_id or not isinstance(user_id, str):
        emit("erro", {"codigo": "usuario_invalido", "mensagem": "Identificação de usuário inválida."})
        return

    sucesso, motivo, cadeira = database.liberar_cadeira(cadeira_id, user_id)

    if sucesso:
        socketio.emit("cadeira_atualizada", models.cadeira_para_dict(cadeira))
        emit("sucesso", {
            "codigo": "cadeira_liberada",
            "mensagem": f"Cadeira {cadeira_id} liberada com sucesso.",
            "cadeira_id": cadeira_id,
        })
    else:
        mensagens = {
            "nao_e_o_dono": "Você não pode liberar uma cadeira que não é sua.",
            "cadeira_nao_ocupada": "Essa cadeira já está disponível.",
            "cadeira_inexistente": "Cadeira inexistente.",
        }
        mensagem = mensagens.get(motivo, "Não foi possível liberar a cadeira.")
        emit("erro", {"codigo": motivo, "mensagem": mensagem, "cadeira_id": cadeira_id})

        cadeira_atual = database.get_cadeira(cadeira_id)
        if cadeira_atual:
            emit("cadeira_atualizada", models.cadeira_para_dict(cadeira_atual))


# ---------------------------------------------------------------------
# Inicialização
# ---------------------------------------------------------------------
if __name__ == "__main__":
    database.init_db()
    print("=" * 60)
    print(" Sistema de Cadeiras Online")
    print(" Servidor iniciando em http://0.0.0.0:5000")
    print(" Acesse http://localhost:5000 neste computador")
    print(" Ou http://<IP-DESTE-COMPUTADOR>:5000 de outros computadores")
    print("=" * 60)
    # host="0.0.0.0" faz o servidor aceitar conexões de qualquer
    # computador da rede local, não só do próprio localhost.
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
