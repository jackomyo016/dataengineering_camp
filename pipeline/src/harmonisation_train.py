""" Module pour harmoniser certains colonnes (Métier, Motif, Orientation Conseillée, Sexe) + Branche"""

import os, re, json, time, hashlib, threading
import requests
import pandas as pd
from dotenv import load_dotenv
import argparse
from concurrent.futures import ThreadPoolExecutor

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
FICHIER = "corresp_metier_branche.json"            # sauvegarde du dictionnaire
verrou_corresp = threading.Lock()


cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
corresp_metier_branche = json.load(open(FICHIER, encoding="utf-8"))

class Indisponible(Exception):
    pass

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
                    regles=REGLES, exemples=EXEMPLES.get(col, "")), effort="medium")
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

def nettoyer(s):
    """Retire l'artefact de copier-coller [/](https://...) (affichage uniquement)."""
    return re.sub(r"\[/\]\([^)]*\)", "/", str(s)).strip()

# --- Sauvegarde / chargement du dictionnaire ---
def sauver_corresp():
    """Écriture atomique : le fichier n'est jamais à moitié écrit. À appeler sous verrou_corresp."""
    tmp = FICHIER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(corresp_metier_branche, f, ensure_ascii=False, indent=1)
    os.replace(tmp, FICHIER)

if os.path.exists(FICHIER):
    sur_disque = json.load(open(FICHIER, encoding="utf-8"))
    for k, v in sur_disque.items():
        corresp_metier_branche.setdefault(k, v)            # les valeurs déjà en mémoire gardent la priorité
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

Choisis UNE SEULE branche de la liste si le métier correspond clairement à l'une d'elles, selon sa fonction et
son périmètre professionnel réel d'après les définitions.

RÈGLES :
- Choisis uniquement parmi les branches de la liste. N'invente aucune branche.
- Le métier est saisi librement : corrige mentalement les fautes, abréviations et variantes d'écriture sans modifier son sens.
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

journal = []                                       # trace des décisions du cas B : (métier, statut, branche(s), raison)

def classer_high(metier):
    """Retourne (branche, raison) ; branche = None si ambigu ; branche = False si pas de réponse exploitable."""
    try:
        rep = appeler(PROMPT_BRANCHE_UNIQUE.format(branches=liste_b, metier=metier, precisions=PRECISIONS),
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

def ajouter_a_liste(metier, anciennes):
    """Ambigu : dictionnaire[métier] = liste contenant les anciennes branches, sans doublon.
    Si le métier a déjà une liste, on la complète ; sinon on la crée. À appeler sous verrou_corresp."""
    actuelle = corresp_metier_branche.get(metier)
    liste = list(actuelle) if isinstance(actuelle, list) else []
    for b in anciennes:
        if pd.notna(b) and b not in liste:
            liste.append(b)
    corresp_metier_branche[metier] = liste
    return liste

def associer_branche(metier, branche, classer=True, anciennes=None):
    """Retourne la branche à utiliser pour le couple (métier, branche).
    - métier NC ou vide : branche inchangée
    - A : métier dans corresp_metier_branche : valeur de la clé si ce n'est pas une liste, sinon branche inchangée
    - B : métier absent : reasoning high parmi les branches existantes
        . non ambigu : la nouvelle branche remplace l'ancienne ; dictionnaire[métier] = nouvelle branche ; sauvegarde
        . ambigu     : l'ancienne branche est conservée ; dictionnaire[métier] = liste qui contient l'ancienne branche
                       (ajoutée si elle n'y est pas déjà) ; sauvegarde
        . Albert indisponible / réponse inexploitable : branche inchangée, rien n'est enregistré
    anciennes : anciennes branches à mettre dans la liste en cas d'ambiguïté (par défaut : [branche]).
    classer=False : lecture seule du dictionnaire, aucune requête."""
    if pd.isna(metier) or not str(metier).strip() or str(metier).strip().upper() == NC:
        return branche
    m = str(metier).strip()

    for k in (m, m.upper()):                                       # A
        if k in corresp_metier_branche:
            v = corresp_metier_branche[k]
            return branche if isinstance(v, list) else v
    if not classer:
        return branche

    b, raison = classer_high(m)                                    # B
    if b is False:
        journal.append((m, "échec", "", raison))
        print(f"  « {m} » non traité : {raison}")
        return branche
    if b is None:                                                  # ambigu : on garde l'ancienne branche
        a_ajouter = list(anciennes) if anciennes is not None else [branche]
        with verrou_corresp:
            liste = ajouter_a_liste(m, a_ajouter)                  # clé = métier, valeur = liste avec l'ancienne branche
            sauver_corresp()
        journal.append((m, "ambigu", " | ".join(map(str, liste)), raison))
        print(f"  « {m} » ambigu ({raison}) : ancienne branche conservée, liste = {liste}")
        return branche
    journal.append((m, "classé", b, raison))                       # non ambigu : nouvelle branche
    print(f"  {m} -> {nettoyer(b)}  ({raison})")
    with verrou_corresp:
        corresp_metier_branche[m] = b                              # clé = métier, valeur = nouvelle branche
        sauver_corresp()
    return b

def appliquer_branches(df, col_m="Métier", col_b="Branche professionnelle", workers=4):
    """Applique associer_branche à tout un DataFrame ; les métiers inconnus sont classés en parallèle (une requête high chacun)."""
    m_str = df[col_m].astype("string").str.strip()
    inconnus = sorted({x for x in m_str.dropna()
                       if x and x.upper() != NC and x not in corresp_metier_branche and x.upper() not in corresp_metier_branche})
    # anciennes branches de chaque métier inconnu : toutes celles présentes dans ses lignes (valeurs vides ignorées)
    anciennes = (pd.DataFrame({"m": m_str, "b": df[col_b]}).dropna()
                 .groupby("m")["b"].agg(lambda s: list(dict.fromkeys(s))).to_dict())
    print(f"{len(inconnus)} métiers absents de corresp_metier_branche -> reasoning {EFFORT_B}")

    def traiter(x):
        liste = anciennes.get(x, [])
        associer_branche(x, liste[0] if liste else None, anciennes=liste)

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(traiter, inconnus))
    # le dictionnaire est à jour : cette passe lit seulement le dictionnaire (aucune requête)
    return pd.Series([associer_branche(m, b, classer=False) for m, b in zip(df[col_m], df[col_b])], index=df.index)


if __name__ == "__main__":
    # associer_branche("Médeciin","NC")
    # associer("Métier","opthtalmo")

    df = pd.read_excel(
    'firstransform.xlsx',   # on lit en texte brut, sans interprétation
    converters={'Date': lambda x: pd.to_datetime(x, format='%d/%m/%Y', errors='coerce')},
        )
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df[df["Date"] > "2026-06-30"]

    COLONNES = ["Motif", "Sexe", "Orientation conseillée","Métier"]

    for col in COLONNES:
        df[col] = associer_colonne(df[col], col)

    df["Branche professionnelle"] = appliquer_branches(df)