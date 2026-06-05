"""Mizan — Interface utilisateur web (MVP Phase 2 Sprint 5).

Application Streamlit qui expose le pipeline complet en mode no-CLI :
  1. Identification client + paramètres
  2. Upload des fichiers d'entrée (GL, référentiel, corrections)
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
                     charger_base_fournisseurs,
                     charger_corrections,
                     construire_index)
from output import generer_simpl, generer_suivi_global                   # noqa: E402
from quality import detecter_doublons, annoter_lignes, TypeAnomalie      # noqa: E402
from models import StatutFacture                                          # noqa: E402
from compute.corrections import CorrectionDate                            # noqa: E402


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

st.markdown(f"""
<style>
    .stApp {{ background: {PAPER}; }}
    .main h1, .main h2, .main h3 {{ color: {NAVY_INK}; }}
    .stButton>button {{
        background: {NAVY};
        color: white;
        border: none;
        border-radius: 6px;
        padding: 0.5rem 1.5rem;
        font-weight: 600;
    }}
    .stButton>button:hover {{
        background: {TEAL_DEEP};
        color: white;
    }}
    .stDownloadButton>button {{
        background: {TEAL_DEEP};
        color: white;
        border: none;
        border-radius: 6px;
        padding: 0.5rem 1.5rem;
        font-weight: 600;
    }}
    .stDownloadButton>button:hover {{
        background: {NAVY};
    }}
    [data-testid="stMetricLabel"] {{
        color: {TEAL_DEEP};
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 2px;
        font-size: 11px;
    }}
    [data-testid="stMetricValue"] {{
        color: {NAVY_INK};
        font-weight: 700;
    }}
    div[data-testid="stSidebar"] {{
        background: white;
        border-right: 1px solid #E5E7EB;
    }}
    div[data-testid="stSidebar"] label,
    div[data-testid="stSidebar"] .stMarkdown {{
        color: {NAVY_INK} !important;
    }}
    div[data-testid="stSidebar"] h3 {{
        color: {NAVY_INK} !important;
        font-size: 12px !important;
        text-transform: uppercase;
        letter-spacing: 2px;
        color: {TEAL_DEEP} !important;
        margin-top: 1.5rem;
    }}
    div[data-testid="stSidebar"] hr {{
        border-color: #E5E7EB !important;
        margin: 1rem 0;
    }}
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
        font-size: 36px;
        font-weight: 700;
        line-height: 1.1;
        margin-top: 0.2rem;
        margin-bottom: 0.5rem;
    }}
    .hero-subtitle {{
        color: {GREY};
        font-size: 15px;
        margin-bottom: 2rem;
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
        "corrections_index": None,
        "corrections_manuelles": None,
        "ocr_resultats": None,
        "suivi_path": None,
        "simpl_path": None,
        "client": "UEMA",
        "trimestre": "1T26",
        "n_if": "14367938",
        "raison_sociale": "STE UEMA INDUSTRY",
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
    st.session_state.ca_n1 = st.number_input(
        "Chiffre d'affaires N-1 (MAD)",
        min_value=0.0,
        value=float(st.session_state.ca_n1),
        step=10000.0,
        format="%.2f",
    )
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

    st.markdown("---")
    st.markdown("### Mode démo")
    if st.button("🎬  Charger l'exemple UEMA 1T26", use_container_width=True):
        st.session_state.demo_mode = True
        st.session_state.client = "UEMA"
        st.session_state.trimestre = "1T26"
        st.session_state.n_if = "14367938"
        st.session_state.raison_sociale = "STE UEMA INDUSTRY"
        st.session_state.ca_n1 = 23369748.49
        st.session_state.activite = 1
        st.success("✓ Exemple UEMA chargé — clique sur **Lancer Mizan**")
        st.rerun()
    if st.session_state.demo_mode:
        st.caption("Mode démo actif — les fichiers samples seront utilisés")
        if st.button("✕ Sortir du mode démo", use_container_width=True):
            st.session_state.demo_mode = False
            st.rerun()

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

col1, col2, col3 = st.columns(3)
with col1:
    f_gl = st.file_uploader(
        "Grand Livre Sage (.xlsx)",
        type=["xlsx"],
        help="Export Sage du Grand Livre fournisseurs sur la période",
    )
with col2:
    f_base = st.file_uploader(
        "Référentiel DGI (.xlsx)",
        type=["xlsx"],
        help="Optionnel — base fournisseurs avec délais, N° IF, ICE, RC…",
    )
with col3:
    f_corrections = st.file_uploader(
        "Corrections dates (.xlsx)",
        type=["xlsx"],
        help="Optionnel — corrections manuelles des dates AN et délais par facture",
    )

# Template Simpl (fixe ou paramétrable)
with st.expander("Templates avancés"):
    col_a, col_b = st.columns(2)
    with col_a:
        f_template = st.file_uploader("Template Suivi Global (.xlsx)", type=["xlsx"])
    with col_b:
        f_simpl_template = st.file_uploader("Template Simpl DGI (.xlsx)", type=["xlsx"])


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

    # 1. Sauvegarde des uploads (ou fallback samples en mode démo)
    progress.progress(10, text="Préparation des fichiers…")
    samples = ROOT / "samples" / "input"
    if st.session_state.demo_mode:
        gl_path   = samples / "UEMA - GL FRS 2026.xlsx"
        base_path = samples / "Référentiel DGI - Cabinet.xlsx"
        corr_path = None
    else:
        gl_path   = _save_uploaded(f_gl) if f_gl else None
        base_path = _save_uploaded(f_base) if f_base else None
        corr_path = _save_uploaded(f_corrections) if f_corrections else None
    template_path = (
        _save_uploaded(f_template) if f_template
        else ROOT / "app" / "templates" / "Modèle Suivi Global.xlsx"
    )
    simpl_template_path = (
        _save_uploaded(f_simpl_template) if f_simpl_template
        else ROOT / "app" / "templates" / "Modèle Simpl DGI.xlsx"
    )

    if not gl_path:
        st.error("⚠️ Le Grand Livre Sage est obligatoire.")
        return

    # 2. Base fournisseurs
    progress.progress(20, text="Chargement de la base fournisseurs…")
    if base_path:
        base = charger_base_fournisseurs(base_path)
    else:
        base = {}
    st.session_state.base_fournisseurs = base

    # 3. Parsing GL
    progress.progress(35, text="Parsing du Grand Livre…")
    ecritures = parser_gl_liste(gl_path)

    # 4. Corrections
    progress.progress(50, text="Chargement des corrections…")
    idx = None
    if corr_path:
        corrections = charger_corrections(corr_path)
        idx = construire_index(corrections)

    # 5. Lettrage
    progress.progress(65, text="Construction des lettrages…")
    # Fusionne corrections manuelles (data_editor) + corrections fichier
    if st.session_state.corrections_manuelles:
        idx = idx or {}
        for c in st.session_state.corrections_manuelles:
            idx[(c.nom_fournisseur.upper(), c.n_facture)] = c
    lettrages, inconnues, hors_base = construire_lettrages(
        ecritures, base_fournisseurs=base,
        delai_par_defaut_jours=st.session_state.delai_defaut,
        corrections_index=idx,
    )
    st.session_state.ecritures = ecritures
    st.session_state.lettrages = lettrages
    st.session_state.inconnues = inconnues
    st.session_state.hors_base = hors_base
    st.session_state.corrections_index = idx

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
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total lignes", f"{len(lignes)}")
    col2.metric("OK RAS", f"{statuts.get('OK RAS', 0)}")
    col3.metric("Retards", f"{statuts.get('Attention, paiement hors délais', 0)}",
                delta=None, delta_color="inverse")
    col4.metric("FNP", f"{statuts.get('Non encore payée', 0)}")
    col5.metric("Anomalies", f"{len(anomalies)}",
                delta=f"{sum(1 for a in anomalies if a.type == TypeAnomalie.DOUBLON_EXACT)} doublons exacts" if anomalies else None)

    # Montants totaux
    st.markdown("#### Montants par statut (MAD)")
    montant_par_statut = {}
    for l in lignes:
        montant_par_statut.setdefault(l.statut.value, Decimal(0))
        montant_par_statut[l.statut.value] += l.montant_ttc

    cols = st.columns(len(montant_par_statut))
    for col, (statut, montant) in zip(cols, montant_par_statut.items()):
        col.metric(statut, f"{float(montant):,.0f}".replace(",", " ") + " MAD")

    # Onglets : aperçu / anomalies / diagnostic / corrections / sondage / téléchargement
    tab_apercu, tab_anomalies, tab_diag, tab_corr, tab_sondage, tab_download = st.tabs([
        "📋 Aperçu Suivi",
        "⚠️ Anomalies",
        "🔍 Diagnostic lettrage",
        "✏️ Corrections dates",
        "🧾 Sondage / OCR",
        "⬇️ Téléchargements",
    ])

    with tab_apercu:
        # Badge visuel par statut
        _BADGE = {
            "OK RAS":                              "🟢 OK RAS",
            "Attention, paiement hors délais":     "🔴 Retard",
            "Non encore payée":                    "🟠 FNP",
            "Paiement partiel":                    "🟡 Partiel",
        }

        # DataFrame pour affichage
        df = pd.DataFrame([{
            "N° Facture":     str(l.n_facture or ""),
            "Fournisseur":    l.fournisseur,
            "Date facture":   pd.to_datetime(l.date_facture) if l.date_facture else pd.NaT,
            "Montant TTC":    float(l.montant_ttc),
            "Délai (j)":      l.delai_convenu_jours,
            "Échéance":       pd.to_datetime(l.date_echeance) if l.date_echeance else pd.NaT,
            "Retard (j)":     l.jours_retard,
            "Statut":         _BADGE.get(l.statut.value, l.statut.value),
            "Paiement":       pd.to_datetime(l.date_paiement_effectif) if l.date_paiement_effectif else pd.NaT,
            "Observations":   l.observations or "",
        } for l in lignes])

        # Filtres — barre compacte
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

        st.dataframe(
            df_filt,
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

    # ─── Tab Corrections dates (D-006) ───────────────────────────────
    with tab_corr:
        st.markdown(
            "Les factures issues d'**À-Nouveaux** (`Cj = AN`) n'ont pas leur vraie "
            "date — elles ressortent au 01/01. Surcharge ici la date réelle "
            "et/ou un délai de paiement spécifique."
        )

        # Pré-remplit avec les factures AN détectées si l'éditeur est vide
        if "corr_edit_df" not in st.session_state:
            an_factures = []
            for l in (st.session_state.lettrages or []):
                for f in l.factures:
                    if f.is_report:
                        an_factures.append({
                            "Code fournisseur": f.code_fournisseur,
                            "Nom fournisseur":  f.nom_fournisseur,
                            "N° Facture":       f.n_facture or "",
                            "Date facture":     None,
                            "Date livraison":   None,
                            "Délai (j)":        None,
                            "Observations":     "AN — à vérifier",
                        })
            # déduplique par (nom, n_facture)
            vus = set()
            uniques = []
            for r in an_factures:
                k = (r["Nom fournisseur"], r["N° Facture"])
                if k in vus:
                    continue
                vus.add(k); uniques.append(r)
            st.session_state.corr_edit_df = pd.DataFrame(uniques)

        st.caption(f"{len(st.session_state.corr_edit_df)} factures AN détectées — saisis les vraies dates :")

        edited = st.data_editor(
            st.session_state.corr_edit_df,
            num_rows="dynamic",
            use_container_width=True,
            height=500,
            hide_index=True,
            key="corr_editor",
            column_config={
                "Date facture":   st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Date livraison": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Délai (j)":      st.column_config.NumberColumn(min_value=0, max_value=365, step=1),
            },
        )

        c1, c2, c3 = st.columns([1, 1, 4])
        with c1:
            if st.button("💾 Enregistrer", use_container_width=True):
                st.session_state.corr_edit_df = edited
                corrections = []
                for _, r in edited.iterrows():
                    d_fact = r.get("Date facture")
                    if pd.isna(d_fact) or not r.get("N° Facture"):
                        continue
                    d_livr = r.get("Date livraison")
                    delai  = r.get("Délai (j)")
                    corrections.append(CorrectionDate(
                        code_fournisseur=str(r.get("Code fournisseur") or "") or None,
                        nom_fournisseur=str(r["Nom fournisseur"]),
                        n_facture=str(r["N° Facture"]),
                        date_facture=pd.to_datetime(d_fact).date(),
                        date_livraison=pd.to_datetime(d_livr).date() if not pd.isna(d_livr) else None,
                        delai_jours=int(delai) if pd.notna(delai) else None,
                        observations=str(r.get("Observations") or "") or None,
                    ))
                st.session_state.corrections_manuelles = corrections
                st.success(f"✓ {len(corrections)} correction(s) enregistrée(s)")
        with c2:
            if st.button("🔄 Recalculer", type="primary", use_container_width=True):
                if not f_gl:
                    st.warning("Re-uploade le GL pour relancer")
                else:
                    _executer_pipeline()
                    st.rerun()
        with c3:
            nb = len(st.session_state.corrections_manuelles or [])
            if nb:
                st.info(f"{nb} correction(s) seront appliquées au prochain run")

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
            if st.button("📥 Verser ces dates dans Corrections"):
                # Reporte les résultats OCR vers l'éditeur de corrections (matching par n° facture)
                df_corr = st.session_state.corr_edit_df.copy()
                n_match = 0
                for r in st.session_state.ocr_resultats:
                    if not r["N° Facture"] or not r["Date facture"]:
                        continue
                    mask = df_corr["N° Facture"].astype(str) == str(r["N° Facture"])
                    if mask.any():
                        df_corr.loc[mask, "Date facture"] = pd.to_datetime(r["Date facture"])
                        n_match += int(mask.sum())
                st.session_state.corr_edit_df = df_corr
                st.success(f"✓ {n_match} ligne(s) renseignée(s). Va dans l'onglet Corrections pour vérifier.")

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
