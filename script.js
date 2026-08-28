/**
 * script.js
 * ---------
 * Lógica do cliente: conecta via WebSocket (Socket.IO) ao backend Python,
 * renderiza as 4 cadeiras e reage em tempo real a qualquer mudança de
 * estado vinda do servidor (ocupação, liberação, reconexão etc.).
 *
 * Identificação do usuário:
 *   Ao entrar, é gerado um ID único por sessão (armazenado em
 *   sessionStorage, então sobrevive a um refresh de página mas é único
 *   por aba/navegador) e é solicitado um nome para exibição.
 */

const TOTAL_CADEIRAS = 4;

// ---------------------------------------------------------------------
// Identificação do usuário/sessão
// ---------------------------------------------------------------------
function gerarUserId() {
  return "user-" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

let userId = sessionStorage.getItem("cadeiras_user_id");
if (!userId) {
  userId = gerarUserId();
  sessionStorage.setItem("cadeiras_user_id", userId);
}

let userName = sessionStorage.getItem("cadeiras_user_name") || null;

// ---------------------------------------------------------------------
// Estado local (espelha o estado do servidor)
// ---------------------------------------------------------------------
let cadeirasState = {}; // { [id]: {id, status, user_id, user_name, occupied_at} }
let cadeiraCarregando = null; // id da cadeira aguardando resposta do servidor

// ---------------------------------------------------------------------
// Referências DOM
// ---------------------------------------------------------------------
const nameModal = document.getElementById("name-modal");
const nameInput = document.getElementById("name-input");
const nameConfirmBtn = document.getElementById("name-confirm-btn");
const nameError = document.getElementById("name-error");
const currentUserNameEl = document.getElementById("current-user-name");
const chairsGrid = document.getElementById("chairs-grid");
const myChairPanel = document.getElementById("my-chair-panel");
const myChairLabel = document.getElementById("my-chair-label");
const releaseBtn = document.getElementById("release-btn");
const connectionBanner = document.getElementById("connection-banner");
const toastContainer = document.getElementById("toast-container");

// ---------------------------------------------------------------------
// Toasts / notificações
// ---------------------------------------------------------------------
function showToast(mensagem, tipo = "info", duracaoMs = 3500) {
  const toast = document.createElement("div");
  toast.className = `toast ${tipo}`;
  toast.textContent = mensagem;
  toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, duracaoMs);
}

// ---------------------------------------------------------------------
// Banner de status de conexão
// ---------------------------------------------------------------------
function setConnectionBanner(state) {
  connectionBanner.classList.remove("hidden", "online", "offline", "reconnecting");
  if (state === "online") {
    connectionBanner.textContent = "Conectado ao servidor.";
    connectionBanner.classList.add("online");
    setTimeout(() => connectionBanner.classList.add("hidden"), 2000);
  } else if (state === "offline") {
    connectionBanner.textContent = "Conexão com o servidor perdida.";
    connectionBanner.classList.add("offline");
  } else if (state === "reconnecting") {
    connectionBanner.textContent = "Tentando reconectar...";
    connectionBanner.classList.add("reconnecting");
  }
}

// ---------------------------------------------------------------------
// Renderização das cadeiras
// ---------------------------------------------------------------------
function criarEsqueletoCadeiras() {
  chairsGrid.innerHTML = "";
  for (let i = 1; i <= TOTAL_CADEIRAS; i++) {
    const card = document.createElement("div");
    card.className = "chair-card carregando";
    card.dataset.id = i;
    card.innerHTML = `
      <span class="chair-icon">🪑</span>
      <div class="chair-title">Cadeira ${i}</div>
      <span class="chair-status-badge carregando">Carregando...</span>
      <div class="chair-occupant">&nbsp;</div>
    `;
    chairsGrid.appendChild(card);
  }
}

function renderCadeira(cadeira, destacar = false) {
  const card = chairsGrid.querySelector(`[data-id="${cadeira.id}"]`);
  if (!card) return;

  const ehMinha = cadeira.status === "ocupada" && cadeira.user_id === userId;
  const estaCarregando = cadeiraCarregando === cadeira.id;

  card.classList.remove("disponivel", "ocupada", "carregando", "minha", "selecionando");
  card.classList.toggle("disponivel", cadeira.status === "disponivel" && !estaCarregando);
  card.classList.toggle("ocupada", cadeira.status === "ocupada" && !estaCarregando);
  card.classList.toggle("carregando", estaCarregando);
  card.classList.toggle("minha", ehMinha);

  const icon = card.querySelector(".chair-icon");
  const badge = card.querySelector(".chair-status-badge");
  const occupantEl = card.querySelector(".chair-occupant");

  if (estaCarregando) {
    icon.textContent = "🪑";
    badge.textContent = "Atualizando...";
    badge.className = "chair-status-badge carregando";
    occupantEl.textContent = "\u00A0";
  } else if (cadeira.status === "disponivel") {
    icon.textContent = "🪑";
    badge.textContent = "Disponível";
    badge.className = "chair-status-badge disponivel";
    occupantEl.textContent = "\u00A0";
  } else {
    icon.textContent = "🔴";
    badge.textContent = "Ocupada";
    badge.className = "chair-status-badge ocupada";
    occupantEl.textContent = ehMinha
      ? "Ocupada por você"
      : `Ocupada por ${cadeira.user_name || "alguém"}`;
  }

  if (destacar) {
    card.classList.add("acabou-de-mudar");
    setTimeout(() => card.classList.remove("acabou-de-mudar"), 550);
  }

  atualizarPainelMinhaCadeira();
}

