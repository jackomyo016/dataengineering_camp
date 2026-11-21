""" Module partant du traitement de la branche"""

from harmonisation_train import *


# ============================================================
# COHÉRENCE MÉTIER -> BRANCHE PROFESSIONNELLE
# (medium sur tous les métiers, high uniquement sur ceux que le medium modifie)
# Nécessite : appeler(prompt, effort=...) et Indisponible, définis plus haut dans la session
# ============================================================
COL_M, COL_B = "Métier", "Branche professionnelle"
CHUNK_M = 40                                # métiers par requête en medium
CHUNK_H = 20                                # métiers par requête en high
NC = "NC"                                   # métier non renseigné : la ligne n'est jamais modifiée

BRANCHES = ['AUTRES PROFESSIONNEL DE LA SANTE', 'MEDECIN', 'AIDE SOIGNANT', 'SERVICE MEDICO SOCIAL', 'KINE',
            'INFIRMIER', 'PHARMACIEN', 'PSYCHOLOGUE', 'ADMINISTRATIF / CADRE SANTE', 'AGENT DE SERVICE ASH',
            'DENTISTE', 'ORTHOPHONISTE', 'SAGE FEMME', 'VETERINAIRE', 'NON PRIS EN CHARGE']
FALLBACK = 'AUTRES PROFESSIONNEL DE LA SANTE'      # métier de santé sans branche précise
HORS_SANTE = 'NON PRIS EN CHARGE'                  # aucun lien avec la santé (+ sans emploi, retraité, grand public)
PROTEGEES = set()                                  # branches jamais modifiées (vide : tout est vérifié)

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
- Auxiliaire de puériculture et puéricultrice : AUTRES PROFESSIONNEL DE LA SANTE.
- SANS EMPLOI, DEMANDEUR D'EMPLOI, SANS PROFESSION, RETRAITE (sans métier de santé précisé) et GRAND PUBLIC :
  NON PRIS EN CHARGE.
- Un étudiant ou élève dans une filière de santé : branche du métier visé (étudiant infirmier : INFIRMIER).
  Un étudiant hors santé : NON PRIS EN CHARGE.
- Un professionnel de santé retraité garde la branche de son métier.
"""
PROMPT_BRANCHE = """Voici la liste des BRANCHES PROFESSIONNELLES disponibles, au format 'code|branche' :
{branches}

Pour chaque MÉTIER ci-dessous, au format 'numéro|métier|branches actuellement observées (code:nombre de lignes)',
choisis UNE SEULE branche de la liste, la plus cohérente avec ce métier.

RÈGLES DE CLASSIFICATION :

- Identifie d'abord le métier exact, puis détermine sa branche.
- Classe le métier selon sa fonction et son périmètre professionnel réel.
- Ne confonds jamais proximité d'activité, secteur commun et équivalence
  professionnelle.
- Une branche peut regrouper plusieurs métiers différents, mais chaque
  métier doit réellement correspondre à son périmètre.
- Une branche spécialisée ne doit pas être attribuée à un métier
  simplement parce qu'il travaille avec les professionnels de cette
  spécialité.
- Ne déduis jamais une qualification, un diplôme, une spécialité ou
  une fonction qui n'est pas indiqué dans l'intitulé.
- Les branches actuellement observées sont des indices et non des
  vérités absolues.
- Si la branche la plus fréquente est cohérente avec la profession,
  conserve-la.
- Si elle est incohérente, choisis une autre branche uniquement si
  son périmètre correspond réellement au métier.
- Si plusieurs branches sont possibles, privilégie celle qui décrit
  le mieux la fonction principale.
- Si aucune branche spécialisée ne convient à un métier de santé,
  utilise AUTRES PROFESSIONNEL DE LA SANTE.
- Pour un métier relevant principalement de l'accompagnement social
  ou médico-social, utilise SERVICE MEDICO SOCIAL.
- Pour un métier sans lien avec la santé ou le médico-social,
  utilise NON PRIS EN CHARGE.
- En cas de doute, ne crée pas d'équivalence professionnelle artificielle.

Les métiers sont saisis librement : corrige mentalement les fautes,
abréviations, accents et variantes d'écriture sans modifier leur sens.

