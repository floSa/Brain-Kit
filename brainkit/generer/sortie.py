"""sortie.py — le PLAN D ECRITURE, isole du reste, et le seul du kit.

Aucun autre module de `brainkit.generer` n appelle `write_text`. Tout passe
par `Sortie.pose()`, et c est verifiable en une commande :

    grep -rnE 'write_text|write_bytes|mkdir' brainkit/generer/
    # -> uniquement sortie.py

Ce n est pas de la coquetterie d architecture, c est l interdiction du lot 4
rendue mecanique : « aucune ecriture dans le vault d'origine, y compris juste pour
tester ». Une seule fonction ecrit, elle refuse par defaut, et elle refuse une
sortie posee A L INTERIEUR du vault.

# Les trois modes, et pourquoi le defaut est celui qui n ecrit rien

| mode      | ou ca ecrit                  | ce que ca rapporte                       |
|---|---|---|
| `check`   | **nulle part**               | l ecart, page par page — c est LA regle 9 |
| `sortie`  | un arbre de travail SEPARE   | l ecart, et un arbre `diff`-able         |
| `ecrire`  | le vault lui-meme            | ce qui a change, rien si rien ne change  |

`ecrire` est aussi le seul mode qui SUPPRIME (`Sortie.supprime`), et seulement
un fichier derive orphelin que l artefact a juge supprimable.

`check` est le defaut. Un generateur dont le defaut ecrit est un generateur qui
ecrira un jour ou personne ne l attendait — et le critere d acceptation de ce
lot est justement de regenerer 765 pages sans en toucher une.

# L idempotence n est pas une propriete du generateur, c est une propriete d ici

`pose()` compare AVANT d ecrire, et n ecrit que si l octet change. Un generateur
relance sur un vault deja a jour n ecrit donc rien — sauf en mode `sortie`, ou
l arbre de travail doit contenir le fichier MEME identique, sans quoi il n y
aurait rien a comparer. La distinction est ecrite ici une fois et nulle part
ailleurs.
"""

from __future__ import annotations

import difflib
import os
from dataclasses import dataclass, field
from pathlib import Path

# Windows plafonne un chemin a 260 caracteres, sauf s il porte le prefixe
# `\\?\`. Un arbre de travail pose sous un dossier temporaire depasse vite ce
# plafond — le vault a des chemins de 60 caracteres, et « Documents/Projets/... »
# en consomme deja 90. Sans ce contournement, un `--sortie` echoue par un
# `FileNotFoundError` qui ne dit rien de sa vraie cause.
_LIMITE_WINDOWS = 240


def _long(p: Path) -> Path:
    if os.name != "nt":
        return p
    brut = str(p)
    if len(brut) < _LIMITE_WINDOWS or brut.startswith("\\\\?\\"):
        return p
    return Path("\\\\?\\" + brut)


CHECK = "check"
SORTIE = "sortie"
ECRIRE = "ecrire"
MODES = (CHECK, SORTIE, ECRIRE)

# Les quatre etats qu une pose peut rendre. Ils ne se confondent pas : `ABSENT`
# est un fichier a creer, `ECART` un fichier a rafraichir, et melanger les deux
# ferait passer une page jamais generee pour une page perimee.
IDENTIQUE = "identique"
ECART = "écart"
ABSENT = "absent"
ECRIT = "écrit"
# Un fichier DERIVE qui n a plus de source, et que `ecrire` a retire. Seul etat de
# suppression du kit, et il vit ici pour la meme raison que l ecriture : une
# seule fonction touche au disque, et on la trouve en une commande.
SUPPRIME = "supprimé"


@dataclass
class Pose:
    chemin: str            # relatif a la racine du vault, en posix
    etat: str
    artefact: str = ""     # quel generateur l a posee
    # La FORME, quand un artefact en a plusieurs : les 74 hubs du vault d'origine sont
    # tous `role: hub` et se composent de trois facons. Sans elle, un rapport ne
    # dit pas laquelle des trois s ecarte, et un test ne peut pas verifier qu une
    # forme a CESSE d etre posee — ce que la boucle sur les axes transverses
    # exige de savoir.
    forme: str = ""
    lignes: int = 0        # taille du `diff` unifie, pour un ECART
    extrait: str = ""      # les premieres lignes du `diff`, pour le rapport

    @property
    def concorde(self) -> bool:
        return self.etat in (IDENTIQUE, ECRIT, SUPPRIME)


