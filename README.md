# Cadeiras Online — Sistema de Seleção de Cadeiras em Tempo Real

Sistema web com **4 cadeiras**, onde múltiplas pessoas em computadores
diferentes (na mesma rede local) podem ocupar/liberar cadeiras e ver as
mudanças **em tempo real**, sem precisar atualizar a página.

- **Backend:** Python (Flask + Flask-SocketIO) + SQLite
- **Frontend:** HTML + CSS + JavaScript puro (sem frameworks)
- **Tempo real:** WebSocket (Socket.IO) — nada de `setInterval` fazendo polling
- **Proteção contra condição de corrida:** transação atômica no banco (`UPDATE ... WHERE status='disponivel'`)

```
cadeiras-online/
│
├── backend/
│   ├── app.py            # Servidor Flask + Socket.IO (rotas e eventos)
│   ├── database.py       # Acesso ao SQLite + lógica atômica de ocupar/liberar
│   ├── models.py         # Serialização e validação de dados
│   └── requirements.txt  # Dependências Python
│
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── script.js
│
├── database/
│   └── cadeiras.db       # Criado automaticamente na primeira execução
│
└── README.md
```

---

## 1. Instalar o Python (Windows)

1. Baixe o instalador em <https://www.python.org/downloads/> (versão 3.10 ou superior).
2. Execute o instalador e **marque a caixa "Add python.exe to PATH"** antes de clicar em Install.
3. Confirme a instalação abrindo o **Prompt de Comando** (`cmd`) e digitando:

   ```cmd
   python --version
   ```

   Deve aparecer algo como `Python 3.12.x`.

---

## 2. Criar o ambiente virtual

Abra o Prompt de Comando **dentro da pasta do projeto** (`cadeiras-online`) e rode:

```cmd
python -m venv venv
```

Ative o ambiente virtual:

```cmd
venv\Scripts\activate
```

Você verá `(venv)` aparecer no início da linha do terminal, indicando que o ambiente está ativo.

---

## 3. Instalar as dependências

Com o ambiente virtual ativado:

```cmd
cd backend
pip install -r requirements.txt
```

---

## 4. Iniciar o backend

Ainda dentro da pasta `backend`, com o ambiente virtual ativo:

```cmd
python app.py
```

Se tudo estiver certo, você verá algo como:

```
[database] 4 cadeiras criadas automaticamente.
============================================================
 Sistema de Cadeiras Online
 Servidor iniciando em http://0.0.0.0:5000
 Acesse http://localhost:5000 neste computador
 Ou http://<IP-DESTE-COMPUTADOR>:5000 de outros computadores
============================================================
```

Abra o navegador em **http://localhost:5000** para testar localmente.

---

## 5. Descobrir o IP do computador que está rodando o servidor

No mesmo computador onde o `app.py` está rodando, abra **outro** Prompt de Comando e digite:

```cmd
ipconfig
```

Procure por **"Endereço IPv4"** dentro da seção da sua rede (Wi-Fi ou Ethernet), algo como:

```
Adaptador de Rede sem Fio Wi-Fi:
   Endereço IPv4. . . . . . . . . . . . . . : 192.168.0.10
```

Esse é o IP que os outros computadores vão usar.

---

## 6. Acessar o sistema de outro computador

Em qualquer outro computador **conectado à mesma rede** (mesmo Wi-Fi/roteador), abra o navegador e acesse:

```
http://192.168.0.10:5000
```

(substituindo `192.168.0.10` pelo IP que você descobriu no passo anterior).

---

## 7. Testar dois usuários simultâneos

1. No **Computador A**, acesse o sistema e informe o nome, por exemplo **"Vandrey"**.
2. No **Computador B**, acesse o mesmo endereço e informe outro nome, por exemplo **"João"**.
3. No Computador A, clique na **Cadeira 2**.
4. Observe no Computador B: a Cadeira 2 muda automaticamente para **ocupada**, mostrando "Ocupada por Vandrey", **sem precisar atualizar a página**.
5. No Computador A, clique em **"Liberar minha cadeira"**.
6. Observe no Computador B: a Cadeira 2 volta a ficar **disponível** automaticamente.

---

## 8. Testar duas pessoas tentando ocupar a mesma cadeira ao mesmo tempo

1. Deixe o **Computador A** e o **Computador B** ambos olhando para a **Cadeira 3**, disponível.
2. Combine com a outra pessoa (ou use dois cliques bem próximos) para clicar na Cadeira 3 **quase ao mesmo tempo** nos dois computadores.
3. Resultado esperado:
   - Apenas **um** dos dois recebe a mensagem de sucesso e passa a ocupar a cadeira.
   - O outro recebe a mensagem **"Essa cadeira acabou de ser ocupada por outra pessoa."**
   - Em ambos os computadores, a Cadeira 3 aparece com o mesmo ocupante (não há inconsistência).

Isso acontece porque o backend usa uma atualização condicional no SQLite
(`UPDATE cadeiras SET ... WHERE id = ? AND status = 'disponivel'`) dentro de
uma transação, garantindo que só uma das duas requisições consiga
efetivamente mudar o status — a outra é recusada com segurança, mesmo que
as duas cheguem ao servidor quase no mesmo instante.

---

## 9. Solução de problemas de firewall / conexão (Windows)

Se outro computador não conseguir acessar `http://<IP>:5000`, o Firewall
do Windows pode estar bloqueando a porta 5000. Para liberar:

1. Abra **Configurações → Rede e Internet → Firewall do Windows Defender**.
2. Clique em **"Configurações avançadas"**.
3. Clique em **"Regras de Entrada" → "Nova Regra..."**.
4. Selecione **"Porta"** → **Avançar**.
5. Selecione **TCP** e informe a porta **5000** → **Avançar**.
6. Selecione **"Permitir a conexão"** → **Avançar**.
7. Marque todos os perfis (Domínio, Particular, Público) → **Avançar**.
8. Dê um nome, por exemplo **"Cadeiras Online 5000"** → **Concluir**.

Outros pontos a verificar:

- Certifique-se de que **ambos os computadores estão na mesma rede** (mesmo Wi-Fi ou mesma rede local).
- Redes públicas de alguns roteadores isolam os dispositivos entre si ("AP isolation/client isolation") — nesse caso, pode ser necessário usar uma rede privada/doméstica.
- Confirme que o servidor foi iniciado com `host="0.0.0.0"` (já configurado em `app.py`) — se estivesse em `127.0.0.1`, só o próprio computador conseguiria acessar.
- Se estiver usando uma VPN, ela pode interferir na visibilidade dos dispositivos na rede local.

---

## Detalhes técnicos relevantes

- **Tempo real:** o servidor usa Flask-SocketIO para emitir o evento
  `cadeira_atualizada` para **todos** os clientes conectados sempre que uma
  cadeira muda de estado — não há necessidade de os clientes ficarem
  perguntando ao servidor em intervalos fixos.
- **Consistência ao entrar no sistema:** ao conectar, cada cliente recebe
  imediatamente o evento `estado_inicial` com o status real das 4
  cadeiras, então mesmo quem entra depois de outras ocupações já vê tudo
  correto.
- **Reconexão:** o Socket.IO tenta reconectar automaticamente; ao
  reconectar, o frontend solicita o estado atual (`solicitar_estado`) para
  corrigir qualquer divergência.
- **Validações no backend:** o servidor nunca confia no frontend — ele
  revalida o ID da cadeira, o dono da cadeira ao liberar, se o usuário já
  possui outra cadeira, e se a cadeira realmente está disponível antes de
  confirmar qualquer ocupação.
