#!/usr/bin/env python3
"""Construit et gere la base de mots (fichier SQLite) utilisee par diceware.py.

Sous-commandes :
  import <xlsx>    convertit un xlsx Lexique en table `mots` NETTOYEE
  add <fichiers>   ajoute des mots a la main (table `mots_ajoutes`) ; dedoublonne
  info             affiche l'etat de la base

Nettoyage (import) : on ne garde que de VRAIS mots. On retire uniquement ce qui
n'est PAS un mot :
  - formes non-lemmes (conjugaisons, feminins) et pluriels  -> IsLem=1, Nombre<>p
  - onomatopees pures (categorie ONO : brrr, beurk, vroum)  -> Cgram<>ONO
    (on garde les mots ayant aussi une entree reelle, ex. bravo = ONO ET NOM)
  - "mots" sans voyelle (structure CVOrtho sans V : pfft)   -> CVOrtho contient V
  - tout ce qui n'est pas en lettres a..z (accents, tirets, chiffres)
  - frequence nulle (jamais attestes)                       -> FreqLemme > 0
On GARDE les mots rares mais reels : le but est un maximum de bons mots.

Tables : mots(mot PRIMARY KEY, freq, cgram) et mots_ajoutes(mot PRIMARY KEY, ...).
"""
import argparse
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

# Colonnes du xlsx Lexique utilisees (a adapter ici si la version differe).
MOT = "1_Mot"
CGRAM = "5_Cgram"
NOMBRE = "8_Nombre"
FREQ = "12_FreqLemme"
ISLEM = "14_IsLem"
CVORTHO = "19_CVOrtho"

# Condition SQL "vrai mot" : ce qui passe est verse dans la table `mots`.
FILTRE_VRAIS_MOTS = f'''
    CAST("{ISLEM}" AS INTEGER) = 1                       -- lemme (ni conjugaison ni pluriel)
    AND ("{NOMBRE}" IS NULL OR "{NOMBRE}" <> 'p')        -- pas de pluriel
    AND "{FREQ}" > 0                                     -- atteste au moins une fois
    AND "{CVORTHO}" LIKE '%V%'                           -- au moins une voyelle (vire pfft, zzzz)
    AND "{CGRAM}" <> 'ONO'                               -- pas une onomatopee pure
    AND LOWER("{MOT}") NOT GLOB '*[^a-z]*'               -- que des lettres a..z
'''

MOT_VALIDE = re.compile(r"^[a-z]+$")
DB_PAR_DEFAUT = Path("lexique.db")


def compter(connexion, table):
    """Nombre de lignes d'une table, ou 0 si la table n'existe pas encore."""
    try:
        return connexion.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return 0


# --------------------------------------------------------------------------- #
# import : xlsx -> table `mots` nettoyee
# --------------------------------------------------------------------------- #
def cmd_import(args):
    if not args.xlsx.exists():
        sys.exit(f"Fichier introuvable : {args.xlsx}")
    try:
        import pandas as pd
    except ModuleNotFoundError:
        sys.exit("pandas requis : pip install pandas openpyxl")

    df = pd.read_excel(args.xlsx)
    df.columns = [str(c).strip() for c in df.columns]

    with sqlite3.connect(args.db) as connexion:
        # 1. Charger le xlsx tel quel dans une table temporaire.
        df.to_sql("_import", connexion, if_exists="replace", index=False)
        total = compter(connexion, "_import")

        # 2. (Re)creer la table propre et n'y verser que les vrais mots.
        connexion.execute("DROP TABLE IF EXISTS lexique")   # ancienne table brute eventuelle
        connexion.execute("DROP TABLE IF EXISTS mots")
        connexion.execute("CREATE TABLE mots (mot TEXT PRIMARY KEY, freq REAL, cgram TEXT)")
        # INSERT OR IGNORE + tri par frequence => on garde la frequence la plus haute
        # pour un mot donne, et le dedoublonnage est automatique (cle primaire).
        connexion.execute(f'''
            INSERT OR IGNORE INTO mots (mot, freq, cgram)
            SELECT LOWER("{MOT}"), "{FREQ}", "{CGRAM}"
            FROM _import
            WHERE {FILTRE_VRAIS_MOTS}
            ORDER BY "{FREQ}" DESC
        ''')
        garde = compter(connexion, "mots")
        connexion.execute("CREATE INDEX IF NOT EXISTS idx_freq ON mots(freq)")
        connexion.execute("DROP TABLE _import")

    print(f"{total} lignes lues -> {garde} mots propres dans {args.db} (table mots)")


