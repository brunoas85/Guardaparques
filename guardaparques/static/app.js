// Interfaz del listado. Lee todo con api/datos y envía los cambios por POST a api/<acción>.
(() => {
"use strict";
const $ = s => document.querySelector(s);
const APP = window.APP || {};
const S = { secc: [], ag: [], dest: [], view: "seccional", q: "", zona: "", bajas: false, canWrite: !!APP.usuario, loaded: false };

const today = () => new Date().toLocaleDateString("sv-SE");
const fmt = d => d ? d.slice(0, 10).split("-").reverse().join("/") : "—";
const norm = s => (s || "").toString().normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
const esc = s => (s ?? "").toString().replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const dniTexto = d => (d || "").replace(/\B(?=(\d{3})+$)/g, ".");
const byName = (a, b) => a.nombre.localeCompare(b.nombre, "es");
const secById = id => S.secc.find(s => s.id === id);

function toast(msg) {
  const t = document.createElement("div"); t.className = "toast"; t.textContent = msg;
  document.body.appendChild(t); setTimeout(() => t.remove(), 2600);
}
function notice(msg, warn) { const n = $("#notice"); n.hidden = !msg; n.textContent = msg || ""; n.classList.toggle("warn", !!warn); }
function confirmBox(title, body) {
  return new Promise(res => {
    $("#cfTitle").textContent = title; $("#cfBody").textContent = body;
    const d = $("#dConf"); d.returnValue = ""; d.showModal();
    d.addEventListener("close", () => res(d.returnValue === "ok"), { once: true });
  });
}

/* ---------- Comunicación con el servidor ---------- */
async function cargar() {
  try {
    const r = await fetch("api/datos", { cache: "no-store" });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "No se pudo leer el listado.");
    S.secc = j.seccionales;
    S.dest = j.destinos;
    S.ag = j.agentes.map(a => {
      const ds = S.dest.filter(d => d.agente_id === a.id);
      const actual = ds.filter(d => !d.hasta).pop() || null;
      return { ...a, activo: !!a.activo, actual, ultimo: actual || ds[ds.length - 1] || null, destinos: ds };
    });
    S.loaded = true;
    opcionesZona();
    if (!$("#notice").classList.contains("warn")) notice("");
    render();
  } catch (e) {
    notice(e.message === "Failed to fetch" ? "No hay conexión con el servidor." : e.message, true);
  }
}
async function enviar(accion, datos) {
  let j = {};
  try {
    const r = await fetch("api/" + accion, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRF": APP.csrf || "" }, body: JSON.stringify(datos),
    });
    j = await r.json().catch(() => ({}));
    if (r.status === 401) { location.href = "login"; return null; }
    if (!r.ok) throw new Error(j.error || "No se pudo guardar el cambio.");
  } catch (e) {
    throw new Error(e.message === "Failed to fetch" ? "No hay conexión con el servidor. El cambio no se guardó." : e.message);
  }
  return j;
}
// Ejecuta una acción mostrando el error en el diálogo; devuelve la respuesta o null.
async function guardar(accion, datos, errEl, boton) {
  errEl.textContent = ""; if (boton) boton.disabled = true;
  try { const j = await enviar(accion, datos); if (j && !j.repetido) await cargar(); return j; }
  catch (e) { errEl.textContent = e.message; return null; }
  finally { if (boton) boton.disabled = false; }
}

