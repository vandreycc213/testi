"""
database.py
-----------
Camada de acesso ao banco de dados SQLite.

Por que SQLite?
    - Não exige instalação de servidor separado (arquivo único em disco).
    - Suporta transações ACID, o que é essencial para garantir que duas
      pessoas nunca ocupem a mesma cadeira ao mesmo tempo (requisito crítico
      do projeto).
    - Mais que suficiente para um cenário de poucas cadeiras/usuários
      simultâneos em rede local.

Estratégia de concorrência:
    O SQLite serializa escritas no nível do arquivo. Usamos, além disso,
    um `threading.Lock` (RLock) no lado da aplicação para que o par
    "verificar disponibilidade -> ocupar" aconteça como uma única operação
    lógica, sem brechas para condição de corrida entre requisições
    concorrentes vindas de computadores diferentes.

    A ocupação em si é feita com um único UPDATE condicional:

        UPDATE cadeiras
           SET status = 'ocupada', ...
         WHERE id = ? AND status = 'disponivel'

    Esse UPDATE só afeta 1 linha se, no exato momento da execução, a
    cadeira ainda estiver disponível. O SQLite garante que esse UPDATE é
    atômico (não existe outro processo conseguindo "fatiar" essa operação
    no meio). Se `cursor.rowcount == 0`, sabemos que outra pessoa venceu a
    corrida, e podemos recusar o pedido com segurança.
"""

import sqlite3
import threading
import os
from datetime import datetime

# Caminho do arquivo do banco (pasta /database na raiz do projeto)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database", "cadeiras.db")

TOTAL_CADEIRAS = 4

# Lock global para serializar as operações críticas de ocupar/liberar.
# Isso evita condições de corrida mesmo que o SQLite já ofereça proteção
# no nível do arquivo — é uma camada extra de segurança na aplicação.
db_lock = threading.RLock()


def get_connection():
    """Cria uma nova conexão SQLite para a thread atual.

    check_same_thread=False porque o Flask-SocketIO pode atender
    requisições em threads diferentes; como cada chamada abre e fecha
    sua própria conexão dentro do lock, isso é seguro.
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # Garante que chaves estrangeiras e modo de journal sejam adequados
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    """Cria a tabela de cadeiras (se não existir) e popula as 4 cadeiras
    automaticamente, sem necessidade de cadastro manual."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    with db_lock:
        conn = get_connection()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cadeiras (
                    id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'disponivel'
                        CHECK (status IN ('disponivel', 'ocupada')),
                    user_id TEXT,
                    user_name TEXT,
                    occupied_at TEXT
                )
                """
            )
            conn.commit()

            cur = conn.execute("SELECT COUNT(*) as total FROM cadeiras")
            total = cur.fetchone()["total"]

            if total == 0:
                for cadeira_id in range(1, TOTAL_CADEIRAS + 1):
                    conn.execute(
                        "INSERT INTO cadeiras (id, status) VALUES (?, 'disponivel')",
                        (cadeira_id,),
                    )
                conn.commit()
                print(f"[database] {TOTAL_CADEIRAS} cadeiras criadas automaticamente.")
            else:
                print(f"[database] Banco já inicializado com {total} cadeiras.")
        finally:
            conn.close()


def get_all_cadeiras():
    """Retorna o estado atual de todas as cadeiras (lista de dicts)."""
    with db_lock:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT id, status, user_id, user_name, occupied_at FROM cadeiras ORDER BY id"
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


def get_cadeira(cadeira_id):
    with db_lock:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT id, status, user_id, user_name, occupied_at FROM cadeiras WHERE id = ?",
                (cadeira_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def usuario_ja_possui_cadeira(user_id):
    """Verifica se o usuário já ocupa alguma cadeira. Retorna o dict da
    cadeira, ou None."""
    with db_lock:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT id, status, user_id, user_name, occupied_at FROM cadeiras "
                "WHERE user_id = ? AND status = 'ocupada'",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def ocupar_cadeira(cadeira_id, user_id, user_name):
    """Tenta ocupar uma cadeira de forma atômica.

    Retorna uma tupla (sucesso: bool, motivo: str, cadeira: dict|None)
    """
    with db_lock:
        conn = get_connection()
        try:
            # Regra de negócio: um usuário não pode ocupar duas cadeiras.
            existente = conn.execute(
                "SELECT id FROM cadeiras WHERE user_id = ? AND status = 'ocupada'",
                (user_id,),
            ).fetchone()
            if existente:
                return False, "voce_ja_possui_cadeira", None

            cadeira = conn.execute(
                "SELECT id FROM cadeiras WHERE id = ?", (cadeira_id,)
            ).fetchone()
            if not cadeira:
                return False, "cadeira_inexistente", None

            timestamp = datetime.now().isoformat(timespec="seconds")

            # Operação atômica: só atualiza se ainda estiver disponível.
            # Esse WHERE extra é a proteção real contra a condição de
            # corrida quando dois cliques chegam quase simultaneamente.
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """
                UPDATE cadeiras
                   SET status = 'ocupada',
                       user_id = ?,
                       user_name = ?,
                       occupied_at = ?
                 WHERE id = ? AND status = 'disponivel'
                """,
                (user_id, user_name, timestamp, cadeira_id),
            )
            conn.commit()

            if cursor.rowcount == 0:
                # Outra pessoa ocupou primeiro (ou ela já estava ocupada)
                return False, "cadeira_ja_ocupada", None

            atualizada = conn.execute(
                "SELECT id, status, user_id, user_name, occupied_at FROM cadeiras WHERE id = ?",
                (cadeira_id,),
            ).fetchone()
            return True, "ok", dict(atualizada)
        except sqlite3.OperationalError as exc:
            conn.rollback()
            return False, f"erro_banco:{exc}", None
        finally:
            conn.close()


def liberar_cadeira(cadeira_id, user_id):
    """Libera uma cadeira, somente se pertencer ao user_id informado.

    Retorna (sucesso: bool, motivo: str, cadeira: dict|None)
    """
    with db_lock:
        conn = get_connection()
        try:
            cadeira = conn.execute(
                "SELECT id, status, user_id FROM cadeiras WHERE id = ?",
                (cadeira_id,),
            ).fetchone()

            if not cadeira:
                return False, "cadeira_inexistente", None

            if cadeira["status"] != "ocupada":
                return False, "cadeira_nao_ocupada", None

            if cadeira["user_id"] != user_id:
                return False, "nao_e_o_dono", None

            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """
                UPDATE cadeiras
                   SET status = 'disponivel',
                       user_id = NULL,
                       user_name = NULL,
                       occupied_at = NULL
                 WHERE id = ? AND user_id = ?
                """,
                (cadeira_id, user_id),
            )
            conn.commit()

            if cursor.rowcount == 0:
                return False, "nao_e_o_dono", None

            atualizada = conn.execute(
                "SELECT id, status, user_id, user_name, occupied_at FROM cadeiras WHERE id = ?",
                (cadeira_id,),
            ).fetchone()
            return True, "ok", dict(atualizada)
        except sqlite3.OperationalError as exc:
            conn.rollback()
            return False, f"erro_banco:{exc}", None
        finally:
            conn.close()
