const API = "";
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const art = {
  espresso: { icon: "☕", label: "SHORT & BOLD", background: "#d9c6aa" },
  americano: { icon: "◉", label: "SMOOTH & SIMPLE", background: "#d9d0bd" },
  cappuccino: { icon: "☕", label: "FOAM & FINESSE", background: "#e6cdb7" },
  latte: { icon: "🥛", label: "SOFT & SILKY", background: "#d7d9c8" },
  flat_white: { icon: "☕", label: "VELVET MICROFOAM", background: "#d8c9ae" },
  mocha: { icon: "🍫", label: "A LITTLE INDULGENCE", background: "#ddc4b0" },
  iced_latte: { icon: "🧊", label: "COOL & CREAMY", background: "#cad8d1" },
  cold_brew: { icon: "🧋", label: "SLOW STEEPED", background: "#c9c4b4" },
};
const sizeFactor = { small: 0.8, medium: 1, large: 1.25 };
const statusOrder = ["received", "checking_inventory", "ingredients_reserved", "preparing", "ready"];
const statusLabels = {
  received: "Order received",
  checking_inventory: "Checking ingredients",
  ingredients_reserved: "Ingredients ready",
  preparing: "Making your coffee",
  ready: "Ready for pickup",
  failed: "Order needs attention",
};
const statusIcons = { received: "✓", checking_inventory: "◉", ingredients_reserved: "▤", preparing: "♨", ready: "✓", failed: "!" };
let menu = [];
let selectedDrink = null;
let currentOrderId = null;
let pollTimer = null;
let activeCategory = "All";

const $ = (id) => document.getElementById(id);

async function loadMenu() {
  try {
    const configResponse = await fetch(`${API}/config`);
    if (configResponse.ok) {
      const config = await configResponse.json();
      if (!config.demo_scenarios_enabled) document.querySelector(".demo-controls").hidden = true;
    }
    const response = await fetch(`${API}/menu`);
    if (!response.ok) throw new Error("Could not load menu");
    const data = await response.json();
    menu = data.items;
    renderMenu();
    updateOrderSummary();
  } catch (error) {
    $("menu-grid").innerHTML = '<p class="menu-loading">We could not load the menu. Refresh the page to try again.</p>';
    showToast(error.message);
  }
}

function renderMenu() {
  const items = menu.filter((item) => activeCategory === "All" || item.category === activeCategory);
  $("menu-count").textContent = `${items.length} ${items.length === 1 ? "coffee" : "coffees"}`;
  $("menu-grid").innerHTML = items.map((item) => {
    const image = art[item.id] || art.cappuccino;
    const selected = selectedDrink?.id === item.id;
    return `<article class="menu-item ${selected ? "selected" : ""}" data-drink="${item.id}" tabindex="0" role="button" aria-pressed="${selected}" aria-label="Choose ${item.name}">
      <div class="menu-art" style="background:${image.background}"><span class="drink-emoji" aria-hidden="true">${image.icon}</span><span class="art-label">${image.label}</span></div>
      <div class="menu-content"><div class="menu-topline"><h3>${item.name}</h3><span class="menu-price">${money.format(item.price)}</span></div>
      <p>${item.description}</p><div class="menu-card-footer"><span class="menu-category">${item.category}</span><span class="choose-label">${selected ? "✓ Selected" : "Choose +"}</span></div></div>
    </article>`;
  }).join("");
  document.querySelectorAll(".menu-item").forEach((card) => {
    const choose = () => selectDrink(card.dataset.drink);
    card.addEventListener("click", choose);
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(); }
    });
  });
}

function selectDrink(id) {
  selectedDrink = menu.find((item) => item.id === id) || null;
  renderMenu();
  updateOrderSummary();
  document.querySelector(".order-card").scrollIntoView({ behavior: "smooth", block: "center" });
}

function updateOrderSummary() {
  const drink = selectedDrink;
  $("selected-name").textContent = drink ? drink.name : "Choose a coffee";
  $("selected-description").textContent = drink ? drink.description : "Select one from the menu above.";
  const image = drink ? (art[drink.id] || art.cappuccino).icon : "☕";
  $("selected-drink").querySelector(".selected-icon").textContent = image;
  $("place-order").disabled = !drink;
  const size = $("size-select").value;
  $("order-price").textContent = drink ? money.format(drink.price * sizeFactor[size]) : "—";
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 3000);
}

