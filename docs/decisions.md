# Décisions métier — DDP automation

> Journal des décisions prises pendant la conception. Chaque décision est **provisoire**
> tant qu'elle n'a pas été validée par un cabinet d'expertise comptable.
> Les **questions à poser au cabinet** sont listées sous chaque décision.

**Légende du statut** :
- 🟡 **Provisoire** : retenue sur la base de l'analyse du GL UEMA, à valider
- 🟢 **Validée** : confirmée par un cabinet comptable
- 🔴 **Invalidée** : à revoir, en attente de nouvelle décision

---

## D-001 — Extraction du n° de facture depuis le libellé

**Statut** : 🟡 Provisoire (2026-05-18)

### Contexte
La sortie attendue contient une colonne `N° Facture` qui doit afficher le n° de la
facture **du fournisseur** (pas le n° de pièce interne Sage). Ce n° est intégré dans
le libellé Sage sous différentes formes :

| Libellé observé (UEMA) | N° à extraire |
|---|---|
| `FN° 26FC0031 A2CIM` | `26FC0031` |
| `FN°03764/2026 VITECMA` | `03764/2026` |
| `FN° 0202522423 AGADIR INOX EXPORT` | `0202522423` |
| `Fact ABM INDUSTRIE` | *(absent)* |

### Décision retenue
- Extraction par regex : `FN°\s*(\S+)` (capture après `FN°` jusqu'au premier espace)
- Si pas de match → fallback sur le **n° pièce Sage** (colonne 3 du GL) avec mention `[ref: NNNN]` dans les observations
- Les zéros de tête (ex: `0202522423`) sont préservés (caractère par caractère)

### Pourquoi
La majorité des libellés contiennent le n° fournisseur clairement identifiable.
Le n° pièce Sage est toujours présent et unique, donc constitue un fallback fiable.

### Questions à poser au cabinet
- **Q1.1** — Le n° de facture affiché doit-il **toujours** être celui du fournisseur, ou peut-on afficher le n° pièce Sage quand le libellé n'est pas exploitable ?
- **Q1.2** — En cas de divergence (n° facture absent du libellé), préférez-vous laisser la cellule **vide** ou remplir avec une référence Sage clairement marquée ?
- **Q1.3** — Faut-il **valider** le format du n° de facture (longueur min/max, caractères autorisés) pour détecter les libellés mal saisis ?

---

## D-002 — Date de livraison vs date facture

**Statut** : 🟡 Provisoire (2026-05-18)

### Contexte
La loi marocaine fait courir les délais de paiement à partir de la **date de livraison**.
Sage stocke uniquement la **date comptable** (date de la pièce). La date de livraison
est inscrite sur la facture papier (PDF) mais pas dans le GL.

Le modèle de suivi attend deux colonnes distinctes (`Date Livraison` et `Date Facture`).
Dans le fichier de référence UEMA, le comptable a recopié la **même date** dans les deux.

### Décision retenue
- `date_livraison = date_facture` automatiquement
- Si le cabinet souhaite distinguer un cas particulier, il édite à la main après génération

### Pourquoi
Aligné sur la pratique observée chez UEMA. L'enrichissement automatique depuis les
PDF de sondage est hors scope phase 1 (vision OCR + extraction de date = projet à part).

### Questions à poser au cabinet
- **Q2.1** — Confirmez-vous que la date de livraison est **rarement disponible** dans le système comptable, et que la pratique standard est d'utiliser la date facture comme référence pour le calcul du délai ?
- **Q2.2** — Existe-t-il des **secteurs ou des fournisseurs spécifiques** pour lesquels la date de livraison doit impérativement être tracée (ex: BTP, contrats avec PV de réception) ?
- **Q2.3** — Le cabinet souhaite-t-il pouvoir saisir manuellement la date de livraison **après** génération automatique (workflow d'enrichissement) ?
- **Q2.4** — En cas de **contrôle fiscal**, l'inspecteur DGI accepte-t-il la date facture comme proxy de la date de livraison ? Y a-t-il une jurisprudence ?

---

## D-003 — Détection des paiements récurrents identiques

**Statut** : 🟡 Provisoire (2026-05-18)

### Contexte
Certains fournisseurs (Maroc Telecom, loyers, abonnements) facturent un **montant identique
chaque mois**. Sans lettrage Sage, impossible d'associer paiements et factures de manière
fiable — on risque de calculer des retards fictifs.

### Décision retenue
1. **Priorité au lettrage Sage** : si une lettre (A, B, …) est posée par le comptable,
   on l'utilise telle quelle, sans recalcul.
2. **Détection automatique de cas ambigus** : si dans la période on trouve **2+ factures
   du même fournisseur avec exactement le même montant** ET au moins une n'est pas lettrée,
   on marque toutes ces factures avec le statut `À vérifier` et une observation explicite.

### Pourquoi
- Le comptable a fait son travail au moment de saisir : on lui fait confiance.
- L'ambiguïté n'existe qu'en absence de lettrage. La règle est conservatrice : on préfère
  signaler trop de cas que masquer un vrai problème.

### Questions à poser au cabinet
- **Q3.1** — Lorsqu'il y a plusieurs factures de même montant pour un fournisseur récurrent, à quelle **fréquence** le lettrage Sage est-il déjà posé ? Toujours / souvent / rarement ?
- **Q3.2** — Comment le cabinet **tranche actuellement** ces cas à la main ? FIFO (la plus ancienne d'abord), date de paiement proche, autre ?
- **Q3.3** — Souhaitez-vous que l'outil **propose une association automatique** (FIFO) et la signale, ou simplement qu'il marque le cas comme à vérifier sans tenter ?
- **Q3.4** — Quel niveau de **tolérance** sur le montant pour considérer deux factures comme "identiques" : exact, ±1 MAD, ±1% ?

---

## D-004 — Tolérance sur les écarts de lettrage

**Statut** : 🟡 Provisoire (2026-05-18)

### Contexte
Lorsqu'une facture (ex: 1 000 MAD) est lettrée avec son paiement (ex: 999,50 MAD),
il subsiste un **écart**. Causes possibles :

- Arrondi comptable (TVA, conversion de devise)
- **Escompte commercial** (paiement comptant avec remise)
- **Frais bancaires** retenus sur le virement
- **Retenue à la source (RAS)** — obligation fiscale au Maroc sur certaines prestations
- **Avoir** ou **note de débit** appliqué partiellement
- Erreur de saisie

### Décision retenue
- Seuil de tolérance combiné : `max(1 MAD, 0,5% du montant facture)`
- En-dessous du seuil → écart ignoré, statut `OK RAS` maintenu
- Au-dessus du seuil → statut `À vérifier`, écart mentionné en observation

### Pourquoi
- Le seuil absolu (1 MAD) absorbe les centimes d'arrondi sur petites factures.
- Le seuil relatif (0,5%) couvre les écarts proportionnels (escomptes, RAS) sur grosses factures.
- C'est la formule standard utilisée en audit financier.

### Exemple numérique

| Facture | Seuil | Écart | Décision |
|---|---|---|---|
| 1 000   | 5 MAD   | 0,50  | Ignoré ✓ |
| 100 000 | 500 MAD | 200   | Ignoré ✓ |
| 100 000 | 500 MAD | 1 200 | Flag → À vérifier |
| 50      | 1 MAD   | 2     | Flag → À vérifier |

### Questions à poser au cabinet
- **Q4.1** — Quels sont les **types d'écarts** les plus fréquents que vous rencontrez ? (arrondi, escompte, RAS, frais bancaires, avoir)
- **Q4.2** — Avez-vous un **seuil interne** déjà utilisé (en MAD et/ou en %) pour considérer un écart comme négligeable ?
- **Q4.3** — Les **escomptes commerciaux** et **retenues à la source** doivent-ils être tracés séparément (compte distinct) ou peuvent-ils être absorbés dans l'écart ?
- **Q4.4** — Les **frais bancaires** sur les virements sortants sont-ils habituellement pris en charge par UEMA (comptabilisés à part) ou retenus sur le montant ?

---

## D-005 — Écritures `OD` à montant insignifiant

**Statut** : 🟡 Provisoire (2026-05-18)

### Contexte
Le journal `OD` (Opérations Diverses) sert dans le GL UEMA à deux finalités très différentes :

1. **Vrais paiements** — Lettres de Change Normalisées (LCN, effets de commerce) :
   ```
   L316  OD #1049  LCN° 0038932 CIQS              D = 34 447,20
   L839  OD #1055  LCN° 0038943 PPRIME            D = 318 180,00
   ```
2. **Régularisations comptables** — résidus d'arrondis :
   ```
   L581  OD #540   Rentree Créance / GOFM        D = 0,01
   L1121 OD #436   Rentree/TOP CAOUTCHOUC...     D = 0,60
   ```

### Décision retenue
- Toute écriture `OD` avec libellé contenant `Rentree` (insensible à la casse) ET montant `< 1 MAD` est **ignorée des calculs DDP**.
- Elle est conservée dans `JeuDonnees.ecritures_inconnues` pour traçabilité (audit / debug).

### Pourquoi
Bruit comptable sans valeur métier. Inclure ces lignes pollue le rapport sans rien apporter.

### Questions à poser au cabinet
- **Q5.1** — Le journal `OD` est-il **standardisé** chez tous vos clients, ou son usage varie ?
- **Q5.2** — Existe-t-il **d'autres types d'écritures OD** que celles vues chez UEMA (LCN, Rentree) qu'il faudrait gérer ?
- **Q5.3** — Quel **seuil** considérez-vous comme "écriture insignifiante" pour les régularisations (1 MAD, 10 MAD, montant nul) ?
- **Q5.4** — Les LCN (effets) doivent-elles être traitées comme des **paiements à leur date d'écriture comptable**, ou à la date d'échéance de l'effet (parfois plusieurs mois plus tard) ?

---

## Questions transverses (à poser au cabinet)

### Sur la base fournisseurs
- **QT.1** — La **base fournisseurs** avec les délais convenus est-elle mise à jour à chaque nouveau contrat ? Quelle est la fréquence de mise à jour ?
- **QT.2** — En l'absence de convention, le **délai par défaut** est-il bien 60 jours (et non 90 ou autre) ?
- **QT.3** — Comment gérez-vous les fournisseurs avec **plusieurs conventions** (ex: 60 j pour produit A, 120 j pour produit B chez le même fournisseur) ?

### Sur le sondage trimestriel
- **QT.4** — Quels sont les **critères de sélection** des fournisseurs du sondage (top N par montant, échantillon aléatoire, fournisseurs nouveaux) ?
- **QT.5** — Le sondage doit-il être **reproductible** d'un trimestre à l'autre (les mêmes fournisseurs si possible) ou **aléatoire à chaque fois** ?

### Sur la déclaration Simpl
- **QT.6** — La maquette du formulaire **Simpl délais de paiements** change-t-elle d'un trimestre à l'autre ou est-elle stable ?
- **QT.7** — Quels champs du Simpl sont **calculés** vs **saisis manuellement** par le client ?
- **QT.8** — Le client doit-il **signer** électroniquement ou physiquement (papier) ?

### Sur la fiscalité
- **QT.9** — Le calcul des **pénalités** de retard est-il du ressort de l'outil ou de la DGI ?
- **QT.10** — Y a-t-il des **fournisseurs exonérés** de la déclaration DDP (administrations, intra-groupe) ?

---

## D-006 — Date réelle des factures reportées (AN)

**Statut** : 🟡 Provisoire (2026-05-18) — **limitation MVP phase 1**

### Contexte
Les factures non payées au 31/12 sont reportées dans le GL Sage via le journal
**À-Nouveau (AN)** avec :
- une date d'écriture = 01/01 de l'exercice courant (date d'ouverture)
- un n° de facture original (ex: `25/02609`) qui contient indirectement le millésime

La **vraie date** de facturation n'est nulle part dans le GL — elle est uniquement
sur le PDF de la facture.

### Exemple
Output référence pour PPRIME 25/023 :
```
N° Facture = 25/023
Date Livraison = 2025-01-31
Date Facture   = 2024-11-10
Date Paiement  = 2026-02-02
Délai          = 90 jours
Échéance       = 2025-04-30
Statut         = Attention, paiement hors délais (retard ~9 mois)
```

→ Le comptable a manuellement enrichi les dates depuis le PDF justificatif.

### Décision retenue (limitation MVP)
- En phase 1, les factures reportées AN gardent comme `date_facture` la date
  d'écriture Sage (01/01/exercice).
- Une **observation** est portée dans le rapport : *« Facture reportée — date à vérifier »*.
- Le comptable corrige manuellement les dates depuis les PDF (≈ 5-10 lignes par trimestre).
- En **phase 2**, on ajoutera un module d'extraction OCR depuis les PDF de sondage
  pour enrichir automatiquement.

### Pourquoi
Sans source de données externe au GL, il n'y a aucun moyen automatique de récupérer
la vraie date. Une heuristique pessimiste (31/12 année précédente) introduirait
des faux retards. Mieux vaut signaler clairement la limitation.

### Questions à poser au cabinet
- **Q6.1** — Combien de factures AN entrent typiquement dans une déclaration ?
  (chez UEMA : 345 sur 774 = 45 % du volume)
- **Q6.2** — Le temps de saisie manuelle des dates depuis les PDF, c'est combien
  de minutes par facture ?
- **Q6.3** — Une extraction OCR depuis les PDF de sondage serait-elle utile en phase 2 ?
- **Q6.4** — Existe-t-il une logique de **dépassement maximal** que le contrôleur DGI
  applique pour les factures dont la vraie date est inconnue (ex: hypothèse pessimiste 60 j) ?

---

## D-007 — Référentiel DGI des fournisseurs (N° IF, ICE, RC, adresse)

**Statut** : 🟡 Provisoire (2026-05-18) — **dépendance externe**

### Contexte
Le formulaire **Simpl** exige pour chaque facture déclarée des informations
sur le fournisseur qui ne figurent **pas** dans le GL Sage :

| Champ Simpl | Source |
|---|---|
| N° IF (Identifiant Fiscal) | Référentiel cabinet |
| N° ICE (15 chiffres) | Référentiel cabinet ou portail DGI |
| N° RC (Registre du Commerce) | Référentiel cabinet |
| Adresse siège social | Référentiel cabinet |
| Ville du RC | Référentiel cabinet |
| Nature des marchandises/services | Spécifique à la facture (PDF) |

### Décision retenue (Phase 1)
- Le modèle `Fournisseur` est étendu avec des champs DGI optionnels.
- Pour le pilote UEMA, ces champs sont **laissés vides** dans l'output Simpl.
- Le cabinet les complète manuellement avant dépôt.
- **Phase 2** : créer un **référentiel DGI partagé** par le cabinet, alimenté
  par les coordonnées récupérées une fois et réutilisées trimestre après trimestre.

### Pourquoi
Ces données sont stables (l'IF d'un fournisseur ne change pas) — il suffit de
les saisir une seule fois. Mais ce ne sont pas des données dérivables du GL.

### Questions à poser au cabinet
- **Q7.1** — Le cabinet maintient-il déjà un **référentiel** avec ces champs ?
  Dans quel format (Excel, base, ERP) ?
- **Q7.2** — Existe-t-il un **moyen automatique** de récupérer ces informations
  (API DGI, scraping du portail Simpl, recherche par ICE) ?
- **Q7.3** — Quelle est la **proportion** de fournisseurs déjà renseignés
  vs à rechercher (nouveaux fournisseurs) chaque trimestre ?
- **Q7.4** — La colonne "Nature des marchandises" est-elle remplie pour
  **toutes les factures** ou uniquement quand le contrôleur le demande ?

---

## D-008 — Mode de dépôt sur le portail Simpl-TVA

**Statut** : 🔴 Bloquante (2026-05-18) — **inconnue côté Nextor, à clarifier avec le cabinet**

### Contexte
Notre pipeline produit un fichier Excel au format officiel **CERFA ADC500B-23I**
(« DECLARATION - DELAIS DE PAIEMENT », articles 78-3 et 78-4 de la loi 15-95).
Ce fichier est censé être transmis à la DGI via le portail **Simpl-TVA**
(`simpl.tax.gov.ma`), mais le **mode exact de dépôt** n'est pas documenté côté Nextor.

### Trois scénarios possibles

| Scénario | Action côté cabinet/client | Impact sur Mizan |
|---|---|---|
| **A — Upload direct du Excel** | Téléverser le `.xlsx` ADC500B-23I tel quel après signature | Mizan livre quasi-final. Pas de travail supplémentaire. |
| **B — Re-saisie manuelle dans le portail** | Ouvrir Simpl-TVA, recopier ligne par ligne depuis l'Excel | Mizan = **support de travail**. Le fichier Excel rempli évite 61 % de re-saisie (D-007). |
| **C — Conversion XML / JSON / format technique** | Fournir un fichier structuré spécifique au format DGI | Nécessite un **module de conversion** à coder en Phase 2 (mapping Excel → XML). |

Selon le scénario retenu, l'effort restant côté Mizan varie de **zéro** (A) à **un sprint complet** (C).

### Décision retenue
**À trancher avec le cabinet.** Pas de décision technique tant que l'information n'est pas confirmée.

### Pourquoi cette décision est bloquante
Sans connaître le mode de dépôt, on ne peut pas :
- Garantir que notre output sera utilisable tel quel par le cabinet
- Évaluer si un module de conversion / dépôt automatique est nécessaire en Phase 2
- Prioriser les sprints suivants (le mode XML implique un effort dev significatif)

### Questions à poser au cabinet
- **Q8.1** — Le portail Simpl-TVA accepte-t-il l'**upload direct** du fichier Excel ADC500B-23I ?
- **Q8.2** — Sinon, faut-il **re-saisir manuellement** chaque ligne, ou existe-t-il un format technique (XML, CSV, JSON) ?
- **Q8.3** — La **signature du client** est-elle physique (impression + signature manuscrite + scan)
  ou numérique (certificat électronique sur le portail) ?
- **Q8.4** — Combien de temps prend le **dépôt** aujourd'hui (en plus de la préparation du fichier) ?
  *(estimation actuelle : 30 min à 2 h selon le scénario)*
- **Q8.5** — Existe-t-il un **accusé de réception** automatique du portail (et sous quelle forme) ?
- **Q8.6** — Le portail nécessite-t-il une **authentification spécifique** du client (login/mdp, certificat, OTP) ?

### Pistes Phase 2 selon la réponse

- **Si scénario A** : rien à faire côté Mizan (notre Excel est le livrable final).
- **Si scénario B** : assistance à la re-saisie via UI Mizan (copier-coller assisté).
- **Si scénario C** : module `output/simpl_xml.py` qui convertit le résultat en format DGI natif.
- **Bonus** (tous scénarios) : module **« dépôt automatique »** qui automatise la connexion au
  portail et le téléversement (impact UX énorme pour le cabinet).

---

## Suivi

| Décision | Statut | Validée le | Par |
|---|---|---|---|
| D-001 (N° facture) | 🟡 | — | — |
| D-002 (Date livraison) | 🟡 | — | — |
| D-003 (Récurrents) | 🟡 | — | — |
| D-004 (Tolérance écart) | 🟡 | — | — |
| D-005 (OD insignifiantes) | 🟡 | — | — |
| D-006 (Dates factures AN) | 🟡 | — | — |
| D-007 (Référentiel DGI) | 🟢 | 2026-05-18 | Phase 2 Sprint 1 |
| D-008 (Mode de dépôt Simpl-TVA) | 🔴 | — | — |

**Légende statut** :
- 🟢 Validée
- 🟡 Provisoire (par défaut)
- 🔴 Bloquante / inconnue, nécessite réponse externe avant de progresser

---

## Notes d'évolution

### 🟢 D-007 résolue (Sprint 1 Phase 2, 2026-05-18)

Le **Référentiel DGI Cabinet** est désormais un fichier Excel à part avec les colonnes
enrichies (IF, ICE, RC, adresse, ville, secteur, nature marchandises).

- **Format** : `samples/input/Référentiel DGI - Cabinet.xlsx` (onglet `Référentiel DGI`)
- **Générateur initial** : `scripts/generer_referentiel_dgi.py` croise la base existante
  avec le Simpl de référence pour pré-remplir 39/109 fournisseurs UEMA.
- **Loader** : `compute/base_fournisseurs.py` auto-détecte le format (legacy 4 cols vs DGI 11 cols).
- **Impact** : **61 % du Simpl auto-rempli** dès cette première version (352/575 lignes).
- **Reste à faire** : le cabinet enrichit progressivement les 70 fournisseurs sans IF/ICE.

---

## D-009 — Convention de comptage du délai de paiement

**Statut** : 🟢 **Validée** (2026-05-22) — **Convention J1 retenue (alignée sur le cabinet)**

### Révision 2026-05-22
La convention J0 initialement retenue (2026-05-19) est **annulée**. Après nouvelle revue
avec le cabinet, il est confirmé que le **jour de la facture compte comme jour 1** du délai
(lecture inclusive). Les "+1 jour" observés côté Mizan dans la comparaison UEMA 1T26
**étaient bien une erreur Mizan**, pas une erreur cabinet.

- **Q9.1 — Jour de la facture = jour 1 ou jour 0 ?** → **Jour 1** (convention cabinet retenue).
- Formule retenue : `échéance = date_livraison + délai − 1` (J1, lecture inclusive).
- Q9.2 à Q9.4 : non priorisées.

### Implication
Modification de `src/compute/delais.py:calculer_date_echeance` — soustraction d'un jour.
Les 286 lignes avec Δ=+1j dans la comparaison UEMA 1T26 doivent disparaître après
re-génération.

### Historique
- 2026-05-19 : J0 retenue (à tort) sur la base d'une première revue cabinet.
- 2026-05-22 : J1 confirmée comme convention métier réelle du cabinet → bascule Mizan.

---

### Trace historique (avant validation)

### Contexte
La comparaison ligne à ligne entre Mizan et la déclaration manuelle du cabinet UEMA 1T26
fait apparaître un **écart systématique sur la date d'échéance** :

- **+1 jour** : 208 lignes / 290 factures normales (**71,7 %**)
- **+2 jours** : 34 lignes (**11,7 %**)
- **+3 à +5 jours** : 12 lignes (4 %)
- Autres : 12 %

L'écart "+1 jour" peut s'expliquer par une **convention de comptage différente** :
- **Mizan** : `échéance = date_livraison + délai` (jour facture = J0, échéance = J+N).
- **Cabinet apparent** : `échéance = date_livraison + délai − 1` (jour facture compté
  comme jour 1, échéance = J+N−1).

L'écart "+2 à +4 jours" pourrait s'expliquer par une **règle "fin de mois"** prévue par
l'**article 78-4 de la loi 15-95** au Maroc :

> *« Pour les factures émises en cours de mois, le délai court à compter du dernier jour
>    du mois de facturation. »*

### Exemple concret
Facture CIQS du 12/02/2026, délai 120 jours :
- Mizan calcule : 12/02 + 120 j = **12/06/2026**
- Cabinet UEMA  : **11/06/2026** (−1 jour)
- Si règle fin de mois : 28/02 + 120 j − 1 = **27/06/2026** (option à vérifier)

### Décision provisoire Nextor
Conserver la convention `échéance = date + délai` (naïve, J0 = jour facture).
À arbitrer avec le cabinet avant industrialisation.

### Questions à poser au cabinet
- **Q9.1** — Quand vous calculez l'échéance d'une facture, le **jour de la facture compte-t-il
  comme jour 1** (échéance = jour facture + délai − 1) ou **jour 0** (échéance = jour facture
  + délai) ?
- **Q9.2** — Appliquez-vous une règle **« fin de mois »** sur les factures émises en cours
  de mois (le délai court à partir du dernier jour du mois de facturation) ? Si oui, dans
  quels cas (toujours, sur demande contractuelle, par secteur) ?
- **Q9.3** — Existe-t-il une **convention sectorielle** différente (BTP, transport, services
  publics) qui s'applique chez certains de vos clients ?
- **Q9.4** — En cas de **contrôle DGI**, sur quel calcul l'administration se base-t-elle —
  jour J0 ou jour J1 ? Y a-t-il une jurisprudence claire ?
