""" 
Module pour harmoniser certains colonnes (Métier, Motif, Orientation Conseillée, Sexe) + Branche
"""

import os, re, json, time, hashlib, threading
import requests
import pandas as pd
from dotenv import load_dotenv
import argparse
from concurrent.futures import ThreadPoolExecutor
import unicodedata
import sys


load_dotenv()

donnees = pd.read_excel("sps_data_2026.xlsx")
BRANCHES = donnees["BRANCHE PRO"].unique().tolist()


API_KEY = os.environ.get("ALBERT_KEY", "")
URL = "https://albert.api.etalab.gouv.fr/v1/chat/completions"
MODELE = "openai/gpt-oss-120b"
HEADERS = {"accept": "application/json", "Authorization": f"Bearer {API_KEY}"}


COLONNES = ["Motif", "Sexe", "Orientation conseillée", "Métier"]
CHUNK = 100                       # valeurs par requête
CACHE = "cache_albert.json"       # réponses déjà obtenues : relancer ne refait aucun appel
#REFERENCE = "valeurs_reference.json"
appels = 0
avec_reasoning = [True]           # passe à False si Albert refuse le paramètre reasoning_effort


REGLES = """PRINCIPE : deux valeurs sont regroupées uniquement si elles désignent EXACTEMENT la même chose, avec la même
précision, et ne diffèrent que par la façon de l'écrire. Toute précision qui qualifie la valeur
(spécialité, contexte, service, public, lieu, niveau, statut, fonction, cause) est une spécialisation
et doit être CONSERVÉE dans la valeur finale.

Sont regroupées (même chose, même précision) :
- fautes d'orthographe ou de frappe
- genre et nombre
- abréviations et sigles du MÊME intitulé
- mots de liaison seuls (de, du, des, et, en)
- ordre des mots différent

NE SONT PAS regroupées (la précision diffère, donc garde les valeurs séparées).
Si tu hésites entre deux valeurs, NE LES REGROUPE PAS.

Valeur finale : la valeur corrigée, avec TOUTES ses précisions, au singulier et au masculin,
en MAJUSCULES sans accents ni ponctuation. Valeurs sans information (NAN, NC, N, 0, NON, AU...) : NON RENSEIGNE."""

EXEMPLES = {
    "Métier": """Exemples de valeurs regroupées : INFRIMIER, INFIRMIERE -> INFIRMIER ; MEDCIN -> MEDECIN ;
AIDE SOIGANT, AIDE SOIGNANTE -> AIDE SOIGNANT ; KINE, KINESITHERAPEUTE -> KINESITHERAPEUTE ;
CADRE SANTE, CADRE DE SANTE -> CADRE DE SANTE.
Exemples de valeurs NON regroupées : INFIRMIER / INFIRMIER ANESTHESISTE / INFIRMIER PSYCHIATRIQUE / INFIRMIER COORDINATEUR ;
AIDE SOIGNANT / AIDE SOIGNANT A DOMICILE / AIDE SOIGNANT EN EHPAD ;
MEDECIN / MEDECIN GENERALISTE / MEDECIN COORDINATEUR / MEDECIN DU TRAVAIL ;
DIRECTEUR / DIRECTEUR ADJOINT ; ETUDIANT EN MEDECINE / MEDECIN ; DIETETICIEN / NUTRITIONNISTE.""",
}

PROMPT_ASSOC = """Colonne « {nom} ». Voici les VALEURS EXISTANTES de cette colonne :
{valeurs}

Chaîne à rattacher : {chaine}

Cherche si l'une des valeurs existantes désigne EXACTEMENT la même chose que cette chaîne, avec la même précision,
aux fautes d'orthographe, genre, nombre, sigle ou mots de liaison près.

{regles}
{exemples}

Réponds par UNE seule ligne :
- la valeur existante, recopiée À L'IDENTIQUE, si elle convient
- AUCUNE si aucune valeur existante ne convient (ou si tu hésites)
Aucun autre texte."""

PRECISIONS = """
DEFINITIONS OPERATIONNELLES DES BRANCHES PROFESSIONNELLES

Ces définitions précisent le périmètre de chaque branche.
Elles doivent être appliquées à tous les métiers, y compris ceux
qui ne sont pas explicitement connus ou rencontrés auparavant.

1. MEDECIN
Regroupe les professions médicales dont la fonction consiste
principalement à exercer la médecine : évaluation clinique,
diagnostic, prescription et traitement.
Une spécialisation médicale reste dans cette branche.

2. AIDE SOIGNANT
Regroupe la profession d'aide-soignant et les fonctions qui
correspondent réellement au périmètre professionnel retenu
pour cette catégorie.
Cette branche ne constitue pas une catégorie générale pour
toute activité d'aide, d'assistance ou d'accompagnement.

3. SERVICE MEDICO SOCIAL
Regroupe les fonctions dont la mission principale relève
de l'accompagnement social, éducatif, de l'autonomie,
de l'inclusion ou du soutien à la vie quotidienne.
Le rattachement dépend de la nature de la mission et non
du lieu d'exercice ou du public accompagné.

4. AUTRES PROFESSIONNEL DE LA SANTE
Regroupe les professions relevant réellement du domaine
sanitaire, paramédical ou des activités professionnelles
de santé, lorsqu'aucune autre branche spécifique ne convient.
Cette catégorie ne doit pas accueillir automatiquement
toutes les personnes travaillant dans un établissement de santé.


5. INFIRMIER
Regroupe les professions infirmières et leurs spécialisations
lorsqu'elles correspondent à une qualification infirmière.

6. KINE
Regroupe les professions de kinésithérapie.

7. PHARMACIEN
Regroupe les professions correspondant à la qualification
et à l'exercice du métier de pharmacien.
Les autres métiers intervenant dans le domaine pharmaceutique
ne sont pas automatiquement rattachés à cette branche.

8. PSYCHOLOGUE
Regroupe les professions correspondant à la qualification
et à l'exercice du métier de psychologue.
Une activité portant sur la psychologie ou l'accompagnement
psychologique ne suffit pas à établir cette qualification.

9. DENTISTE
Regroupe les professions correspondant à l'exercice
de la chirurgie dentaire.
Les fonctions d'assistance ou de soutien dentaire ne sont
pas automatiquement rattachées à cette branche.

10. ORTHOPHONISTE
Regroupe les professions d'orthophonie.

11. SAGE FEMME
Regroupe les professions de sage-femme.

12. VETERINAIRE
Regroupe les professions vétérinaires.

13. ADMINISTRATIF / CADRE SANTE
Regroupe les fonctions dont la mission principale relève
de l'administration, de la gestion, de l'organisation,
de la direction ou de l'encadrement dans le domaine sanitaire.
Une fonction de coordination ou de responsabilité ne suffit
pas à elle seule : la nature réelle de la fonction doit être établie.

14. AGENT DE SERVICE ASH
Regroupe les fonctions de service hospitalier, d'entretien,
d'hygiène et de logistique hôtelière.
Le simple fait de travailler dans un établissement de santé
ne justifie pas un classement dans cette branche.

15. NON PRIS EN CHARGE
Regroupe les professions et situations qui ne relèvent pas
du périmètre sanitaire ou médico-social défini.
Une profession inconnue ou insuffisamment détaillée ne doit
pas être considérée automatiquement comme hors santé.
Les métiers qui semblent n'avoir VRAIMENT aucun lien avec le domaine de la santé doivent être dans cette catégorie.
Si c'est pas de la santé, ça va dans cette catégorie et pas une autre

REGLES GENERALES DE DELIMITATION

- Une branche représente une famille de classement et non
  nécessairement une profession unique.
- Deux professions peuvent être complémentaires sans appartenir
  à la même branche.
- La proximité des activités ne prouve pas une équivalence.
- Le lieu de travail ne détermine pas à lui seul la branche.
- Le public accompagné ne détermine pas à lui seul la branche.
- Le secteur d'activité de l'établissement ne détermine pas
  à lui seul la branche.
- La fonction principale et la qualification explicitement
  indiquées sont prioritaires.
- Une branche spécifique doit être privilégiée uniquement
  lorsque son périmètre professionnel correspond réellement.
- AUTRES PROFESSIONNEL DE LA SANTE et SERVICE MEDICO SOCIAL
  ne sont pas des catégories interchangeables.
- En cas de doute, ne déduis jamais une qualification absente
  de l'intitulé.
- Ne force pas une affectation simplement pour obtenir
  une classification plus précise.

REGLES COMPLEMENTAIRES

- Les métiers du soin, de la petite enfance et de l'accompagnement font partie de la santé
  (auxiliaire de puériculture, puéricultrice, auxiliaire de vie, AMP, AES, ambulancier, brancardier,
  manipulateur radio, préparateur en pharmacie, technicien de laboratoire, diététicien, ergothérapeute,
  psychomotricien, éducateur spécialisé, assistant social...). Ils ne vont jamais dans NON PRIS EN CHARGE.
- Auxiliaire de puériculture et puéricultrice : AUTRES PROFESSIONNELS DE LA SANTE.
- SANS EMPLOI, DEMANDEUR D'EMPLOI, SANS PROFESSION, RETRAITE (sans métier de santé précisé) et GRAND PUBLIC :
  NON PRIS EN CHARGE.
- Un étudiant ou élève dans une filière de santé : branche du métier visé (étudiant infirmier : INFIRMIER).
  Un étudiant hors santé : NON PRIS EN CHARGE.
- Un professionnel de santé retraité garde la branche de son métier. Si c'est retraité 
"""

