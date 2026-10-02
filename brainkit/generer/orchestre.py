"""orchestre.py — quels generateurs tournent, dans quel ordre, et le rapport.

Trois choix, et ils sont le lot :

1. **Un seul balayage du vault pour les quatre.** Le le vault d'origine en faisait quatre,
   dont un qui relisait le JSON produit par un autre — donc un vault vieux d une
   execution. Le chainage disparait : `corpus.py` lit une fois, les quatre
   composent.

2. **Le rapport est chiffre, artefact par artefact, a chaque execution.** Pas
   derriere une option. Le critere d acceptation du lot est un `diff` VIDE, et un
   compte global ne le prouve pas : il faut savoir lequel des quatre s ecarte, de
   combien de lignes, et sur quelle page.

3. **Un refus n est pas un ecart.** Une page sans zone AUTO, un manifeste qui ne
   declare pas un fichier de sortie, une sortie posee sous le vault : ce sont des
   REFUS, imprimes a part et comptes a part. Melanger les deux ferait passer un
   generateur qui n a pas tourne pour un generateur qui a trouve le vault
   conforme — c est la meme leçon que « une regle absente ressemble a une regle
   satisfaite ».
"""

from __future__ import annotations

from pathlib import Path

from . import bandeau, carte, hubs, index, liens
from .corpus import Corpus, charge_corpus
from .prose import Prose
from .sortie import CHECK, ECRIRE, ECRIT, IDENTIQUE, Sortie
from ..valider.manifeste import Modele

# Les quatre, dans l ordre. Ferme par le kit : un artefact est du code.
ARTEFACTS = ("index", "hubs", "liens", "bandeau")

# Les artefacts FACULTATIFS : ils ne tournent par defaut que si le manifeste les
# declare, et un manifeste qui ne les declare pas n a ni refus ni ecart a leur
# sujet. C est ce qui laisse intacts les manifestes ecrits avant eux. Demandes
# explicitement (`--quoi carte`) sans declaration, ils REFUSENT comme les autres.
FACULTATIFS = ("carte",)


def par_defaut(mo: Modele) -> tuple[str, ...]:
    """Les artefacts d une execution sans `--quoi` : les quatre, plus les declares."""
    return ARTEFACTS + tuple(a for a in FACULTATIFS if a == "carte" and carte.declaree(mo))

# Plafond de passes du point fixe. Cf. `genere_tout`.
PASSES_MAX = 4


def _une_passe(mo: Modele, racine: Path, mode: str, dossier: Path | None,
               quoi: tuple[str, ...], corpus: Corpus | None) -> Sortie:
    s = Sortie(racine=racine, mode=mode, dossier=dossier)
    if s.refus:
        return s
    c = corpus if corpus is not None else charge_corpus(mo, racine)
    p = Prose(mo)
    for a in ARTEFACTS + FACULTATIFS:
        if a not in quoi:
            continue
        if a == "index":
            index.genere(c, p, s)
        elif a == "hubs":
            hubs.genere(c, p, s)
        elif a == "liens":
            liens.genere(c, p, s)
        elif a == "bandeau":
            bandeau.genere(c, s, s.trous)
        elif a == "carte":
            if carte.declaree(mo):
                carte.genere(c, p, s)
            else:
                s.refuse("`genere.carte` n'est pas déclaré — rien à générer")
    s.corpus = c
    return s