DEFINITIONS DES BRANCHES A RESPECTER IMPERATIVEMENT :

{precisions}

Réponds uniquement par des lignes au format :
numéro | code | raison en 6 mots maximum
Utilise uniquement un code de la liste. N'invente aucune branche.
Chaque numéro doit apparaître exactement une fois. Aucun autre texte.

{lot}"""

def classer(liste_ids, effort):
    """Retourne {id: (code, raison)} pour les métiers de liste_ids."""
    lot = "\n".join(
        f"{i}|{mid[i]}|" + (",".join(f"{c}:{n}" for c, n in sorted(obs[mid[i]].items(), key=lambda x: -x[1])) or "aucune")
        for i in liste_ids)
    rep = appeler(PROMPT_BRANCHE.format(branches=liste_branches, precisions=PRECISIONS, lot=lot), effort=effort)
    out = {}
    for ligne in rep.splitlines():
        m = re.match(r"^\s*(\d+)\s*\|\s*(B\d+)\s*(?:\|\s*(.*))?$", ligne.strip().strip("`"))
        if m and int(m.group(1)) in liste_ids and m.group(2) in codes:
            out.setdefault(int(m.group(1)), (m.group(2), (m.group(3) or "").strip()))
    return out

def classer_par_lots(ids, taille, effort):
    """Classe par lots ; si Albert est trop lent ou indisponible (504...), le lot est coupé en deux."""
    res = {}
    def rec(sous_ids):
        try:
            res.update(classer(sous_ids, effort))
        except Indisponible:
            if len(sous_ids) <= 5:
                print(f"  lot de {len(sous_ids)} abandonné")
                return
            m = len(sous_ids) // 2
            rec(sous_ids[:m]); rec(sous_ids[m:])
    for k in range(0, len(ids), taille):
        rec(ids[k:k + taille])
        print(f"  {effort} : {min(k + taille, len(ids))}/{len(ids)}")
    return res


def second_transformation(file):

    harmonisation_df(file)
    # --- 0. Sauvegarde / restauration de la branche d'origine (le bloc peut être relancé) ---
    df = pd.read_excel(
        file.replace(".","2."),   # on lit en texte brut, sans interprétation
        converters={'Date': lambda x: pd.to_datetime(x, format='%d/%m/%Y', errors='coerce')},
    )
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    if "branche_origine" not in globals():
        branche_origine = df[COL_B].copy()
    df[COL_B] = branche_origine.copy()

    codes = {f"B{i + 1}": b for i, b in enumerate(BRANCHES)}
    inv = {b: c for c, b in codes.items()}

    # --- 1. Vérification : valeurs de la colonne branche absentes de la liste ---
    bstr = df[COL_B].astype("string").str.strip()
    connues = set(BRANCHES) | PROTEGEES | {NC}
    inconnues = bstr.dropna()[~bstr.dropna().isin(connues)].value_counts()
    print("Valeurs de la colonne branche absentes de la liste (seront remplacées si le métier est connu) :")
    print(inconnues.to_string() if len(inconnues) else "  aucune")

    # --- 2. Lignes concernées : métier renseigné (ni vide, ni NC) et branche non protégée ---
    cle = df[COL_M].astype("string").str.strip()
    concerne = cle.notna() & (cle != NC) & ~bstr.isin(list(PROTEGEES))

    # --- 3. Répartition observée : uniquement les branches de la liste ---
    obs = {m: {} for m in cle[concerne].unique()}
    sous = pd.DataFrame({"m": cle[concerne], "b": bstr[concerne]}).dropna()
    sous = sous[sous["b"].isin(inv)]
    for (m, b), n in sous.groupby(["m", "b"]).size().items():
        obs[m][inv[b]] = int(n)
    metiers = sorted(obs)
    mid = dict(enumerate(metiers))
    print(f"\n{len(metiers)} métiers à vérifier ({int(concerne.sum())} lignes concernées, "
        f"{int((~concerne).sum())} lignes laissées telles quelles)")


    liste_branches = "\n".join(f"{c}|{b}" for c, b in codes.items())


    # --- 4. Passe 1 : TOUS les métiers, reasoning MEDIUM ---
    tous = list(mid)
    medium = classer_par_lots(tous, CHUNK_M, "medium")
    manquants = [i for i in tous if i not in medium]
    print(f"{len(medium)}/{len(tous)} métiers classés en medium, {len(manquants)} oubliés")
    if manquants:
        medium.update(classer_par_lots(manquants, 15, "medium"))

    branche_medium = {mid[i]: codes[c] for i, (c, r) in medium.items()}

    # --- 4a. Quels métiers le medium MODIFIE-t-il ? (au moins une ligne changerait de branche) ---
    lignes = pd.DataFrame({"m": cle[concerne], "b": bstr[concerne]})
    lignes["decision"] = lignes["m"].map(branche_medium)
    lignes = lignes[lignes["decision"].notna()]
    change = lignes["b"].astype("object").where(lignes["b"].notna(), "∅") != lignes["decision"]
    modifies = sorted(set(lignes.loc[change, "m"]))
    id_de = {m: i for i, m in mid.items()}
    ids_modifies = [id_de[m] for m in modifies]
    print(f"\n{len(modifies)} métiers modifiés par le medium sur {len(tous)} -> revérifiés en reasoning HIGH")

    # --- 4b. Passe 2 : reasoning HIGH uniquement sur les métiers modifiés par le medium ---
    high = classer_par_lots(ids_modifies, CHUNK_H, "high")
    print(f"{len(high)}/{len(ids_modifies)} métiers classés en high")

    metier_branche, raisons, desaccords = {}, {}, []
    for i in tous:
        m = mid[i]
        if i in high:                                   # décision high : prioritaire
            metier_branche[m] = codes[high[i][0]]
            raisons[i] = high[i][1]
            if i in medium and high[i][0] != medium[i][0]:
                desaccords.append((m, codes[medium[i][0]], codes[high[i][0]], high[i][1]))
        elif i in medium:                               # métier non modifié par le medium, ou high sans réponse
            metier_branche[m] = codes[medium[i][0]]
            raisons[i] = medium[i][1]
        elif obs[m]:                                    # aucune réponse : branche majoritaire observée
            metier_branche[m] = codes[max(obs[m].items(), key=lambda x: x[1])[0]]

    print(f"\n--- {len(desaccords)} métiers où le high contredit le medium ---")
    for m, a, b, r in desaccords[:40]:
        print(f"  {m} : {a} -> {b}  ({r})")

    # --- 4c. Vérification stricte des métiers envoyés en NON PRIS EN CHARGE ---
    hs_metiers = sorted(m for m, b in metier_branche.items() if b == HORS_SANTE)
    if hs_metiers:
        hid = dict(enumerate(hs_metiers))
        PROMPT_VERIF = """Voici des métiers saisis librement (avec d'éventuelles fautes ou abréviations), au format 'numéro|métier'.
    Pour chacun, dis s'il a un lien, MÊME INDIRECT, avec la santé, le soin, le paramédical, le médico-social, le social,
    la petite enfance, la pharmacie ou le vétérinaire (y compris les étudiants et élèves de ces filières).
    - OUI : lien avec ces domaines, ou doute
    - NON : aucun lien (droit, commerce, informatique, journalisme, sécurité, restauration, bâtiment, arts...)
    Les statuts sans métier précis (sans emploi, demandeur d'emploi, sans profession, retraité, grand public,
    particulier) n'ont aucun lien : réponds NON.
    Réponds uniquement par des lignes : numéro | OUI ou NON. Chaque numéro exactement une fois. Aucun autre texte.

    {lot}"""
        lien = {}
        for k in range(0, len(hid), 60):
            ids_lot = list(hid)[k:k + 60]
            try:
                rep = appeler(PROMPT_VERIF.format(lot="\n".join(f"{i}|{hid[i]}" for i in ids_lot)), effort="medium")
            except Indisponible:
                print("  vérification d'un lot impossible (Albert indisponible) : métiers laissés en doute")
                continue
            for l in rep.splitlines():
                m = re.match(r"^\s*(\d+)\s*\|\s*(OUI|NON)\s*$", l.strip().strip("`"), re.I)
                if m and int(m.group(1)) in hid:
                    lien.setdefault(hid[int(m.group(1))], m.group(2).upper())
        a_reaffecter = [m for m in hs_metiers if lien.get(m, "OUI") == "OUI"]      # pas de réponse = doute = on réaffecte
        print(f"{len(a_reaffecter)} métiers retirés de « {HORS_SANTE} » après vérification : {a_reaffecter[:30]}")

        if a_reaffecter:
            sante_codes = {c: b for c, b in codes.items() if b != HORS_SANTE}
            PROMPT_REAFF = """Branches disponibles, au format 'code|branche' :
    {branches}

    Ces métiers ont un lien avec la santé, le soin ou le médico-social. Pour chacun, au format 'numéro|métier',
    choisis la branche la plus proche. Si aucune ne convient précisément, réponds {fb_code} (« {fallback} »).
    Réponds uniquement par des lignes : numéro | code. Chaque numéro exactement une fois. Aucun autre texte.

    {lot}"""
            rid = dict(enumerate(a_reaffecter))
            try:
                rep = appeler(PROMPT_REAFF.format(
                    branches="\n".join(f"{c}|{b}" for c, b in sante_codes.items()),
                    fb_code=inv[FALLBACK], fallback=FALLBACK,
                    lot="\n".join(f"{i}|{m}" for i, m in rid.items())), effort="medium")
            except Indisponible:
                rep = ""
            for l in rep.splitlines():
                m = re.match(r"^\s*(\d+)\s*\|\s*(B\d+)\s*$", l.strip().strip("`"))
                if m and int(m.group(1)) in rid and m.group(2) in sante_codes:
                    metier_branche[rid[int(m.group(1))]] = sante_codes[m.group(2)]
            for mt in a_reaffecter:                     # réponse manquante : fourre-tout de santé plutôt que hors santé
                if metier_branche.get(mt) == HORS_SANTE:
                    metier_branche[mt] = FALLBACK

    sans_decision = [m for m in metiers if m not in metier_branche]

    # --- 5. Application : une seule branche par métier (seulement sur les lignes concernées) ---
    avant = df[COL_B].copy()
    df.loc[concerne, COL_B] = cle[concerne].map(metier_branche).fillna(df.loc[concerne, COL_B])

    # --- 6. Contrôles ---
    modifie = (avant.fillna("∅") != df[COL_B].fillna("∅"))
    print(f"\n{modifie.sum()} lignes modifiées sur {len(df)}")
    print(f"Lignes avec Métier = {NC} dont la branche a changé : {int((modifie & (cle == NC)).sum())}  (doit être 0)")
    verif = df[concerne].groupby(cle[concerne])[COL_B].nunique()
    print(f"Métiers avec plus d'une branche : {(verif > 1).sum()}  (doit être 0)")
    print(f"Métiers sans branche décidée (laissés inchangés) : {len(sans_decision)} {sans_decision[:20]}")

    changements = (pd.DataFrame({COL_M: df[COL_M], "branche_avant": avant, "branche_apres": df[COL_B]})[modifie]
                .groupby([COL_M, "branche_avant", "branche_apres"], dropna=False).size()
                .reset_index(name="nb_lignes").sort_values("nb_lignes", ascending=False))
    print("\n--- Modifications les plus fréquentes (à relire) ---")
    print(changements.head(40).to_string(index=False))

    print(f"\n--- Métiers rattachés à « {HORS_SANTE} » (à relire : aucun métier de santé ne doit y figurer) ---")
    print(sorted(m for m, b in metier_branche.items() if b == HORS_SANTE))

    # --- 7. Export ---
    corresp_mb = pd.DataFrame({
        COL_M: metiers,
        "branche_medium": [branche_medium.get(m) for m in metiers],
        "verifie_en_high": [m in set(modifies) for m in metiers],
        "branche_finale": [metier_branche.get(m) for m in metiers],
        "raison": [raisons.get(i, "") for i in mid],
        "repartition_avant": [", ".join(f"{codes[c]} ({n})" for c, n in sorted(obs[m].items(), key=lambda x: -x[1])) or "aucune" for m in metiers],
        "nb_lignes": [int((cle == m).sum()) for m in metiers],
    })
    desaccords_df = pd.DataFrame(desaccords, columns=[COL_M, "branche_medium", "branche_high", "raison_high"])
    with pd.ExcelWriter("coherence_metier_branche.xlsx") as xl:
        corresp_mb.to_excel(xl, sheet_name="metier_branche", index=False)
        changements.to_excel(xl, sheet_name="modifications", index=False)
        desaccords_df.to_excel(xl, sheet_name="high_vs_medium", index=False)

    df.to_excel(file.replace(".","2."), index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Transforme un fichier .xlsx de consultations."
    )
    parser.add_argument(
        "fichier_xlsx",
        help="Chemin du fichier .xlsx à traiter"
    )
    args = parser.parse_args()
    file = args.fichier_xlsx

    second_transformation(file)


    # harmonisation_df(file)
    # # --- 0. Sauvegarde / restauration de la branche d'origine (le bloc peut être relancé) ---
    # df = pd.read_excel(
    #     file.replace(".","2."),   # on lit en texte brut, sans interprétation
    #     converters={'Date': lambda x: pd.to_datetime(x, format='%d/%m/%Y', errors='coerce')},
    # )
    # df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    # if "branche_origine" not in globals():
    #     branche_origine = df[COL_B].copy()
    # df[COL_B] = branche_origine.copy()

    # codes = {f"B{i + 1}": b for i, b in enumerate(BRANCHES)}
    # inv = {b: c for c, b in codes.items()}

    # # --- 1. Vérification : valeurs de la colonne branche absentes de la liste ---
    # bstr = df[COL_B].astype("string").str.strip()
    # connues = set(BRANCHES) | PROTEGEES | {NC}
    # inconnues = bstr.dropna()[~bstr.dropna().isin(connues)].value_counts()
    # print("Valeurs de la colonne branche absentes de la liste (seront remplacées si le métier est connu) :")
    # print(inconnues.to_string() if len(inconnues) else "  aucune")

    # # --- 2. Lignes concernées : métier renseigné (ni vide, ni NC) et branche non protégée ---
    # cle = df[COL_M].astype("string").str.strip()
    # concerne = cle.notna() & (cle != NC) & ~bstr.isin(list(PROTEGEES))

    # # --- 3. Répartition observée : uniquement les branches de la liste ---
    # obs = {m: {} for m in cle[concerne].unique()}
    # sous = pd.DataFrame({"m": cle[concerne], "b": bstr[concerne]}).dropna()
    # sous = sous[sous["b"].isin(inv)]
    # for (m, b), n in sous.groupby(["m", "b"]).size().items():
    #     obs[m][inv[b]] = int(n)
    # metiers = sorted(obs)
    # mid = dict(enumerate(metiers))
    # print(f"\n{len(metiers)} métiers à vérifier ({int(concerne.sum())} lignes concernées, "
    #     f"{int((~concerne).sum())} lignes laissées telles quelles)")


    # liste_branches = "\n".join(f"{c}|{b}" for c, b in codes.items())


    # # --- 4. Passe 1 : TOUS les métiers, reasoning MEDIUM ---
    # tous = list(mid)
    # medium = classer_par_lots(tous, CHUNK_M, "medium")
    # manquants = [i for i in tous if i not in medium]
    # print(f"{len(medium)}/{len(tous)} métiers classés en medium, {len(manquants)} oubliés")
    # if manquants:
    #     medium.update(classer_par_lots(manquants, 15, "medium"))

    # branche_medium = {mid[i]: codes[c] for i, (c, r) in medium.items()}

    # # --- 4a. Quels métiers le medium MODIFIE-t-il ? (au moins une ligne changerait de branche) ---
    # lignes = pd.DataFrame({"m": cle[concerne], "b": bstr[concerne]})
    # lignes["decision"] = lignes["m"].map(branche_medium)
    # lignes = lignes[lignes["decision"].notna()]
    # change = lignes["b"].astype("object").where(lignes["b"].notna(), "∅") != lignes["decision"]
    # modifies = sorted(set(lignes.loc[change, "m"]))
    # id_de = {m: i for i, m in mid.items()}
    # ids_modifies = [id_de[m] for m in modifies]
    # print(f"\n{len(modifies)} métiers modifiés par le medium sur {len(tous)} -> revérifiés en reasoning HIGH")

    # # --- 4b. Passe 2 : reasoning HIGH uniquement sur les métiers modifiés par le medium ---
    # high = classer_par_lots(ids_modifies, CHUNK_H, "high")
    # print(f"{len(high)}/{len(ids_modifies)} métiers classés en high")

    # metier_branche, raisons, desaccords = {}, {}, []
    # for i in tous:
    #     m = mid[i]
    #     if i in high:                                   # décision high : prioritaire
    #         metier_branche[m] = codes[high[i][0]]
    #         raisons[i] = high[i][1]
    #         if i in medium and high[i][0] != medium[i][0]:
    #             desaccords.append((m, codes[medium[i][0]], codes[high[i][0]], high[i][1]))
    #     elif i in medium:                               # métier non modifié par le medium, ou high sans réponse
    #         metier_branche[m] = codes[medium[i][0]]
    #         raisons[i] = medium[i][1]
    #     elif obs[m]:                                    # aucune réponse : branche majoritaire observée
    #         metier_branche[m] = codes[max(obs[m].items(), key=lambda x: x[1])[0]]

    # print(f"\n--- {len(desaccords)} métiers où le high contredit le medium ---")
    # for m, a, b, r in desaccords[:40]:
    #     print(f"  {m} : {a} -> {b}  ({r})")

    # # --- 4c. Vérification stricte des métiers envoyés en NON PRIS EN CHARGE ---
    # hs_metiers = sorted(m for m, b in metier_branche.items() if b == HORS_SANTE)
    # if hs_metiers:
    #     hid = dict(enumerate(hs_metiers))
    #     PROMPT_VERIF = """Voici des métiers saisis librement (avec d'éventuelles fautes ou abréviations), au format 'numéro|métier'.
    # Pour chacun, dis s'il a un lien, MÊME INDIRECT, avec la santé, le soin, le paramédical, le médico-social, le social,
    # la petite enfance, la pharmacie ou le vétérinaire (y compris les étudiants et élèves de ces filières).
    # - OUI : lien avec ces domaines, ou doute
    # - NON : aucun lien (droit, commerce, informatique, journalisme, sécurité, restauration, bâtiment, arts...)
    # Les statuts sans métier précis (sans emploi, demandeur d'emploi, sans profession, retraité, grand public,
    # particulier) n'ont aucun lien : réponds NON.
    # Réponds uniquement par des lignes : numéro | OUI ou NON. Chaque numéro exactement une fois. Aucun autre texte.

    # {lot}"""
    #     lien = {}
    #     for k in range(0, len(hid), 60):
    #         ids_lot = list(hid)[k:k + 60]
    #         try:
    #             rep = appeler(PROMPT_VERIF.format(lot="\n".join(f"{i}|{hid[i]}" for i in ids_lot)), effort="medium")
    #         except Indisponible:
    #             print("  vérification d'un lot impossible (Albert indisponible) : métiers laissés en doute")
    #             continue
    #         for l in rep.splitlines():
    #             m = re.match(r"^\s*(\d+)\s*\|\s*(OUI|NON)\s*$", l.strip().strip("`"), re.I)
    #             if m and int(m.group(1)) in hid:
    #                 lien.setdefault(hid[int(m.group(1))], m.group(2).upper())
    #     a_reaffecter = [m for m in hs_metiers if lien.get(m, "OUI") == "OUI"]      # pas de réponse = doute = on réaffecte
    #     print(f"{len(a_reaffecter)} métiers retirés de « {HORS_SANTE} » après vérification : {a_reaffecter[:30]}")

    #     if a_reaffecter:
    #         sante_codes = {c: b for c, b in codes.items() if b != HORS_SANTE}
    #         PROMPT_REAFF = """Branches disponibles, au format 'code|branche' :
    # {branches}

    # Ces métiers ont un lien avec la santé, le soin ou le médico-social. Pour chacun, au format 'numéro|métier',
    # choisis la branche la plus proche. Si aucune ne convient précisément, réponds {fb_code} (« {fallback} »).
    # Réponds uniquement par des lignes : numéro | code. Chaque numéro exactement une fois. Aucun autre texte.

    # {lot}"""
    #         rid = dict(enumerate(a_reaffecter))
    #         try:
    #             rep = appeler(PROMPT_REAFF.format(
    #                 branches="\n".join(f"{c}|{b}" for c, b in sante_codes.items()),
    #                 fb_code=inv[FALLBACK], fallback=FALLBACK,
    #                 lot="\n".join(f"{i}|{m}" for i, m in rid.items())), effort="medium")
    #         except Indisponible:
    #             rep = ""
    #         for l in rep.splitlines():
    #             m = re.match(r"^\s*(\d+)\s*\|\s*(B\d+)\s*$", l.strip().strip("`"))
    #             if m and int(m.group(1)) in rid and m.group(2) in sante_codes:
    #                 metier_branche[rid[int(m.group(1))]] = sante_codes[m.group(2)]
    #         for mt in a_reaffecter:                     # réponse manquante : fourre-tout de santé plutôt que hors santé
    #             if metier_branche.get(mt) == HORS_SANTE:
    #                 metier_branche[mt] = FALLBACK

    # sans_decision = [m for m in metiers if m not in metier_branche]

    # # --- 5. Application : une seule branche par métier (seulement sur les lignes concernées) ---
    # avant = df[COL_B].copy()
    # df.loc[concerne, COL_B] = cle[concerne].map(metier_branche).fillna(df.loc[concerne, COL_B])

    # # --- 6. Contrôles ---
    # modifie = (avant.fillna("∅") != df[COL_B].fillna("∅"))
    # print(f"\n{modifie.sum()} lignes modifiées sur {len(df)}")
    # print(f"Lignes avec Métier = {NC} dont la branche a changé : {int((modifie & (cle == NC)).sum())}  (doit être 0)")
    # verif = df[concerne].groupby(cle[concerne])[COL_B].nunique()
    # print(f"Métiers avec plus d'une branche : {(verif > 1).sum()}  (doit être 0)")
    # print(f"Métiers sans branche décidée (laissés inchangés) : {len(sans_decision)} {sans_decision[:20]}")

    # changements = (pd.DataFrame({COL_M: df[COL_M], "branche_avant": avant, "branche_apres": df[COL_B]})[modifie]
    #             .groupby([COL_M, "branche_avant", "branche_apres"], dropna=False).size()
    #             .reset_index(name="nb_lignes").sort_values("nb_lignes", ascending=False))
    # print("\n--- Modifications les plus fréquentes (à relire) ---")
    # print(changements.head(40).to_string(index=False))

    # print(f"\n--- Métiers rattachés à « {HORS_SANTE} » (à relire : aucun métier de santé ne doit y figurer) ---")
    # print(sorted(m for m, b in metier_branche.items() if b == HORS_SANTE))

    # # --- 7. Export ---
    # corresp_mb = pd.DataFrame({
    #     COL_M: metiers,
    #     "branche_medium": [branche_medium.get(m) for m in metiers],
    #     "verifie_en_high": [m in set(modifies) for m in metiers],
    #     "branche_finale": [metier_branche.get(m) for m in metiers],
    #     "raison": [raisons.get(i, "") for i in mid],
    #     "repartition_avant": [", ".join(f"{codes[c]} ({n})" for c, n in sorted(obs[m].items(), key=lambda x: -x[1])) or "aucune" for m in metiers],
    #     "nb_lignes": [int((cle == m).sum()) for m in metiers],
    # })
    # desaccords_df = pd.DataFrame(desaccords, columns=[COL_M, "branche_medium", "branche_high", "raison_high"])
    # with pd.ExcelWriter("coherence_metier_branche.xlsx") as xl:
    #     corresp_mb.to_excel(xl, sheet_name="metier_branche", index=False)
    #     changements.to_excel(xl, sheet_name="modifications", index=False)
    #     desaccords_df.to_excel(xl, sheet_name="high_vs_medium", index=False)