# Définitions alignées sur les noms de branches utilisés
PRECISIONS = PRECISIONS.replace("AUTRES PROFESSIONNEL DE LA SANTE", "AUTRES PROFESSIONNELS DE LA SANTE")
if "JOURNALISTE" not in PRECISIONS:
    PRECISIONS += """
16. JOURNALISTE
Regroupe les professions du journalisme et des médias (journaliste, reporter, journaliste reporter d'images,
rédacteur, chroniqueur).
"""

NC = "NC"
EFFORT_B = "high"
EXCLURE = {"NC"}                                   # valeurs qui ne sont pas de vraies branches : jamais proposées
FICHIER = "corresp_metierxprofil_branche.json"     # nouveau fichier : clés « métier||profil »
SEP = "||"
PROFIL_NPEC = "NON PRIS EN CHARGE"                 # un profil de cette valeur impose la branche NON PRIS EN CHARGE
COL_PROFIL = "Profil de l'appelant"
verrou_corresp = threading.Lock()


cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
corresp_metier_branche = json.load(open(FICHIER, encoding="utf-8"))

class Indisponible(Exception):
    pass


### 1.Harmonisation colonnes


def appeler(prompt, tentatives=5, effort="medium"):
    global appels
    cle = hashlib.sha1((MODELE + prompt).encode("utf-8")).hexdigest()
    if cle in cache:
        return cache[cle]

    for t in range(tentatives):
        payload = {
            "model": MODELE,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_completion_tokens": 16000,
            "stream": False,
        }
        if avec_reasoning[0]:
            payload["reasoning_effort"] = effort

        try:
            r = requests.post(URL, headers=HEADERS, json=payload, timeout=300)
        except requests.RequestException as e:
            print(f"  réseau : {e.__class__.__name__}, nouvel essai")
            time.sleep(5 * (t + 1))
            continue

        if r.status_code == 200:
            try:
                choix = r.json()["choices"][0]
                texte = choix["message"].get("content") or ""
            except Exception:
                texte, choix = "", {}
            if texte.strip():
                appels += 1
                cache[cle] = texte
                json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
                return texte
            print(f"  réponse vide (finish_reason={choix.get('finish_reason')}), nouvel essai")
            time.sleep(3)
            continue

        print(f"  HTTP {r.status_code} : {r.text[:200]}")
        if r.status_code in (400, 422) and "reasoning_effort" in payload:
            avec_reasoning[0] = False                # Albert refuse ce paramètre : on le retire
            continue
        if r.status_code in (401, 403):
            raise SystemExit("Clé ALBERT_KEY invalide ou droits insuffisants.")
        if r.status_code == 404:
            raise SystemExit(f"Modèle introuvable : {MODELE}. Voir la liste via GET /v1/models.")
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After", 10 * (t + 1))))
        else:
            time.sleep(5 * 2 ** t)                   # 500, 502, 503... : attente progressive

    raise Indisponible("Albert indisponible après plusieurs tentatives")

def associer(col, chaine):
    """Retourne la valeur de la colonne à laquelle la chaîne est rattachée.
    Référence : correspondance_colonnes.xlsx (feuille = colonne ; label -> nouvelle_valeur).
    - chaîne déjà présente dans la colonne « label » du fichier : sa nouvelle_valeur est renvoyée, ni appel, ni écriture
    - sinon : valeur trouvée localement (casse/accents), ou candidats proches puis Albert, ou nouvelle valeur
        et la ligne label = chaîne, nouvelle_valeur = résultat est ajoutée au fichier
    - Albert indisponible : renvoie None, rien n'est enregistré
    Le fichier est relu à l'appel si sa date de modification a changé. Écriture : associer.flush_tous ajouts
    (défaut 1 = immédiate), à la fin du programme (atexit), ou à la demande avec associer.sauver().
    Cadence Albert : associer.max_par_minute requêtes/minute (défaut 30)."""
    import difflib, unicodedata, atexit
    from collections import deque

    chaine = str(chaine).strip()
    if not chaine:
        return None

    fichier = "correspondance_colonnes.xlsx"
    feuille = col[:31]
    COLS = ["label", "nouvelle_valeur", "nb_lignes"]

    def norm(s):
        s = unicodedata.normalize("NFD", str(s).upper())
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        return re.sub(r"[^A-Z0-9 ]", " ", s).split()

    def mtime():
        return os.path.getmtime(fichier) if os.path.exists(fichier) else None

    etat = associer.__dict__.setdefault("etat", {})

    # --- écriture dans le fichier (définie une seule fois) ---
    if not hasattr(associer, "sauver"):
        def sauver():
            en_attente = {c: e for c, e in etat.items() if e["nouveaux"]}
            if not en_attente:
                print("  sauver : rien à écrire")
                return
            # relecture du fichier au moment de l'écriture : on n'écrit que les labels absents de la colonne « label »
            feuilles = (pd.read_excel(fichier, sheet_name=None, dtype=str, keep_default_na=False)
                        if os.path.exists(fichier) else {})
            maj = {}
            for c, e in en_attente.items():
                base = feuilles.get(c[:31], pd.DataFrame(columns=COLS))
                for k in COLS:
                    if k not in base:
                        base[k] = ""
                presents = set(base["label"].astype(str).str.strip())
                a_ecrire = [n for n in e["nouveaux"] if n["label"] not in presents]
                if a_ecrire:
                    base = pd.concat([base, pd.DataFrame(a_ecrire)], ignore_index=True)
                    base = base.sort_values(["nouvelle_valeur", "label"]).reset_index(drop=True)
                    feuilles[c[:31]] = base
                maj[c] = (base, len(a_ecrire))
            n = sum(k for _, k in maj.values())
            if n:
                tmp = fichier.replace(".xlsx", "_tmp.xlsx")
                try:
                    with pd.ExcelWriter(tmp) as xl:
                        for nom, d in feuilles.items():
                            d.to_excel(xl, sheet_name=nom, index=False)
                    os.replace(tmp, fichier)
                except Exception as ex:
                    print(f"  ÉCRITURE ÉCHOUÉE ({ex.__class__.__name__}) : {ex}. "
                          f"Fichier ouvert dans Excel ? Les ajouts restent en mémoire, relancez associer.sauver().")
                    return
            for c, (d, _) in maj.items():
                etat[c]["df"], etat[c]["nouveaux"] = d, []
            for e in etat.values():
                e["mtime"] = mtime()                  # le fichier vient d'être écrit par nous : pas de relecture inutile
            print(f"  sauver : {n} ligne(s) écrite(s) dans {fichier}" if n
                  else "  sauver : rien à écrire (labels déjà présents dans le fichier)")

        associer.sauver = sauver
        associer.appels_ts = deque()
        atexit.register(sauver)

    # --- (re)chargement de la feuille de la colonne : au premier appel, ou si le fichier a changé ---
    def charger():
        d = pd.DataFrame(columns=COLS)
        if os.path.exists(fichier):
            try:
                d = pd.read_excel(fichier, sheet_name=feuille, dtype=str, keep_default_na=False)
            except ValueError:                       # feuille absente
                pass
        for k in COLS:
            if k not in d:
                d[k] = ""
        d["label"] = d["label"].astype(str).str.strip()
        d["nouvelle_valeur"] = d["nouvelle_valeur"].astype(str).str.strip()
        d = d[(d["label"] != "") & (d["nouvelle_valeur"] != "")].reset_index(drop=True)

        en_attente = etat[col]["nouveaux"] if col in etat else []       # ajouts pas encore écrits : conservés
        labels = dict(zip(d["label"], d["nouvelle_valeur"]))
        valeurs = {v: norm(v) for v in set(d["nouvelle_valeur"])}
        for n in en_attente:
            labels.setdefault(n["label"], n["nouvelle_valeur"])
            valeurs.setdefault(n["nouvelle_valeur"], norm(n["nouvelle_valeur"]))
        index = {" ".join(norm(l)): v for l, v in labels.items()}
        index.update({" ".join(m): v for v, m in valeurs.items()})
        etat[col] = {"df": d, "valeurs": valeurs, "index": index, "labels": labels,
                     "nouveaux": en_attente, "mtime": mtime()}

    if col not in etat or etat[col]["mtime"] != mtime():
        charger()
    e = etat[col]

    # 0. La chaîne est déjà dans la colonne « label » du fichier : valeur renvoyée, AUCUNE écriture
    if chaine in e["labels"]:
        return e["labels"][chaine]

    mots_c = norm(chaine)
    texte_c = " ".join(mots_c)

    # 1. Connue à la casse/aux accents près (label ou valeur finale), sans appel
    if texte_c in e["index"]:
        resultat = e["index"][texte_c]
    else:
        # 2. Préfiltrage local des candidats
        scores = []
        sm = difflib.SequenceMatcher(None, "", texte_c)
        for v, mots_v in e["valeurs"].items():
            texte_v = " ".join(mots_v)
            prefixe = any(len(a) >= 3 and len(b) >= 3 and a[:3] == b[:3] for a in mots_c for b in mots_v)
            sigle = len(mots_c) == 1 and len(texte_c) >= 2 and texte_c == "".join(m[0] for m in mots_v)
            score = 0.0
            sm.set_seq1(texte_v)
            if sm.real_quick_ratio() >= 0.5 and sm.quick_ratio() >= 0.5:
                score = sm.ratio()
            if score >= 0.5 or prefixe or sigle:
                scores.append((score + (0.5 if sigle else 0), v))
        candidats = [v for _, v in sorted(scores, reverse=True)[:40]]

        if not candidats:
            resultat = chaine                        # rien de proche : nouvelle valeur, sans appel
        else:
            # 3. Albert tranche parmi les candidats (cadence limitée)
            ts, limite = associer.appels_ts, getattr(associer, "max_par_minute", 30)
            while ts and time.time() - ts[0] > 60:
                ts.popleft()
            if len(ts) >= limite:
                time.sleep(max(0, 61 - (time.time() - ts[0])))
            try:
                reponse = appeler(PROMPT_ASSOC.format(
                    nom=col, valeurs="\n".join(candidats), chaine=chaine,
                    regles=REGLES, exemples=EXEMPLES.get(col, "")), effort="high")
            except Indisponible:
                print(f"  « {chaine} » non traitée (Albert indisponible), à relancer plus tard")
                return None
            ts.append(time.time())
            choix = reponse.strip().splitlines()[0].strip().strip("`\"' ")
            resultat = choix if choix in candidats else chaine

        if resultat not in e["valeurs"]:             # nouvelle valeur finale : mémoire à jour
            e["valeurs"][resultat] = norm(resultat)
            e["index"][" ".join(e["valeurs"][resultat])] = resultat
        e["index"][texte_c] = resultat

    # 4. La chaîne n'est pas dans la colonne « label » : on ajoute label = chaîne, nouvelle_valeur = résultat
    e["labels"][chaine] = resultat
    e["nouveaux"].append({"label": chaine, "nouvelle_valeur": resultat, "nb_lignes": "1"})
    if sum(len(x["nouveaux"]) for x in etat.values()) >= getattr(associer, "flush_tous", 1):
        associer.sauver()

    return resultat