@dataclass
class Sortie:
    """Le plan d ecriture d une execution."""

    racine: Path                       # le vault LU
    mode: str = CHECK
    dossier: Path | None = None        # l arbre de travail, si mode `sortie`
    contexte_du_diff: int = 6          # lignes d extrait gardees par ecart
    poses: list[Pose] = field(default_factory=list)
    refus: list[str] = field(default_factory=list)
    # Les cellules de bandeau sans source dans le frontmatter. SIGNALEES et
    # jamais comblees : une cellule vide dit qu un champ manque, c est une
    # information, et la remplir au juge l effacerait.
    trous: list[str] = field(default_factory=list)
    corpus: object | None = None        # le corpus lu, pour le rapport
    passes: int = 1                     # passes qu il a fallu pour le point fixe

    # ------------------------------------------------------------------ #
    def __post_init__(self) -> None:
        self.racine = self.racine.resolve()
        if self.mode not in MODES:
            self.refus.append(f"mode inconnu : `{self.mode}`")
            return
        if self.mode == SORTIE:
            if self.dossier is None:
                self.refus.append("mode `sortie` sans dossier de sortie")
                return
            self.dossier = self.dossier.resolve()
            # LE garde-fou du lot : une sortie qui vit sous le vault ecrirait
            # dans le vault par un autre nom.
            if self.dossier == self.racine or self.racine in self.dossier.parents:
                self.refus.append(
                    f"la sortie `{self.dossier}` vit SOUS le vault "
                    f"`{self.racine}` — refusé : ce serait écrire dans le vault "
                    f"par un autre nom")

    @property
    def ecrit_dans_le_vault(self) -> bool:
        return self.mode == ECRIRE

    # ------------------------------------------------------------------ #
    def lit(self, rel: str) -> str | None:
        """Le contenu ACTUEL d un artefact, lu dans le vault. None s il n existe pas.

        Toujours lu dans le vault, jamais dans le dossier de sortie : ce qu on
        regenere est ce que le vault porte, et une seconde execution ne doit pas
        se comparer a sa propre sortie.

        Lecture en fins de ligne UNIVERSELLES, ecriture en fins de ligne de la
        PLATEFORME — exactement comme les quatre scripts du vault d'origine, et il faut
        dire pourquoi. Le vault est stocke en LF et sorti au format natif
        (`.gitattributes` : `* text=auto`, `core.autocrlf: true`), donc sous
        Windows ses 765 fichiers sont CRLF sur le disque. La comparaison porte
        donc sur le texte LOGIQUE, ou une fin de ligne est « \\n » quelle qu elle
        soit ; l ecriture rend au disque la convention de son checkout. Comparer
        les octets bruts ferait apparaitre 765 ecarts de fin de ligne qui ne sont
        pas des ecarts de contenu, et masquerait les vrais.
        """
        p = self.racine / rel
        if not p.is_file():
            return None
        return p.read_text(encoding="utf-8")

    # ------------------------------------------------------------------ #
    def pose(self, rel: str, texte: str, artefact: str = "",
             forme: str = "") -> Pose:
        """Pose un artefact regenere. Rend l etat, et n ecrit que si on l a demande."""
        # Deux generateurs qui posent le MEME fichier : le second compare au
        # vault et non a la pose du premier, donc il l ecrase en silence. Aucun
        # cas dans le vault d'origine — les zones de hub et les bandeaux vivent dans des
        # roles differents — mais un manifeste peut le declarer par erreur, et
        # ecraser en silence est precisement ce qu on refuse de faire.
        deja = next((p for p in self.poses if p.chemin == rel), None)
        if deja is not None:
            self.refus.append(
                f"{rel} : posé deux fois — par `{deja.artefact}` puis par "
                f"`{artefact}`. Le second écraserait le premier.")
            return deja
        avant = self.lit(rel)
        if avant == texte:
            etat, lignes, extrait = IDENTIQUE, 0, ""
        elif avant is None:
            etat, lignes, extrait = ABSENT, len(texte.splitlines()), ""
        else:
            diff = list(difflib.unified_diff(
                avant.splitlines(), texte.splitlines(),
                fromfile=f"{rel} (vault)", tofile=f"{rel} (régénéré)",
                lineterm="", n=0))
            etat = ECART
            lignes = max(len(diff) - 2, 0)      # sans les deux en-tetes
            extrait = "\n".join(diff[2:2 + self.contexte_du_diff])

        cible: Path | None = None
        if self.mode == SORTIE and self.dossier is not None:
            cible = self.dossier / rel          # meme identique : il faut pouvoir diff
        elif self.mode == ECRIRE and etat != IDENTIQUE:
            cible = self.racine / rel
        if cible is not None:
            cible = _long(cible)
            cible.parent.mkdir(parents=True, exist_ok=True)
            cible.write_text(texte, encoding="utf-8")
            if self.mode == ECRIRE:
                etat = ECRIT

        p = Pose(rel, etat, artefact, forme, lignes, extrait)
        self.poses.append(p)
        return p

    def supprime(self, rel: str, artefact: str, ecart: str) -> Pose:
        """Retire un fichier derive devenu orphelin — en mode `ecrire` seulement.

        L APPELANT a deja verifie ce qui fait qu un fichier est supprimable (son
        dossier, sa marque, l option du manifeste). Ici on ne verifie que ce que
        le plan d ecriture garantit pour tous : le chemin reste DANS le vault, et
        c est un fichier ordinaire, pas un lien symbolique. Hors `ecrire`, ou si
        l une de ces gardes echoue, la pose est un ECART et rien n est touche —
        `ecart` dit pourquoi.
        """
        cible = (self.racine / rel)
        sur = (self.mode == ECRIRE and cible.is_file() and not cible.is_symlink()
               and self.racine in cible.resolve().parents)
        if sur:
            _long(cible).unlink()
            p = Pose(rel, SUPPRIME, artefact, "", 1, "fichier dérivé sans source : supprimé")
        else:
            p = Pose(rel, ECART, artefact, "", 1, ecart)
        self.poses.append(p)
        return p

    def refuse(self, message: str) -> None:
        self.refus.append(message)

    # ------------------------------------------------------------------ #
    def ecarts(self) -> list[Pose]:
        return [p for p in self.poses if not p.concorde]

    def par_artefact(self, avec_forme: bool = False) -> dict[str, tuple[int, int, int]]:
        """{artefact : (poses, ecarts, lignes de diff)} — le rapport chiffre."""
        out: dict[str, list[int]] = {}
        for p in self.poses:
            cle = f"{p.artefact}/{p.forme}" if avec_forme and p.forme else p.artefact
            c = out.setdefault(cle, [0, 0, 0])
            c[0] += 1
            if not p.concorde:
                c[1] += 1
                c[2] += p.lignes
        return {k: (v[0], v[1], v[2]) for k, v in sorted(out.items())}
