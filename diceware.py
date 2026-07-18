#!/usr/bin/env python3
"""Genere une liste diceware a partir d'une base de mots deja nettoyee.

La base SQLite est construite et geree a part par `build_db.py` (import du xlsx
Lexique, ajout de mots, info). Ce programme-ci ne fait QUE de la generation :
il choisit des mots et les met en forme (PDF par defaut, sinon console/texte/CSV).

Il lit deux tables (construites par build_db.py) :
  - `mots`         : les vrais mots (socle nettoye) ;
  - `mots_ajoutes` : les mots ajoutes a la main, inclus en priorite.

Principe du diceware : chaque mot porte un code obtenu en lancant des des a 6
faces. Pour une phrase de passe, on lance les des et on lit les mots. Plus il y a
de mots, plus le code est long, plus la phrase est difficile a deviner.
"""
import argparse
import hashlib
import math
import random
import re
import sqlite3
import sys
from collections import namedtuple
from datetime import date
from pathlib import Path

# Un mot valide ne contient que des lettres minuscules a..z.
MOT_VALIDE = re.compile(r"^[a-z]+$")

# Fichier optionnel listant des mots a jeter (un par ligne, '#' = commentaire).
FICHIER_EXCLUSIONS = Path(__file__).parent / "exclude.txt"

DB_PAR_DEFAUT = Path("lexique.db")

# Mise en page PDF, en millimetres (sauf interligne/police en points).
PDF_MARGE_G = 15        # marge gauche
PDF_MARGE_D = 15        # marge droite
PDF_MARGE_HAUT = 15     # marge haute
PDF_MARGE_BAS = 8       # marge basse (securite d'impression)
PDF_BANDEAU = 12        # hauteur du bandeau de titre sur les pages de mots
PDF_PIED = 5            # hauteur reservee au pied de page (hash + seed)
PDF_INTERLIGNE = 12     # points, hauteur d'une ligne de mot
PDF_POLICE = 9          # points, taille des mots (Courier)

# Table de separateurs (option) : 1 de -> 1 symbole, tire entre chaque mot.
# Les 6 plus faciles a taper (et non ambigus). log2(6) ~ 2,58 bits chacun.
SEPARATEURS = ["=", "?", "!", "@", "#", "$"]

# Resultat d'une selection, transporte entre les etapes de generer().
Plan = namedtuple("Plan", "sets_codes nb_des k max_sets vivier bits total_mots sous_titre")


# =========================================================================== #
# 1. Rassembler les mots (socle + ajouts, nettoyes)
# =========================================================================== #
def lire_mots(db, min_len, max_len, min_freq):
    """Mots du socle (table `mots`), du plus frequent au moins frequent."""
    requete = ("SELECT mot FROM mots WHERE length(mot) BETWEEN ? AND ? AND freq > ? "
               "ORDER BY freq DESC")
    with sqlite3.connect(db) as connexion:
        try:
            return [m for (m,) in connexion.execute(requete, (min_len, max_len, min_freq))]
        except sqlite3.OperationalError:            # table mots absente
            return []


def lire_mots_ajoutes(db, min_len, max_len):
    """Mots ajoutes a la main (table `mots_ajoutes`), filtres par longueur."""
    with sqlite3.connect(db) as connexion:
        try:
            lignes = connexion.execute("SELECT mot FROM mots_ajoutes").fetchall()
        except sqlite3.OperationalError:
            return []
    return [m for (m,) in lignes if min_len <= len(m) <= max_len]


def charger_exclusions(chemin):
    """Ensemble des mots a jeter (fichier : un mot par ligne, '#' = commentaire)."""
    if not chemin.exists():
        return set()
    exclus = set()
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        mot = ligne.split("#", 1)[0].strip().lower()
        if mot:
            exclus.add(mot)
    return exclus


def clean(mots, exclus):
    """Deduplique et retire les mots exclus, en conservant l'ordre d'entree.

    Les mots en tete (les ajouts) sont donc gardes en priorite. Le socle etant
    deja en a..z, le filtre MOT_VALIDE ne sert que de garde-fou pour les ajouts.
    """
    deja_vus, resultat = set(), []
    for mot in mots:
        mot = str(mot).strip().lower()
        if mot in deja_vus or mot in exclus or not MOT_VALIDE.match(mot):
            continue
        deja_vus.add(mot)
        resultat.append(mot)
    return resultat