def associer_colonne(serie, col):
    """Applique associer() aux valeurs uniques d'une colonne.
    - dédoublonne avant d'appeler associer (une seule résolution par valeur distincte)
    - les lignes à ajouter sont écrites une seule fois à la fin (sinon chaque ajout réécrirait le fichier)
    - une valeur non traitée (Albert indisponible) reste inchangée"""
    uniques = serie.dropna().astype(str).str.strip().unique()
    resultat = {}
    debut = time.time()
    ancien_seuil = getattr(associer, "flush_tous", 1)
    associer.flush_tous = 10 ** 9                     # pas d'écriture pendant la boucle
    try:
        for n, s in enumerate(uniques, 1):
            resultat[s] = associer(col, s)
            if n % 25 == 0 or n == len(uniques):
                print(f"  {col} : {n}/{len(uniques)} ({time.time() - debut:.0f}s)")
    finally:
        associer.flush_tous = ancien_seuil
        if hasattr(associer, "sauver"):
            associer.sauver()                         # écriture unique, même en cas d'erreur
    return serie.map(lambda x: (resultat.get(str(x).strip()) or x) if pd.notna(x) else x)


### 2.Traitement du profil
#
# Principe : le modèle ne juge QUE le profil (cas 1 / 2 / 3). La décision finale est appliquée par le CODE :
#   (0) profil déjà une des 3 catégories                    -> inchangé
#   (1) profil très lié à la santé                           -> statut étudiant ? ETUDIANT EN SANTE : PROFESSIONNEL DE SANTE
#   (2) profil absolument sans lien avec la santé            -> NON PRIS EN CHARGE
#   (3) profil vague / ambigu (GRAND PUBLIC compris)         -> branche liée à la santé ?
#                                                               statut étudiant ? ETUDIANT EN SANTE : PROFESSIONNEL DE SANTE
#                                                               sinon NON PRIS EN CHARGE
# Mémoire : le cas de chaque profil est enregistré (feuille « cas_profils ») : un profil déjà jugé n'est jamais re-raisonné,
# et chaque combinaison (profil, statut, branche) décidée est enregistrée explicitement (feuille « transformations »).

PROFIL_SANTE = "PROFESSIONNEL DE SANTE"
PROFIL_ETUDIANT = "ETUDIANT EN SANTE"
PROFILS = [PROFIL_ETUDIANT, PROFIL_SANTE, PROFIL_NPEC]
EFFORT_PROFIL = "high"
COL_STATUT = "Statut de l'appelant"
COL_BRANCHE = "Branche professionnelle"
FICHIER_TRANSFO = "transformations_profil_v2.xlsx"   # NOUVEAU fichier : les anciennes décisions (fausses) ne sont pas reprises
COLS_TRANSFO = ["cas", "profil_base", "statut", "branche", "profil_final", "nature_profil", "base_decision",
                "source", "raison", "description", "nb_lignes", "premiere_decision"]
COLS_CAS = ["profil", "cas", "raison", "date"]
NATURE_CAS = {"1": "PRECIS_SANTE", "2": "PRECIS_HORS_SANTE", "3": "VAGUE"}
CAS_TEXTE = {
    "1": "profil très lié à la santé : étudiant ou professionnel déduit du statut",
    "2": "profil sans aucun lien avec la santé : NON PRIS EN CHARGE",
    "3": "profil vague : décision d'après la branche (lien avec la santé ?) puis le statut"}
SANS_INFO_PROFIL = {"", "NC", "NAN", "NA", "N", "NON RENSEIGNE", "NONE", "NULL", "0", "X", "AUCUN", "AUCUNE",
                    "RAS", "INCONNU", "SANS OBJET", "NON CONCERNE", "TEST", "ERREUR"}
VAGUES_PROFIL = {"GRAND PUBLIC", "AUTRE", "AUTRES", "ETUDIANT", "SALARIE", "LIBERAL", "RETRAITE"}
journal_profil = []                  # trace : (valeur, catégorie, source, raison)


def _cle_profil(s):
    """Forme comparable : majuscules, sans accents ni ponctuation."""
    s = unicodedata.normalize("NFD", str(s).upper())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9]+", " ", s).strip()

CATEGORIES_PROFIL = {_cle_profil(p): p for p in PROFILS}
CATEGORIES_PROFIL["NON PRISE EN CHARGE"] = PROFIL_NPEC

def _val(x):
    return "NC" if pd.isna(x) or not str(x).strip() else str(x).strip()

def _sans_info(x):
    """Statut ou branche sans information exploitable (NC, vide, NON PRIS EN CHARGE...) = pas de lien avec la santé."""
    k = _cle_profil(x)
    return k in SANS_INFO_PROFIL or k in ("NON PRIS EN CHARGE", "NON PRISE EN CHARGE")

ETU_STATUT = {}      # {statut: True/False} : jugé par Albert (reasoning), mémorisé dans la feuille « statuts_etudiant »
COLS_STATUT = ["statut", "etudiant", "raison", "date"]

def _statut_etudiant(statut):
    """Le statut est-il lié à un étudiant ? Valeur jugée par Albert (ETU_STATUT), jamais par mots-clés."""
    return ETU_STATUT.get(statut, False)

SANTE_BRANCHE = {}   # {branche: True/False} : jugé par Albert (reasoning), mémorisé dans la feuille « branches_sante »
COLS_BRANCHE = ["branche", "lien_sante", "raison", "date"]

def _branche_sante(branche):
    """La branche a-t-elle un réel lien avec la santé ? Valeur jugée par Albert (SANTE_BRANCHE)."""
    return SANTE_BRANCHE.get(branche, False)

PROMPT_BRANCHE_SANTE = """Colonne « Branche professionnelle » : branche attribuée à une personne qui contacte un service d'aide
aux professionnels de santé (exemples : MEDECIN, INFIRMIER, SERVICE MEDICO SOCIAL, ADMINISTRATIF / CADRE SANTE, AGENT DE SERVICE ASH,
NON PRIS EN CHARGE, NC...). Pour chaque branche, juge si elle a un RÉEL LIEN AVEC LA SANTÉ (soin, paramédical, pharmacie,
médico-social, social, petite enfance, vétérinaire, fonctions administratives/logistiques/techniques de la santé) ou non.
NON PRIS EN CHARGE, NC et les valeurs sans information n'ont pas de lien avec la santé. Ne déduis rien qui ne soit pas dans la valeur.

Réponds uniquement par des lignes au format :
numéro | OUI ou NON | raison en 10 mots maximum
Chaque numéro doit apparaître exactement une fois. Aucun autre texte.

{lot}"""

PROMPT_STATUT = """Colonne « Statut de l'appelant » : statut d'une personne qui contacte un service d'aide aux professionnels
de santé. Pour chaque statut, juge s'il est LIÉ À UN ÉTUDIANT (personne en formation : étudiant, élève, interne, externe,
apprenti, stagiaire en formation, ou toute formulation équivalente, fautes et abréviations comprises) ou non.
Un statut de professionnel en activité (SALARIE, LIBERAL, RETRAITE...) ou sans information (NC...) n'est pas lié à un étudiant.
Ne déduis rien qui ne soit pas dans la valeur.

Réponds uniquement par des lignes au format :
numéro | OUI ou NON | raison en 10 mots maximum
Chaque numéro doit apparaître exactement une fois. Aucun autre texte.

{lot}"""

def _cas_de(l):
    if l.get("cas") in ("1", "2", "3"):
        return l["cas"]
    return {v: k for k, v in NATURE_CAS.items()}.get(l.get("nature_profil", ""), "")