/* ---------- Render ---------- */
/* ---------- Zonas ---------- */
const ORDEN_ZONAS = ["ugd norte", "ugd centro", "ugd sur"];
const zonaDeSecc = id => { const s = id && secById(id); return s ? s.zona || "" : ""; };
const zonaDe = a => zonaDeSecc(a.activo ? a.actual && a.actual.seccional_id : a.ultimo && a.ultimo.seccional_id);
// Texto con el que la búsqueda encuentra una zona: "UGD Sur" también como "zona sur".
const textoZona = z => { const n = norm(z); return n ? n + " " + n.replace(/^ugd\s+/, "zona ") : ""; };
const enZona = z => !S.zona || norm(z) === norm(S.zona);
function opcionesZona() {
  const sel = $("#zona"), zonas = [...new Set(S.secc.map(s => s.zona).filter(Boolean))].sort((x, y) => {
    const i = ORDEN_ZONAS.indexOf(norm(x)), j = ORDEN_ZONAS.indexOf(norm(y));
    return (i < 0 ? 99 : i) - (j < 0 ? 99 : j) || x.localeCompare(y, "es");
  });
  if (S.zona && !zonas.some(z => norm(z) === norm(S.zona))) S.zona = "";
  sel.innerHTML = `<option value="">Todas las zonas</option>` +
    zonas.map(z => `<option value="${esc(z)}"${norm(z) === norm(S.zona) ? " selected" : ""}>${esc(z)}</option>`).join("");
  sel.hidden = !zonas.length;
}
function sinCoincidencias() {
  const partes = [S.q && `“${esc(S.q)}”`, S.zona && esc(S.zona)].filter(Boolean);
  return `<div class="empty">Nada coincide con ${partes.join(" en ")}.</div>`;
}

