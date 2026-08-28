"""
models.py
---------
Funções de serialização e validação relacionadas à entidade "Cadeira".

Mantido separado de database.py para deixar claro o que é acesso a dados
(database.py) e o que é regra de formatação/validação (models.py).
"""

from database import TOTAL_CADEIRAS


def cadeira_para_dict(cadeira_row):
    """Converte uma linha de cadeira (dict vindo do SQLite) no formato
    que será enviado ao frontend via JSON/WebSocket."""
    return {
        "id": cadeira_row["id"],
        "status": cadeira_row["status"],
        "user_id": cadeira_row.get("user_id"),
        "user_name": cadeira_row.get("user_name"),
        "occupied_at": cadeira_row.get("occupied_at"),
    }


def estado_completo(cadeiras):
    """Empacota a lista de cadeiras em um payload padronizado."""
    return {
        "total": TOTAL_CADEIRAS,
        "cadeiras": [cadeira_para_dict(c) for c in cadeiras],
    }


def validar_cadeira_id(cadeira_id):
    """Valida se o ID da cadeira é um inteiro dentro do intervalo válido
    (1 a TOTAL_CADEIRAS). Nunca confiamos no valor vindo do frontend sem
    checar aqui primeiro."""
    try:
        cadeira_id = int(cadeira_id)
    except (TypeError, ValueError):
        return None
    if 1 <= cadeira_id <= TOTAL_CADEIRAS:
        return cadeira_id
    return None


def validar_nome_usuario(nome):
    """Sanitiza e valida o nome informado pelo usuário."""
    if not isinstance(nome, str):
        return None
    nome = nome.strip()
    if not nome:
        return None
    # Limita tamanho para evitar abuso
    return nome[:40]
