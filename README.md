# `diceware-fr`

Générateur de listes "Diceware" avec lexique français. Ici le lexique provient du _Lexique 4.00_ sur [lexique.org](http://www.lexique.org/).

---
## C'est quoi le Diceware

> [!info] Définition
> _Le diceware, ou méthode du lancer de dés [...], est, en cryptologie, une méthode employée pour créer des phrases secrètes, des mots de passe et d'autres variables cryptographiques en utilisant un dé ordinaire à six faces comme générateur de nombres aléatoires physique._ — [Wikipedia](https://fr.wikipedia.org/wiki/Diceware)

L'objectif ici : produire une phrase de passe dont chaque mot est sélectionné par une **véritable source aléatoire** (le dé) dans une grande liste. La phrase est ainsi **aisément mémorisable** et **résistante au crack par force brute**.

## De la robustesse d'un mot de passe

La « force » d'un mot de passe s'estime par son _entropie_. [Wiki](https://fr.wikipedia.org/wiki/Robustesse_d%27un_mot_de_passe)

$$ E = n \times \log_2(G)$$

- $E$ : entropie (en bits) ;
- $n$ : nombre d'éléments (caractères ou mots) ;
- $\log_2$ : logarithme binaire, qui donne le nombre de bits ;
- $G$ : la _gamme_ (nombre de variations possibles par élément).

> [!error] Condition de tirage
> Il est **impératif** que chaque élément (mot ou caractère) soit tiré **aléatoirement** (dé ou vrai générateur d'aléa). Sinon l'entropie — donc la robustesse — s'effondre. **La majorité des mots de passe sont devinés, pas « cassés ».**

Exemples :

- 8 chiffres seuls : $E = 8 \times \log_2(10) = 8 \times 3{,}322 = 26{,}6$ bits.
- 8 caractères ASCII imprimables hors espace ($G = 94$) : $E = 8 \times \log_2(94) = 8 \times 6{,}55 = 52{,}4$ bits.
- Phrase de passe : $n$ = nombre de mots, $G$ = taille du dictionnaire de tirage. Pour le Diceware, $G = 7776$ (voir plus bas la section **« Nombre de mots »** pour le pourquoi).

> [!warning] Ajouter un élément plutôt qu'agrandir la gamme
> Pour renforcer un mot de passe, mieux vaut **ajouter un caractère ou un mot aléatoire** que d'agrandir la gamme $G$ : l'entropie croît linéairement avec $n$, mais seulement de façon **logarithmique** avec $G$.

D'où le tableau (entropie en bits selon la gamme et le nombre d'éléments) :

| Gamme                       | $n=5$ | $n=6$ | $n=7$ | $n=8$  | $n=10$ | $n=14$ | $n=20$ |
| --------------------------- | ----- | ----- | ----- | ------ | ------ | ------ | ------ |
| `[0-9]` = 10                | 16,61 | 19,93 | 23,25 | 26,58  | 33,22  | 46,51  | 66,44  |
| `[a-z0-9]` = 36             | 25,85 | 31,02 | 36,19 | 41,36  | 51,70  | 72,38  | 103,40 |
| `[A-Za-z0-9@#+= ?!/[` = 94  | 32,77 | 39,33 | 45,88 | 52,44  | 65,55  | 91,76  | 131,09 |
| `Diceware` = 7776           | 64,62 | 77,55 | 90,47 | 103,40 | 129,25 | 180,95 | 258,50 |

> [!info] Robustesse nécessaire
> Au-delà de **~72 bits** un mot de passe est jugé suffisamment robuste ; au-delà de **~80 bits** il est considéré incassable par force brute pour une entité « classique » (temps de calcul hors de portée). Une phrase de **6 mots** Diceware (~77 bits) atteint déjà ce seuil.

---
## Source

Télécharger le xlsx Lexique : https://www.lexique.org/ (ou dépôt openlexicon).

## Installation

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Deux programmes aux rôles nets :
- **`build_db.py`** : **gestion de la base** (import du xlsx, ajout de mots, info).
  C'est là qu'a lieu tout le nettoyage.
- **`diceware.py`** : **génération pure** de la liste. Ne modifie jamais la base.

La base a deux tables : `mots` (socle nettoyé) et `mots_ajoutes` (mots ajoutés à la
main). Les deux sont fusionnées et dédoublonnées à la génération.

```sh
# --- Gestion de la base (build_db.py) ---
python build_db.py import Lexique4.xlsx            # xlsx -> table mots nettoyee
python build_db.py add recents.txt perso.txt      # ajoute des mots (persiste, dedoublonne)
python build_db.py info                            # etat de la base
```

```sh
# --- Generation (diceware.py) : sortie PDF par defaut, liste ronde 6^d ---
python diceware.py                                 # ecrit diceware-fr.pdf
python diceware.py --pdf liste.pdf                # PDF a un autre nom
python diceware.py --console --cols 4             # grille dans le terminal
python diceware.py --plain > liste.txt            # brute 'set code mot', 1/ligne
python diceware.py --csv liste.csv                # export CSV (set,code,mot)
python diceware.py --sets 0 --min_len 3           # multi-sets auto (+ entropie)
python diceware.py --shuffle --pdf secret.pdf     # liste ALEATOIRE unique (secrete)
python diceware.py --shuffle --seed 1234          # idem mais reproductible (graine)
```

Pour ajouter des mots : `build_db.py add` (persisté dans la base).

Sortie : **PDF par défaut** (`diceware-fr.pdf`) ; sinon `--console` (grille),
`--plain` (brut) ou `--csv`. L'en-tête rappelle l'entropie selon la longueur de
phrase (4 à 8 mots).

## Nombre de mots : liste ronde (puissance de 6)

On rogne à la **plus grande puissance de 6 ≤ nb de candidats** (`6^d`). La liste
est « ronde » : chaque code de dés correspond à un mot, code max = `6…6`, aucun
tirage à rejeter. On garde les `6^d` mots **les plus fréquents**.

Pourquoi viser haut : chaque mot vaut `d × log2(6) ≈ d × 2,585` bits. Plus il y
a de mots, plus `d` est grand, plus l'entropie par mot monte. On maximise donc
le nombre de candidats (fréquence, longueur) pour atteindre le `6^d` supérieur.

**Plafond réel de ce Lexique** : ~37 700 candidats max (< 46 656), donc la plus
grande liste ronde atteignable est **7776 mots = 5 dés = 12,9 bits/mot** — la
taille diceware standard.

## Multi-sets (`--sets`) : plus d'entropie sans plus de dés

Quand on ne peut pas atteindre `6^(d+1)` (il faudrait 46 656 mots), on découpe le
pool en **k sets de `6^d` mots**. Un mot = `(set, code de dés)`, ce qui porte
l'entropie à `log2(k · 6^d) = d·log2(6) + log2(k)` bits.

- `--sets 0` : auto = `pool // 6^d` sets pleins. `--sets N` : borné à ce max.
- **Tirage** : choisir le set **au hasard** (1 dé, relancer si `> k`) puis rouler
  les `d` dés. Le dé de set réintroduit un petit rejet (celui qu'on évitait sur le mot).
- ⚠️ **Le `+log2(k)` n'existe que si le set est choisi aléatoirement**, pas par
  préférence. Sinon on reste à `d·log2(6)` bits.

### Répartition : round-robin stratifié (pas alphabétique)

Le pool trié par fréquence est distribué par `rang i → set i mod k`. Chaque set
reçoit donc le même profil de fréquence **et** couvre tout l'alphabet `a..z` — pas
de set « poubelle » de mots rares ni de tranche alphabétique. Déterministe et
reproductible (mieux qu'un shuffle, équilibré seulement en moyenne).

> Note : la répartition n'a **aucun** effet sur l'entropie (chaque mot reste
> équiprobable si les sets sont pleins et le tirage uniforme). C'est un critère de
> **représentativité**, pas de sécurité.

*Alternative non implémentée* : une seule liste + rejet sur 6 dés (relancer si le
code dépasse le pool). Utilise tout le pool (~15,2 bits) au prix d'un rejet plus
fréquent. Le multi-sets garde des sous-listes propres de 5 dés.

## Liste aléatoire (`--shuffle`)

Par défaut la liste est **déterministe** : les mots les plus fréquents, triés,
**toujours la même liste**. C'est le mode « feuille standard, ré-imprimable à
l'identique ». Avec `--shuffle`, on mélange tout le stock et on en tire un
échantillon → **une liste différente à chaque exécution**.

- Hasard **cryptographique** (`SystemRandom` → `os.urandom`). Le `random` par défaut
  de Python n'est **pas** utilisé pour le tirage.
- `--seed N` rend la liste **reproductible** (pour ré-imprimer la même). Attention :
  la sécurité se réduit alors à la graine — une graine faible = liste devinable.
  Sans `--shuffle`, `--seed` n'a aucun effet (rien à mélanger).
- **Mémorabilité** : `--shuffle` ne mélange pas tout le stock (qui contient des mots
  rares) mais seulement le **vivier** des mots les plus fréquents, de taille
  `--shuffle_factor × mots_nécessaires` (défaut 2). `1` = pas de hasard réel ; plus
  grand = plus de variété mais mots moins courants.

## Ajouter des mots (`build_db.py add`)

`python build_db.py add fichier.txt` ajoute des mots à la base (table
`mots_ajoutes`) — utile pour des mots récents. Format : un mot par ligne, `#` =
commentaire. Ces mots sont **prioritaires** (toujours retenus) et **dédoublonnés**
(clé primaire). Ils sont fusionnés au socle à la génération.

## Export CSV (`--csv`)

`--csv FICHIER` écrit la liste en CSV avec les colonnes `set,code,mot` (une ligne par
mot). Pratique pour un tableur ou un autre outil.

Le tirage de la phrase se fait **toujours aux dés réels**, sur la liste imprimée.

⚠️ **Le secret de la liste est un bonus NON comptabilisé** (principe de Kerckhoffs) :
compte toujours ton entropie comme si la liste était publique (`log2` de sa taille).
Si la liste fuite, tu retombes sur cette valeur — ce qui reste correct. Ne t'appuie
jamais sur le secret de la liste comme défense principale.

## PDF cherchable

Sortie **par défaut** (`diceware-fr.pdf`). La **1re page** est une page de garde
façon article (police serif, titre centré, filet, sections numérotées) :
- **Consignes** : comment lancer les dés et lire les mots (auto-suffisant sur papier) ;
- **Contraintes de service (option)** : comment satisfaire les politiques qui
  exigent plusieurs classes de caractères — **spécial** (séparateur tiré au dé
  parmi `= ? ! @ # $`, `+~2,6 bits/espace`), **majuscule** (capitaliser une lettre)
  et **chiffre** (en ajouter un). Honnête : ces ajouts servent surtout à passer les
  contrôles, la force vient des mots. Symboles éditables via `SEPARATEURS` ;
- **Entropie** : bits/mot + longueurs conseillées + repères (mot de passe humain, seuils) ;
- **Empreinte** : `Seed` (comment reproduire la liste) et `Hash` (identifier/vérifier
  la feuille — deux impressions au même hash sont identiques). Le hash et le seed
  sont aussi affichés en console.

Pages de mots : **marge basse élargie** (sécurité d'impression) et guides de lecture
discrets — filet gris clair tous les 5 rangs + séparateurs de colonnes (pas de
remplissage zébré). Mise en page réglable via les constantes `PDF_*` en tête de
`diceware.py`.

`--pdf` produit un PDF en **texte réel** (reportlab) : `Ctrl+F` fonctionne sur le
code **et** sur le mot. Comme les codes sont attribués dans l'ordre alphabétique,
la liste est **triée à la fois par index et par mot** — une seule table sert aux
deux recherches (mot → code et code → mot).

## Logique de l'indice

- `d` = plus grand entier tel que `6^d <= nb_candidats` ; on garde `6^d` mots.
- Chaque mot reçoit un code base-6 en chiffres `1..6` (`11111` … `66666`).
- Codes attribués dans l'ordre alphabétique → ordre alpha == ordre des codes.

## Nettoyage à l'import (`build_db.py`)

Principe : **on ne retire que ce qui n'est pas un mot**, on garde le maximum de
vrais mots (même rares) pour des passphrases de toute longueur. Colonnes Lexique
utilisées (voir les constantes en tête de `build_db.py`) :

- **lemmes uniquement** (`14_IsLem = 1`) → ni conjugaison ;
- **pas de pluriel** (`8_Nombre <> 'p'`) → pas d'accord ;
- **pas d'onomatopée pure** (`5_Cgram <> 'ONO'`) → retire `brrr`, `beurk`, `vroum`…
  mais **garde** les mots qui ont aussi une entrée réelle (`bravo` = ONO **et** NOM) ;
- **au moins une voyelle** (`19_CVOrtho` contient `V`) → retire `pfft`, `zzzz`… ;
- **`[a-z]` strict** → exclut accents, tirets, apostrophes, chiffres ;
- **`12_FreqLemme > 0`** → retire les mots jamais attestés ;
- **dédupliqué** sur le mot (clé primaire ; on garde la fréquence la plus haute).

Résultat : ~38 600 mots propres (~35 500 en 3–12 lettres). Note : la contrainte
`[a-z]` sacrifie les mots accentués (`été`, `forêt`) — non par « junk » mais pour
qu'une passphrase soit **saisissable sans ambiguïté** au clavier.

À la génération, on filtre en plus par longueur (`--min_len`/`--max_len`) et
fréquence mini optionnelle (`--min_freq`, défaut 0), on applique `exclude.txt`, et
la liste finale est triée alphabétiquement.

### exclude.txt

La plupart des non-mots sont déjà retirés à l'import. `exclude.txt` ne sert plus
que pour des résidus à écarter à la main (anglicismes, ou noms tagués `NOM` que tu
juges indésirables comme `miam`/`boum`). Un mot par ligne, `#` = commentaire. Les
mots ajoutés via `build_db.py add` ne sont soumis à aucun filtre (curation manuelle).

## Crédits

Outil personnel. Code et documentation rédigés avec l'assistance de **Claude**
(Claude Code, Anthropic), sous direction, relecture et tests humains. Les choix de
conception et le contenu pédagogique (section « De la robustesse ») sont de l'auteur.
