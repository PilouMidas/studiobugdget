/* Picturial — Devis de production : interface web (vanilla JS, aucune dépendance). */
"use strict";

const state = {
  filmId: localStorage.getItem("picturial.filmId") || null,
  tab: "accueil",
  devis: null,
  referentiel: null,
  collapsed: new Set(),
  recapitulatif: false,
  allExpanded: true,
};

const app = document.getElementById("app");
const modalRoot = document.getElementById("modal-root");
const saveEl = document.getElementById("save-indicator");

/* ---------------- utilitaires ---------------- */

function el(tag, attrs, ...children) {
  const e = document.createElement(tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "value") e.value = v;
    else if (k === "checked") e.checked = !!v;
    else e.setAttribute(k, v);
  }
  for (const c of children.flat(9)) {
    if (c == null) continue;
    e.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return e;
}

function fmt(n) {
  if (n === null || n === undefined || n === "" || isNaN(n)) return "";
  return Number(n).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
}
function fmtPlain(n) {
  if (n === null || n === undefined || n === "" || isNaN(n)) return "";
  return Number(n).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function parseNum(s) {
  if (s === null || s === undefined || s === "") return null;
  const v = parseFloat(String(s).replace(/[   ]/g, "").replace(",", "."));
  return isNaN(v) ? null : v;
}
function setSave(txt, cls) {
  saveEl.textContent = txt;
  saveEl.className = "save" + (cls ? " " + cls : "");
}

async function api(path, method = "GET", body = null) {
  setSave("Enregistrement…", "saving");
  const opt = { method, headers: {} };
  if (body !== null) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const res = await fetch(path, opt);
  const isJson = (res.headers.get("Content-Type") || "").includes("json");
  const data = isJson ? await res.json() : await res.blob();
  if (!res.ok) {
    setSave("Erreur", "error");
    const err = new Error((data && data.erreur) || ("HTTP " + res.status));
    err.status = res.status;
    err.data = data;
    throw err;
  }
  setSave("Enregistré ✓ " + new Date().toLocaleTimeString("fr-FR"), "");
  return data;
}

/* ---------------- modales et menus ---------------- */

function openModal(title, buildFn, width) {
  const backdrop = el("div", { class: "modal-backdrop" });
  const modal = el("div", { class: "modal" });
  if (width) modal.style.width = width + "px";
  modal.append(el("h2", { text: title }));
  const content = el("div");
  modal.append(content);
  const actions = el("div", { class: "modal-actions" });
  modal.append(actions);
  backdrop.append(modal);
  modalRoot.append(backdrop);
  const close = () => backdrop.remove();
  backdrop.addEventListener("mousedown", (e) => { if (e.target === backdrop) close(); });
  buildFn(content, actions, close);
  return { close, content, actions, modal };
}
function closeMenus() {
  document.querySelectorAll(".menu").forEach((m) => m.remove());
  document.removeEventListener("click", closeMenus);
}
function openMenu(anchor, items) {
  closeMenus();
  const menu = el("div", { class: "menu" });
  const r = anchor.getBoundingClientRect();
  menu.style.left = Math.min(r.left, window.innerWidth - 260) + "px";
  menu.style.top = (r.bottom + 4) + "px";
  for (const it of items) {
    if (it === "-") { menu.append(el("hr")); continue; }
    menu.append(el("button", { class: it.danger ? "danger" : "", text: it.label, onclick: (e) => { e.stopPropagation(); closeMenus(); it.fn(); } }));
  }
  document.body.append(menu);
  setTimeout(() => document.addEventListener("click", closeMenus), 0);
}

/* ---------------- navigation ---------------- */

document.querySelectorAll("#tabs .tab").forEach((b) =>
  b.addEventListener("click", () => { state.tab = b.dataset.tab; render(); }));

async function loadReferentiel() {
  state.referentiel = await api("/api/referentiel");
}
async function loadDevis() {
  state.devis = await api(`/api/films/${state.filmId}/devis`);
}

async function render() {
  document.querySelectorAll("#tabs .tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === state.tab));
  const hasFilm = !!state.filmId;
  document.querySelectorAll('#tabs .tab[data-tab="parametres"], #tabs .tab[data-tab="devis"], #tabs .tab[data-tab="region"]')
    .forEach((b) => (b.style.display = hasFilm ? "" : "none"));
  try {
    if (state.tab === "accueil") return renderAccueil();
    if (!state.referentiel) await loadReferentiel();
    if (state.tab === "baremes") return renderBaremes();
    if (!hasFilm) { state.tab = "accueil"; return renderAccueil(); }
    if (state.tab === "parametres") return renderParametres();
    if (!state.devis || state.devis.film.id !== state.filmId) await loadDevis();
    if (state.tab === "devis") return renderDevis();
    if (state.tab === "region") return renderRegion();
  } catch (e) {
    app.innerHTML = "";
    app.append(el("div", { class: "banner", text: "Erreur : " + e.message }));
  }
}

function selectFilm(id, tab = "devis") {
  state.filmId = id;
  localStorage.setItem("picturial.filmId", id);
  state.tab = tab;
  state.devis = null;
  render();
}

/* ---------------- accueil ---------------- */

async function renderAccueil() {
  const films = await api("/api/films");
  app.innerHTML = "";
  app.append(el("h1", { text: "Vos films" }));
  app.append(el("p", { class: "hint", text: "Créez un devis, rouvrez-en un ou dupliquez-le pour étudier une autre hypothèse. Le projet « À la recherche de la Boum — démonstration » contient des montants fictifs prêts à tester." }));
  const grid = el("div", { class: "film-grid" });
  for (const f of films) {
    const card = el("div", { class: "film-card" });
    card.append(el("h3", { text: f.titre }));
    card.append(el("div", { class: "meta", text: `${f.societe || "—"} · ${f.type_oeuvre || ""} · région : ${f.region_cible || "—"}` }));
    const actions = el("div", { class: "actions" });
    actions.append(el("button", { class: "primary", text: "Ouvrir le devis", onclick: () => selectFilm(f.id, "devis") }));
    actions.append(el("button", { class: "secondary", text: "Paramètres du film", onclick: () => selectFilm(f.id, "parametres") }));
    actions.append(el("button", {
      class: "secondary", text: "Dupliquer",
      onclick: async () => { const r = await api(`/api/films/${f.id}/dupliquer`, "POST"); selectFilm(r.id, "devis"); },
    }));
    actions.append(el("button", {
      class: "danger", text: "Supprimer",
      onclick: async () => {
        if (!confirm(`Supprimer définitivement le film « ${f.titre} » et tout son devis ?`)) return;
        await api(`/api/films/${f.id}`, "DELETE");
        if (state.filmId === f.id) { state.filmId = null; localStorage.removeItem("picturial.filmId"); }
        renderAccueil();
      },
    }));
    card.append(actions);
    grid.append(card);
  }
  app.append(grid);
  app.append(el("button", {
    class: "primary", style: "margin-top:18px", text: "+ Nouveau film (projet vierge)",
    onclick: () => modalNouveauFilm(),
  }));
}

function modalNouveauFilm() {
  openModal("Nouveau film", (content, actions, close) => {
    const titre = el("input", { style: "width:100%", placeholder: "Titre du film" });
    const societe = el("input", { style: "width:100%", placeholder: "Société de production" });
    content.append(el("div", { class: "field" }, el("label", { text: "Titre" }), titre));
    content.append(el("div", { class: "field" }, el("label", { text: "Société de production" }), societe));
    actions.append(el("button", { class: "secondary", text: "Annuler", onclick: close }));
    actions.append(el("button", {
      class: "primary", text: "Créer le projet vierge",
      onclick: async () => {
        const r = await api("/api/films", "POST", { titre: titre.value, societe: societe.value });
        close();
        selectFilm(r.id, "parametres");
      },
    }));
  });
}

/* ---------------- paramètres du film ---------------- */

async function renderParametres() {
  const film = await api(`/api/films/${state.filmId}`);
  const ref = state.referentiel;
  app.innerHTML = "";
  app.append(el("h1", { text: "Paramètres du film" }));
  app.append(el("div", { class: "banner", text: "Hypothèses propres à ce projet : convention, grille, date de référence des barèmes, région cible et taux de charges employeur. Les barèmes communs se gèrent dans l’onglet « Barèmes »." }));

  const convSel = el("select");
  for (const c of ref.conventions) convSel.append(el("option", { value: c.id, text: c.nom, selected: c.id === film.convention_id }));
  const grilleSel = el("select");
  function fillGrilles() {
    grilleSel.innerHTML = "";
    const c = ref.conventions.find((x) => x.id === convSel.value);
    for (const g of (c ? c.grilles : [])) grilleSel.append(el("option", { value: g.id, text: `${g.version} (effet ${g.date_effet}) — ${g.statut === "verifie" ? "vérifié" : "démonstration"}`, selected: g.id === film.grille_id }));
  }
  fillGrilles();
  convSel.addEventListener("change", fillGrilles);

  const regionSel = el("select");
  for (const r of ref.regions) regionSel.append(el("option", { value: r, text: r, selected: r === film.region_cible }));

  const fields = {
    titre: el("input", { value: film.titre }),
    societe: el("input", { value: film.societe }),
    type_oeuvre: el("input", { value: film.type_oeuvre }),
    date_debut: el("input", { type: "date", value: film.date_debut }),
    date_fin: el("input", { type: "date", value: film.date_fin }),
    date_ref_baremes: el("input", { type: "date", value: film.date_ref_baremes }),
    taux_charges: el("input", { type: "number", step: "0.01", min: "0", max: "1", value: film.taux_charges }),
  };
  const chargesMode = el("select", {},
    el("option", { value: "avec", text: "Charges accolées à chaque engagement (sous-ligne « charges employeur »)", selected: film.charges_mode === "avec" }),
    el("option", { value: "poste_dedie", text: "Charges dans un poste dédié de la nomenclature (chaque euro compté une seule fois)", selected: film.charges_mode === "poste_dedie" }));

  const grid = el("div", { class: "form-grid" },
    el("label", { text: "Titre du film" }), fields.titre,
    el("label", { text: "Société de production" }), fields.societe,
    el("label", { text: "Type d’œuvre" }), fields.type_oeuvre,
    el("label", { text: "Date de début prévisionnelle" }), fields.date_debut,
    el("label", { text: "Date de fin prévisionnelle" }), fields.date_fin,
    el("label", { text: "Convention collective" }), convSel,
    el("label", { text: "Grille / catégorie retenue" }), grilleSel,
    el("label", { text: "Date de référence des barèmes" }), fields.date_ref_baremes,
    el("label", { text: "Région ciblée pour le devis" }), regionSel,
    el("label", { text: "Charges employeur (hypothèse)" }), fields.taux_charges,
    el("label", { text: "Imputation des charges" }), chargesMode,
  );
  app.append(grid);

  const actions = el("div", { class: "form-actions" });
  actions.append(el("button", {
    class: "primary", text: "Enregistrer les paramètres",
    onclick: async () => {
      const body = {
        titre: fields.titre.value, societe: fields.societe.value, type_oeuvre: fields.type_oeuvre.value,
        date_debut: fields.date_debut.value, date_fin: fields.date_fin.value,
        convention_id: convSel.value, grille_id: grilleSel.value, date_ref_baremes: fields.date_ref_baremes.value,
        taux_charges: parseNum(fields.taux_charges.value) ?? 0.4, charges_mode: chargesMode.value,
      };
      if (regionSel.value !== film.region_cible) body.region_cible = regionSel.value;
      try {
        await api(`/api/films/${state.filmId}`, "PUT", body);
      } catch (e) {
        if (e.data && e.data.confirmation_requise) return modalConfirmerRegion(regionSel.value, async (option) => {
          await api(`/api/films/${state.filmId}`, "PUT", { region_cible: regionSel.value, option_ventilation: option });
          state.devis = null; render();
        });
        alert(e.message);
      }
      state.devis = null;
      render();
    },
  }));
  actions.append(el("button", {
    class: "secondary", text: "Actualiser les barèmes du devis…",
    onclick: () => modalActualiserBaremes(),
  }));
  app.append(actions);

  const health = await api("/api/health");
  app.append(el("p", { class: "hint", style: "margin-top:24px", text: `Base de données locale (conservée même si vous remplacez le dossier de l’application) : ${health.db}` }));
}

function modalConfirmerRegion(region, apres) {
  openModal("Changer de région cible ?", (content, actions, close) => {
    content.append(el("p", { text: `Vous passez la région cible à « ${region} » alors que des dépenses sont déjà ventilées. Que faire des affectations existantes ?` }));
    actions.append(el("button", {
      class: "secondary", text: "Conserver les ventilations existantes",
      onclick: async () => { close(); await apres("conserver"); },
    }));
    actions.append(el("button", {
      class: "danger", text: "Tout remettre « à ventiler »",
      onclick: async () => { close(); await apres("reinitialiser"); },
    }));
    actions.append(el("button", { class: "secondary", text: "Annuler", onclick: close }));
  });
}

async function modalActualiserBaremes() {
  let preview;
  try { preview = await api(`/api/films/${state.filmId}/baremes/actualiser`, "POST", { appliquer: false }); }
  catch (e) { alert(e.message); return; }
  openModal("Actualiser les barèmes du devis — aperçu des écarts", (content, actions, close) => {
    content.append(el("p", { class: "hint", text: `Date de référence : ${preview.date_ref}. Le devis conserve ses chiffres tant que vous ne validez pas. Les salaires négociés sont préservés ; ceux qui passeraient sous le nouveau minimum sont signalés.` }));
    const t = el("table", { class: "mini" });
    t.append(el("tr", {}, el("th", { text: "Fonction" }), el("th", { text: "Ancien min." }), el("th", { text: "Nouveau min." }), el("th", { text: "Salaire retenu" }), el("th", { class: "num", text: "Impact brut" }), el("th", { text: "Note" })));
    for (const a of preview.apercu) {
      t.append(el("tr", {},
        el("td", { text: a.fonction + (a.nom ? " — " + a.nom : "") }),
        el("td", { class: "num", text: fmt(a.ancien_minimum) }),
        el("td", { class: "num", text: fmt(a.nouveau_minimum) }),
        el("td", { class: "num", text: fmt(a.nouveau_salaire) }),
        el("td", { class: "num", text: (a.impact_brut >= 0 ? "+" : "") + fmt(a.impact_brut) }),
        el("td", { text: a.note })));
    }
    if (!preview.apercu.length) t.append(el("tr", {}, el("td", { colspan: "6", text: "Aucun engagement à actualiser." })));
    content.append(t);
    actions.append(el("button", { class: "secondary", text: "Annuler", onclick: close }));
    actions.append(el("button", {
      class: "primary", text: "Valider l’actualisation",
      onclick: async () => {
        await api(`/api/films/${state.filmId}/baremes/actualiser`, "POST", { appliquer: true });
        close();
        state.devis = null;
        render();
      },
    }));
  });
}

/* ---------------- devis ---------------- */

function renderDevis() {
  const d = state.devis;
  app.innerHTML = "";
  app.append(el("h1", { text: `Devis — ${d.film.titre}` }));
  const nomConv = (state.referentiel.conventions.find((c) => c.id === d.film.convention_id) || {}).nom || "—";
  const grille = (state.referentiel.conventions.flatMap((c) => c.grilles).find((g) => g.id === d.film.grille_id)) || {};
  app.append(el("div", { class: "banner", text: `Nomenclature provisoire à neuf grands postes (éditable). Convention : ${nomConv} · ${grille.version || ""} (effet ${grille.date_effet || "?"}) · date de référence : ${d.film.date_ref_baremes} · région : ${d.film.region_cible} · charges employeur : ${(d.film.taux_charges * 100).toFixed(0)} %` }));

  const t = d.totaux;
  const bar = el("div", { class: "totaux-bar" },
    el("div", {}, el("div", { class: "big", text: fmt(t.montant) }), el("div", { class: "lbl", text: "Total général" })),
    el("div", {}, el("div", { class: "big", text: fmt(t.en_region) }), el("div", { class: "lbl", text: "En région" })),
    el("div", {}, el("div", { class: "big", text: fmt(t.hors_region) }), el("div", { class: "lbl", text: "Hors région" })),
    el("div", {}, el("div", { class: "big", text: fmt(t.a_ventiler) }), el("div", { class: "lbl", text: "À ventiler" })),
    el("div", { class: "spacer" }),
    el("button", { class: "secondary", text: state.recapitulatif ? "Mode détaillé" : "Mode Récapitulatif", onclick: () => { state.recapitulatif = !state.recapitulatif; renderDevis(); } }),
    el("button", { class: "secondary", text: "Tout déplier", onclick: () => { state.allExpanded = true; state.collapsed.clear(); renderDevis(); } }),
    el("button", { class: "secondary", text: "Tout replier", onclick: () => { state.allExpanded = false; renderDevis(); } }),
  );
  app.append(bar);
  const leg = el("p", { class: "legend" });
  leg.append("Légende : ", el("span", { class: "m-saisi", text: "montant saisi" }), " · ",
    el("span", { class: "m-calcule", text: "montant calculé" }), " · ",
    el("span", { class: "m-hyp", text: "⚠ hypothèse à vérifier" }),
    " — le total d’une ligne détaillée est la somme de ses sous-détails.");
  app.append(leg);

  const parentMap = {};
  const depthMap = {};
  (function mapNodes(nodes, parent, depth) {
    for (const n of nodes) { parentMap[n.id] = parent; depthMap[n.id] = depth; if (n.children) mapNodes(n.children, n.id, depth + 1); }
  })(d.arbre, null, 0);

  async function saveLigne(id, champs) {
    try {
      await api(`/api/lignes/${id}`, "PUT", champs);
      await loadDevis();
      renderDevis();
    } catch (e) { alert(e.message); renderDevis(); }
  }
  function countDesc(n) { return (n.children || []).reduce((a, c) => a + 1 + countDesc(c), 0); }
  async function ventiler(n, mode) {
    try { await api(`/api/lignes/${n.id}/ventilation`, "POST", { mode }); }
    catch (e) { alert(e.message); }
    await loadDevis(); renderDevis();
  }
  function menuItems(n) {
    const items = [];
    if (n.type !== "poste") items.push({ label: "✚ Ajouter un sous-détail", fn: () => modalSousDetail(n) });
    if (["poste", "rubrique", "ligne"].includes(n.type)) items.push({ label: "👤 Ajouter un technicien", fn: () => modalTechnicien(n.id) });
    if (n.type === "poste") items.push({ label: "✚ Ajouter une rubrique", fn: () => modalNouvelleLigne(n, "rubrique") });
    if (n.type === "poste" || n.type === "rubrique") items.push({ label: "✚ Ajouter une ligne budgétaire", fn: () => modalNouvelleLigne(n, "ligne") });
    if (n.type === "poste") items.push({ label: "✚ Ajouter un grand poste", fn: () => modalNouvelleLigne(null, "poste") });
    if (n.technicien) items.push({ label: "👤 Ouvrir l’engagement (tarif, durées)", fn: () => modalOuvrirTechnicien(n.technicien.id) });
    items.push({ label: "⧉ Dupliquer", fn: async () => { await api(`/api/lignes/${n.id}/dupliquer`, "POST"); await loadDevis(); renderDevis(); } });
    items.push({ label: "➜ Déplacer vers…", fn: () => modalDeplacer(n) });
    items.push("-");
    items.push({ label: "🗺 Tout affecter en région", fn: () => ventiler(n, "tout_en") });
    items.push({ label: "🗺 Tout affecter hors région", fn: () => ventiler(n, "tout_hors") });
    items.push({ label: "🗺 Ventiler en région…", fn: () => modalVentiler(n) });
    items.push("-");
    items.push({
      label: "🗑 Supprimer", danger: true,
      fn: async () => {
        const nb = 1 + countDesc(n);
        if (!confirm(`Supprimer « ${n.libelle} »${nb > 1 ? ` et ses ${nb - 1} sous-ligne(s)` : ""} ? Action définitive.`)) return;
        await api(`/api/lignes/${n.id}`, "DELETE");
        await loadDevis(); renderDevis();
      },
    });
    return items;
  }

  const wrap = el("div", { class: "table-wrap" });
  const table = el("table", { class: "devis" });
  table.append(el("thead", {}, el("tr", {},
    el("th", { text: "Code" }), el("th", { text: "Libellé" }),
    el("th", { class: "num", text: "Qté" }), el("th", { text: "Unité" }), el("th", { class: "num", text: "Coût unit. / forfait" }),
    el("th", { class: "num", text: "Montant" }), el("th", { class: "num", text: "En région" }), el("th", { class: "num", text: "Hors région" }), el("th", { class: "num", text: "À ventiler" }),
    el("th", { text: "Note" }), el("th", { text: "Actions", style: "text-align:right" }))));
  const tbody = el("tbody");
  table.append(tbody);
  wrap.append(table);
  app.append(wrap);

  const uniteOptions = state.referentiel.unites;
  function rowFor(n, prof) {
    const tr = el("tr", { class: n.type, "data-id": n.id });
    const hasKids = n.children && n.children.length > 0;
    const chev = el("span", {
      class: "chevron", text: hasKids ? (state.collapsed.has(n.id) ? "▸" : "▾") : " ",
      onclick: () => {
        if (!hasKids) return;
        if (state.collapsed.has(n.id)) state.collapsed.delete(n.id); else state.collapsed.add(n.id);
        renderDevis();
      },
    });
    tr.append(el("td", { class: "code" }, chev, " " + (n.chemin || n.code || "")));
    const libInput = el("input", { class: "cell", value: n.libelle, style: "min-width:220px" });
    libInput.addEventListener("change", () => saveLigne(n.id, { libelle: libInput.value }));
    tr.append(el("td", { style: "padding-left:" + prof * 16 + "px" }, libInput));

    const qte = el("input", { class: "cell num", value: n.quantite ?? "", style: "width:70px" });
    qte.addEventListener("change", () => saveLigne(n.id, { quantite: parseNum(qte.value) }));
    const unite = el("select", { class: "cell", style: "min-width:90px" });
    for (const u of uniteOptions) unite.append(el("option", { value: u, text: u, selected: u === n.unite }));
    unite.addEventListener("change", () => saveLigne(n.id, { unite: unite.value }));
    const pu = el("input", { class: "cell num", value: n.cout_unitaire ?? "", style: "width:100px" });
    pu.addEventListener("change", () => saveLigne(n.id, { cout_unitaire: parseNum(pu.value) }));
    const forfait = el("input", { class: "cell num", value: n.montant_forfait ?? "", style: "width:110px" });
    forfait.addEventListener("change", () => saveLigne(n.id, { montant_forfait: parseNum(forfait.value) }));

    let mcls = "montant " + (n.statut_montant || "calcule");
    if (n.technicien && ((n.tech_info && n.tech_info.avertissements || []).length || n.technicien.hypothese_manuelle)) mcls += " hyp";
    const montantTd = el("td", { class: mcls, text: fmt(n.montant) });
    if (n.technicien && n.tech_info) montantTd.title = (n.tech_info.avertissements || []).join("\n");

    tr.append(
      el("td", { class: "num" }, qte),
      el("td", {}, unite),
      el("td", { class: "num" }, (n.montant_forfait != null && !hasKids) ? forfait : pu),
      montantTd,
      el("td", { class: "num", text: n.en_region ? fmt(n.en_region) : "—" }),
      el("td", { class: "num", text: n.hors_region ? fmt(n.hors_region) : "—" }),
      el("td", { class: "num", style: n.a_ventiler ? "color:var(--hyp)" : "", text: n.a_ventiler ? fmt(n.a_ventiler) : "—" }),
    );
    const note = el("input", { class: "cell", value: n.note, style: "min-width:120px" });
    note.addEventListener("change", () => saveLigne(n.id, { note: note.value }));
    tr.append(el("td", {}, note));
    tr.append(el("td", { class: "actions-cell" },
      el("button", { class: "menu-btn", text: "⋯", title: "Actions de la ligne", onclick: (e) => { e.stopPropagation(); openMenu(e.currentTarget, menuItems(n)); } })));
    return tr;
  }

  function renderRows(nodes, prof) {
    for (const n of nodes) {
      const tr = rowFor(n, prof);
      tbody.append(tr);
      if (n.children && n.children.length) renderRows(n.children, prof + 1);
    }
  }
  renderRows(d.arbre, 0);

  function applyVisibility(nodes, visible = true) {
    for (const n of nodes) {
      const tr = tbody.querySelector(`tr[data-id="${n.id}"]`);
      if (!tr) continue;
      const parentHidden = parentMap[n.id] ? !isVisible(parentMap[n.id]) : !visible;
      const recapoHide = state.recapitulatif && n.type !== "poste";
      const depthHide = !state.allExpanded && depthMap[n.id] > 1;
      const selfHidden = parentHidden || state.collapsed.has(n.id) || recapoHide || depthHide;
      tr.style.display = selfHidden ? "none" : "";
      if (n.children && n.children.length) applyVisibility(n.children, !selfHidden);
    }
    function isVisible(id) {
      const tr = tbody.querySelector(`tr[data-id="${id}"]`);
      return tr && tr.style.display !== "none";
    }
  }
  applyVisibility(d.arbre);
}

function modalNouvelleLigne(parent, type) {
  const label = { poste: "un grand poste", rubrique: "une rubrique", ligne: "une ligne budgétaire" }[type];
  openModal(`Ajouter ${label}`, (content, actions, close) => {
    const code = el("input", { style: "width:80px", placeholder: type === "poste" ? "N°" : "" });
    const lib = el("input", { style: "width:100%" });
    content.append(el("div", { class: "field" }, el("label", { text: "Code" }), code));
    content.append(el("div", { class: "field" }, el("label", { text: "Intitulé" }), lib));
    actions.append(el("button", { class: "secondary", text: "Annuler", onclick: close }));
    actions.append(el("button", {
      class: "primary", text: "Ajouter",
      onclick: async () => {
        await api(`/api/films/${state.filmId}/lignes`, "POST", { parent_id: parent ? parent.id : null, type, code: code.value, libelle: lib.value });
        close(); await loadDevis(); renderDevis();
      },
    }));
  });
}

function modalSousDetail(parent) {
  const aDejaEnfants = parent.children && parent.children.length > 0;
  const forfait = parent.montant_forfait;
  openModal(`Ajouter un sous-détail sous « ${parent.libelle} »`, (content, actions, close) => {
    let reprendre = null;
    if (forfait != null && !aDejaEnfants) {
      const box = el("div", { class: "info-box" });
      box.append(el("p", { style: "margin:0 0 6px", text: `Cette ligne contient une estimation forfaitaire de ${fmt(forfait)}. Que souhaitez-vous en faire ?` }));
      const r1 = el("input", { type: "radio", name: "rep" + parent.id, checked: true });
      const r2 = el("input", { type: "radio", name: "rep" + parent.id });
      box.append(el("label", { style: "display:block" }, r1, ` Reprendre les ${fmt(forfait)} comme premier sous-détail (aucun double comptage)`));
      box.append(el("label", { style: "display:block" }, r2, " Remplacer l’estimation par les sous-détails saisis"));
      content.append(box);
      r1.addEventListener("change", () => (reprendre = true));
      r2.addEventListener("change", () => (reprendre = false));
      reprendre = true;
    }
    const lib = el("input", { style: "width:100%", placeholder: "Intitulé (ex. Corps caméra)" });
    const qte = el("input", { class: "num", style: "width:90px" });
    const unite = el("select");
    for (const u of state.referentiel.unites) unite.append(el("option", { value: u, text: u, selected: u === "jour" }));
    const pu = el("input", { class: "num", style: "width:110px", placeholder: "Coût unitaire €" });
    const forf = el("input", { class: "num", style: "width:110px", placeholder: "ou montant forfait €" });
    const ht = el("input", { type: "checkbox", checked: true });
    content.append(el("div", { class: "field" }, el("label", { text: "Intitulé" }), lib));
    content.append(el("div", { style: "display:flex;gap:10px;align-items:end" },
      el("div", { class: "field" }, el("label", { text: "Quantité" }), qte),
      el("div", { class: "field" }, el("label", { text: "Unité" }), unite),
      el("div", { class: "field" }, el("label", { text: "Coût unitaire (€)" }), pu),
      el("div", { class: "field" }, el("label", { text: "Forfait (€)" }), forf)));
    content.append(el("div", { class: "field" }, el("label", {}, ht, " Base HT (achats / prestations)")));
    content.append(el("p", { class: "hint", text: "Quantité × coût unitaire, ou forfait. Le total de la ligne parent suivra automatiquement ses sous-détails." }));
    actions.append(el("button", { class: "secondary", text: "Annuler", onclick: close }));
    actions.append(el("button", {
      class: "primary", text: "Ajouter le sous-détail",
      onclick: async () => {
        if (!lib.value.trim()) { alert("Saisissez un intitulé."); return; }
        const body = { sous_detail: true, parent_id: parent.id, libelle: lib.value, quantite: parseNum(qte.value), unite: unite.value, cout_unitaire: parseNum(pu.value), montant_forfait: parseNum(forf.value), ht: ht.checked, reprendre };
        try { await api(`/api/films/${state.filmId}/lignes`, "POST", body); }
        catch (e) { alert(e.message); return; }
        close(); await loadDevis(); renderDevis();
      },
    }));
  });
}

function modalDeplacer(n) {
  const d = state.devis;
  const options = [];
  function subtreeHas(node, id2) { if (node.id === id2) return true; return (node.children || []).some((c) => subtreeHas(c, id2)); }
  (function walk(nodes, prof) {
    for (const x of nodes) {
      if (x.id !== n.id && !subtreeHas(n, x.id)) options.push({ id: x.id, label: "　".repeat(prof) + (x.chemin || x.code) + " — " + x.libelle });
      if (x.children) walk(x.children, prof + 1);
    }
  })(d.arbre, 0);
  openModal(`Déplacer « ${n.libelle} » vers…`, (content, actions, close) => {
    const sel = el("select", { style: "width:100%" });
    for (const o of options) sel.append(el("option", { value: o.id, text: o.label }));
    content.append(el("div", { class: "field" }, el("label", { text: "Nouvelle position (poste / rubrique / ligne)" }), sel));
    actions.append(el("button", { class: "secondary", text: "Annuler", onclick: close }));
    actions.append(el("button", {
      class: "primary", text: "Déplacer",
      onclick: async () => {
        await api(`/api/lignes/${n.id}/deplacer`, "POST", { parent_id: sel.value });
        close(); await loadDevis(); renderDevis();
      },
    }));
  });
}

function modalVentiler(n) {
  openModal(`Ventiler « ${n.libelle} » (${fmt(n.montant)})`, (content, actions, close) => {
    const en = el("input", { class: "num", style: "width:130px", value: n.en_region ? fmtPlain(n.en_region) : "" });
    const hors = el("input", { class: "num", style: "width:130px", value: n.hors_region ? fmtPlain(n.hors_region) : "" });
    content.append(el("p", { class: "hint", text: "Saisissez le montant en région ; le hors région se calcule (ou saisissez les deux). Le reliquat reste « à ventiler »." }));
    content.append(el("div", { style: "display:flex;gap:14px" },
      el("div", { class: "field" }, el("label", { text: "En région (€)" }), en),
      el("div", { class: "field" }, el("label", { text: "Hors région (€)" }), hors)));
    actions.append(el("button", { class: "secondary", text: "Annuler", onclick: close }));
    actions.append(el("button", {
      class: "primary", text: "Enregistrer la ventilation",
      onclick: async () => {
        try {
          await api(`/api/lignes/${n.id}/ventilation`, "POST", { mode: "partiel", en_region: parseNum(en.value), hors_region: parseNum(hors.value) });
        } catch (e) { alert(e.message); return; }
        close(); await loadDevis(); renderDevis();
      },
    }));
  });
}

/* ---------------- technicien ---------------- */

function fonctionsDuFilm() {
  const film = state.devis.film;
  const conv = state.referentiel.conventions.find((c) => c.id === film.convention_id);
  const grille = conv && conv.grilles.find((g) => g.id === film.grille_id);
  if (grille) return { fonctions: grille.fonctions, grille, conv };
  if (conv && conv.grilles.length) return { fonctions: conv.grilles[0].fonctions, grille: conv.grilles[0], conv };
  return { fonctions: [], grille: null, conv };
}

function modalTechnicien(parentId, techExistant = null) {
  const { fonctions, grille, conv } = fonctionsDuFilm();
  const film = state.devis.film;
  openModal(techExistant ? "Ouvrir l’engagement" : "Ajouter un technicien", (content, actions, close) => {
    const recherche = el("input", { style: "width:100%", placeholder: "Rechercher une fonction (ex. Chef opérateur du son)…", list: "liste-fonctions" });
    const datalist = el("datalist", { id: "liste-fonctions" });
    for (const f of fonctions) datalist.append(el("option", { value: f.nom }));
    content.append(el("div", { class: "field" }, el("label", { text: "Fonction (barème du film)" }), recherche, datalist));

    const nom = el("input", { style: "width:100%", placeholder: "Nom de la personne (facultatif en préparation)", value: techExistant ? techExistant.nom : "" });
    content.append(el("div", { class: "field" }, el("label", { text: "Nom (facultatif)" }), nom));

    const infoBox = el("div", { class: "info-box" });
    const salaire = el("input", { class: "num", style: "width:130px" });
    const uniteSel = el("select");
    for (const u of state.referentiel.unites) uniteSel.append(el("option", { value: u, text: u }));
    const hypMan = el("input", { type: "checkbox" });
    const warnBox = el("div");
    content.append(infoBox);
    content.append(el("div", { class: "field" }, el("label", { text: "Salaire retenu (brut)" }), salaire, " / ", uniteSel));
    content.append(warnBox);

    const phasesTable = el("table", { class: "mini" });
    phasesTable.append(el("tr", {}, el("th", { text: "Phase" }), el("th", { class: "num", text: "Quantité" }), el("th", { text: "Unité" })));
    const phaseInputs = {};
    for (const ph of state.referentiel.phases) {
      const q = el("input", { class: "num", style: "width:80px" });
      const u = el("select", { class: "cell" });
      for (const uu of state.referentiel.unites) u.append(el("option", { value: uu, text: uu }));
      phaseInputs[ph] = { q, u };
      phasesTable.append(el("tr", {}, el("td", { text: ph }), el("td", { class: "num" }, q), el("td", {}, u)));
    }
    content.append(el("h2", { text: "Périodes de travail" }), phasesTable);
    content.append(el("div", { class: "field" }, el("label", {}, hypMan, " Hypothèse manuelle : unité différente du barème, sans division automatique (clairement identifiée)")));
    const preview = el("div", { class: "preview-tech" });
    content.append(preview);

    let fonc = techExistant ? fonctions.find((f) => f.id === techExistant.fonction_id) : null;
    if (techExistant) {
      recherche.value = fonc ? fonc.nom : "";
      salaire.value = techExistant.salaire;
      uniteSel.value = techExistant.unite;
      hypMan.checked = !!techExistant.hypothese_manuelle;
    }

    function refresh() {
      fonc = fonctions.find((f) => f.nom === recherche.value) || null;
      infoBox.innerHTML = "";
      warnBox.innerHTML = "";
      if (!fonc) { preview.innerHTML = ""; return; }
      if (salaire.value === "") salaire.value = fonc.minimum;
      if (!hypMan.checked) { uniteSel.value = fonc.unite; for (const ph of state.referentiel.phases) phaseInputs[ph].u.value = fonc.unite; }
      infoBox.append(el("p", { style: "margin:0" },
        el("strong", { text: `${fonc.nom} — minimum ${fmt(fonc.minimum)} / ${fonc.unite}` }),
        " · ", el("span", { class: "badge " + (fonc.statut === "verifie" ? "verifie" : "demo"), text: fonc.statut === "verifie" ? "VÉRIFIÉ" : "DÉMONSTRATION" }),
        ` · source : ${fonc.source || "non renseignée"}`,
        grille ? ` · ${conv.nom} — ${grille.version} (effet ${grille.date_effet})` : "",
        ` · date de référence du film : ${film.date_ref_baremes}`));
      const s = parseNum(salaire.value);
      if (s != null && s < fonc.minimum) {
        warnBox.append(el("div", { class: "warn-box", text: `⚠ Le salaire saisi (${fmt(s)}) est inférieur au minimum applicable (${fmt(fonc.minimum)} / ${fonc.unite}). Le minimum reste visible pour comparaison ; l’écart sera signalé dans le devis.` }));
      }
      if (fonc.unite !== "jour" && !hypMan.checked) {
        warnBox.append(el("div", { class: "info-box", text: `Le barème est en « ${fonc.unite} » : aucune division automatique (ex. semaine → jours) n’est appliquée. Saisissez les quantités en « ${fonc.unite} », ou cochez « hypothèse manuelle » pour une autre unité, clairement identifiée.` }));
      }
      const taux = film.taux_charges;
      let brut = 0;
      for (const ph of state.referentiel.phases) brut += (parseNum(phaseInputs[ph].q.value) || 0) * (s || 0);
      const charges = brut * taux;
      preview.innerHTML = "";
      preview.append(el("div", { class: "ligne" }, el("span", { text: "Brut total" }), el("strong", { text: fmt(brut) })));
      preview.append(el("div", { class: "ligne" }, el("span", { text: `Charges employeur estimées (${(taux * 100).toFixed(0)} %)` }), el("strong", { text: fmt(charges) })));
      preview.append(el("div", { class: "ligne total" }, el("span", { text: "Coût employeur total" }), el("span", { text: fmt(brut + charges) })));
    }
    recherche.addEventListener("input", refresh);
    salaire.addEventListener("input", refresh);
    hypMan.addEventListener("change", refresh);
    for (const ph of state.referentiel.phases) {
      phaseInputs[ph].q.addEventListener("input", refresh);
      phaseInputs[ph].u.addEventListener("change", refresh);
    }
    if (techExistant) {
      api(`/api/techniciens/${techExistant.id}`).then((fiche) => {
        for (const p of fiche.phases) {
          if (phaseInputs[p.phase]) { phaseInputs[p.phase].q.value = p.quantite; phaseInputs[p.phase].u.value = p.unite; }
        }
        refresh();
      });
    }
    refresh();

    actions.append(el("button", { class: "secondary", text: "Annuler", onclick: close }));
    actions.append(el("button", {
      class: "primary", text: techExistant ? "Enregistrer les modifications" : "Valider l’engagement",
      onclick: async () => {
        if (!fonc) { alert("Choisissez une fonction dans la liste (barème du film)."); return; }
        const phases = state.referentiel.phases
          .map((ph) => ({ phase: ph, quantite: parseNum(phaseInputs[ph].q.value) || 0, unite: phaseInputs[ph].u.value }))
          .filter((p) => p.quantite > 0);
        if (!phases.length) { alert("Saisissez au moins une période de travail (préparation, tournage ou finitions)."); return; }
        const body = { fonction_id: fonc.id, nom: nom.value, salaire: parseNum(salaire.value), unite: uniteSel.value, phases, hypothese_manuelle: hypMan.checked };
        try {
          if (techExistant) await api(`/api/techniciens/${techExistant.id}`, "PUT", body);
          else { body.parent_id = parentId; await api(`/api/films/${state.filmId}/techniciens`, "POST", body); }
        } catch (e) { alert(e.message); return; }
        close(); await loadDevis(); renderDevis();
      },
    }));
  }, 760);
}

function modalOuvrirTechnicien(techId) {
  api(`/api/techniciens/${techId}`).then((fiche) => {
    openModal(`Engagement — ${fiche.fonction ? fiche.fonction.nom : ""}${fiche.technicien.nom ? " — " + fiche.technicien.nom : ""}`, (content, actions, close) => {
      const t = el("table", { class: "mini" });
      t.append(el("tr", {}, el("th", { text: "Phase" }), el("th", { class: "num", text: "Qté" }), el("th", { text: "Unité" }), el("th", { class: "num", text: "Brut" })));
      for (const p of fiche.phases) t.append(el("tr", {}, el("td", { text: p.phase }), el("td", { class: "num", text: String(p.quantite) }), el("td", { text: p.unite }), el("td", { class: "num", text: fmt(p.montant) })));
      content.append(t);
      const pv = el("div", { class: "preview-tech" });
      pv.append(el("div", { class: "ligne" }, el("span", { text: "Brut" }), el("strong", { text: fmt(fiche.brut) })));
      pv.append(el("div", { class: "ligne" }, el("span", { text: `Charges employeur (${(fiche.taux_charges * 100).toFixed(0)} %)` }), el("strong", { text: fmt(fiche.charges) })));
      pv.append(el("div", { class: "ligne total" }, el("span", { text: "Coût employeur total" }), el("span", { text: fmt(fiche.cout_employeur) })));
      content.append(pv);
      content.append(el("p", { class: "hint", text: `Barème retenu au chiffrage : minimum ${fmt(fiche.technicien.minimum_snapshot)} / ${fiche.technicien.unite} · date de référence ${fiche.technicien.date_ref_snapshot || fiche.film.date_ref_baremes}` + (fiche.fonction ? ` · minimum actuel de la fonction : ${fmt(fiche.fonction.minimum)} / ${fiche.fonction.unite}` : "") }));
      for (const w of fiche.avertissements) content.append(el("div", { class: "warn-box", text: "⚠ " + w }));
      actions.append(el("button", { class: "secondary", text: "Fermer", onclick: close }));
      actions.append(el("button", {
        class: "primary", text: "Modifier le tarif ou les durées",
        onclick: () => { close(); modalTechnicien(null, fiche.technicien); },
      }));
    }, 640);
  });
}

/* ---------------- région ---------------- */

async function renderRegion() {
  const v = await api(`/api/films/${state.filmId}/region`);
  const ref = state.referentiel;
  app.innerHTML = "";
  app.append(el("h1", { text: "Ventilation territoriale" }));
  app.append(el("p", { class: "hint", text: "Deux vues issues des mêmes dépenses : le devis général et la répartition « En région / Hors région ». Toute action ici modifie la ligne d’origine du devis — aucune copie n’est créée." }));

  const regionSel = el("select");
  for (const r of ref.regions) regionSel.append(el("option", { value: r, text: r, selected: r === v.region }));
  app.append(el("div", { class: "toolbar" },
    el("strong", { text: "Région cible :" }), regionSel,
    el("button", {
      class: "secondary", text: "Appliquer",
      onclick: async () => {
        try { await api(`/api/films/${state.filmId}`, "PUT", { region_cible: regionSel.value }); }
        catch (e) {
          if (e.data && e.data.confirmation_requise) {
            return modalConfirmerRegion(regionSel.value, async (option) => {
              await api(`/api/films/${state.filmId}`, "PUT", { region_cible: regionSel.value, option_ventilation: option });
              state.devis = null; render();
            });
          }
          alert(e.message);
        }
        state.devis = null; render();
      },
    })));

  const t = v.totaux;
  function card(val, lbl, accent) { return el("div", { class: "card" + (accent ? " accent" : "") }, el("div", { class: "v", text: val }), el("div", { class: "l", text: lbl })); }
  app.append(el("div", { class: "cards" },
    card(fmt(t.montant), "Devis général", false),
    card(fmt(t.en_region), `En région — ${v.region}`, true),
    card(fmt(t.hors_region), "Hors région", false),
    card(fmt(t.a_ventiler), "À ventiler (reliquat)", false),
    card(t.montant ? (t.en_region / t.montant * 100).toFixed(1) + " %" : "—", "Part régionale du budget", true)));
  app.append(el("p", { class: v.egalite_ok ? "ok" : "ko", text: v.egalite_ok ? `✓ Contrôle : en région + hors région + à ventiler = ${fmt(t.en_region + t.hors_region + t.a_ventiler)} = devis général (${fmt(t.montant)})` : "✗ Incohérence de ventilation détectée." }));

  app.append(el("h2", { text: "Sous-totaux par grand poste" }));
  const tp = el("table", { class: "devis" });
  tp.append(el("thead", {}, el("tr", {}, el("th", { text: "Code" }), el("th", { text: "Poste" }), el("th", { class: "num", text: "Montant" }), el("th", { class: "num", text: "En région" }), el("th", { class: "num", text: "Hors région" }), el("th", { class: "num", text: "À ventiler" }))));
  const tb = el("tbody");
  for (const p of v.par_poste) tb.append(el("tr", { class: "poste" }, el("td", { class: "code", text: p.code }), el("td", { text: p.libelle }), el("td", { class: "num", text: fmt(p.montant) }), el("td", { class: "num", text: fmt(p.en_region) }), el("td", { class: "num", text: fmt(p.hors_region) }), el("td", { class: "num", text: fmt(p.a_ventiler) })));
  tb.append(el("tr", { class: "poste" }, el("td", {}), el("td", { text: "TOTAL" }), el("td", { class: "num", text: fmt(t.montant) }), el("td", { class: "num", text: fmt(t.en_region) }), el("td", { class: "num", text: fmt(t.hors_region) }), el("td", { class: "num", text: fmt(t.a_ventiler) })));
  tp.append(tb);
  app.append(el("div", { class: "table-wrap", style: "max-height:38vh" }, tp));

  app.append(el("h2", { text: "Affectation ligne par ligne" }));
  app.append(el("p", { class: "hint", text: "« → en région » / « → hors région » bascule toute la dépense d’un côté à l’autre en un geste et modifie la ligne d’origine." }));
  const tl = el("table", { class: "devis" });
  tl.append(el("thead", {}, el("tr", {}, el("th", { text: "Code" }), el("th", { text: "Ligne" }), el("th", { class: "num", text: "Montant" }), el("th", { class: "num", text: "En région (€)" }), el("th", { class: "num", text: "Hors région (€)" }), el("th", { class: "num", text: "À ventiler" }), el("th", { text: "Bascule" }))));
  const tbl = el("tbody");
  async function setVent(l, body) {
    try {
      await api(`/api/lignes/${l.id}/ventilation`, "POST", body);
      state.devis = null;
      render();
    } catch (e) { alert(e.message); render(); }
  }
  for (const l of v.lignes) {
    const en = el("input", { class: "cell num", style: "width:110px", value: l.en_region ? fmtPlain(l.en_region) : "" });
    const hors = el("input", { class: "cell num", style: "width:110px", value: l.hors_region ? fmtPlain(l.hors_region) : "" });
    en.addEventListener("change", () => setVent(l, { mode: "partiel", en_region: parseNum(en.value), hors_region: parseNum(hors.value) }));
    hors.addEventListener("change", () => setVent(l, { mode: "partiel", en_region: parseNum(en.value), hors_region: parseNum(hors.value) }));
    tbl.append(el("tr", { class: l.type },
      el("td", { class: "code", text: l.chemin }), el("td", { text: l.libelle }),
      el("td", { class: "num", text: fmt(l.montant) }),
      el("td", { class: "num" }, en), el("td", { class: "num" }, hors),
      el("td", { class: "num", style: l.a_ventiler ? "color:var(--hyp)" : "", text: l.a_ventiler ? fmt(l.a_ventiler) : "—" }),
      el("td", {},
        el("button", { class: "small", text: "→ en région", onclick: () => setVent(l, { mode: "tout_en" }) }),
        " ",
        el("button", { class: "small", text: "→ hors région", onclick: () => setVent(l, { mode: "tout_hors" }) }))));
  }
  tl.append(tbl);
  app.append(el("div", { class: "table-wrap" }, tl));
}

/* ---------------- barèmes ---------------- */

function renderBaremes() {
  const ref = state.referentiel;
  app.innerHTML = "";
  app.append(el("h1", { text: "Barèmes — conventions, grilles, fonctions" }));
  app.append(el("div", { class: "banner", text: "Référentiel commun à tous les films, modifiable ici sans toucher au code. Chaque montant porte sa source et son statut : « VÉRIFIÉ » (source indiquée) ou « DÉMONSTRATION » (montant fictif). Plusieurs versions datées d’une grille peuvent coexister ; chaque film choisit sa version et sa date de référence. En l’absence de tarif, la saisie manuelle reste possible dans le devis et son origine y est visible." }));
  app.append(el("div", { class: "toolbar" },
    el("button", { class: "primary", text: "+ Nouvelle convention", onclick: () => modalConvention() })));

  for (const c of ref.conventions) {
    const sec = el("div", { class: "bareme-section" });
    sec.append(el("div", { style: "display:flex;align-items:center;gap:10px;flex-wrap:wrap" },
      el("h2", { style: "margin:0", text: c.nom }),
      el("button", { class: "small", text: "Renommer", onclick: () => modalConvention(c) }),
      el("button", { class: "small", text: "+ Nouvelle version de grille", onclick: () => modalGrille(c) })));
    if (c.description) sec.append(el("p", { class: "hint", text: c.description }));
    for (const g of c.grilles) {
      const gbox = el("div", { style: "margin:10px 0 6px;border-left:3px solid var(--jaune);padding-left:12px" });
      gbox.append(el("div", { style: "display:flex;gap:10px;align-items:center;flex-wrap:wrap" },
        el("strong", { text: `${g.version} — effet ${g.date_effet}` }),
        el("span", { class: "badge " + (g.statut === "verifie" ? "verifie" : "demo"), text: g.statut === "verifie" ? "VÉRIFIÉ" : "DÉMONSTRATION" }),
        el("span", { class: "hint", text: "source : " + (g.source || "non renseignée") }),
        el("button", { class: "small", text: "Modifier la version", onclick: () => modalGrille(c, g) }),
        el("button", { class: "small", text: "+ Ajouter une fonction", onclick: () => modalFonction(c, g) })));
      const t = el("table");
      t.append(el("tr", {}, el("th", { text: "Fonction" }), el("th", { class: "num", text: "Minimum" }), el("th", { text: "Unité" }), el("th", { text: "Validité" }), el("th", { text: "Source" }), el("th", { text: "Statut" }), el("th", { text: "" })));
      for (const f of g.fonctions) {
        t.append(el("tr", {},
          el("td", { text: f.nom }),
          el("td", { class: "num", text: fmt(f.minimum) }),
          el("td", { text: f.unite }),
          el("td", { text: `${f.valide_du || "—"} → ${f.valide_au || "—"}` }),
          el("td", { class: "hint", text: f.source || "—" }),
          el("td", {}, el("span", { class: "badge " + (f.statut === "verifie" ? "verifie" : "demo"), text: f.statut === "verifie" ? "VÉRIFIÉ" : "DÉMONSTRATION" })),
          el("td", {}, el("button", { class: "small", text: "Modifier le tarif", onclick: () => modalFonction(c, g, f) }))));
      }
      gbox.append(t);
      sec.append(gbox);
    }
    app.append(sec);
  }
}

function modalConvention(conv) {
  openModal(conv ? "Modifier la convention" : "Nouvelle convention", (content, actions, close) => {
    const nom = el("input", { style: "width:100%", value: conv ? conv.nom : "" });
    const desc = el("input", { style: "width:100%", value: conv ? conv.description : "" });
    content.append(el("div", { class: "field" }, el("label", { text: "Nom" }), nom));
    content.append(el("div", { class: "field" }, el("label", { text: "Description" }), desc));
    actions.append(el("button", { class: "secondary", text: "Annuler", onclick: close }));
    actions.append(el("button", {
      class: "primary", text: conv ? "Enregistrer" : "Créer",
      onclick: async () => {
        if (conv) await api(`/api/conventions/${conv.id}`, "PUT", { nom: nom.value, description: desc.value });
        else await api("/api/conventions", "POST", { nom: nom.value, description: desc.value });
        close(); await loadReferentiel(); render();
      },
    }));
  });
}

function modalGrille(conv, grille) {
  openModal(grille ? `Modifier la version ${grille.version}` : "Nouvelle version de grille", (content, actions, close) => {
    const version = el("input", { style: "width:100%", value: grille ? grille.version : "" });
    const dateEffet = el("input", { type: "date", value: grille ? grille.date_effet : new Date().toISOString().slice(0, 10) });
    const source = el("input", { style: "width:100%", value: grille ? grille.source : "", placeholder: "Référence de la source des montants" });
    const statut = el("select", {},
      el("option", { value: "demonstration", text: "DÉMONSTRATION (montants fictifs)", selected: !grille || grille.statut === "demonstration" }),
      el("option", { value: "verifie", text: "VÉRIFIÉ (source renseignée)", selected: grille && grille.statut === "verifie" }));
    content.append(el("div", { class: "field" }, el("label", { text: "Version" }), version));
    content.append(el("div", { class: "field" }, el("label", { text: "Date d’effet" }), dateEffet));
    content.append(el("div", { class: "field" }, el("label", { text: "Source / référence" }), source));
    content.append(el("div", { class: "field" }, el("label", { text: "Statut des montants" }), statut));
    actions.append(el("button", { class: "secondary", text: "Annuler", onclick: close }));
    actions.append(el("button", {
      class: "primary", text: grille ? "Enregistrer" : "Créer la version",
      onclick: async () => {
        if (grille) await api(`/api/grilles/${grille.id}`, "PUT", { version: version.value, date_effet: dateEffet.value, source: source.value, statut: statut.value });
        else await api(`/api/conventions/${conv.id}/grilles`, "POST", { version: version.value, date_effet: dateEffet.value, source: source.value, statut: statut.value });
        close(); await loadReferentiel(); render();
      },
    }));
  });
}

function modalFonction(conv, grille, fonction) {
  openModal(fonction ? `Modifier « ${fonction.nom} »` : "Nouvelle fonction", (content, actions, close) => {
    const nom = el("input", { style: "width:100%", value: fonction ? fonction.nom : "" });
    const min = el("input", { class: "num", style: "width:140px", value: fonction ? fmtPlain(fonction.minimum) : "" });
    const unite = el("select");
    for (const u of state.referentiel.unites) unite.append(el("option", { value: u, text: u, selected: fonction ? fonction.unite === u : u === "jour" }));
    const du = el("input", { type: "date", value: fonction ? fonction.valide_du : "" });
    const au = el("input", { type: "date", value: fonction ? fonction.valide_au : "" });
    const source = el("input", { style: "width:100%", value: fonction ? fonction.source : "", placeholder: "Référence / source du montant" });
    const statut = el("select", {},
      el("option", { value: "demonstration", text: "DÉMONSTRATION", selected: !fonction || fonction.statut === "demonstration" }),
      el("option", { value: "verifie", text: "VÉRIFIÉ", selected: fonction && fonction.statut === "verifie" }));
    content.append(el("div", { class: "field" }, el("label", { text: "Fonction" }), nom));
    content.append(el("div", { style: "display:flex;gap:12px" },
      el("div", { class: "field" }, el("label", { text: "Minimum (€)" }), min),
      el("div", { class: "field" }, el("label", { text: "Unité de rémunération" }), unite)));
    content.append(el("div", { style: "display:flex;gap:12px" },
      el("div", { class: "field" }, el("label", { text: "Valide du" }), du),
      el("div", { class: "field" }, el("label", { text: "Valide au" }), au)));
    content.append(el("div", { class: "field" }, el("label", { text: "Source / référence" }), source));
    content.append(el("div", { class: "field" }, el("label", { text: "Statut" }), statut));
    actions.append(el("button", { class: "secondary", text: "Annuler", onclick: close }));
    actions.append(el("button", {
      class: "primary", text: fonction ? "Enregistrer le tarif" : "Ajouter la fonction",
      onclick: async () => {
        const m = parseNum(min.value);
        if (!nom.value.trim() || m == null) { alert("Fonction et minimum requis."); return; }
        const body = { nom: nom.value, minimum: m, unite: unite.value, valide_du: du.value, valide_au: au.value, source: source.value, statut: statut.value };
        if (fonction) await api(`/api/fonctions/${fonction.id}`, "PUT", body);
        else await api(`/api/grilles/${grille.id}/fonctions`, "POST", body);
        close(); await loadReferentiel(); render();
      },
    }));
  }, 640);
}

/* ---------------- barre d'actions ---------------- */

document.getElementById("btn-excel").addEventListener("click", () => {
  if (state.filmId) window.location = `/api/films/${state.filmId}/export.xlsx`;
});
document.getElementById("btn-print").addEventListener("click", () => {
  if (state.filmId) window.open(`/print/${state.filmId}`, "_blank");
});
document.getElementById("btn-backup").addEventListener("click", () => {
  if (state.filmId) window.location = `/api/films/${state.filmId}/backup`;
});
document.getElementById("btn-restore").addEventListener("click", () => {
  document.getElementById("file-restore").click();
});
document.getElementById("file-restore").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const text = await f.text();
  try {
    const r = await api("/api/restaurer", "POST", JSON.parse(text));
    alert("Projet restauré (copie « (restauré) » créée).");
    selectFilm(r.id, "devis");
  } catch (err) { alert(err.message); }
  e.target.value = "";
});

render();
