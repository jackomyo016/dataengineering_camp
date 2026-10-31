
#!/usr/bin/env python3

# Créé par Simon le 26 avril 2020
# V1.0 le 29 avril 2020
# V2.0 le 9 juin 2023
# V3.0 le 3 juillet 2024

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from kestra import Kestra
import numpy as np
import pandas as pd
import json

region_mapping = {
   "00": "NC",
   "971": "Guadeloupe",
   "972": "Martinique",
   "973": "Guyane",
   "974": "La Réunion",
   "976": "Mayotte",
   "75": "Ile-de-France",
   "77": "Ile-de-France",
   "78": "Ile-de-France",
   "91": "Ile-de-France",
   "92": "Ile-de-France",
   "93": "Ile-de-France",
   "94": "Ile-de-France",
   "95": "Ile-de-France",
   "18": "Centre-Val de Loire",
   "28": "Centre-Val de Loire",
   "36": "Centre-Val de Loire",
   "37": "Centre-Val de Loire",
   "41": "Centre-Val de Loire",
   "45": "Centre-Val de Loire",
   "21": "Bourgogne-Franche-Comté",
   "25": "Bourgogne-Franche-Comté",
   "39": "Bourgogne-Franche-Comté",
   "58": "Bourgogne-Franche-Comté",
   "70": "Bourgogne-Franche-Comté",
   "71": "Bourgogne-Franche-Comté",
   "89": "Bourgogne-Franche-Comté",
   "90": "Bourgogne-Franche-Comté",
   "14": "Normandie",
   "27": "Normandie",
   "50": "Normandie",
   "61": "Normandie",
   "76": "Normandie",
   "02": "Hauts-de-France",
   "2": "Hauts-de-France",
   "59": "Hauts-de-France",
   "60": "Hauts-de-France",
   "62": "Hauts-de-France",
   "80": "Hauts-de-France",
   "24": "Nouvelle-Aquitaine",
   "33": "Nouvelle-Aquitaine",
   "40": "Nouvelle-Aquitaine",
   "47": "Nouvelle-Aquitaine",
   "64": "Nouvelle-Aquitaine",
   "79": "Nouvelle-Aquitaine",
   "86": "Nouvelle-Aquitaine",
   "44": "Pays de la Loire",
   "49": "Pays de la Loire",
   "53": "Pays de la Loire",
   "72": "Pays de la Loire",
   "85": "Pays de la Loire",
   "22": "Bretagne",
   "29": "Bretagne",
   "35": "Bretagne",
   "56": "Bretagne",
   "08": "Grand-Est",
   "8": "Grand-Est",
   "10": "Grand-Est",
   "51": "Grand-Est",
   "52": "Grand-Est",
   "54": "Grand-Est",
   "55": "Grand-Est",
   "57": "Grand-Est",
   "67": "Grand-Est",
   "68": "Grand-Est",
   "88": "Grand-Est",
   "32": "Occitanie",
   "46": "Occitanie",
   "65": "Occitanie",
   "81": "Occitanie",
   "82": "Occitanie",
   "09": "Occitanie",
   "9": "Occitanie",
   "11": "Occitanie",
   "12": "Occitanie",
   "30": "Occitanie",
   "31": "Occitanie",
   "34": "Occitanie",
   "48": "Occitanie",
   "66": "Occitanie",
   "01": "Auvergne-Rhône-Alpes",
   "1": "Auvergne-Rhône-Alpes",
   "03": "Auvergne-Rhône-Alpes",
   "3": "Auvergne-Rhône-Alpes",   
   "07": "Auvergne-Rhône-Alpes",
   "7": "Auvergne-Rhône-Alpes",
   "15": "Auvergne-Rhône-Alpes",
   "26": "Auvergne-Rhône-Alpes",
   "38": "Auvergne-Rhône-Alpes",
   "42": "Auvergne-Rhône-Alpes",
   "43": "Auvergne-Rhône-Alpes",
   "63": "Auvergne-Rhône-Alpes",
   "69": "Auvergne-Rhône-Alpes",
   "73": "Auvergne-Rhône-Alpes",
   "74": "Auvergne-Rhône-Alpes",
   "04": "Provence-Alpes-Côte d’Azur",
   "05": "Provence-Alpes-Côte d’Azur",
   "06": "Provence-Alpes-Côte d’Azur",
   "4": "Provence-Alpes-Côte d’Azur",
   "5": "Provence-Alpes-Côte d’Azur",
   "6": "Provence-Alpes-Côte d’Azur",
   "13": "Provence-Alpes-Côte d’Azur",
   "83": "Provence-Alpes-Côte d’Azur",
   "84": "Provence-Alpes-Côte d’Azur",
   "16": "Nouvelle-Aquitaine",
   "17": "Nouvelle-Aquitaine",
   "19": "Nouvelle-Aquitaine",
   "23": "Nouvelle-Aquitaine",
   "87": "Nouvelle-Aquitaine",
   "2A": "Corse",
   "2B": "Corse"
}