def decider(cas, statut, branche):
    """Règles (1), (2), (3) appliquées par le code. Retourne (catégorie, base, raison)."""
    etu = _statut_etudiant(statut)
    if cas == "2":
        return PROFIL_NPEC, "PROFIL", "profil sans aucun lien avec la santé"
    if cas == "1":
        return ((PROFIL_ETUDIANT, "STATUT", f"profil lié à la santé, statut {statut} = étudiant") if etu else
                (PROFIL_SANTE, "STATUT", f"profil lié à la santé, statut {statut} = pas étudiant"))
    # cas 3 : on se base sur la branche
    if not _branche_sante(branche):
        return PROFIL_NPEC, "BRANCHE", f"profil vague et branche {branche} sans lien avec la santé"
    return ((PROFIL_ETUDIANT, "STATUT+BRANCHE", f"profil vague, branche {branche} liée à la santé, statut {statut} = étudiant") if etu else
            (PROFIL_SANTE, "STATUT+BRANCHE", f"profil vague, branche {branche} liée à la santé, statut {statut} = pas étudiant"))


LISTE_PROFESSIONS_SANTE = """Professions médicales et de la pharmacie : chirurgien-dentiste, médecin, pharmacien, physicien médical,
préparateur en pharmacie, sage-femme.
Auxiliaires médicaux : aide-soignant, ambulancier, assistant dentaire, assistant de régulation médicale, audioprothésiste,
auxiliaire de puériculture, diététicien, épithésiste, ergothérapeute, infirmier, manipulateur en électroradiologie,
masseur-kinésithérapeute, opticien-lunetier, orthésiste, orthophoniste, orthoptiste, pédicure-podologue, psychomotricien,
technicien de laboratoire médical.
Autres professions réglementées : accompagnateur à la mobilité, accompagnateur de personnes âgées, AESH, agent de crèche,
agent de service médico-social, aide à domicile, aide médico-psychologique (AMP/AES), aide ménager, assistant audioprothésiste,
assistant en soins en gérontologie, assistant familial, assistant médical, assistante maternelle, autres personnels socio-éducatifs,
auxiliaire de vie sociale (AVS), auxiliaire vétérinaire, cadre d'intervention socio-éducative, cadre de santé,
cadre et agent administratif (finance, RH...), cadre et agent logistique (archiviste, secrétaire, comptable...),
cadre et agent technique (agent des services hospitaliers, brancardier, plombier...), chiropracteur,
conseiller en économie sociale et familiale, délégué de l'assurance maladie, directeur des soins,
éducateur (spécialisé, de jeunes enfants, technique spécialisé), encadrant et responsable d'unité d'intervention sociale,
enseignant en activité physique adaptée (APA), ingénieur (biomédical, qualité, informatique...),
métiers de l'industrie pharmaceutique (production, R&D, qualité, réglementaire, promotion...), moniteur éducateur, ostéopathe,
ostéopathe animalier, prothésiste dentaire, psychologue, psychothérapeute, sapeur-pompier, secrétaire médical,
technicien de l'intervention sociale et familiale, vétérinaire, visiteur médical.
Autres professions non réglementées : brancardier, directeur et coordonnateur de MSP et CPTS, médiateur en santé,
optométriste, psychanalyste, sophrologue."""

PROMPT_PROFIL_LOT = """Colonne « Profil de l'appelant » : valeur saisie librement par une personne qui contacte un service d'aide
aux professionnels de santé. Tu juges UNIQUEMENT le PROFIL (tu ne connais ni son statut ni sa branche, et tu n'as pas à les deviner).

Classe chaque profil dans UN des 3 cas :

CAS 1 : le profil est TRÈS LIÉ À LA SANTÉ : profession de la liste ci-dessous ou voisine, soin, paramédical, pharmacie,
médico-social, social, petite enfance, vétérinaire, fonction administrative/logistique/technique d'un établissement de santé ;
ou service, structure, secteur de santé (EHPAD, HOPITAL, CLINIQUE, PMI, SSIAD, AP-HP...). Les fautes, abréviations et variantes
comptent (IDE, AS, ASH, kiné...). Un étudiant/élève/interne dans une filière de santé est aussi cas 1.

CAS 2 : le profil n'a ABSOLUMENT AUCUN lien avec la santé et tu en es TOTALEMENT SÛR (JOURNALISTE, AVOCAT, BOULANGER,
étudiant en droit...).

CAS 3 : le profil est VAGUE ou AMBIGU : il ne permet pas, seul, de savoir si la personne relève de la santé. Par exemple :
GRAND PUBLIC (qui peut parfois avoir un lien avec la santé), PARTICULIER, USAGER, AUTRES, DIVERS, statut générique (SALARIE,
LIBERAL, RETRAITE, EMPLOYE, STAGIAIRE, BENEVOLE), « étudiant » sans filière, fonction sans domaine (AGENT, CADRE, RESPONSABLE,
ASSISTANT, TECHNICIEN, DIRECTEUR), valeur sans information (NC, NAN, INCONNU...), valeur inintelligible.

Au moindre doute entre cas 1 et cas 3, ou entre cas 2 et cas 3 : cas 3. Ne déduis rien qui ne soit pas dans la valeur.

LISTE DES PROFESSIONNELS DE SANTÉ CIBLÉS (non exhaustive) :
{liste}

Réponds uniquement par des lignes au format :
numéro | cas | raison en 12 mots maximum
Chaque numéro doit apparaître exactement une fois. Aucun autre texte.

{lot}"""


def _description(c, d):
    p, s, b = c
    cas = d.get("cas", "")
    return (f"Cas {cas or '?'} ({CAS_TEXTE.get(cas, 'cas non déterminé')}). "
            f"Profil « {p} », statut {s}, branche {b} -> {d['cat']}. "
            f"Décidé d'après {d.get('base') or 'non renseigné'}. Source du cas : {d['source']}. Raison : {d['raison']}.")

def _lire_transfos():
    """Mémoire des décisions par combinaison : {(profil_base, statut, branche): ligne}."""
    if not os.path.exists(FICHIER_TRANSFO):
        return {}
    try:
        d = pd.read_excel(FICHIER_TRANSFO, sheet_name="transformations", dtype=str, keep_default_na=False)
    except ValueError:
        return {}
    for k in COLS_TRANSFO:
        if k not in d:
            d[k] = ""
    return {(r.profil_base, r.statut, r.branche): r._asdict() for r in d[COLS_TRANSFO].itertuples(index=False)}

def _lire_cas_profils():
    """Mémoire du cas de chaque profil : {profil: (cas, raison)}. Un profil présent ici n'est JAMAIS re-raisonné."""
    if not os.path.exists(FICHIER_TRANSFO):
        return {}
    try:
        d = pd.read_excel(FICHIER_TRANSFO, sheet_name="cas_profils", dtype=str, keep_default_na=False)
    except ValueError:
        return {}
    return {r.profil: (r.cas, r.raison) for r in d.itertuples(index=False) if r.cas in ("1", "2", "3")}

def _lire_statuts():
    """Mémoire des statuts jugés : {statut: (etudiant bool, raison, date)}."""
    if not os.path.exists(FICHIER_TRANSFO):
        return {}
    try:
        d = pd.read_excel(FICHIER_TRANSFO, sheet_name="statuts_etudiant", dtype=str, keep_default_na=False)
    except ValueError:
        return {}
    return {r.statut: (r.etudiant == "OUI", r.raison, r.date) for r in d.itertuples(index=False)
            if r.etudiant in ("OUI", "NON")}

def _lire_branches():
    """Mémoire des branches jugées : {branche: (lien_sante bool, raison, date)}."""
    if not os.path.exists(FICHIER_TRANSFO):
        return {}
    try:
        d = pd.read_excel(FICHIER_TRANSFO, sheet_name="branches_sante", dtype=str, keep_default_na=False)
    except ValueError:
        return {}
    return {r.branche: (r.lien_sante == "OUI", r.raison, r.date) for r in d.itertuples(index=False)
            if r.lien_sante in ("OUI", "NON")}