function porDni(a, q) {
  const d = q.replace(/[.\s-]/g, "");
  return !!a.dni && /^\d{3,}$/.test(d) && a.dni.includes(d);
}
function visibles() {
  const q = norm(S.q);
  return S.ag.filter(a => (S.bajas || a.activo) && enZona(zonaDe(a)) &&
    (!q || norm(a.nombre).includes(q) || norm(a.legajo).includes(q) || porDni(a, q) || norm(a.ultimo && a.ultimo.seccional).includes(q) || textoZona(zonaDe(a)).includes(q)));
}
function render() {
  const act = S.ag.filter(a => a.activo);
  $("#stA").textContent = act.length; $("#stS").textContent = S.secc.length;
  $("#stV").textContent = act.filter(a => !a.actual).length;
  $("#editActions").hidden = !S.canWrite;
  $("#bExport").hidden = !S.ag.length;
  if (!S.loaded) return;
  const out = $("#out");
  if (!S.ag.length && !S.secc.length) {
    out.innerHTML = `<div class="empty"><h2>Todavía no hay guardaparques cargados</h2>
      Acá va a aparecer cada guardaparque con la seccional donde presta funciones.${S.canWrite ? ` Empezá pegando el listado actual o cargando las seccionales.
      <div class="btns"><button class="btn primary" type="button" data-act="import">Cargar listado</button><button class="btn" type="button" data-act="addS">+ Seccional</button></div>`
      : ` Cuando RRHH lo cargue, lo vas a ver en esta página.`}</div>`;
    return;
  }
  out.innerHTML = S.view === "seccional" ? vistaSeccional() : S.view === "listado" ? vistaListado() : vistaMovimientos();
}
function vistaSeccional() {
  const ags = visibles(), q = norm(S.q);
  const enSec = (a, id) => a.activo ? a.actual && a.actual.seccional_id === id : a.ultimo && a.ultimo.seccional_id === id;
  const grupos = S.secc.slice().sort(byName).map(s => ({ s, list: ags.filter(a => enSec(a, s.id)).sort(byName) }))
    .filter(g => enZona(g.s.zona) && (!q || g.list.length || norm(g.s.nombre).includes(q) || textoZona(g.s.zona).includes(q)));
  const sin = ags.filter(a => !S.secc.some(s => enSec(a, s.id))).sort(byName);
  if (sin.length) grupos.push({ s: { id: 0, nombre: "Sin seccional asignada" }, list: sin });
  if (!grupos.length) return sinCoincidencias();
  return `<div class="grid">${grupos.map(({ s, list }) => `
    <section class="secc${s.id ? "" : " sin"}"><h3>
      <span class="tit">${s.id && S.canWrite ? `<button class="linkish" type="button" data-act="editS" data-id="${s.id}" title="Editar seccional">${esc(s.nombre)}</button>` : esc(s.nombre)}</span>
      <span class="meta">${s.zona ? `<span>${esc(s.zona)}</span>` : ""}<b class="count" title="${list.length} guardaparque${list.length === 1 ? "" : "s"}">${list.length}</b></span></h3>
      <ul>${list.length ? list.map(a => `<li><button class="linkish" type="button" data-act="hist" data-id="${a.id}">${esc(a.nombre)}</button>
        ${a.activo ? `<span class="since">${a.actual ? "desde " + fmt(a.actual.desde) : ""}</span>` : `<span class="pill off">Baja</span>`}</li>`).join("")
        : `<li class="none">Sin guardaparques asignados</li>`}</ul></section>`).join("")}</div>`;
}
function vistaListado() {
  const ags = visibles().sort(byName);
  if (!ags.length) return S.q || S.zona ? sinCoincidencias() : `<div class="empty">No hay guardaparques activos.</div>`;
  return `<div class="tablebox"><table><thead><tr><th>Guardaparque</th><th>Legajo</th><th>Seccional</th><th>Desde</th><th></th></tr></thead><tbody>
    ${ags.map(a => `<tr><td><button class="linkish" type="button" data-act="hist" data-id="${a.id}">${esc(a.nombre)}</button>${a.activo ? "" : ` <span class="pill off">Baja</span>`}</td>
      <td class="num">${esc(a.legajo) || "—"}</td>
      <td>${a.actual ? `<span class="pill">${esc(a.actual.seccional)}</span>` : `<span class="sub">${a.activo ? "Sin asignar" : "—"}</span>`}</td>
      <td class="num">${a.actual ? fmt(a.actual.desde) : "—"}</td>
      <td class="ops">${S.canWrite && a.activo ? `<button class="btn small" type="button" data-act="move" data-id="${a.id}">Cambiar seccional</button><button class="btn small" type="button" data-act="editA" data-id="${a.id}">Editar</button>` : ""}</td></tr>`).join("")}
    </tbody></table></div>`;
}
function movimientos() {
  const ev = [];
  for (const a of S.ag) {
    a.destinos.forEach((d, i) => { if (i > 0) { const p = a.destinos[i - 1];
      ev.push({ fecha: d.desde, a, de: p.seccional, hacia: d.seccional, zonas: [zonaDeSecc(p.seccional_id), zonaDeSecc(d.seccional_id)], ref: d.referencia, por: d.registrado_por }); } });
    if (!a.activo && a.baja_fecha) ev.push({ fecha: a.baja_fecha, a, de: a.ultimo && a.ultimo.seccional, zonas: [zonaDe(a)], baja: true });
  }
  return ev.sort((x, y) => (y.fecha || "").localeCompare(x.fecha || ""));
}
function vistaMovimientos() {
  const q = norm(S.q);
  const ev = movimientos().filter(e => (!S.zona || e.zonas.some(enZona)) &&
    (!q || norm(e.a.nombre).includes(q) || norm(e.de).includes(q) || norm(e.hacia).includes(q) || e.zonas.some(z => textoZona(z).includes(q))));
  if (!ev.length && (S.q || S.zona)) return sinCoincidencias();
  if (!ev.length) return `<div class="empty"><h2>Sin movimientos registrados</h2>Cada vez que se usa “Cambiar seccional”, el traslado queda anotado acá con su fecha.</div>`;
  return `<div class="tablebox"><ul class="timeline">${ev.map(e => `<li><span class="when">${fmt(e.fecha)}</span>
    <span><button class="linkish" type="button" data-act="hist" data-id="${e.a.id}">${esc(e.a.nombre)}</button><br>
    <span class="sub">${e.baja ? `Baja · estaba en ${esc(e.de || "—")}` : `${esc(e.de)}<span class="arrow">→</span>${esc(e.hacia)}`}${e.ref ? ` · ${esc(e.ref)}` : ""}${e.por ? ` · cargó ${esc(e.por)}` : ""}</span></span></li>`).join("")}</ul></div>`;
}

/* ---------- Diálogos ---------- */
function opcionesSeccional(sel, actual, conVacio) {
  sel.innerHTML = (conVacio ? `<option value="">Sin asignar</option>` : "") +
    S.secc.slice().sort(byName).map(s => `<option value="${s.id}"${s.id === actual ? " selected" : ""}>${esc(s.nombre)}</option>`).join("");
}
let cur = null;