def traiter_csv(fichier_csv):
    """
    Traite le fichier CSV fourni.

    Retourne toujours un dictionnaire contenant :
        - réussite : 1 si le traitement réussit, sinon 0
        - data     : DataFrame pandas si succès, sinon None
    """
    resultat = {"réussite": 0, "data": None}

    try:

        # Classes de transformation des données
        class NonCommunique:
            @staticmethod
            def apply(value):
                if str(value) in ["", "00", "0", "0.0", "N"]:
                    return "NC"
                return value

        class OuiNon:
            @staticmethod
            def apply(value):
                if str(value).lower() == "n":
                    return "NON"
                elif str(value).lower() == "o":
                    return "OUI"
                return value

        class Decorate:
            @staticmethod
            def lower(value):
                return str(value).lower().strip()

            @staticmethod
            def apo(value):
                if isinstance(value, str):
                    return value.replace("?", "'")
                return value

            @staticmethod
            def upper(value):
                return str(value).strip().upper()

            @staticmethod
            def is_sunday(date):
                return 1 if date.weekday() == 6 else 0

            @staticmethod
            def contains_aphp(value):
                if isinstance(value, str):
                    if "aphp" in value.lower() or "ap-hp" in value.lower():
                        return "APHP"
                return None

            @staticmethod
            def get_status_code(status):
                status = str(status).lower()

                if (
                    "etudiant" in status
                    or "etudiant en sante" in status
                    or "etudiant hors sante" in status
                ):
                    return "E"
                elif "salarie" in status:
                    return "S"
                elif "liberal" in status:
                    return "L"
                elif "retraite" in status:
                    return "R"
                elif "nc" in status:
                    return "NC"

                return None

        def convert_departement_to_region(departement):
            return region_mapping.get(str(departement), "NC")

        # Lecture du fichier CSV
        df = pd.read_csv(
            fichier_csv,
            sep=";",
            encoding="utf-8"
        )

        #print(f"Lecture du fichier CSV réussie : {fichier_csv}")

        # Transformations des colonnes
        df["Âge"] = df["Âge"].apply(NonCommunique.apply)

        df["Métier"] = df["Métier"].apply(Decorate.upper)

        df["Profil de l'appelant"] = (
            df["Profil de l'appelant"].apply(Decorate.upper)
        )

        df["Statut de l'appelant"] = (
            df["Statut de l'appelant"].apply(Decorate.upper)
        )

        df["Région"] = (
            df["Département"].apply(convert_departement_to_region)
        )

        df["Orientation conseillée"] = (
            df["Orientation conseillée"].apply(Decorate.apo)
        )

        df["Nom du spécialiste conseillé"] = (
            df["Nom du spécialiste conseillé"]
            .apply(Decorate.upper)
            .apply(NonCommunique.apply)
        )

        df["Addiction OUI / NON -  quel produit"] = (
            df["Addiction OUI / NON -  quel produit"]
            .apply(Decorate.upper)
            .apply(NonCommunique.apply)
            .apply(OuiNon.apply)
        )

        # Suppression des colonnes inutiles
        df.drop(
            columns=["Type", "Entreprise"],
            inplace=True
        )

        # Extraction de la date et de l'heure
        def extract_date_time(datetime_str):
            try:
                date_str, time_str = datetime_str.split(" ", 1)
                return date_str.strip(), time_str.strip()
            except (ValueError, AttributeError):
                return pd.NaT, pd.NaT

        df[["Date", "Heure"]] = (
            df["Début"]
            .apply(extract_date_time)
            .apply(pd.Series)
        )

        # Identification des dimanches
        def get_sunday(date_str):
            try:
                date = datetime.strptime(date_str, "%d/%m/%Y")
                return Decorate.is_sunday(date)
            except (ValueError, TypeError):
                return None

        df["Dimanche"] = df["Date"].apply(get_sunday)

        # Identification APHP
        df["APHP"] = (
            df["Branche professionnelle"]
            .apply(Decorate.contains_aphp)
        )

        masque_aphp_vide = df["APHP"].isnull()

        df.loc[masque_aphp_vide, "APHP"] = (
            df.loc[masque_aphp_vide, "Profil de l'appelant"]
            .apply(Decorate.contains_aphp)
        )

        # Identification du statut de l'appelant
        df["Statut Code"] = (
            df["Statut de l'appelant"]
            .apply(Decorate.get_status_code)
        )

        # Réorganisation des colonnes
        columns_order = [
            "Dimanche",
            "Heure",
            "Date",
            "Fin",
            "Durée",
            "Motif",
            "Avis",
            "Code ANACT",
            "Âge",
            "Métier",
            "APHP",
            "Branche professionnelle",
            "Profil de l'appelant",
            "Statut de l'appelant",
            "Statut Code",
            "Département",
            "Région",
            "Gravité de l'appel (0 à 5)",
            "Sexe",
            "Orientation conseillée",
            "Nom du spécialiste conseillé",
            "Addiction OUI / NON -  quel produit",
        ]

        df = df.reindex(columns=columns_order)
        df.reset_index(drop=True, inplace=True)

        # Enregistrement du CSV transformé
        now = datetime.now()
        formatted_date = now.strftime("%Y-%m-%d-%H-%M-%S")

        fichier_sortie = (
            f"consultations_{formatted_date}.csv"
        )

        # df.to_csv(
        #     fichier_sortie,
        #     sep=";",
        #     index=False,
        #     encoding="utf-8-sig"
        # )

        #print(f"Enregistrement réussi : {fichier_sortie}")

        # Résultat du traitement
        resultat["réussite"] = 1
        resultat["data"] = df.values.tolist()
        return resultat

    except Exception as e:
        #print(
            #f"Erreur lors du traitement de '{fichier_csv}' : {e}",
            #file=sys.stderr
        #)
        return resultat


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Transforme un fichier CSV de consultations."
    )

    parser.add_argument(
        "fichier_csv",
        help="Chemin du fichier CSV à traiter"
    )

    args = parser.parse_args()

    resultat = traiter_csv(args.fichier_csv)
    outputs = {
    'downloads': resultat
                }

    Kestra.outputs(outputs)

