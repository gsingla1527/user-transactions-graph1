const API_BASE = "https://user-transactions-graph-1.onrender.com/";

let cy = cytoscape({
  container: document.getElementById("cy"),
  style: [
    {
      selector: "node[kind = 'user']",
      style: {
        "background-color": "#38bdf8",
        "label": "data(label)",
        "font-size": "8px",
        "text-valign": "center",
        "text-halign": "center",
        "color": "#0f172a"
      }
    },
    {
      selector: "node[kind = 'transaction']",
      style: {
        "background-color": "#a855f7",
        "label": "data(label)",
        "font-size": "7px",
        "text-valign": "center",
        "text-halign": "center",
        "shape": "round-rectangle",
        "color": "#f9fafb"
      }
    },
    {
      selector: "edge[type *= 'SENT'], edge[type *= 'RECEIVED']",
      style: {
        "line-color": "#22c55e",
        "target-arrow-color": "#22c55e",
        "target-arrow-shape": "triangle",
        "width": 1.5,
        "curve-style": "bezier"
      }
    },
    {
      selector: "edge[type ^= 'SHARES']",
      style: {
        "line-style": "dashed",
        "line-color": "#eab308",
        "width": 1.2
      }
    },
    {
      selector: "edge[type ^= 'RELATED']",
      style: {
        "line-color": "#fb7185",
        "target-arrow-color": "#fb7185",
        "target-arrow-shape": "triangle",
        "width": 1.4,
        "curve-style": "bezier"
      }
    },
    {
      selector: "edge",
      style: {
        "opacity": 0.9
      }
    },
    {
      selector: ":selected",
      style: {
        "border-width": 2,
        "border-color": "#f97316"
      }
    }
  ],
  layout: {
    name: "cose",
    animate: true
  },
  wheelSensitivity: 0.2
});

const statusEl = document.getElementById("status");
function setStatus(text) {
  statusEl.textContent = text;
}

async function fetchJSON(url) {
  setStatus("Loading...");
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    setStatus("Done");
    return data;
  } catch (e) {
    console.error(e);
    setStatus("Error: " + e.message);
    return null;
  }
}

function drawGraph(graph) {
  cy.elements().remove();

  const elements = [];

  graph.nodes.forEach((n) => {
    elements.push({
      data: {
        id: n.id,
        label: n.label,
        kind: n.kind
      }
    });
  });

  graph.edges.forEach((e) => {
    elements.push({
      data: {
        id: e.source + "_" + e.target + "_" + e.type,
        source: e.source,
        target: e.target,
        type: e.type
      }
    });
  });

  cy.add(elements);
  cy.layout({ name: "cose", animate: true }).run();
}

document.getElementById("loadUserBtn").addEventListener("click", async () => {
  const userId = document.getElementById("userSearch").value.trim();
  if (!userId) return;
  const data = await fetchJSON(`${API_BASE}/relationships/user/${userId}`);
  if (data) drawGraph(data);
});

document.getElementById("loadTxBtn").addEventListener("click", async () => {
  const txId = document.getElementById("txSearch").value.trim();
  if (!txId) return;
  const data = await fetchJSON(`${API_BASE}/relationships/transaction/${txId}`);
  if (data) drawGraph(data);
});

document.getElementById("loadUserListBtn").addEventListener("click", async () => {
  const list = await fetchJSON(`${API_BASE}/users?limit=50`);
  const container = document.getElementById("listContainer");
  if (!list) return;
  container.innerHTML = "";
  list.forEach((u) => {
    const div = document.createElement("div");
    div.className = "list-item";
    div.textContent = `${u.user_id} · ${u.name}`;
    div.onclick = () => {
      document.getElementById("userSearch").value = u.user_id;
      document.getElementById("loadUserBtn").click();
    };
    container.appendChild(div);
  });
});

document.getElementById("loadTxListBtn").addEventListener("click", async () => {
  const list = await fetchJSON(`${API_BASE}/transactions?limit=50`);
  const container = document.getElementById("listContainer");
  if (!list) return;
  container.innerHTML = "";
  list.forEach((t) => {
    const div = document.createElement("div");
    div.className = "list-item";
    div.textContent = `${t.tx_id} · ${t.amount} ${t.currency}`;
    div.onclick = () => {
      document.getElementById("txSearch").value = t.tx_id;
      document.getElementById("loadTxBtn").click();
    };
    container.appendChild(div);
  });
});

// Filters (simple example: hide by CSS classes)
function applyFilters() {
  const showUsers = document.getElementById("toggleUsers").checked;
  const showTxs = document.getElementById("toggleTxs").checked;
  const showShared = document.getElementById("toggleShared").checked;
  const showMoney = document.getElementById("toggleMoney").checked;
  const showTT = document.getElementById("toggleTT").checked;

  cy.nodes().forEach((n) => {
    if (n.data("kind") === "user") {
      n.style("display", showUsers ? "element" : "none");
    } else {
      n.style("display", showTxs ? "element" : "none");
    }
  });

  cy.edges().forEach((e) => {
    const type = e.data("type") || "";
    let show = true;
    if (type.startsWith("SHARES") && !showShared) show = false;
    if ((type.includes("SENT") || type.includes("RECEIVED")) && !showMoney) show = false;
    if (type.startsWith("RELATED") && !showTT) show = false;
    e.style("display", show ? "element" : "none");
  });
}

["toggleUsers", "toggleTxs", "toggleShared", "toggleMoney", "toggleTT"].forEach((id) => {
  document.getElementById(id).addEventListener("change", applyFilters);
});

// Basic node click info
cy.on("tap", "node", (evt) => {
  const node = evt.target;
  const info = `Node: ${node.id()} (${node.data("kind")})`;
  setStatus(info);
});