function abrirMover(a) {
  cur = a;
  $("#mvWho").textContent = `${a.nombre} · hoy en ${a.actual ? a.actual.seccional : "ninguna seccional"}`;
  opcionesSeccional($("#mvSec"), 0, false);
  const otra = S.secc.slice().sort(byName).find(s => !a.actual || s.id !== a.actual.seccional_id);
  if (otra) $("#mvSec").value = otra.id;
  $("#mvDate").value = today(); $("#mvNote").value = "";
  $("#mvErr").textContent = otra ? "" : "Primero cargá la seccional de destino con “+ Seccional”.";
  $("#dMove").showModal();
}
$("#fMove").addEventListener("submit", async ev => {
  if (!ev.submitter || ev.submitter.value !== "ok") return;
  ev.preventDefault();
  const destino = +$("#mvSec").value;
  const ok = await guardar("agente_mover", { id: cur.id, seccional_id: destino, desde: $("#mvDate").value, referencia: $("#mvNote").value }, $("#mvErr"), ev.submitter);
  if (ok) { $("#dMove").close(); toast(`${cur.nombre} pasó a ${secById(destino).nombre}`); }
});

function abrirAgente(a) {
  cur = a || null; delete $("#fAg").dataset.repOk;
  $("#agTitle").textContent = a ? "Editar guardaparque" : "Nuevo guardaparque";
  $("#agName").value = a ? a.nombre : ""; $("#agLeg").value = a ? a.legajo : ""; $("#agDni").value = a ? a.dni || "" : "";
  opcionesSeccional($("#agSec"), 0, true);
  $("#agSecBox").hidden = !!a; $("#agDateBox").hidden = !!a; $("#agDate").value = today();
  $("#agBaja").hidden = !a;
  $("#agErr").textContent = "";
  $("#dAg").showModal();
}
$("#fAg").addEventListener("submit", async ev => {
  if (!ev.submitter || ev.submitter.value !== "ok") return;
  ev.preventDefault();
  const datos = { nombre: $("#agName").value, legajo: $("#agLeg").value, dni: $("#agDni").value, confirmar_repetido: !!$("#fAg").dataset.repOk };
  if (cur) datos.id = cur.id; else if ($("#agSec").value) { datos.seccional_id = +$("#agSec").value; datos.desde = $("#agDate").value; }
  const j = await guardar(cur ? "agente_editar" : "agente_crear", datos, $("#agErr"), ev.submitter);
  if (!j) return;
  if (j.repetido) { $("#fAg").dataset.repOk = "1"; $("#agErr").textContent = "Ya hay un guardaparque con ese nombre. Tocá Guardar de nuevo si es otra persona."; return; }
  $("#dAg").close(); toast(cur ? "Datos actualizados" : `${datos.nombre.trim()} agregado`);
});
$("#agBaja").addEventListener("click", async () => {
  const a = cur; $("#dAg").close();
  if (!await confirmBox("Dar de baja", `${a.nombre} deja de figurar en el listado activo con fecha de hoy. Su historial se conserva y se ve con “Mostrar bajas”.`)) return;
  try { await enviar("agente_baja", { id: a.id, fecha: today() }); await cargar(); toast(`${a.nombre} dado de baja`); }
  catch (e) { notice(e.message, true); }
});