def _ecrire_transfos(lignes, decisions_run, nouvelles, resume, cas_profils, statuts=None, branches=None):
    """Écriture atomique : transformations (mémoire cumulée), decisions_run, nouvelles_decisions, resume, cas_profils."""
    d = pd.DataFrame(list(lignes.values()), columns=COLS_TRANSFO)
    d = d.sort_values(["cas", "profil_final", "profil_base", "statut", "branche"]).reset_index(drop=True)
    r = (pd.DataFrame(decisions_run, columns=COLS_TRANSFO)
         .sort_values(["cas", "profil_base", "statut", "branche"]).reset_index(drop=True))
    n = pd.DataFrame(nouvelles, columns=COLS_TRANSFO)
    cp = pd.DataFrame([{"profil": p, "cas": c, "raison": rs, "date": dt} for p, (c, rs, dt) in cas_profils.items()],
                      columns=COLS_CAS).sort_values(["cas", "profil"]).reset_index(drop=True)

    st = pd.DataFrame([{"statut": s, "etudiant": "OUI" if e else "NON", "raison": rs, "date": dt}
                       for s, (e, rs, dt) in (statuts or {}).items()], columns=COLS_STATUT)
    st = st.sort_values(["etudiant", "statut"]).reset_index(drop=True)

    br = pd.DataFrame([{"branche": b, "lien_sante": "OUI" if e else "NON", "raison": rs, "date": dt}
                       for b, (e, rs, dt) in (branches or {}).items()], columns=COLS_BRANCHE)
    br = br.sort_values(["lien_sante", "branche"]).reset_index(drop=True)

    def ecrire(chemin):
        tmp = chemin.replace(".xlsx", "_tmp.xlsx")
        with pd.ExcelWriter(tmp) as xl:
            br.to_excel(xl, sheet_name="branches_sante", index=False)
            st.to_excel(xl, sheet_name="statuts_etudiant", index=False)
            d.to_excel(xl, sheet_name="transformations", index=False)
            r.to_excel(xl, sheet_name="decisions_run", index=False)
            n.to_excel(xl, sheet_name="nouvelles_decisions", index=False)
            resume.to_excel(xl, sheet_name="resume", index=False)
            cp.to_excel(xl, sheet_name="cas_profils", index=False)
        os.replace(tmp, chemin)

    chemin = FICHIER_TRANSFO
    try:
        ecrire(chemin)
    except Exception as ex:
        chemin = FICHIER_TRANSFO.replace(".xlsx", time.strftime("_%Y%m%d_%H%M%S.xlsx"))
        print(f"  !!! ÉCRITURE DE {FICHIER_TRANSFO} ÉCHOUÉE ({ex.__class__.__name__}) : fichier ouvert dans Excel ? "
              f"Décisions écrites dans {chemin} (à renommer pour qu'elles servent de mémoire).")
        try:
            ecrire(chemin)
        except Exception as ex2:
            print(f"  !!! ÉCRITURE IMPOSSIBLE ({ex2.__class__.__name__}) : {ex2}")
            return False

    relu = pd.read_excel(chemin, sheet_name="decisions_run", dtype=str, keep_default_na=False)
    present = set(zip(relu["profil_base"], relu["statut"], relu["branche"]))
    attendu = {(l["profil_base"], l["statut"], l["branche"]) for l in decisions_run}
    manque = attendu - present
    print(f"  vérification : {len(attendu) - len(manque)}/{len(attendu)} décisions retrouvées dans {chemin}")
    if manque:
        print(f"  !!! décisions absentes du fichier : {sorted(manque)[:20]}")
    return not manque


def traiter_profil(serie, statut=None, branche=None, memoriser=True, chunk=20, workers=1, effort=EFFORT_PROFIL):
    """Classe « Profil de l'appelant » en PROFESSIONNEL DE SANTE / ETUDIANT EN SANTE / NON PRIS EN CHARGE.
    - cas 0 : profil déjà une des 3 catégories -> inchangé, ni requête ni enregistrement
    - le CAS (1, 2, 3) de chaque profil unique est jugé une seule fois par Albert (reasoning), puis mémorisé
    - la décision de chaque combinaison (profil, statut, branche) est appliquée par decider() (règles du code)
    - toute décision des cas 1, 2, 3 est enregistrée explicitement dans FICHIER_TRANSFO"""
    idx = serie.index
    statut = statut if statut is not None else pd.Series("NC", index=idx)
    branche = branche if branche is not None else pd.Series("NC", index=idx)
    df = pd.DataFrame({"p": serie.map(_val), "s": statut.reindex(idx).map(_val), "b": branche.reindex(idx).map(_val)})
    nb = df.groupby(["p", "s", "b"]).size()
    combos = list(nb.index)
    aujourd_hui = time.strftime("%Y-%m-%d %H:%M")

    # --- 1. cas de chaque profil unique ---
    memoire = _lire_cas_profils()                                   # {profil: (cas, raison)}
    cas_profils = {p: (c, r, "") for p, (c, r) in memoire.items()}   # écrit à la fin (avec date)
    ancien = pd.read_excel(FICHIER_TRANSFO, sheet_name="cas_profils", dtype=str, keep_default_na=False) \
        if os.path.exists(FICHIER_TRANSFO) and memoire else None
    if ancien is not None:
        cas_profils = {r.profil: (r.cas, r.raison, r.date) for r in ancien.itertuples(index=False) if r.cas in ("1", "2", "3")}

    cas_source, a_juger = {}, []
    for p in sorted(set(df["p"])):
        k = _cle_profil(p)
        if k in CATEGORIES_PROFIL:
            cas_source[p] = ("0", "inchangé", "le profil est déjà une des 3 catégories")
        elif p in cas_profils:
            cas_source[p] = (cas_profils[p][0], "mémoire", cas_profils[p][1])
        else:
            a_juger.append(p)
    print(f"{len(set(df['p']))} profils uniques : {sum(v[1] == 'inchangé' for v in cas_source.values())} cas 0, "
          f"{sum(v[1] == 'mémoire' for v in cas_source.values())} en mémoire, "
          f"{len(a_juger)} à juger en reasoning {effort}")

    def albert(liste):
        ids = dict(enumerate(liste))
        res = {}

        def classer(liste_ids):
            lot = "\n".join(f"{i}|{ids[i]}" for i in liste_ids)
            rep = appeler(PROMPT_PROFIL_LOT.format(lot=lot, liste=LISTE_PROFESSIONS_SANTE), effort=effort)
            for ligne in rep.splitlines():
                parts = [x.strip() for x in ligne.strip().strip("`").split("|", 2)]
                if len(parts) < 2 or not parts[0].isdigit():
                    continue
                m = re.search(r"[123]", parts[1])
                i = int(parts[0])
                if m and i in liste_ids:
                    res.setdefault(ids[i], (m.group(0), parts[2] if len(parts) > 2 else ""))

        def rec(sous):
            try:
                classer(sous)
            except Indisponible:
                if len(sous) <= 1:
                    print(f"  {ids[sous[0]]} non classé (Albert indisponible)")
                    return
                m = len(sous) // 2
                rec(sous[:m]); rec(sous[m:])

        def passe(liste_ids, taille):
            lots = [liste_ids[k:k + taille] for k in range(0, len(liste_ids), taille)]
            if workers > 1:
                with ThreadPoolExecutor(workers) as ex:
                    list(ex.map(rec, lots))
            else:
                for n, l in enumerate(lots, 1):
                    rec(l)
                    print(f"  {n}/{len(lots)} lots")

        passe(list(ids), chunk)
        manquants = [i for i in ids if ids[i] not in res]
        if manquants:
            print(f"  {len(manquants)} profils oubliés, nouvel essai")
            passe(manquants, 3)
        return res

    if a_juger:
        for p, (cas, raison) in albert(a_juger).items():
            cas_source[p] = (cas, "albert", raison)
            cas_profils[p] = (cas, raison, aujourd_hui)
    echecs = [p for p in a_juger if p not in cas_source]
    if echecs:
        print(f"  {len(echecs)} profils non jugés (valeur inchangée, retentés au prochain run) : {echecs}")

    # --- 1 bis. chaque statut unique : lié à un étudiant ? (jugé par Albert, mémorisé) ---
    statuts_mem = _lire_statuts()
    ETU_STATUT.clear()
    a_juger_s = []
    for s in sorted(set(df["s"])):
        if s in statuts_mem:
            ETU_STATUT[s] = statuts_mem[s][0]
        elif _cle_profil(s) in SANS_INFO_PROFIL:                       # NC, vide... : aucune information
            ETU_STATUT[s] = False
            statuts_mem[s] = (False, "statut sans information", aujourd_hui)
        else:
            a_juger_s.append(s)
    print(f"{len(set(df['s']))} statuts uniques : {len(statuts_mem)} en mémoire, {len(a_juger_s)} à juger en reasoning {effort}")
    if a_juger_s:
        ids_s = dict(enumerate(a_juger_s))

        def juger_statuts(liste_ids):
            lot = "\n".join(f"{i}|{ids_s[i]}" for i in liste_ids)
            rep = appeler(PROMPT_STATUT.format(lot=lot), effort=effort)
            for ligne in rep.splitlines():
                parts = [x.strip() for x in ligne.strip().strip("`").split("|", 2)]
                if len(parts) < 2 or not parts[0].isdigit() or parts[1].upper()[:3] not in ("OUI", "NON"):
                    continue
                i = int(parts[0])
                if i in ids_s and ids_s[i] not in ETU_STATUT:
                    e = parts[1].upper().startswith("OUI")
                    ETU_STATUT[ids_s[i]] = e
                    statuts_mem[ids_s[i]] = (e, parts[2] if len(parts) > 2 else "", aujourd_hui)

        for tentative in range(2):                                     # 2e passe pour les oubliés
            restes = [i for i in ids_s if ids_s[i] not in ETU_STATUT]
            for k in range(0, len(restes), chunk):
                print(f"  statuts : lot {k // chunk + 1}/{-(-len(restes) // chunk)} (passe {tentative + 1})", flush=True)
                try:
                    juger_statuts(restes[k:k + chunk])
                except Indisponible:
                    print("  Albert indisponible pour des statuts, retentés au prochain run")
        non_juges = [s for s in a_juger_s if s not in ETU_STATUT]
        if non_juges:
            print(f"  statuts non jugés (traités comme non étudiants ce run, NON mémorisés) : {non_juges}")

    # --- 1 ter. chaque branche unique : lien avec la santé ? (jugé par Albert, mémorisé) ---
    branches_mem = _lire_branches()
    SANTE_BRANCHE.clear()
    a_juger_b = []
    for b in sorted(set(df["b"])):
        if b in branches_mem:
            SANTE_BRANCHE[b] = branches_mem[b][0]
        elif _sans_info(b):                                            # NC, vide, NON PRIS EN CHARGE : aucune branche attribuée
            SANTE_BRANCHE[b] = False
            branches_mem[b] = (False, "aucune branche attribuée (NC / NON PRIS EN CHARGE)", aujourd_hui)
        else:
            a_juger_b.append(b)
    print(f"{len(set(df['b']))} branches uniques : {len(branches_mem)} en mémoire, {len(a_juger_b)} à juger en reasoning {effort}")
    if a_juger_b:
        ids_b = dict(enumerate(a_juger_b))

        def juger_branches(liste_ids):
            lot = "\n".join(f"{i}|{ids_b[i]}" for i in liste_ids)
            rep = appeler(PROMPT_BRANCHE_SANTE.format(lot=lot), effort=effort)
            for ligne in rep.splitlines():
                parts = [x.strip() for x in ligne.strip().strip("`").split("|", 2)]
                if len(parts) < 2 or not parts[0].isdigit() or parts[1].upper()[:3] not in ("OUI", "NON"):
                    continue
                i = int(parts[0])
                if i in ids_b and ids_b[i] not in SANTE_BRANCHE:
                    e = parts[1].upper().startswith("OUI")
                    SANTE_BRANCHE[ids_b[i]] = e
                    branches_mem[ids_b[i]] = (e, parts[2] if len(parts) > 2 else "", aujourd_hui)

        for tentative in range(2):                                     # 2e passe pour les oubliés
            restes = [i for i in ids_b if ids_b[i] not in SANTE_BRANCHE]
            for k in range(0, len(restes), chunk):
                print(f"  branches : lot {k // chunk + 1}/{-(-len(restes) // chunk)} (passe {tentative + 1}) "
                      f"- {len(SANTE_BRANCHE)} branches jugées au total", flush=True)
                try:
                    juger_branches(restes[k:k + chunk])
                except Indisponible:
                    print("  Albert indisponible pour des branches, retentées au prochain run")
        non_juges = [b for b in a_juger_b if b not in SANTE_BRANCHE]
        if non_juges:
            print(f"  branches non jugées (traitées comme sans lien avec la santé ce run, NON mémorisées) : {non_juges}")

    # --- 2. décision de chaque combinaison, par les règles du code ---
    deja = _lire_transfos()
    mapping = {}
    for c in combos:
        p, s, b = c
        if p not in cas_source:
            continue
        cas, src, raison_cas = cas_source[p]
        if cas == "0":
            mapping[c] = dict(cat=CATEGORIES_PROFIL[_cle_profil(p)], cas="0", base="PROFIL", source=src, raison=raison_cas)
        else:
            cat, base, raison = decider(cas, s, b)
            mapping[c] = dict(cat=cat, cas=cas, base=base, source=f"{src} (cas du profil) + règles",
                              raison=f"{raison} ; cas du profil : {raison_cas}" if raison_cas else raison)
            journal_profil.append((" | ".join(c), cat, mapping[c]["source"], mapping[c]["raison"]))

    # --- 3. enregistrement explicite ---
    if memoriser:
        lignes, nouvelles, decisions_run = dict(deja), [], []
        for c in combos:
            d = mapping.get(c)
            if d is None or d["cas"] == "0":
                continue
            ligne = {"cas": d["cas"], "profil_base": c[0], "statut": c[1], "branche": c[2],
                     "profil_final": d["cat"], "nature_profil": NATURE_CAS.get(d["cas"], ""),
                     "base_decision": d["base"], "source": d["source"], "raison": d["raison"],
                     "description": _description(c, d), "nb_lignes": str(int(nb[c])),
                     "premiere_decision": deja[c]["premiere_decision"] if c in deja else aujourd_hui}
            if c not in deja or deja[c]["profil_final"] != d["cat"]:
                nouvelles.append(ligne)
            lignes[c] = ligne
            decisions_run.append(ligne)
        if decisions_run or a_juger or a_juger_s or a_juger_b:
            resume = (pd.DataFrame([{"profil_base": l["profil_base"], "profil_final": l["profil_final"],
                                     "nb_lignes": int(l["nb_lignes"])} for l in decisions_run],
                                   columns=["profil_base", "profil_final", "nb_lignes"])
                      .groupby(["profil_base", "profil_final"], as_index=False)["nb_lignes"].sum()
                      .sort_values(["profil_final", "nb_lignes"], ascending=[True, False]))
            if _ecrire_transfos(lignes, decisions_run, nouvelles, resume, cas_profils, statuts_mem, branches_mem):
                print(f"  {FICHIER_TRANSFO} : {len(nouvelles)} nouvelle(s) décision(s), {len(decisions_run)} pour ce fichier, "
                      f"{len(cas_profils)} profils en mémoire")
                for l in nouvelles[:20]:
                    print("   +", l["description"])
        else:
            print("  aucune décision à enregistrer (tout est cas 0)")

    resultat = pd.Series([mapping[(p, s, b)]["cat"] if (p, s, b) in mapping else orig
                          for p, s, b, orig in zip(df["p"], df["s"], df["b"], serie)], index=idx)
    print(resultat.value_counts(dropna=False).to_string())
    return resultat