# --------------------------------------------------------------------------- #
# add : faire grossir la base (fichiers texte -> table mots_ajoutes)
# --------------------------------------------------------------------------- #
def cmd_add(args):
    with sqlite3.connect(args.db) as connexion:
        connexion.execute(
            "CREATE TABLE IF NOT EXISTS mots_ajoutes "
            "(mot TEXT PRIMARY KEY, source TEXT, ajoute_le TEXT)")
        avant = compter(connexion, "mots_ajoutes")
        for fichier in args.fichiers:
            if not fichier.exists():
                sys.exit(f"Fichier introuvable : {fichier}")
            for ligne in fichier.read_text(encoding="utf-8").splitlines():
                mot = ligne.split("#", 1)[0].strip().lower()
                if mot and MOT_VALIDE.match(mot):
                    connexion.execute(
                        "INSERT OR IGNORE INTO mots_ajoutes (mot, source, ajoute_le) "
                        "VALUES (?, ?, ?)",
                        (mot, fichier.name, date.today().isoformat()))
        apres = compter(connexion, "mots_ajoutes")
    print(f"{apres - avant} nouveau(x) mot(s) ; {apres} au total dans mots_ajoutes")


# --------------------------------------------------------------------------- #
# info : etat de la base
# --------------------------------------------------------------------------- #
def compter_doublons(connexion):
    """Mots ajoutes deja presents dans le socle (seul doublon possible, les tables
    ayant chacune une cle primaire). Renvoie 0 si une table manque."""
    try:
        return connexion.execute(
            "SELECT COUNT(*) FROM mots_ajoutes WHERE mot IN (SELECT mot FROM mots)"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def cmd_info(args):
    if not args.db.exists():
        sys.exit(f"Base absente : {args.db}")
    with sqlite3.connect(args.db) as connexion:
        n_mots = compter(connexion, "mots")
        n_ajoutes = compter(connexion, "mots_ajoutes")
        n_doublons = compter_doublons(connexion)
    print(f"Base : {args.db}")
    print(f"  mots         : {n_mots} mots propres (socle)")
    print(f"  mots_ajoutes : {n_ajoutes} mots (ajouts)")
    print(f"  doublons     : {n_doublons} (ajouts déjà présents dans le socle)")


def main():
    parser = argparse.ArgumentParser(
        prog="build_db", description="Construit et gere la base de mots pour diceware.py")
    sous = parser.add_subparsers(dest="commande", required=True)

    p_imp = sous.add_parser("import", help="xlsx Lexique -> table mots nettoyee")
    p_imp.add_argument("xlsx", type=Path, help="chemin du fichier Lexique .xlsx")
    p_imp.add_argument("--db", type=Path, default=DB_PAR_DEFAUT)
    p_imp.set_defaults(func=cmd_import)

    p_add = sous.add_parser("add", help="ajouter des mots (fait grossir la base)")
    p_add.add_argument("fichiers", nargs="+", type=Path, help="fichiers de mots (1 par ligne)")
    p_add.add_argument("--db", type=Path, default=DB_PAR_DEFAUT)
    p_add.set_defaults(func=cmd_add)

    p_info = sous.add_parser("info", help="afficher l'etat de la base")
    p_info.add_argument("--db", type=Path, default=DB_PAR_DEFAUT)
    p_info.set_defaults(func=cmd_info)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