function abrirSeccional(s) {
  cur = s || null;
  $("#scTitle").textContent = s ? "Editar seccional" : "Nueva seccional";
  $("#scName").value = s ? s.nombre : ""; $("#scZona").value = s ? s.zona : ""; $("#scErr").textContent = "";
  $("#scDel").hidden = !s; $("#dSec").showModal();
}
$("#fSec").addEventListener("submit", async ev => {
  if (!ev.submitter || ev.submitter.value !== "ok") return;
  ev.preventDefault();
  const datos = { nombre: $("#scName").value, zona: $("#scZona").value }; if (cur) datos.id = cur.id;
  if (await guardar("seccional_guardar", datos, $("#scErr"), ev.submitter)) { $("#dSec").close(); toast(cur ? "Seccional actualizada" : `${datos.nombre.trim()} creada`); }
});
$("#scDel").addEventListener("click", async () => {
  const s = cur;
  if (S.ag.some(a => a.actual && a.actual.seccional_id === s.id)) { $("#scErr").textContent = "Tiene guardaparques asignados. Trasladalos antes de eliminarla."; return; }
  $("#dSec").close();
  if (!await confirmBox("Eliminar seccional", `Se elimina “${s.nombre}”. El historial de quienes pasaron por ahí conserva el nombre.`)) return;
  try { await enviar("seccional_eliminar", { id: s.id }); await cargar(); toast("Seccional eliminada"); }
  catch (e) { notice(e.message, true); }
});

function abrirHistorial(a) {
  $("#hiTitle").textContent = a.nombre;
  const items = a.destinos.slice().reverse().map(d => `<li class="${d.hasta ? "" : "now"}"><b>${esc(d.seccional)}</b>
    <span class="sub">${d.hasta ? `${fmt(d.desde)} al ${fmt(d.hasta)}` : `Actual · desde ${fmt(d.desde)}`}${d.referencia ? " · " + esc(d.referencia) : ""}${d.registrado_por ? " · cargó " + esc(d.registrado_por) : ""}</span></li>`);
  if (!a.activo) items.unshift(`<li><b>Baja</b><span class="sub">${fmt(a.baja_fecha)}</span></li>`);
  if (!a.destinos.length) items.push(`<li><b>Sin seccional asignada</b></li>`);
  $("#hiList").innerHTML = items.join("") + (a.legajo || a.dni ? `<li style="list-style:none"><span class="sub">${[a.legajo && "Legajo " + esc(a.legajo), a.dni && "DNI " + esc(dniTexto(a.dni))].filter(Boolean).join("<br>")}</span></li>` : "");
  $("#hiMove").hidden = $("#hiEdit").hidden = !(S.canWrite && a.activo);
  $("#hiReact").hidden = !(S.canWrite && !a.activo);
  $("#hiMove").onclick = () => { $("#dHist").close(); abrirMover(a); };
  $("#hiEdit").onclick = () => { $("#dHist").close(); abrirAgente(a); };
  $("#hiReact").onclick = async () => {
    $("#dHist").close();
    try { await enviar("agente_reactivar", { id: a.id }); await cargar(); toast(`${a.nombre} reactivado. Asignale una seccional con “Cambiar seccional”.`); }
    catch (e) { notice(e.message, true); }
  };
  $("#dHist").showModal();
}

function abrirImportar() { $("#impText").value = ""; $("#impDate").value = today(); $("#impErr").textContent = ""; $("#dImp").showModal(); }
$("#fImp").addEventListener("submit", async ev => {
  if (!ev.submitter || ev.submitter.value !== "ok") return;
  ev.preventDefault();
  if (!$("#impText").value.trim()) { $("#impErr").textContent = "Pegá al menos una línea con nombre y seccional."; return; }
  const j = await guardar("importar", { texto: $("#impText").value, desde: $("#impDate").value }, $("#impErr"), ev.submitter);
  if (!j) return;
  $("#dImp").close();
  toast(`${j.agregados} cargados${j.repetidos.length ? ` · ${j.repetidos.length} ya existían y se saltearon` : ""}`);
});