async function placeOrder() {
  if (!selectedDrink) return;
  const button = $("place-order");
  button.disabled = true;
  button.innerHTML = "Sending to the counter…";
  try {
    const response = await fetch(`${API}/orders`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        drink: selectedDrink.id,
        size: $("size-select").value,
        scenario: $("scenario-select").value,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "We could not place that order.");
    currentOrderId = data.order_id;
    localStorage.setItem("daily-grind-last-order", String(currentOrderId));
    $("order-lookup").value = currentOrderId;
    showTracking(data.order_id);
    showToast(`Order #${data.order_id} is in!`);
    $("tracking").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = !selectedDrink;
    button.innerHTML = 'Place my order <span>→</span>';
  }
}

function renderHistory(order) {
  const history = new Map(order.history.map((item) => [item.status, item]));
  const terminalFailed = order.status === "failed";
  const activeIndex = terminalFailed ? -1 : statusOrder.indexOf(order.status);
  const percent = terminalFailed ? 100 : Math.max(5, activeIndex / (statusOrder.length - 1) * 100);
  $("progress-fill").style.width = `${percent}%`;
  $("progress-fill").style.background = terminalFailed ? "#a64d3e" : "var(--olive)";
  const steps = terminalFailed ? [...statusOrder.slice(0, Math.max(1, history.size)), "failed"] : statusOrder;
  $("journey-steps").innerHTML = steps.map((status) => {
    const item = history.get(status);
    const index = statusOrder.indexOf(status);
    const done = item && status !== order.status;
    const current = status === order.status;
    const date = item ? new Date(item.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" }) : "Up next";
    return `<div class="journey-step ${done ? "done" : ""} ${current ? "current" : ""}"><span class="journey-icon">${statusIcons[status]}</span><span><strong>${statusLabels[status]}</strong><small>${date}</small></span></div>`;
  }).join("");
}

async function showTracking(orderId) {
  if (pollTimer) window.clearInterval(pollTimer);
  pollTimer = null;
  currentOrderId = Number(orderId);
  $("tracking-empty").hidden = true;
  $("tracking-live").hidden = false;
  $("tracking-order-number").textContent = `#${currentOrderId}`;
  localStorage.setItem("daily-grind-last-order", String(currentOrderId));
  const shouldContinue = await refreshTracking();
  if (shouldContinue) pollTimer = window.setInterval(refreshTracking, 900);
}

async function refreshTracking() {
  if (!currentOrderId) return;
  try {
    const response = await fetch(`${API}/orders/${currentOrderId}`, { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Order not found");
    const drink = menu.find((item) => item.id === data.drink);
    const title = data.status === "ready" ? "Your coffee is ready." : data.status === "failed" ? "Let's get this sorted." : "Your coffee is on its way.";
    $("tracking-title").textContent = title;
    const latest = data.history[data.history.length - 1];
    $("tracking-subtitle").textContent = latest?.message || "We're getting everything ready.";
    $("tracking-status").textContent = data.status.replaceAll("_", " ").toUpperCase();
    $("tracking-status").classList.toggle("status-failed", data.status === "failed");
    $("tracking-drink").textContent = drink?.name || data.drink;
    $("tracking-size").textContent = `${data.size.charAt(0).toUpperCase()}${data.size.slice(1)} cup`;
    $("tracking-total").textContent = money.format(data.price);
    renderHistory(data);
    if (data.status === "ready" || data.status === "failed") {
      window.clearInterval(pollTimer);
      pollTimer = null;
      return false;
    }
    return true;
  } catch (error) {
    window.clearInterval(pollTimer);
    pollTimer = null;
    $("tracking-title").textContent = "We couldn't find that order.";
    $("tracking-subtitle").textContent = error.message;
    $("tracking-status").textContent = "NOT FOUND";
    $("tracking-status").classList.add("status-failed");
    showToast(error.message);
    return false;
  }
}

$("size-select").addEventListener("change", updateOrderSummary);
$("place-order").addEventListener("click", placeOrder);
document.querySelectorAll(".category-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    activeCategory = tab.dataset.category;
    document.querySelectorAll(".category-tab").forEach((item) => item.classList.toggle("active", item === tab));
    renderMenu();
  });
});
$("lookup-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const id = Number($("order-lookup").value);
  if (Number.isInteger(id) && id > 0) showTracking(id);
});
$("copy-order").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(String(currentOrderId)); showToast("Order number copied."); }
  catch { showToast(`Your order number is #${currentOrderId}.`); }
});
$("footer-year").textContent = new Date().getFullYear();

loadMenu().then(() => {
  const last = localStorage.getItem("daily-grind-last-order");
  if (last) {
    $("last-order").hidden = false;
    $("last-order").innerHTML = `Last order: <button type="button" id="resume-last-order">#${last} · Track it</button>`;
    $("resume-last-order").addEventListener("click", () => {
      $("order-lookup").value = last;
      showTracking(last);
      $("tracking").scrollIntoView({ behavior: "smooth" });
    });
  }
});