FICHIER_COMBOS = "toutes_combinaisons_profil.xlsx"

def exporter_toutes_combinaisons(profil_base, profil_entree, statut, branche_avant, profil_final, branche_finale):
    """Écrit TOUTES les combinaisons rencontrées dans les données (cas 0 compris), avec la décision, dans
    toutes_combinaisons_profil.xlsx. Une ligne = une combinaison unique de profil d'origine (avant l'étape 5), statut,
    branche utilisée pour décider le profil, branche finale (après l'étape 6) et profil final, avec le cas, la source,
    la raison et la phrase explicite reprises de transformations_profil_v2.xlsx.
    Les séries ont le même index ; à appeler après l'étape 6 et avant le drop de « Statut de l'appelant »."""
    d = pd.DataFrame({"profil_base": profil_base.map(_val), "profil_entree": profil_entree.map(_val),
                      "statut": statut.map(_val), "branche_avant": branche_avant.map(_val),
                      "profil_final": profil_final.map(_val), "branche_finale": branche_finale.map(_val)})
    t = d.groupby(list(d.columns), as_index=False).size().rename(columns={"size": "nb_lignes"})
    deja = _lire_transfos()
    lignes = []
    for r in t.itertuples(index=False):
        l = deja.get((r.profil_entree, r.statut, r.branche_avant))
        if r.profil_base != r.profil_entree:                          # profil réécrit avant la classification (étape 5)
            cas, source = "étape 5", "règle étape 5"
            raison = f"profil {r.profil_base} réécrit d'après le statut {r.statut}"
            desc = f"Étape 5 : profil « {r.profil_base} » réécrit d'après le statut {r.statut} -> {r.profil_final}"
        elif l:
            cas, source, raison, desc = _cas_de(l) or "?", l["source"], l["raison"], l["description"]
        elif _cle_profil(r.profil_entree) in CATEGORIES_PROFIL:
            cas, source, raison = "0", "inchangé", "le profil était déjà une des 3 catégories"
            desc = f"Cas 0 : profil « {r.profil_entree} » déjà une des 3 catégories, inchangé"
        else:
            cas, source, raison, desc = "?", "non classé", "", "Non classé (voir les messages de la console)"
        lignes.append({"cas": cas, "profil_base": r.profil_base, "statut": r.statut, "branche_avant": r.branche_avant,
                       "branche_finale": r.branche_finale,
                       "branche_modifiee": "OUI" if r.branche_avant != r.branche_finale else "NON",
                       "profil_final": r.profil_final, "source": source, "raison": raison,
                       "nb_lignes": r.nb_lignes, "description": desc})
    out = (pd.DataFrame(lignes).sort_values(["cas", "profil_base", "statut", "branche_avant", "branche_finale"])
           .reset_index(drop=True))
    chemin = FICHIER_COMBOS
    try:
        out.to_excel(chemin, index=False)
    except Exception as ex:
        chemin = FICHIER_COMBOS.replace(".xlsx", time.strftime("_%Y%m%d_%H%M%S.xlsx"))
        print(f"  !!! ÉCRITURE DE {FICHIER_COMBOS} ÉCHOUÉE ({ex.__class__.__name__}) : écrit dans {chemin}")
        out.to_excel(chemin, index=False)
    print(f"  {chemin} : {len(out)} combinaisons uniques rencontrées "
          f"({int((out['branche_modifiee'] == 'OUI').sum())} où la branche a changé à l'étape 6)")
    return out



### 3.Correspondance métier et branche

def nettoyer(s):
    """Retire l'artefact de copier-coller [/](https://...) (affichage uniquement)."""
    return re.sub(r"\[/\]\([^)]*\)", "/", str(s)).strip()

# --- Profil et clés (métier, profil) ---
def est_npec(profil):
    return (profil is not None and not pd.isna(profil)
            and str(profil).strip().upper() in {"NON PRIS EN CHARGE", "NON PRISE EN CHARGE"})

def norm_profil(profil):
    """Profil normalisé : NON PRIS EN CHARGE (et sa variante) -> PROFIL_NPEC ; vide, NAN, NON RENSEIGNE -> NC."""
    if profil is None or pd.isna(profil):
        return NC
    if est_npec(profil):
        return PROFIL_NPEC
    s = str(profil).strip()
    return NC if s.upper() in {"", "NAN", "NON RENSEIGNE"} else s

def texte_profil(profil):
    """Profil affiché dans le prompt ; NC ou NON PRIS EN CHARGE -> « non précisé »."""
    p = norm_profil(profil)
    return "non précisé" if p in {NC, PROFIL_NPEC} else p