/* ---------- Usuarios ---------- */
async function listarUsuarios() {
  try {
    const j = await enviar("usuarios_listar", {});
    $("#usList").innerHTML = j.usuarios.map(u => `<tr><td>${esc(u.nombre)}${u.activo ? "" : ` <span class="pill off">Inactivo</span>`}</td><td>${esc(u.usuario)}</td>
      <td>${u.es_admin ? "Administrador" : "Edición"}</td>
      <td class="ops"><button class="btn small" type="button" data-us="clave" data-id="${u.id}">Nueva contraseña</button><button class="btn small" type="button" data-us="${u.activo ? "off" : "on"}" data-id="${u.id}">${u.activo ? "Desactivar" : "Activar"}</button></td></tr>`).join("");
  } catch (e) { $("#usErr").textContent = e.message; }
}
const bUsers = $("#bUsers");
if (bUsers) bUsers.addEventListener("click", () => { $("#usErr").textContent = ""; listarUsuarios(); $("#dUsers").showModal(); });
$("#usAdd").addEventListener("click", async () => {
  $("#usErr").textContent = "";
  try {
    await enviar("usuario_crear", { nombre: $("#usNombre").value, usuario: $("#usUser").value, clave: $("#usClave").value, es_admin: $("#usAdmin").checked });
    toast(`Usuario ${$("#usUser").value} creado`);
    $("#usNombre").value = $("#usUser").value = $("#usClave").value = ""; $("#usAdmin").checked = false;
    listarUsuarios();
  } catch (e) { $("#usErr").textContent = e.message; }
});
$("#usList").addEventListener("click", async e => {
  const b = e.target.closest("[data-us]"); if (!b) return;
  $("#usErr").textContent = "";
  try {
    if (b.dataset.us === "clave") {
      const abc = "abcdefghjkmnpqrstuvwxyz23456789";
      const clave = Array.from(crypto.getRandomValues(new Uint32Array(10)), (n, i) => (i === 5 ? "-" : "") + abc[n % abc.length]).join("");
      await enviar("usuario_clave", { id: +b.dataset.id, clave });
      $("#usErr").textContent = `Nueva contraseña: ${clave} · Anotala y pasásela a la persona; no se vuelve a mostrar.`;
    } else {
      await enviar("usuario_activo", { id: +b.dataset.id, activo: b.dataset.us === "on" });
      listarUsuarios();
    }
  } catch (err) { $("#usErr").textContent = err.message; }
});

const bMiClave = $("#bMiClave");
if (bMiClave) bMiClave.addEventListener("click", () => { $("#clActual").value = $("#clNueva").value = ""; $("#clErr").textContent = ""; $("#dClave").showModal(); });
$("#fClave").addEventListener("submit", async ev => {
  if (!ev.submitter || ev.submitter.value !== "ok") return;
  ev.preventDefault();
  if (await guardar("mi_clave", { actual: $("#clActual").value, nueva: $("#clNueva").value }, $("#clErr"), ev.submitter)) { $("#dClave").close(); toast("Contraseña actualizada"); }
});

/* ---------- Eventos generales ---------- */
document.querySelectorAll(".tabs button").forEach(b => b.addEventListener("click", () => {
  S.view = b.dataset.view; document.querySelectorAll(".tabs button").forEach(x => x.setAttribute("aria-pressed", x === b));
  try { localStorage.setItem("gp-vista", S.view); } catch (e) {}
  render();
}));
$("#q").addEventListener("input", e => { S.q = e.target.value; render(); });
$("#zona").addEventListener("change", e => { S.zona = e.target.value; render(); });
$("#bajas").addEventListener("change", e => { S.bajas = e.target.checked; render(); });
$("#bAddA").addEventListener("click", () => abrirAgente());
$("#bAddS").addEventListener("click", () => abrirSeccional());
$("#bImport").addEventListener("click", abrirImportar);
$("#out").addEventListener("click", e => {
  const b = e.target.closest("[data-act]"); if (!b) return;
  const a = S.ag.find(x => x.id === +b.dataset.id), act = b.dataset.act;
  if (act === "hist" && a) abrirHistorial(a);
  else if (act === "move" && a) abrirMover(a);
  else if (act === "editA" && a) abrirAgente(a);
  else if (act === "editS") abrirSeccional(secById(+b.dataset.id));
  else if (act === "import") abrirImportar();
  else if (act === "addS") abrirSeccional();
});

try { const v = localStorage.getItem("gp-vista"); const b = v && document.querySelector(`.tabs button[data-view="${v}"]`); if (b) b.click(); } catch (e) {}
render();
cargar();
// Refresca cada minuto por si otra persona de RRHH hizo cambios, salvo con un diálogo abierto.
setInterval(() => { if (!document.hidden && !document.querySelector("dialog[open]")) cargar(); }, 60000);
})();
