"""Mizan — Interface utilisateur web (MVP Phase 2 Sprint 5).

Application Streamlit qui expose le pipeline complet en mode no-CLI :
  1. Identification client + paramètres
  2. Upload des fichiers d'entrée (GL, référentiel)
  3. Exécution (parsing, lettrage, calcul, anomalies)
  4. Dashboard interactif + téléchargements

Lancement :
    cd mizan && streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import calendar
import sys
import tempfile
import time
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parser import parser_gl_liste                                       # noqa: E402
from lettrage import construire_lettrages                                # noqa: E402
from compute import (calculer_toutes_lignes,                             # noqa: E402
                     charger_base_fournisseurs)
from output import generer_simpl, generer_suivi_global                   # noqa: E402
from quality import detecter_doublons, annoter_lignes, TypeAnomalie      # noqa: E402
from models import StatutFacture                                          # noqa: E402


# ─── Charte Nextor / Mizan ────────────────────────────────────────────────

NAVY      = "#2B4C6F"
NAVY_DEEP = "#1E3A5F"
NAVY_INK  = "#142A44"
TEAL      = "#4ECDC4"
TEAL_DEEP = "#1E8C84"
GREEN     = "#2E864E"
RED       = "#EF4444"
ORANGE    = "#F59E0B"
PAPER     = "#F8FAFC"
GREY      = "#64748B"


# ─── Config page ──────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Mizan — Automatisation DDP",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─── Authentification par passphrase (Streamlit Cloud) ────────────────────

def _gate_password() -> None:
    """Bloque l'accès à l'app tant que la passphrase n'est pas saisie.

    La passphrase est lue depuis `st.secrets["auth"]["passphrase"]`. Si la
    clé est absente (dev local sans secrets), l'app est ouverte.
    """
    try:
        expected = st.secrets["auth"]["passphrase"]
    except (KeyError, FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return  # pas de secret configuré → mode ouvert (dev local)

    if st.session_state.get("_auth_ok"):
        return

    st.markdown("### 🔐 Accès Mizan")
    pwd = st.text_input("Passphrase", type="password", key="_auth_input")
    if st.button("Entrer", type="primary"):
        if pwd == expected:
            st.session_state["_auth_ok"] = True
            st.rerun()
        else:
            st.error("Passphrase incorrecte.")
    st.stop()


_gate_password()


# ─── CSS personnalisé (charte Nextor) ─────────────────────────────────────

LINE    = "#E2E8F0"
PAPER_2 = "#EEF3F8"

st.markdown(f"""
<style>
    /* ─── Base ─────────────────────────────────────────────── */
    .stApp {{ background: {PAPER}; }}
    html, body, [class*="css"] {{
        font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
        -webkit-font-smoothing: antialiased;
    }}
    .main .block-container {{
        max-width: 1180px;
        padding-top: 2.2rem;
        padding-bottom: 4rem;
    }}
    .main h1, .main h2, .main h3 {{ color: {NAVY_INK}; letter-spacing: -0.01em; }}
    .main h3 {{
        font-size: 1.15rem;
        font-weight: 700;
        margin-top: 2.2rem;
        margin-bottom: 0.8rem;
        padding-bottom: 0.4rem;
        border-bottom: 1px solid {LINE};
    }}
    .main h4 {{ color: {NAVY_DEEP}; font-weight: 600; margin-top: 1.2rem; }}
    p, li, .main .stMarkdown {{ color: #334155; line-height: 1.6; }}

    /* ─── Boutons ──────────────────────────────────────────── */
    .stButton>button {{
        background: {NAVY};
        border: none;
        border-radius: 8px;
        padding: 0.55rem 1.6rem;
        font-weight: 600;
        transition: all 0.15s ease;
        box-shadow: 0 1px 2px rgba(20,42,68,0.10);
    }}
    /* Texte toujours blanc (le libellé est dans un <p> interne) */
    .stButton>button, .stButton>button p, .stButton>button div {{
        color: #FFFFFF !important;
    }}
    .stButton>button:hover {{
        background: {TEAL_DEEP};
        transform: translateY(-1px);
        box-shadow: 0 5px 14px rgba(30,140,132,0.25);
    }}
    .stButton>button:disabled {{
        background: #AEBDCE;
        box-shadow: none;
        transform: none;
        cursor: not-allowed;
    }}
    .stButton>button:disabled, .stButton>button:disabled p {{
        color: #F1F5F9 !important;
    }}
    .stDownloadButton>button, .stDownloadButton>button p, .stDownloadButton>button div {{
        color: #FFFFFF !important;
    }}
    .stDownloadButton>button {{
        background: {TEAL_DEEP};
        border: none;
        border-radius: 8px;
        padding: 0.55rem 1.6rem;
        font-weight: 600;
        transition: all 0.15s ease;
        box-shadow: 0 1px 2px rgba(20,42,68,0.10);
    }}
    .stDownloadButton>button:hover {{
        background: {NAVY};
        transform: translateY(-1px);
        box-shadow: 0 5px 14px rgba(43,76,111,0.25);
    }}

    /* ─── Cartes de métriques ──────────────────────────────── */
    [data-testid="stMetric"] {{
        background: white;
        border: 1px solid {LINE};
        border-radius: 12px;
        padding: 1rem 1.2rem;
        box-shadow: 0 1px 3px rgba(20,42,68,0.05);
        transition: box-shadow 0.15s ease;
    }}
    [data-testid="stMetric"]:hover {{
        box-shadow: 0 4px 12px rgba(20,42,68,0.10);
    }}
    [data-testid="stMetricLabel"] {{
        color: {TEAL_DEEP};
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        font-size: 11px;
    }}
    [data-testid="stMetricValue"] {{
        color: {NAVY_INK};
        font-weight: 700;
        font-size: 1.7rem;
    }}

    /* ─── Onglets ──────────────────────────────────────────── */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {{
        gap: 6px;
        border-bottom: 1px solid {LINE};
    }}
    [data-testid="stTabs"] [data-baseweb="tab"] {{
        font-weight: 600;
        color: {GREY};
        padding: 0.5rem 1rem;
        border-radius: 8px 8px 0 0;
    }}
    [data-testid="stTabs"] [data-baseweb="tab"]:hover {{
        background: {PAPER_2};
        color: {NAVY_INK};
    }}
    [data-testid="stTabs"] [aria-selected="true"] {{
        color: {NAVY_INK};
        background: {PAPER_2};
    }}

    /* ─── Zone d'upload ────────────────────────────────────── */
    [data-testid="stFileUploader"] section {{
        border: 1.5px dashed #C2D2E2;
        border-radius: 12px;
        background: white;
        transition: border-color 0.15s ease, background 0.15s ease;
    }}
    [data-testid="stFileUploader"] section:hover {{
        border-color: {TEAL};
        background: #FAFEFE;
    }}

    /* ─── Tableaux & inputs ────────────────────────────────── */
    [data-testid="stDataFrame"] {{
        border: 1px solid {LINE};
        border-radius: 10px;
        overflow: hidden;
    }}
    [data-testid="stExpander"] {{
        border: 1px solid {LINE};
        border-radius: 10px;
    }}
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div {{
        border-radius: 8px;
    }}

    /* ─── Barre latérale ───────────────────────────────────── */
    div[data-testid="stSidebar"] {{
        background: white;
        border-right: 1px solid {LINE};
    }}
    div[data-testid="stSidebar"] label,
    div[data-testid="stSidebar"] .stMarkdown {{
        color: {NAVY_INK} !important;
    }}
    div[data-testid="stSidebar"] h3 {{
        font-size: 12px !important;
        text-transform: uppercase;
        letter-spacing: 2px;
        color: {TEAL_DEEP} !important;
        margin-top: 1.5rem;
        border: none;
    }}
    div[data-testid="stSidebar"] hr {{
        border-color: {LINE} !important;
        margin: 1rem 0;
    }}

    /* ─── Hero ─────────────────────────────────────────────── */
    .eyebrow {{
        color: {TEAL_DEEP};
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 3px;
        text-transform: uppercase;
        margin-bottom: 0;
    }}
    .hero-title {{
        color: {NAVY_INK};
        font-size: 38px;
        font-weight: 800;
        line-height: 1.1;
        margin-top: 0.3rem;
        margin-bottom: 0.6rem;
        letter-spacing: -0.02em;
    }}
    .hero-subtitle {{
        color: {GREY};
        font-size: 15px;
        margin-bottom: 2.2rem;
        max-width: 640px;
    }}
</style>
""", unsafe_allow_html=True)


# ─── État de session ──────────────────────────────────────────────────────

def init_state():
    defaults = {
        "demo_mode": False,
        "lignes": None,
        "anomalies": None,
        "base_fournisseurs": None,
        "lettrages": None,
        "ecritures": None,
        "inconnues": None,
        "hors_base": None,
        "ocr_resultats": None,
        "suivi_path": None,
        "simpl_path": None,
        "client": "UEMA",
        "trimestre": "1T26",
        "n_if": "14367938",
        "raison_sociale": "STE UEMA INDUSTRY",
        # CA N-1 : non affiché dans l'app, mais transmis à l'en-tête du Simpl.
        "ca_n1": 23369748.49,
        "activite": 1,
        "delai_defaut": 60,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


init_state()


# ─── Sidebar — identification client ──────────────────────────────────────

with st.sidebar:
    # Logo Nextor — bundle local dans app/assets/
    logo_path = ROOT / "app" / "assets" / "logo_navy.png"
    if logo_path.exists():
        st.image(str(logo_path), width=200)
    else:
        st.markdown(
            f"<div style='padding:1rem 0; font-size:32px; font-weight:bold; color:{NAVY_INK};'>Mizan</div>"
            f"<div style='font-size:11px; color:{GREY};'>l'équilibre des paiements</div>",
            unsafe_allow_html=True,
        )
    st.markdown(
        f"<div style='font-size:11px; color:{GREY}; margin-top:0.5rem;'>"
        f"<i>l'équilibre des paiements</i></div>",
        unsafe_allow_html=True,
    )

    st.markdown("### Identification client")

    st.session_state.client = st.text_input("Code client", st.session_state.client)
    st.session_state.trimestre = st.selectbox(
        "Trimestre",
        ["1T26", "2T26", "3T26", "4T26", "1T27"],
        index=0,
    )

    st.markdown("---")
    st.markdown("### Métadonnées DGI")
    st.session_state.n_if = st.text_input("N° IF du client", st.session_state.n_if)
    st.session_state.raison_sociale = st.text_input("Raison sociale", st.session_state.raison_sociale)
    # Chiffre d'affaires N-1 : champ retiré de l'interface (rempli côté Simpl).
    st.session_state.activite = st.number_input(
        "Code activité",
        min_value=0,
        value=int(st.session_state.activite),
    )

    st.markdown("---")
    st.session_state.delai_defaut = st.slider(
        "Délai par défaut (jours)",
        min_value=30, max_value=120,
        value=int(st.session_state.delai_defaut),
    )

    # ─── Mode démo (désactivé pour le moment) ─────────────────────────
    # st.markdown("---")
    # st.markdown("### Mode démo")
    # if st.button("🎬  Charger l'exemple UEMA 1T26", use_container_width=True):
    #     st.session_state.demo_mode = True
    #     st.session_state.client = "UEMA"
    #     st.session_state.trimestre = "1T26"
    #     st.session_state.n_if = "14367938"
    #     st.session_state.raison_sociale = "STE UEMA INDUSTRY"
    #     st.session_state.ca_n1 = 23369748.49
    #     st.session_state.activite = 1
    #     st.success("✓ Exemple UEMA chargé — clique sur **Lancer Mizan**")
    #     st.rerun()
    # if st.session_state.demo_mode:
    #     st.caption("Mode démo actif — les fichiers samples seront utilisés")
    #     if st.button("✕ Sortir du mode démo", use_container_width=True):
    #         st.session_state.demo_mode = False
    #         st.rerun()

    st.markdown("---")
    st.markdown(
        f"<div style='font-size:11px; color:{GREY}; padding-top:1rem; text-align:center;'>"
        f"<b style='color:{NAVY_INK};'>NEXTOR</b><br>"
        f"<a href='https://nextor-it.com' style='color:{TEAL_DEEP}; text-decoration:none;'>nextor-it.com</a>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ─── Hero ─────────────────────────────────────────────────────────────────

st.markdown('<p class="eyebrow">Mizan · Phase 2 · MVP</p>', unsafe_allow_html=True)
st.markdown('<h1 class="hero-title">Déclaration des Délais de Paiement</h1>', unsafe_allow_html=True)
st.markdown(
    '<p class="hero-subtitle">Du Grand Livre Sage au formulaire Simpl-TVA — '
    'en quelques secondes, sans saisie client.</p>',
    unsafe_allow_html=True,
)


# ─── Étape 1 — Uploads ────────────────────────────────────────────────────

st.markdown("### 1.  Fichiers d'entrée")

col1, col2 = st.columns(2)
with col1:
    f_gl = st.file_uploader(
        "Grand Livre Sage (.xlsx)",
        type=["xlsx"],
        help="Export Sage du Grand Livre fournisseurs sur la période",
    )
with col2:
    f_base = st.file_uploader(
        "Base fournisseurs / Suivi Global (.xlsx)",
        type=["xlsx"],
        help="Le Suivi Global du cabinet (onglet « Base Frs Permanente ») — "
             "fournit les délais de paiement réels par fournisseur. "
             "Sans ce fichier, un délai de 60 j est appliqué par défaut.",
    )


# ─── Étape 2 — Exécution ──────────────────────────────────────────────────

st.markdown("### 2.  Exécution du pipeline")


def _save_uploaded(file, suffix=".xlsx") -> Path:
    """Sauve un upload Streamlit dans un fichier temporaire."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file.getvalue())
        return Path(tmp.name)


def _executer_pipeline():
    """Lance le pipeline complet et stocke les résultats en session."""
    progress = st.progress(0, text="Démarrage…")
    t0 = time.time()

    # 1. Sauvegarde de l'upload (seul le Grand Livre est requis ; les
    #    templates utilisent les versions embarquées dans app/templates).
    progress.progress(10, text="Préparation des fichiers…")
    gl_path   = _save_uploaded(f_gl) if f_gl else None
    base_path = _save_uploaded(f_base) if f_base else None
    template_path = ROOT / "app" / "templates" / "Modèle Suivi Global.xlsx"
    simpl_template_path = ROOT / "app" / "templates" / "Modèle Simpl DGI.xlsx"

    if not gl_path:
        st.error("⚠️ Le Grand Livre Sage est obligatoire.")
        return

    # 2. Base fournisseurs
    progress.progress(20, text="Chargement de la base fournisseurs…")
    if base_path:
        base = charger_base_fournisseurs(base_path)
    else:
        base = {}
        st.warning(
            "⚠️ Aucune base fournisseurs fournie — un délai de **60 j** est "
            "appliqué par défaut à tous les fournisseurs. Les FNP « en retard » "
            "peuvent être **surestimées**. Charge le Suivi Global du cabinet "
            "(onglet « Base Frs Permanente ») pour utiliser les délais réels.",
            icon="⚠️",
        )
    st.session_state.base_fournisseurs = base

    # 3. Parsing GL
    progress.progress(35, text="Parsing du Grand Livre…")
    ecritures = parser_gl_liste(gl_path)

    # 4. Lettrage
    progress.progress(65, text="Construction des lettrages…")
    lettrages, inconnues, hors_base = construire_lettrages(
        ecritures, base_fournisseurs=base,
        delai_par_defaut_jours=st.session_state.delai_defaut,
    )
    st.session_state.ecritures = ecritures
    st.session_state.lettrages = lettrages
    st.session_state.inconnues = inconnues
    st.session_state.hors_base = hors_base

    # 6. Calcul délais
    progress.progress(75, text="Calcul des échéances et retards…")
    # Période = début du trimestre choisi
    tri = int(st.session_state.trimestre[0])
    annee = 2000 + int(st.session_state.trimestre[2:])
    mois_debut = {1: 1, 2: 4, 3: 7, 4: 10}[tri]
    debut = date(annee, mois_debut, 1)
    # Date de clôture = dernier jour du trimestre (pour le retard à date des FNP)
    mois_fin = {1: 3, 2: 6, 3: 9, 4: 12}[tri]
    dernier_jour = calendar.monthrange(annee, mois_fin)[1]
    fin = date(annee, mois_fin, dernier_jour)
    lignes = calculer_toutes_lignes(lettrages, debut_periode=debut, fin_periode=fin)

    # 7. Anomalies
    progress.progress(85, text="Détection des anomalies…")
    anomalies = detecter_doublons(lignes)
    lignes = annoter_lignes(lignes, anomalies)
    st.session_state.lignes = lignes
    st.session_state.anomalies = anomalies

    # 8. Génération Excel
    progress.progress(92, text="Génération des fichiers Excel…")
    out_dir = Path(tempfile.mkdtemp(prefix="mizan_out_"))
    suivi_path = out_dir / f"Suivi Global DDP {st.session_state.client} {st.session_state.trimestre}.xlsx"
    generer_suivi_global(
        chemin_template=template_path,
        chemin_sortie=suivi_path,
        lignes=lignes,
        base_fournisseurs=base,
        client=st.session_state.client,
        exercice=annee,
    )

    simpl_path = out_dir / f"Simpl DDP {st.session_state.client} {st.session_state.trimestre}.xlsx"
    generer_simpl(
        chemin_template=simpl_template_path,
        chemin_sortie=simpl_path,
        lignes=lignes,
        base_fournisseurs=base,
        n_if_client=st.session_state.n_if,
        raison_sociale=st.session_state.raison_sociale,
        periode_trimestre=tri,
        annee=annee,
        chiffre_affaires_n1=Decimal(str(st.session_state.ca_n1)),
        activite_code=st.session_state.activite,
    )
    st.session_state.suivi_path = suivi_path
    st.session_state.simpl_path = simpl_path

    duree = time.time() - t0
    progress.progress(100, text=f"Terminé en {duree:.1f} s")
    time.sleep(0.4)
    progress.empty()
    st.success(f"✓ Pipeline complet exécuté en **{duree:.1f} secondes**")


col_run, col_info = st.columns([1, 4])
with col_run:
    if st.button("▶  Lancer Mizan", type="primary", use_container_width=True):
        if f_gl or st.session_state.demo_mode:
            _executer_pipeline()
        else:
            st.warning("Charge d'abord un Grand Livre Sage (ou active le mode démo)")
with col_info:
    if st.session_state.lignes is None:
        st.info("Charge ton Grand Livre Sage puis clique sur **Lancer Mizan**.")


# ─── Étape 3 — Dashboard résultats ────────────────────────────────────────

if st.session_state.lignes is not None:
    lignes = st.session_state.lignes
    anomalies = st.session_state.anomalies or []

    st.markdown("### 3.  Résultats")

    # KPIs en cartes
    statuts = Counter(l.statut.value for l in lignes)
    fnp_total = statuts.get('Non encore payée', 0)
    fnp_retard = sum(1 for l in lignes
                     if l.statut.value == 'Non encore payée'
                     and l.jours_retard and l.jours_retard > 0)
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total lignes", f"{len(lignes)}")
    col2.metric("OK RAS", f"{statuts.get('OK RAS', 0)}")
    col3.metric("Retards", f"{statuts.get('Attention, paiement hors délais', 0)}",
                delta=None, delta_color="inverse")
    col4.metric("FNP", f"{fnp_total}",
                delta=f"dont {fnp_retard} en retard" if fnp_retard else "toutes dans les délais",
                delta_color="inverse" if fnp_retard else "off")
    col5.metric("Anomalies", f"{len(anomalies)}",
                delta=f"{sum(1 for a in anomalies if a.type == TypeAnomalie.DOUBLON_EXACT)} doublons exacts" if anomalies else None)

    # Montants totaux — les FNP sont scindées en retard / dans les délais
    st.markdown("#### Montants par statut (MAD)")
    _LIBELLE = {
        "OK RAS": "🟢 OK RAS",
        "Attention, paiement hors délais": "🔴 Retard",
        "Paiement partiel": "🟡 Partiel",
    }
    montant_par_statut = {}
    for l in lignes:
        v = l.statut.value
        if v == "Non encore payée":
            label = ("🟠 FNP en retard"
                     if (l.jours_retard and l.jours_retard > 0)
                     else "🟢 FNP dans les délais")
        else:
            label = _LIBELLE.get(v, v)
        montant_par_statut.setdefault(label, Decimal(0))
        montant_par_statut[label] += l.montant_ttc

    cols = st.columns(len(montant_par_statut))
    for col, (statut, montant) in zip(cols, montant_par_statut.items()):
        col.metric(statut, f"{float(montant):,.0f}".replace(",", " ") + " MAD")

    # Onglets : aperçu / anomalies / diagnostic / sondage / téléchargement
    tab_apercu, tab_anomalies, tab_diag, tab_sondage, tab_download = st.tabs([
        "📋 Aperçu Suivi",
        "⚠️ Anomalies",
        "🔍 Diagnostic lettrage",
        "🧾 Sondage / OCR",
        "⬇️ Téléchargements",
    ])

    with tab_apercu:
        # Badge visuel par statut. Les FNP sont scindées en deux selon que
        # l'échéance est dépassée à la clôture (retard à date > 0) ou non.
        def _badge(l):
            v = l.statut.value
            if v == "Non encore payée":
                if l.jours_retard and l.jours_retard > 0:
                    return "🟠 FNP en retard"
                return "🟢 FNP dans les délais"
            return {
                "OK RAS":                          "🟢 OK RAS",
                "Attention, paiement hors délais": "🔴 Retard",
                "Paiement partiel":                "🟡 Partiel",
            }.get(v, v)

        # DataFrame pour affichage
        df = pd.DataFrame([{
            "N° Facture":     str(l.n_facture or ""),
            "Fournisseur":    l.fournisseur,
            "Date facture":   pd.to_datetime(l.date_facture) if l.date_facture else pd.NaT,
            "Montant TTC":    float(l.montant_ttc),
            "Délai (j)":      l.delai_convenu_jours,
            "Échéance":       pd.to_datetime(l.date_echeance) if l.date_echeance else pd.NaT,
            "Retard (j)":     l.jours_retard,
            "Statut":         _badge(l),
            "Paiement":       pd.to_datetime(l.date_paiement_effectif) if l.date_paiement_effectif else pd.NaT,
            "Observations":   l.observations or "",
        } for l in lignes])

        # Filtres — regroupés dans une carte
        with st.container(border=True):
            col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 1, 1])
            with col_f1:
                filtre_statut = st.multiselect(
                    "Filtrer par statut",
                    options=sorted(df["Statut"].unique()),
                    default=[],
                    placeholder="Tous les statuts",
                )
            with col_f2:
                filtre_frs = st.text_input("Rechercher un fournisseur", "", placeholder="Nom ou code…")
            with col_f3:
                seul_retards = st.checkbox("Retards uniquement", value=False)
            with col_f4:
                taille = st.select_slider(
                    "Hauteur",
                    options=["Compact", "Normal", "Grand", "Plein écran"],
                    value="Grand",
                )
        hauteur_px = {"Compact": 420, "Normal": 600, "Grand": 850, "Plein écran": 1200}[taille]

        df_filt = df
        if filtre_statut:
            df_filt = df_filt[df_filt["Statut"].isin(filtre_statut)]
        if filtre_frs:
            df_filt = df_filt[df_filt["Fournisseur"].str.contains(filtre_frs, case=False, na=False)]
        if seul_retards:
            df_filt = df_filt[df_filt["Retard (j)"].fillna(-1) > 0]

        # Bornes pour la ProgressColumn (retards)
        retard_max = max(int(df["Retard (j)"].abs().max() or 1), 30)

        # Zébrage : alternance blanc / gris très clair pour la lisibilité
        df_filt = df_filt.reset_index(drop=True)

        def _zebra(row):
            bg = "#FFFFFF" if row.name % 2 == 0 else "#F1F5F9"
            return [f"background-color: {bg}"] * len(row)

        df_styled = df_filt.style.apply(_zebra, axis=1)

        st.dataframe(
            df_styled,
            use_container_width=True,
            height=hauteur_px,
            hide_index=True,
            column_config={
                "N° Facture": st.column_config.TextColumn(width="small"),
                "Fournisseur": st.column_config.TextColumn(width="medium"),
                "Date facture": st.column_config.DateColumn(format="DD/MM/YYYY", width="small"),
                "Montant TTC": st.column_config.NumberColumn(
                    format="%.2f MAD", width="small",
                    help="Montant toutes taxes comprises",
                ),
                "Délai (j)": st.column_config.NumberColumn(format="%d j", width="small"),
                "Échéance":   st.column_config.DateColumn(format="DD/MM/YYYY", width="small"),
                "Retard (j)": st.column_config.ProgressColumn(
                    format="%d j",
                    min_value=-retard_max,
                    max_value=retard_max,
                    help="Positif = retard, négatif = paiement anticipé",
                    width="small",
                ),
                "Statut":   st.column_config.TextColumn(width="medium"),
                "Paiement": st.column_config.DateColumn(format="DD/MM/YYYY", width="small"),
                "Observations": st.column_config.TextColumn(width="large"),
            },
        )
        st.caption(f"Affichage : **{len(df_filt)}** / {len(df)} lignes")

    with tab_anomalies:
        if not anomalies:
            st.info("Aucune anomalie détectée.")
        else:
            df_a = pd.DataFrame([{
                "Type":          a.type.value.replace("_", " "),
                "Fournisseur":   a.fournisseur,
                "Lignes":        ", ".join(str(i + 10) for i in a.indices_lignes),
                "Description":   a.description,
            } for a in anomalies])

            # KPI anomalies
            c1, c2, c3 = st.columns(3)
            c1.metric("Doublons exacts",
                     sum(1 for a in anomalies if a.type == TypeAnomalie.DOUBLON_EXACT))
            c2.metric("Doublons probables",
                     sum(1 for a in anomalies if a.type == TypeAnomalie.DOUBLON_PROBABLE))
            c3.metric("Montants récurrents",
                     sum(1 for a in anomalies if a.type == TypeAnomalie.MONTANT_RECURRENT))

            st.dataframe(df_a, use_container_width=True, height=400)

    # ─── Tab Diagnostic lettrage ─────────────────────────────────────
    with tab_diag:
        lettrages = st.session_state.lettrages or []
        inconnues = st.session_state.inconnues or []
        hors_base = st.session_state.hors_base or []
        ecritures = st.session_state.ecritures or []

        desequilibres = [l for l in lettrages if l.lettre and not l.est_solde]
        fnp_groupes   = [l for l in lettrages if not l.paiements and l.factures]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Lettrages", len(lettrages))
        c2.metric("Déséquilibrés", len(desequilibres))
        c3.metric("Écritures non classifiées", len(inconnues))
        c4.metric("Fournisseurs hors base", len(hors_base))

        st.markdown("#### Lettrages déséquilibrés")
        if not desequilibres:
            st.success("Tous les lettrages sont soldés au centime.")
        else:
            df_dis = pd.DataFrame([{
                "Fournisseur":      l.fournisseur.nom,
                "Lettre":           l.lettre,
                "Total factures":   float(l.total_factures),
                "Total paiements":  float(l.total_paiements),
                "Écart (MAD)":      float(l.ecart),
                "Nb factures":      len(l.factures),
                "Nb paiements":     len(l.paiements),
            } for l in desequilibres])
            st.dataframe(df_dis, hide_index=True, use_container_width=True, height=300,
                         column_config={
                             "Total factures":  st.column_config.NumberColumn(format="%.2f"),
                             "Total paiements": st.column_config.NumberColumn(format="%.2f"),
                             "Écart (MAD)":     st.column_config.NumberColumn(format="%.2f"),
                         })

        st.markdown("#### Fournisseurs hors base")
        if not hors_base:
            st.success("Tous les fournisseurs présents dans le GL sont référencés.")
        else:
            noms = {e.code_fournisseur: e.nom_fournisseur for e in ecritures}
            df_hb = pd.DataFrame([{"Code": c, "Nom": noms.get(c, "?")} for c in hors_base])
            st.dataframe(df_hb, hide_index=True, use_container_width=True, height=300)
            st.caption("Astuce : ajouter ces fournisseurs au Référentiel DGI pour remplir IF / ICE / RC")

        st.markdown("#### Écritures non classifiées")
        if not inconnues:
            st.success("Toutes les écritures ont été interprétées.")
        else:
            df_inc = pd.DataFrame([{
                "Ligne":   e.ligne_source,
                "C.j":     e.code_journal.value,
                "Débit":   float(e.debit),
                "Crédit":  float(e.credit),
                "Libellé": e.libelle,
            } for e in inconnues[:200]])
            st.dataframe(df_inc, hide_index=True, use_container_width=True, height=300)
            if len(inconnues) > 200:
                st.caption(f"… {len(inconnues) - 200} autres écritures non affichées")

    # ─── Tab Sondage / OCR ───────────────────────────────────────────
    with tab_sondage:
        st.markdown(
            "Le sondage trimestriel exige un PDF justificatif (facture, avis "
            "de virement, LCN) pour les fournisseurs sélectionnés. Mizan peut "
            "extraire automatiquement le n° et la date via OCR."
        )

        # 1. Sélection des fournisseurs à justifier
        st.markdown("#### Fournisseurs à justifier")
        seuil_montant = st.slider(
            "Seuil de montant (MAD) — fournisseurs au-dessus + tous les retards > 60 j",
            min_value=0, max_value=500_000, value=50_000, step=10_000,
        )

        montant_par_frs = {}
        retard_par_frs  = {}
        for l in lignes:
            montant_par_frs[l.fournisseur] = montant_par_frs.get(l.fournisseur, 0) + float(l.montant_ttc)
            r = l.jours_retard or 0
            if r > retard_par_frs.get(l.fournisseur, 0):
                retard_par_frs[l.fournisseur] = r

        a_sonder = []
        for frs, mtn in montant_par_frs.items():
            if mtn >= seuil_montant or retard_par_frs.get(frs, 0) > 60:
                a_sonder.append({
                    "Fournisseur": frs,
                    "Montant total (MAD)": round(mtn, 2),
                    "Retard max (j)": retard_par_frs.get(frs, 0),
                })
        a_sonder.sort(key=lambda r: -r["Montant total (MAD)"])
        df_son = pd.DataFrame(a_sonder)
        st.dataframe(df_son, hide_index=True, use_container_width=True, height=300,
                     column_config={
                         "Montant total (MAD)": st.column_config.NumberColumn(format="%.2f"),
                     })
        st.caption(f"**{len(a_sonder)}** fournisseur(s) à justifier sur {len(montant_par_frs)} actifs")

        # 2. OCR des PDFs justificatifs
        st.markdown("#### OCR des justificatifs")
        pdfs = st.file_uploader(
            "Glisse les PDF justificatifs (factures, avis de virement)",
            type=["pdf"], accept_multiple_files=True,
        )

        col_o1, col_o2 = st.columns([1, 5])
        with col_o1:
            run_ocr = st.button("🔎 Lancer OCR", use_container_width=True, disabled=not pdfs)
        with col_o2:
            if pdfs:
                st.caption(f"{len(pdfs)} PDF prêt(s) — OCR fra+ara (Tesseract requis)")

        if run_ocr and pdfs:
            try:
                from ocr.extracteur_facture import extraire_pdf, TypeDocument
            except ImportError as e:
                st.error(f"OCR indisponible : {e}")
            else:
                resultats = []
                bar = st.progress(0, text="OCR en cours…")
                for i, pdf in enumerate(pdfs, 1):
                    p = _save_uploaded(pdf, suffix=".pdf")
                    try:
                        for r in extraire_pdf(p):
                            if r.type_document == TypeDocument.FACTURE:
                                resultats.append({
                                    "PDF":          Path(pdf.name).name,
                                    "Page":         r.page,
                                    "N° Facture":   r.n_facture or "",
                                    "Date facture": r.date_facture,
                                    "Confiance":    round(r.confiance, 2),
                                })
                    except Exception as e:
                        st.warning(f"Échec OCR {pdf.name} : {e}")
                    bar.progress(i / len(pdfs), text=f"{i}/{len(pdfs)}")
                bar.empty()
                st.session_state.ocr_resultats = resultats

        if st.session_state.ocr_resultats:
            df_ocr = pd.DataFrame(st.session_state.ocr_resultats)
            st.dataframe(df_ocr, hide_index=True, use_container_width=True, height=400,
                         column_config={
                             "Date facture": st.column_config.DateColumn(format="DD/MM/YYYY"),
                             "Confiance":    st.column_config.ProgressColumn(min_value=0, max_value=1),
                         })

    with tab_download:
        st.markdown("#### Fichiers générés")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            if st.session_state.suivi_path:
                with open(st.session_state.suivi_path, "rb") as f:
                    st.download_button(
                        "⬇️  Télécharger Suivi Global DDP",
                        data=f.read(),
                        file_name=st.session_state.suivi_path.name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
                st.caption("Fichier interne cabinet — piste d'audit complète")
        with col_d2:
            if st.session_state.simpl_path:
                with open(st.session_state.simpl_path, "rb") as f:
                    st.download_button(
                        "⬇️  Télécharger Simpl DGI",
                        data=f.read(),
                        file_name=st.session_state.simpl_path.name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
                st.caption("Formulaire officiel à signer par le client")

# Footer
st.markdown("---")
st.markdown(
    f"<div style='text-align:center; color:{GREY}; font-size:11px; padding:1rem 0;'>"
    f"<b>Mizan</b> · l'équilibre des paiements · "
    f"<a href='https://nextor-it.com' style='color:{TEAL_DEEP};'>nextor-it.com</a> · "
    f"Mai 2026"
    f"</div>",
    unsafe_allow_html=True,
)