def cle_mp(metier, profil):
    """Clé du dictionnaire : (métier, profil normalisé), ou None si le métier est vide."""
    if metier is None or pd.isna(metier) or not str(metier).strip():
        return None
    return (str(metier).strip(), norm_profil(profil))

# --- Sauvegarde / chargement du dictionnaire (clés (m, p) <-> « m||p » dans le JSON) ---
def vers_json(d):
    return {f"{m}{SEP}{p}": v for (m, p), v in d.items()}

def depuis_json(d):
    out = {}
    for k, v in d.items():
        if SEP in k:
            m, p = k.rsplit(SEP, 1)
            out[(m, p or NC)] = v
    return out

def sauver_corresp():
    """Écriture atomique : le fichier n'est jamais à moitié écrit. À appeler sous verrou_corresp."""
    tmp = FICHIER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(vers_json(corresp_metierxprofil_branche), f, ensure_ascii=False, indent=1)
    os.replace(tmp, FICHIER)

if "corresp_metierxprofil_branche" not in globals():
    corresp_metierxprofil_branche = {}
normalise = {}
for (m, p), v in list(corresp_metierxprofil_branche.items()):          # clés déjà en mémoire (ex : multiples_final)
    k = cle_mp(m, p)
    if k is not None:
        normalise[k] = v
corresp_metierxprofil_branche.clear()
corresp_metierxprofil_branche.update(normalise)
if os.path.exists(FICHIER):
    sur_disque = depuis_json(json.load(open(FICHIER, encoding="utf-8")))
    for k, v in sur_disque.items():
        corresp_metierxprofil_branche.setdefault(k, v)                 # les valeurs déjà en mémoire gardent la priorité
    print(f"{len(sur_disque)} correspondances rechargées depuis {FICHIER}")
with verrou_corresp:
    sauver_corresp()

# --- Branches existantes choisissables (NC exclu) ---
branches_ok = sorted(b for b in BRANCHES if nettoyer(b) not in EXCLURE)
codes_b = {f"B{i + 1}": b for i, b in enumerate(branches_ok)}
liste_b = "\n".join(f"{c}|{nettoyer(b)}" for c, b in codes_b.items())

PROMPT_BRANCHE_UNIQUE = """Voici la liste des BRANCHES PROFESSIONNELLES existantes, au format 'code|branche' :
{branches}

Métier à classer : {metier}
Profil de la personne qui a déclaré ce métier : {profil}

Choisis UNE SEULE branche de la liste si le métier correspond clairement à l'une d'elles, selon sa fonction et
son périmètre professionnel réel d'après les définitions.

RÈGLES :
- Choisis uniquement parmi les branches de la liste. N'invente aucune branche.
- Le métier est saisi librement : corrige mentalement les fautes, abréviations et variantes d'écriture sans modifier son sens.
- Le profil est un CONTEXTE : il indique le statut de la personne (par exemple étudiant en santé, professionnel de santé).
  Utilise-le pour lever un doute (un « étudiant » dont le profil est « ETUDIANT EN SANTE » est dans une filière de santé),
  mais il ne remplace jamais le métier et ne permet pas de déduire un diplôme ou une qualification absente de l'intitulé.
  Si le profil est « non précisé », ignore-le.
- Ne déduis pas de diplôme, de qualification ou de spécialité absente de l'intitulé.
- Un métier clairement sans lien avec la santé ou le médico-social va dans NON PRIS EN CHARGE.
- Un métier clairement de santé sans branche spécialisée va dans AUTRES PROFESSIONNELS DE LA SANTE.
- Réponds AUCUNE si l'affectation est AMBIGUË : plusieurs branches aussi plausibles les unes que les autres,
  intitulé trop vague pour trancher (agent, assistant, responsable, étudiant, santé, hôpital...), ou métier inintelligible.
  En cas de doute réel, réponds AUCUNE : l'ancienne branche sera conservée.

DEFINITIONS DES BRANCHES A RESPECTER IMPERATIVEMENT :

{precisions}

Réponds par UNE seule ligne au format :
code ou AUCUNE | raison en 8 mots maximum
Aucun autre texte."""

journal = []                          # trace des décisions : (métier, profil, résultat, branche(s), raison)

def classer_high(metier, profil):
    """Retourne (branche, raison) ; branche = None si ambigu ; branche = False si pas de réponse exploitable."""
    try:
        rep = appeler(PROMPT_BRANCHE_UNIQUE.format(branches=liste_b, metier=metier, profil=texte_profil(profil),
                                                   precisions=PRECISIONS),
                      effort=EFFORT_B)
    except Indisponible as e:
        return False, f"Albert indisponible ({e})"
    for ligne in rep.splitlines():
        m = re.match(r"^\s*(AUCUNE|B\d+)\b\s*(?:\|\s*(.*))?$", ligne.strip().strip("`"), re.I)
        if not m:
            continue
        choix, raison = m.group(1).upper(), (m.group(2) or "").strip()
        if choix == "AUCUNE":
            return None, raison or "ambigu"
        if choix in codes_b:
            return codes_b[choix], raison
    return False, "réponse inexploitable"

def ajouter_a_liste(cle, anciennes):
    """Ambigu : dictionnaire[(métier, profil)] = liste contenant les anciennes branches, sans doublon.
    Si la combinaison a déjà une liste, on la complète ; sinon on la crée. À appeler sous verrou_corresp."""
    actuelle = corresp_metierxprofil_branche.get(cle)
    liste = list(actuelle) if isinstance(actuelle, list) else []
    for b in anciennes:
        if pd.notna(b) and b not in liste:
            liste.append(b)
    corresp_metierxprofil_branche[cle] = liste
    return liste

def associer_branche(metier, branche, profil=None, classer=True, anciennes=None):
    """Retourne la branche à utiliser pour le trio (métier, branche, profil).
    - profil NON PRIS EN CHARGE : branche NON PRIS EN CHARGE directement, sans requête ; la combinaison
      (métier, profil) est ajoutée au dictionnaire si elle est nouvelle (métier renseigné)
    - métier NC ou vide : branche inchangée
    - A : (métier, profil) dans corresp_metierxprofil_branche : valeur de la clé si ce n'est pas une liste, sinon branche inchangée
    - B : combinaison jamais rencontrée : reasoning high parmi les branches existantes, profil dans le prompt
        . non ambigu : la nouvelle branche remplace l'ancienne ; dictionnaire[(métier, profil)] = nouvelle branche
        . ambigu     : l'ancienne branche est conservée ; dictionnaire[(métier, profil)] = liste contenant l'ancienne
                       branche (ajoutée si elle n'y est pas déjà)
        . Albert indisponible / réponse inexploitable : branche inchangée, rien n'est enregistré
      Chaque ajout est sauvegardé tout de suite dans le JSON.
    anciennes : anciennes branches à mettre dans la liste en cas d'ambiguïté (par défaut : [branche]).
    classer=False : lecture seule du dictionnaire, aucune requête et aucune écriture."""
    cle = cle_mp(metier, profil)
    metier_nc = cle is None or cle[0].upper() == NC

    if est_npec(profil):                                           # le profil impose la branche
        if classer and not metier_nc and corresp_metierxprofil_branche.get(cle) != PROFIL_NPEC:
            with verrou_corresp:
                corresp_metierxprofil_branche[cle] = PROFIL_NPEC   # combinaison nouvelle : ajoutée et sauvegardée
                sauver_corresp()
        return PROFIL_NPEC
    if metier_nc:
        return branche

    for k in dict.fromkeys([cle, (cle[0].upper(), cle[1])]):       # A
        if k in corresp_metierxprofil_branche:
            v = corresp_metierxprofil_branche[k]
            return branche if isinstance(v, list) else v
    if not classer:
        return branche

    m, p = cle
    b, raison = classer_high(m, p)                                 # B
    if b is False:
        journal.append((m, p, "échec", "", raison))
        print(f"  « {m} » | {p} non traité : {raison}")
        return branche
    if b is None:                                                  # ambigu : on garde l'ancienne branche
        a_ajouter = list(anciennes) if anciennes is not None else [branche]
        with verrou_corresp:
            liste = ajouter_a_liste(cle, a_ajouter)                # clé = (métier, profil), valeur = liste avec l'ancienne branche
            sauver_corresp()
        journal.append((m, p, "ambigu", " | ".join(map(str, liste)), raison))
        print(f"  « {m} » | {p} ambigu ({raison}) : ancienne branche conservée, liste = {liste}")
        return branche
    journal.append((m, p, "classé", b, raison))                    # non ambigu : nouvelle branche
    print(f"  {m} | {p} -> {nettoyer(b)}  ({raison})")
    with verrou_corresp:
        corresp_metierxprofil_branche[cle] = b                     # clé = (métier, profil), valeur = nouvelle branche
        sauver_corresp()
    return b