function renderTodasCadeiras() {
  Object.values(cadeirasState)
    .sort((a, b) => a.id - b.id)
    .forEach((c) => renderCadeira(c));
}

function atualizarPainelMinhaCadeira() {
  const minha = Object.values(cadeirasState).find(
    (c) => c.status === "ocupada" && c.user_id === userId
  );
  if (minha) {
    myChairPanel.classList.remove("hidden");
    myChairLabel.textContent = `Cadeira ${minha.id}`;
    releaseBtn.dataset.cadeiraId = minha.id;
  } else {
    myChairPanel.classList.add("hidden");
  }
}

// ---------------------------------------------------------------------
// Modal de nome de usuário
// ---------------------------------------------------------------------
function abrirModalNome() {
  nameModal.classList.remove("hidden");
  nameInput.value = userName || "";
  setTimeout(() => nameInput.focus(), 50);
}

function fecharModalNome() {
  nameModal.classList.add("hidden");
}

function confirmarNome() {
  const valor = nameInput.value.trim();
  if (!valor) {
    nameError.classList.remove("hidden");
    return;
  }
  nameError.classList.add("hidden");
  userName = valor.slice(0, 40);
  sessionStorage.setItem("cadeiras_user_name", userName);
  currentUserNameEl.textContent = userName;
  fecharModalNome();
}

nameConfirmBtn.addEventListener("click", confirmarNome);
nameInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") confirmarNome();
});

if (userName) {
  currentUserNameEl.textContent = userName;
} else {
  abrirModalNome();
}

// ---------------------------------------------------------------------
// Conexão Socket.IO
// ---------------------------------------------------------------------
const socket = io({
  reconnection: true,
  reconnectionAttempts: Infinity,
  reconnectionDelay: 1000,
  reconnectionDelayMax: 5000,
});

socket.on("connect", () => {
  setConnectionBanner("online");
});

socket.on("disconnect", () => {
  setConnectionBanner("offline");
});

socket.on("reconnect_attempt", () => {
  setConnectionBanner("reconnecting");
});

socket.on("reconnect", () => {
  // Ao reconectar, busca o estado atual para corrigir a interface.
  socket.emit("solicitar_estado");
  setConnectionBanner("online");
});

socket.on("estado_inicial", (payload) => {
  criarEsqueletoCadeiras();
  cadeirasState = {};
  payload.cadeiras.forEach((c) => {
    cadeirasState[c.id] = c;
  });
  renderTodasCadeiras();
});

socket.on("cadeira_atualizada", (cadeira) => {
  cadeirasState[cadeira.id] = cadeira;
  if (cadeiraCarregando === cadeira.id) {
    cadeiraCarregando = null;
  }
  renderCadeira(cadeira, true);
});

socket.on("sucesso", (info) => {
  showToast(info.mensagem, "success");
});

socket.on("erro", (info) => {
  if (info.cadeira_id && cadeiraCarregando === info.cadeira_id) {
    cadeiraCarregando = null;
    const cadeiraAtual = cadeirasState[info.cadeira_id];
    if (cadeiraAtual) renderCadeira(cadeiraAtual);
  }
  showToast(info.mensagem, "error");
});

// ---------------------------------------------------------------------
// Interações do usuário
// ---------------------------------------------------------------------
chairsGrid.addEventListener("click", (e) => {
  const card = e.target.closest(".chair-card");
  if (!card) return;

  const id = parseInt(card.dataset.id, 10);
  const cadeira = cadeirasState[id];
  if (!cadeira) return;

  if (!userName) {
    abrirModalNome();
    return;
  }

  if (cadeira.status === "ocupada") {
    if (cadeira.user_id === userId) {
      showToast("Esta cadeira já é sua. Use o botão para liberá-la.", "info");
    } else {
      showToast("Cadeira já ocupada.", "error");
    }
    return;
  }

  if (cadeiraCarregando !== null) {
    return; // já existe uma solicitação em andamento
  }

  const jaTenhoCadeira = Object.values(cadeirasState).some(
    (c) => c.status === "ocupada" && c.user_id === userId
  );
  if (jaTenhoCadeira) {
    showToast("Você já possui uma cadeira.", "error");
    return;
  }

  if (!socket.connected) {
    showToast("Conexão com o servidor perdida.", "error");
    return;
  }

  cadeiraCarregando = id;
  renderCadeira(cadeira);

  socket.emit("ocupar_cadeira", {
    cadeira_id: id,
    user_id: userId,
    user_name: userName,
  });
});

releaseBtn.addEventListener("click", () => {
  const id = parseInt(releaseBtn.dataset.cadeiraId, 10);
  if (!id) return;

  if (!socket.connected) {
    showToast("Conexão com o servidor perdida.", "error");
    return;
  }

  releaseBtn.disabled = true;
  socket.emit("liberar_cadeira", { cadeira_id: id, user_id: userId });
  setTimeout(() => {
    releaseBtn.disabled = false;
  }, 800);
});

// ---------------------------------------------------------------------
// Inicialização visual (enquanto aguarda o primeiro estado do servidor)
// ---------------------------------------------------------------------
criarEsqueletoCadeiras();