def rassembler_mots(args):
    """Fusionne ajouts + socle et nettoie l'ensemble (ajouts prioritaires)."""
    exclus = charger_exclusions(FICHIER_EXCLUSIONS)
    ajouts = lire_mots_ajoutes(args.db, args.min_len, args.max_len)
    socle = lire_mots(args.db, args.min_len, args.max_len, args.min_freq)
    return clean(ajouts + socle, exclus)


# =========================================================================== #
# 2. Geometrie (des / sets), selection et codage
# =========================================================================== #
def plus_grande_puissance_de_six(n):
    """Plus grand d tel que 6**d <= n. Ex : n=20000 -> 5 (6**5=7776 <= 20000 < 6**6)."""
    d = 0
    while 6 ** (d + 1) <= n:
        d += 1
    return d


def calculer_geometrie(nb_mots, nb_sets_voulus):
    """Renvoie (d, taille_set, k, max_sets) selon le stock de mots disponible."""
    d = plus_grande_puissance_de_six(nb_mots)
    taille_set = 6 ** d
    max_sets = max(1, nb_mots // taille_set)
    k = max_sets if nb_sets_voulus <= 0 else min(nb_sets_voulus, max_sets)
    return d, taille_set, k, max_sets


def repartir_en_sets(mots, k):
    """Distribue les mots dans k sets a tour de role, puis trie chaque set."""
    sets = [[] for _ in range(k)]
    for position, mot in enumerate(mots):
        sets[position % k].append(mot)
    for un_set in sets:
        un_set.sort()
    return sets


def numero_vers_des(numero, nb_des):
    """Numero (0,1,2,...) -> code de des. Ex nb_des=5 : 0->'11111', 7775->'66666'."""
    code = ""
    for _ in range(nb_des):
        code = str(numero % 6 + 1) + code
        numero //= 6
    return code


def add_dice_codes(mots, nb_des):
    """Renvoie [(code, mot)] ; l'ordre alphabetique des mots donne l'ordre des codes."""
    return [(numero_vers_des(i, nb_des), mot) for i, mot in enumerate(mots)]


def selectionner(mots, args):
    """Choisit les mots, les repartit en sets et les code. Renvoie un Plan.

    Sans --shuffle : les `besoin` mots les plus frequents (deterministe).
    Avec --shuffle : on melange le VIVIER des plus frequents (facteur x besoin)
    pour rester memorable, puis on en prend `besoin`.
    """
    nb_des, taille_set, k, max_sets = calculer_geometrie(len(mots), args.sets)
    besoin = k * taille_set

    vivier = besoin
    if args.shuffle:
        hasard = random.Random(args.seed) if args.seed is not None else random.SystemRandom()
        vivier = min(len(mots), max(besoin, int(args.shuffle_factor * besoin)))
        choisis = mots[:vivier]
        hasard.shuffle(choisis)
        choisis = choisis[:besoin]
    else:
        choisis = mots[:besoin]

    sets_codes = [add_dice_codes(un_set, nb_des) for un_set in repartir_en_sets(choisis, k)]
    total = k * 6 ** nb_des
    sous_titre = f"{total} mots, {args.min_len}-{args.max_len} lettres"
    return Plan(sets_codes, nb_des, k, max_sets, vivier, math.log2(total), total, sous_titre)


# =========================================================================== #
# 3. Provenance : seed lisible + empreinte
# =========================================================================== #
def libelle_seed(args):
    """Texte decrivant l'origine de la liste (pour l'entete, le PDF, le pied)."""
    if not args.shuffle:
        return "liste standard déterministe (mots les plus fréquents)"
    if args.seed is not None:
        return f"{args.seed} (aléatoire reproductible)"
    return "aléa système (non reproductible)"


def empreinte_liste(sets_codes):
    """Hash court (sha256) identifiant la liste : set + code + mot de chaque ligne.

    Deux feuilles au meme hash sont identiques (verification / distinction).
    """
    canon = "\n".join(f"{s}:{code}:{mot}"
                      for s, paires in enumerate(sets_codes, 1)
                      for code, mot in paires)
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


# =========================================================================== #
# 4. Sorties texte (entete console, grille, CSV)
# =========================================================================== #
def afficher_entete(args, plan, n_candidats, seed_txt, empreinte):
    """Lignes d'information (prefixees '#') communes a toutes les sorties."""
    apercu = " · ".join(f"{L} mots={L * plan.bits:.0f}b" for L in (4, 5, 6, 7, 8))
    print(f"# {n_candidats} candidats -> {plan.k} set(s) de 6^{plan.nb_des} = {plan.total_mots} "
          f"mots | {plan.bits:.1f} bits/mot | {plan.max_sets} set(s) possible(s)")
    print(f"# entropie d'une phrase : {apercu}")
    print(f"# empreinte {empreinte} | seed : {seed_txt}")
    if args.shuffle:
        print(f"# liste ALEATOIRE : tiree parmi les {plan.vivier} mots les plus frequents ; "
              f"garder secrete = bonus non compte ; si elle fuite -> {plan.bits:.1f} bits/mot")
    if plan.k > 1:
        print(f"# pour tirer un mot : choisir un set 1..{plan.k} AU HASARD "
              f"(1 de, relancer si >{plan.k}) puis lancer {plan.nb_des} des")
        print(f"# les +{math.log2(plan.k):.1f} bits ne comptent que si le set est choisi au hasard")
    print()


def afficher_grille(paires, nb_colonnes):
    """Grille console : colonnes lues de haut en bas, puis colonne suivante."""
    nb_lignes = math.ceil(len(paires) / nb_colonnes)
    largeur_mot = max(len(mot) for _, mot in paires)
    for ligne in range(nb_lignes):
        cellules = []
        for colonne in range(nb_colonnes):
            indice = colonne * nb_lignes + ligne
            if indice < len(paires):
                code, mot = paires[indice]
                cellules.append(f"{code} {mot:<{largeur_mot}}")
        print("   ".join(cellules).rstrip())


def afficher_console(sets_codes, k, nb_colonnes, brut):
    """Affiche chaque set en grille (defaut) ou en brut 'set code mot' (--plain)."""
    for numero_set, paires in enumerate(sets_codes, start=1):
        if k > 1:
            print(f"== SET {numero_set}/{k} ==")
        if brut:
            prefixe = f"{numero_set} " if k > 1 else ""
            for code, mot in paires:
                print(f"{prefixe}{code} {mot}")
        else:
            afficher_grille(paires, nb_colonnes)
        if k > 1:
            print()


def ecrire_csv(sets_codes, chemin):
    """Ecrit la liste en CSV : colonnes set, code, mot (une ligne par mot)."""
    import csv
    with open(chemin, "w", newline="", encoding="utf-8") as fichier:
        redacteur = csv.writer(fichier)
        redacteur.writerow(["set", "code", "mot"])
        for numero_set, paires in enumerate(sets_codes, start=1):
            for code, mot in paires:
                redacteur.writerow([numero_set, code, mot])


# =========================================================================== #
# 5. Sortie PDF : page de garde + pages de mots
# =========================================================================== #
def construire_infos(sous_titre, nb_des, k, bits, seed_txt, empreinte):
    """Contenu de la page de garde, en elements typees dessines plus bas :
      ("txt", s)              paragraphe (serif)
      ("mono", s)             ligne a chasse fixe (Courier)
      ("septable", head, sym) table des separateurs : 2 lignes + filet
      ("gap",)                espace vertical
    """
    def txt(s):
        return ("txt", s)

    def mono(s):
        return ("mono", s)

    gap = ("gap",)

    faces = ["3", "1", "4", "2", "6", "5"][:nb_des]
    consignes = [txt("Pour chaque mot de la phrase :")]
    if k > 1:
        consignes.append(txt(f"0. Choisissez un jeu au hasard : un dé (relancez si le résultat > {k})."))
    consignes += [
        txt(f"1. Lancez {nb_des} dés et lisez-les de gauche à droite : un code de {nb_des} chiffres."),
        txt("2. Cherchez ce code dans la liste ; le mot en face est votre mot."),
        txt("3. Recommencez pour 6 mots ou plus, reliés par un séparateur."),
        gap,
        mono(f"Exemple :  dés {' '.join(faces)}  ->  code {''.join(faces)}  ->  le mot en face"),
    ]

    bits_sep = math.log2(len(SEPARATEURS))
    entete = "  " + "    ".join(str(i) for i in range(1, len(SEPARATEURS) + 1))
    symboles = "  " + "    ".join(SEPARATEURS)
    contraintes = [
        txt("Un tiret suffit. Si un service exige plusieurs classes de caractères :"),
        gap,
        txt("Spécial — entre deux mots, tirez 1 dé et prenez le symbole :"),
        ("septable", entete, symboles),
        txt("Majuscule — mettez une capitale à la 1re lettre d'un mot."),
        txt("Chiffre — ajoutez un chiffre à une extrémité de la phrase."),
        gap,
        txt(f"Le séparateur ajoute ~{bits_sep:.1f} bits par espace (~+{round(5 * bits_sep)} bits sur 6 mots)."),
        txt("Majuscule et chiffre : simples ajouts de conformité — la force vient des mots."),
    ]

    entropie = [
        txt(f"Chaque mot apporte environ {bits:.1f} bits."),
        txt(f"6 mots ~ {round(6 * bits)} bits · 7 mots ~ {round(7 * bits)} · 8 mots ~ {round(8 * bits)}."),
        gap,
        txt("Un mot de passe humain de 8 à 10 caractères vaut ~30 à 50 bits."),
        txt("Au-delà de ~80 bits, une attaque hors-ligne devient hors de portée :"),
        txt("visez 6 mots pour un secret maître, 7 à 8 pour davantage."),
    ]

    empreinte_bloc = [
        mono(f"Seed : {seed_txt}"),
        mono(f"Hash : {empreinte}"),
        mono(f"Généré le {date.today().isoformat()}"),
    ]

    return {
        "titre": sous_titre,
        "lead": "Feuille de référence pour composer une phrase de passe par tirage de dés.",
        "pied": f"Hash {empreinte} --- Seed : {seed_txt}",
        "sections": [
            ("Consignes", consignes),
            ("Contraintes de service (option)", contraintes),
            ("Entropie", entropie),
            ("Empreinte", empreinte_bloc),
        ],
    }


def _dessiner_septable(feuille, x, y, entete, symboles, mm):
    """Table des separateurs : ligne des chiffres, filet, ligne des symboles."""
    feuille.setFont("Courier", 11)
    feuille.drawString(x, y, entete)
    feuille.setStrokeColorRGB(0.55, 0.55, 0.55)
    feuille.setLineWidth(0.5)
    feuille.line(x, y - 1.8 * mm, x + len(entete) * 6.6, y - 1.8 * mm)
    feuille.drawString(x, y - 6 * mm, symboles)
    return y - 12 * mm


def _dessiner_couverture(feuille, infos, mm):
    """Page de garde facon article : titre centre, filet, sections numerotees."""
    from reportlab.lib.pagesizes import A4
    largeur, hauteur = A4
    xg, xd = PDF_MARGE_G * mm, largeur - PDF_MARGE_D * mm
    x_txt, x_mono = xg + 5 * mm, xg + 7 * mm
    y = hauteur - (PDF_MARGE_HAUT + 6) * mm

    feuille.setFillColorRGB(0, 0, 0)                  # tout est noir sur la couverture
    feuille.setFont("Times-Bold", 20)
    feuille.drawCentredString(largeur / 2, y, "Liste Diceware — Francais")
    y -= 7 * mm
    feuille.setFont("Times-Italic", 10)
    feuille.drawCentredString(largeur / 2, y, infos["titre"])
    y -= 6 * mm
    feuille.setStrokeColorRGB(0, 0, 0)
    feuille.setLineWidth(0.6)
    feuille.line(xg, y, xd, y)
    y -= 9 * mm
    feuille.setFont("Times-Italic", 10.5)
    feuille.drawString(xg, y, infos["lead"])
    y -= 11 * mm

    for numero, (titre_section, elements) in enumerate(infos["sections"], start=1):
        feuille.setFont("Times-Bold", 13)
        feuille.drawString(xg, y, f"{numero}.  {titre_section}")
        y -= 7 * mm
        for kind, *val in elements:
            if kind == "txt":
                feuille.setFont("Times-Roman", 10.5)
                feuille.drawString(x_txt, y, val[0])
                y -= 5.4 * mm
            elif kind == "mono":
                feuille.setFont("Courier", 8)
                feuille.drawString(x_mono, y, val[0])
                y -= 5.4 * mm
            elif kind == "septable":
                y = _dessiner_septable(feuille, x_mono, y, val[0], val[1], mm)
            elif kind == "gap":
                y -= 3 * mm
        y -= 4 * mm
    feuille.showPage()


def ecrire_pdf(sets_codes, chemin, nb_colonnes, sous_titre, infos):
    """PDF en vrai texte (Ctrl+F sur code et mot) : page de garde puis pages de mots.

    Chaque set commence sur une nouvelle page. Necessite la librairie reportlab.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
        from reportlab.pdfbase.pdfmetrics import stringWidth
    except ModuleNotFoundError:
        sys.exit("reportlab requis pour le PDF : pip install reportlab "
                 "(ou utilise --console / --plain / --csv)")

    largeur, hauteur = A4
    marge_g, marge_d = PDF_MARGE_G * mm, PDF_MARGE_D * mm
    marge_haut, marge_bas = PDF_MARGE_HAUT * mm, PDF_MARGE_BAS * mm
    interligne = PDF_INTERLIGNE
    pied = infos.get("pied") if infos else None

    y_titre = hauteur - marge_haut
    y_haut = y_titre - PDF_BANDEAU * mm                       # 1re ligne de mots
    lignes_par_page = max(1, int((y_haut - marge_bas - PDF_PIED * mm) / interligne))
    largeur_colonne = (largeur - marge_g - marge_d) / nb_colonnes
    mots_par_page = lignes_par_page * nb_colonnes
    nb_sets = len(sets_codes)

    def dessiner_bandeau(etiquette, page, nb_pages):
        feuille.setFillColorRGB(0, 0, 0)
        feuille.setFont("Times-Bold", 10)
        feuille.drawString(marge_g, y_titre, f"Liste Diceware — {sous_titre}{etiquette}")
        feuille.setFont("Times-Roman", 8)
        feuille.drawRightString(largeur - marge_d, y_titre, f"p. {page}/{nb_pages}")
        feuille.setStrokeColorRGB(0, 0, 0)
        feuille.setLineWidth(0.4)
        feuille.line(marge_g, y_titre - 3 * mm, largeur - marge_d, y_titre - 3 * mm)

    def dessiner_guides(nb_lignes):
        # Filets gris tous les 5 rangs + separateurs de colonnes (aide a la lecture).
        feuille.setStrokeColorRGB(0.7, 0.7, 0.7)
        feuille.setLineWidth(0.25)
        for r in range(5, nb_lignes, 5):
            yy = y_haut - (r - 0.7) * interligne
            feuille.line(marge_g, yy, largeur - marge_d, yy)
        for c in range(1, nb_colonnes):
            xx = marge_g + c * largeur_colonne - 1 * mm
            feuille.line(xx, y_haut + interligne * 0.4,
                         xx, y_haut - (nb_lignes - 1) * interligne - interligne * 0.4)

    def dessiner_pied():
        if not pied:
            return
        feuille.setStrokeColorRGB(0.8, 0.8, 0.8)
        feuille.setLineWidth(0.3)
        feuille.line(marge_g, marge_bas + 2.5 * mm, largeur - marge_d, marge_bas + 2.5 * mm)
        feuille.setFillColorRGB(0.4, 0.4, 0.4)
        feuille.setFont("Courier-Bold", 9)
        feuille.drawCentredString(largeur / 2, marge_bas, pied)

    feuille = canvas.Canvas(str(chemin), pagesize=A4)
    if infos:
        _dessiner_couverture(feuille, infos, mm)

    for numero_set, paires in enumerate(sets_codes, start=1):
        etiquette = f"  —  SET {numero_set}/{nb_sets}" if nb_sets > 1 else ""
        nb_pages = max(1, math.ceil(len(paires) / mots_par_page))
        for page in range(nb_pages):
            morceau = paires[page * mots_par_page:(page + 1) * mots_par_page]
            nb_lignes = math.ceil(len(morceau) / nb_colonnes)

            dessiner_bandeau(etiquette, page + 1, nb_pages)
            dessiner_guides(nb_lignes)
            feuille.setFillColorRGB(0, 0, 0)
            feuille.setFont("Courier", PDF_POLICE)
            for indice, (code, mot) in enumerate(morceau):
                colonne, ligne = divmod(indice, nb_lignes)
                x = marge_g + colonne * largeur_colonne
                y = y_haut - ligne * interligne
                feuille.drawString(x, y, f"{code}  {mot}")
            dessiner_pied()
            feuille.showPage()
    feuille.save()


# =========================================================================== #
# Orchestration
# =========================================================================== #
def ecrire_sortie(args, plan, seed_txt, empreinte):
    """Aiguille vers la sortie demandee (CSV, console/brut, ou PDF par defaut)."""
    if args.csv:
        ecrire_csv(plan.sets_codes, args.csv)
        print(f"CSV ecrit : {args.csv}")
    elif args.console or args.plain:
        afficher_console(plan.sets_codes, plan.k, args.cols, args.plain)
    else:
        infos = construire_infos(plan.sous_titre, plan.nb_des, plan.k, plan.bits, seed_txt, empreinte)
        ecrire_pdf(plan.sets_codes, args.pdf, args.cols, plan.sous_titre, infos)
        print(f"PDF ecrit : {args.pdf}")


def generer(args):
    if not args.db.exists():
        sys.exit(f"Base absente : {args.db} (construis-la avec build_db.py)")
    mots = rassembler_mots(args)
    if not mots:
        sys.exit("Aucun mot retenu : base vide ? filtres trop stricts ?")

    plan = selectionner(mots, args)
    seed_txt = libelle_seed(args)
    empreinte = empreinte_liste(plan.sets_codes)

    afficher_entete(args, plan, len(mots), seed_txt, empreinte)
    ecrire_sortie(args, plan, seed_txt, empreinte)


def lire_options():
    p = argparse.ArgumentParser(
        prog="diceware", description="Genere une liste diceware depuis la base nettoyee "
                                     "(construite par build_db.py)")
    p.add_argument("--db", type=Path, default=DB_PAR_DEFAUT)
    p.add_argument("--min_len", type=int, default=4, help="longueur mini d'un mot (defaut 4)")
    p.add_argument("--max_len", type=int, default=10, help="longueur maxi d'un mot (defaut 10)")
    p.add_argument("--min_freq", type=float, default=0.0,
                   help="frequence mini (defaut 0 = tous ; augmenter pour des mots plus courants)")
    p.add_argument("--sets", type=int, default=1,
                   help="nombre de sets de 6**d mots (defaut 1, 0 = automatique/maximum)")
    p.add_argument("--shuffle", action="store_true",
                   help="liste tiree AU HASARD (unique a chaque fois ; a garder secrete)")
    p.add_argument("--shuffle_factor", type=float, default=2.0,
                   help="avec --shuffle : tirer parmi les (facteur x mots_necessaires) plus "
                        "frequents, pour rester memorable (defaut 2 ; 1 = pas de hasard)")
    p.add_argument("--seed", type=int, default=None,
                   help="graine du hasard : rend la liste reproductible")
    p.add_argument("--cols", type=int, default=5, help="colonnes affichees / PDF (defaut 5)")
    # Sortie : PDF par defaut ; --console (grille), --plain (brut) ou --csv sinon.
    p.add_argument("--pdf", type=Path, default=Path("diceware-fr.pdf"),
                   help="chemin du PDF (defaut diceware-fr.pdf)")
    p.add_argument("--csv", type=Path, default=None, help="ecrire un CSV au lieu du PDF")
    p.add_argument("--console", action="store_true", help="afficher la grille dans le terminal")
    p.add_argument("--plain", action="store_true", help="afficher en brut 'set code mot'")
    return p.parse_args()


def main():
    generer(lire_options())


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:      # sortie coupee par | head ou | less
        sys.exit(0)