def appliquer_branches(df, col_m="Métier", col_b="Branche professionnelle", col_profil=COL_PROFIL, workers=4):
    """Applique associer_branche à tout un DataFrame.
    - lignes au profil NON PRIS EN CHARGE : branche NON PRIS EN CHARGE, combinaisons nouvelles ajoutées au JSON (une écriture)
    - autres combinaisons (métier, profil) jamais rencontrées : classées en parallèle (une requête high chacune)
    - dernière passe : lecture seule du dictionnaire (aucune requête)"""
    m_str = df[col_m].astype("string").str.strip()
    if col_profil in df.columns:
        p_norm = df[col_profil].map(norm_profil)
    else:
        print(f"Colonne « {col_profil} » absente : le profil est traité comme NC.")
        p_norm = pd.Series(NC, index=df.index)

    m_up = m_str.fillna("").str.upper()
    valides = (m_up != "") & (m_up != NC)
    base = pd.DataFrame({"m": m_str, "p": p_norm, "b": df[col_b]})[valides]

    # 1. profil NON PRIS EN CHARGE : combinaisons nouvelles ajoutées en une seule écriture
    npec = base["p"] == PROFIL_NPEC
    nouveaux_npec = [k for k in {(m, PROFIL_NPEC) for m in base.loc[npec, "m"]}
                     if corresp_metierxprofil_branche.get(k) != PROFIL_NPEC]
    if nouveaux_npec:
        with verrou_corresp:
            for k in nouveaux_npec:
                corresp_metierxprofil_branche[k] = PROFIL_NPEC
            sauver_corresp()
    print(f"{int((p_norm == PROFIL_NPEC).sum())} lignes au profil {PROFIL_NPEC} -> branche imposée "
          f"({len(nouveaux_npec)} combinaisons ajoutées)")

    # 2. combinaisons (métier, profil) jamais rencontrées
    autres = base[~npec]
    inconnus = sorted({(m, p) for m, p in zip(autres["m"], autres["p"])
                       if (m, p) not in corresp_metierxprofil_branche
                       and (m.upper(), p) not in corresp_metierxprofil_branche})
    anciennes = (autres.dropna(subset=["b"]).groupby(["m", "p"])["b"]
                 .agg(lambda s: list(dict.fromkeys(s))).to_dict())
    print(f"{len(inconnus)} combinaisons (métier, profil) absentes du dictionnaire -> reasoning {EFFORT_B}")

    def traiter(k):
        liste = anciennes.get(k, [])
        associer_branche(k[0], liste[0] if liste else None, profil=k[1], anciennes=liste)

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(traiter, inconnus))

    # 3. le dictionnaire est à jour : cette passe lit seulement le dictionnaire (aucune requête)
    return pd.Series([associer_branche(m, b, profil=p, classer=False)
                      for m, b, p in zip(df[col_m], df[col_b], p_norm)], index=df.index)



# ---- MAIN : ajouter « import sys » avec les imports du haut du script ----

class Tee:
    """Tout ce qui s'affiche dans la console est aussi écrit dans le fichier de log."""
    def __init__(self, chemin):
        self.f = open(chemin, "w", encoding="utf-8")
        self.out = sys.stdout
    def write(self, s):
        self.out.write(s)
        self.f.write(s)
        self.f.flush()
    def flush(self):
        self.out.flush()
        self.f.flush()


def ecrire_excel(feuilles, chemin):
    """Écrit {nom_feuille: DataFrame} dans un .xlsx (atomique). Fichier ouvert dans Excel : écrit dans un fichier horodaté,
    rien n'est jamais perdu. Retourne le chemin réellement écrit."""
    def ecrire(c):
        tmp = c.replace(".xlsx", "_tmp.xlsx")
        with pd.ExcelWriter(tmp) as xl:
            for nom, d in feuilles.items():
                d.to_excel(xl, sheet_name=nom[:31], index=False)
        os.replace(tmp, c)
    try:
        ecrire(chemin)
        return chemin
    except Exception as ex:
        alt = chemin.replace(".xlsx", time.strftime("_%Y%m%d_%H%M%S.xlsx"))
        print(f"  !!! ÉCRITURE DE {chemin} ÉCHOUÉE ({ex.__class__.__name__}) : fichier ouvert dans Excel ? Écrit dans {alt}")
        ecrire(alt)
        return alt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transforme du fichier via le tuto")
    parser.add_argument("fichier_excel", help="Chemin du fichier XLSX à traiter")
    parser.add_argument("--sortie", default=None, help="Fichier XLSX de sortie (défaut : <entrée>_transforme.xlsx)")
    args = parser.parse_args()

    base_nom = os.path.splitext(args.fichier_excel)[0]
    sortie = args.sortie or base_nom + "_transforme.xlsx"
    sys.stdout = Tee(base_nom + "_log.txt")           # LOG COMPLET de la console
    print(f"=== Run du {time.strftime('%Y-%m-%d %H:%M:%S')} : {args.fichier_excel} ===")

    df = pd.read_excel(
        args.fichier_excel,
        converters={'Date': lambda x: pd.to_datetime(x, format='%d/%m/%Y', errors='coerce')},
    )
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df[(df["Date"] >= "2025-07-01") & ((df["Date"] <= "2025-08-31"))]

    print(f"{len(df)} lignes lues")

    profil_base = df[COL_PROFIL].copy()          # valeur d'origine, avant l'étape 5

    # Etape 5
    df.loc[(df["Profil de l'appelant"] == "AP-HP") & (df["Statut de l'appelant"] == "ETUDIANT EN SANTE"), "Profil de l'appelant"] = "ETUDIANT EN SANTE"
    df.loc[(df["Profil de l'appelant"] == "AP-HP") & (df["Statut de l'appelant"] == "NC"), "Profil de l'appelant"] = "NON PRIS EN CHARGE"
    df.loc[(df["Profil de l'appelant"] == "AP-HP") & (df["Statut de l'appelant"].isin(["SALARIE", "LIBERAL", "RETRAITE"])), "Profil de l'appelant"] = "PROFESSIONNEL DE SANTE"

    # Etape 4
    df.loc[df["Orientation conseillée"] == "Psychologue en face à face Réseau SPS",
           "Nom du spécialiste conseillé"] = "Psychologue SPS"
    df.loc[df["Orientation conseillée"] == "Psychologue en face à face Réseau SPS",
           "Orientation conseillée"] = "Psychologue en face à face"
    df.loc[df["Statut de l'appelant"] == "NON PRIS EN CHARGE", "Statut Code"] = "NC"

    # Etape 3
    for col in ["Motif", "Sexe", "Orientation conseillée", "Métier", "Branche professionnelle"]:
        df[col] = associer_colonne(df[col], col)

    # Profil : jugé par le modèle (profil, statut, branche) ; décisions et mémoire enregistrées dans transformations_profil_v2.xlsx
    profil_entree, branche_avant = df[COL_PROFIL].copy(), df[COL_BRANCHE].copy()
    df[COL_PROFIL] = traiter_profil(df[COL_PROFIL], df[COL_STATUT], df[COL_BRANCHE])
    df["Métier"] = df["Métier"].apply(lambda x: "NC" if (x == "NON RENSEIGNE") else x)
    pd.DataFrame(journal_profil, columns=["combinaison", "catégorie", "source", "raison"]) \
        .to_excel(base_nom + "_decisions_profil.xlsx", index=False)

    #df.to_excel("test.xlsx", index = False)

    # Etape 6
    df["Branche professionnelle"] = appliquer_branches(df)
    combos = exporter_toutes_combinaisons(profil_base, profil_entree, df[COL_STATUT], branche_avant,
                                          df[COL_PROFIL], df[COL_BRANCHE])

    # --- Enregistrement de TOUT ---
    # 1. décisions de branche de ce run (classé / ambigu / échec)
    dec_branche = pd.DataFrame(journal, columns=["metier", "profil", "resultat", "branche(s)", "raison"])

    # 2. métiers ambigus (liste récupérable) avec le nombre de lignes concernées
    nb_mp = (pd.DataFrame({"metier": df["Métier"].astype("string").str.strip(),
                           "profil": df[COL_PROFIL].map(norm_profil)})
             .dropna().groupby(["metier", "profil"]).size())
    ambigus = pd.DataFrame([{"metier": m, "profil": p, "anciennes_branches": " | ".join(map(str, v)),
                             "nb_lignes": int(nb_mp.get((m, p), 0))}
                            for (m, p), v in corresp_metierxprofil_branche.items() if isinstance(v, list)],
                           columns=["metier", "profil", "anciennes_branches", "nb_lignes"])
    if len(ambigus):
        ambigus = ambigus.sort_values("nb_lignes", ascending=False)

    # 3. fichier final
    df = df.sort_values(by=["Date", "Heure"], ascending=[False, False])
    df.columns = ["PROFIL APPELANT" if name_col == "Profil de l'appelant"
                  else ("BRANCHE PRO" if name_col == "Branche professionnelle" else name_col)
                  for name_col in df.columns]
    df = df.drop(columns=["Statut de l'appelant"])

    chemin_final = ecrire_excel({"donnees": df}, sortie)
    chemin_suivi = ecrire_excel({"decisions_branche": dec_branche, "metiers_ambigus": ambigus,
                                 "combinaisons_profil": combos}, base_nom + "_suivi.xlsx")

    print(f"\n=== Enregistré ===")
    print(f"  données finales        : {chemin_final} ({len(df)} lignes)")
    print(f"  suivi du run           : {chemin_suivi} (decisions_branche, metiers_ambigus, combinaisons_profil)")
    print(f"  décisions profil       : {base_nom}_decisions_profil.xlsx")
    print(f"  mémoire profils        : {FICHIER_TRANSFO} (transformations, nouvelles_decisions, cas_profils, statuts_etudiant, branches_sante)")
    print(f"  mémoire métier/branche : {FICHIER}")
    print(f"  correspondance colonnes: correspondance_colonnes.xlsx")
    print(f"  log de la console      : {base_nom}_log.txt")
    print(df.head(20))