def genere_tout(mo: Modele, racine: Path, mode: str = CHECK,
                dossier: Path | None = None,
                quoi: tuple[str, ...] | None = None,
                corpus: Corpus | None = None) -> Sortie:
    """Une passe en `check` et en `sortie`, un POINT FIXE en `ecrire`.

    Pourquoi le point fixe, et pourquoi seulement en ecriture. Deux artefacts
    dependent de ce que les autres ecrivent :

      - la zone AUTO d un hub porte des WIKILINKS. Les reecrire change les liens
        sortants du hub, donc la carte des liens — qui a ete composee, dans la
        meme passe, depuis le corpus lu AVANT ;
      - un hub transverse peut etre CREE. La page n existait pas quand le
        catalogue a compte les pages : il en annonce donc un de moins.

    Le le vault d'origine avait le meme defaut, et sa procedure de cloture le contournait a
    la main : « lancer `build_index.py` puis `build_mocs.py` / `build_links.py` »
    — un ordre a retenir, qui ne repare que le premier des deux cas et jamais le
    second. Ici, une passe qui a ECRIT quelque chose invalide le corpus : on
    relit et on recommence, jusqu a ce qu une passe n ecrive plus rien. C est la
    definition de l idempotence, appliquee a l ORCHESTRATION et pas seulement a
    chaque generateur.

    En `check` et en `sortie`, une seule passe — et c est voulu : le rapport doit
    dire ce que le vault EST, pas ce qu il deviendrait apres reparation. Un vault
    dont le catalogue ne compte pas encore un hub a creer est en ecart, et le
    dire est exactement le travail de `--check`.
    """
    if quoi is None:
        quoi = par_defaut(mo)
    s = _une_passe(mo, racine, mode, dossier, quoi, corpus)
    if mode != ECRIRE or not s.poses:
        return s
    passes = 1
    # Un REFUS n interrompt PAS le point fixe, et c est un correctif du lot :
    # une page sans zone AUTO ou sans titre est une condition STABLE du vault,
    # identique a chaque passe. S arreter dessus laissait les artefacts derives
    # composes depuis le corpus d AVANT la reparation — le defaut exact que le
    # point fixe existe pour supprimer.
    while any(p.etat == ECRIT for p in s.poses) and passes < PASSES_MAX:
        precedent = s
        s = _une_passe(mo, racine, mode, dossier, quoi, None)
        s.passes = passes + 1
        s.trous = precedent.trous or s.trous
        passes += 1
    if passes >= PASSES_MAX and any(p.etat == ECRIT for p in s.poses):
        s.refuse(f"le point fixe n'est pas atteint en {PASSES_MAX} passes — "
                 f"deux générateurs se contredisent, et c'est un défaut du kit, "
                 f"pas du vault")
    return s


# --------------------------------------------------------------------------- #
def imprime(s: Sortie, mo: Modele, racine: Path, detail: int = 12) -> int:
    """Le rapport. Sort en 2 s il reste un ecart en mode `check`, 1 sur un refus."""
    c = s.corpus
    n_pages = len(c.pages) if isinstance(c, Corpus) else 0
    suffixe = f", {s.passes} passes" if s.passes > 1 else ""
    print(f"générer ({s.mode}{suffixe}) — {n_pages} page(s) lue(s) — vault "
          f"`{racine.name}`, manifeste "
          f"`{mo.chemin.name if mo.chemin else '(inconnu)'}`")
    if s.dossier is not None:
        print(f"  sortie : {s.dossier}")

    for a, (poses, ecarts, lignes) in s.par_artefact(avec_forme=True).items():
        etat = "concorde" if not ecarts else f"{ecarts} écart(s), {lignes} ligne(s)"
        print(f"  {a or '(sans artefact)':18s} · {poses:4d} artefact(s) — {etat}")

    trous = s.trous
    if trous:
        print(f"\n  {len(trous)} bandeau(x) à cellule vide — champ absent du "
              f"frontmatter :")
        for t in trous[:detail]:
            print(f"    - {t}")
        if len(trous) > detail:
            print(f"    … {len(trous) - detail} autre(s)")

    ecarts = s.ecarts()
    if ecarts:
        print(f"\n{len(ecarts)} artefact(s) en écart :")
        for p in ecarts[:detail]:
            print(f"  [{p.etat}] {p.chemin} ({p.lignes} ligne(s) de diff)")
            for l in p.extrait.splitlines():
                print(f"      {l}")
        if len(ecarts) > detail:
            print(f"  … {len(ecarts) - detail} autre(s)")

    if s.refus:
        print(f"\n{len(s.refus)} refus :")
        for r in s.refus:
            print(f"  [REFUS] {r}")

    if s.refus:
        return 1
    if ecarts:
        # Code 2, comme le `--check` du vault d'origine : « il reste quelque chose a
        # regenerer » n est pas la meme chose qu une erreur d execution.
        return 2
    n = sum(1 for p in s.poses if p.etat != IDENTIQUE)
    if s.mode == ECRIRE:
        print(f"\nOK — {n} artefact(s) écrit(s), "
              f"{len(s.poses) - n} déjà à jour.")
    else:
        print(f"\nOK — les {len(s.poses)} artefacts concordent avec le vault.")
    return 0
