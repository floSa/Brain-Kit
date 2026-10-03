"""carte.py — la carte de lecture : un L0 court, un L1 par dossier.

Un agent qui ouvre une conversation sur un brain de mille pages n'a que deux
moyens de « prendre la vue d'ensemble » : lire l'index entier, ou lire les hubs
un à un. Le premier coûte des dizaines de milliers de jetons et ne dit rien du
contenu des notions ; les seconds sont écrits pour naviguer, pas pour résumer.
La carte est le troisième moyen :

  - **L0** (`genere.carte.fichier`) — une page de moins de `lignes_max` lignes :
    un dossier par ligne, ses sous-dossiers promus dessous, le nombre de pages
    par rôle, et le lien vers le fichier L1 qui le détaille ;
  - **L1** (`genere.carte.dossier`/<dossier>.md) — toutes les pages du dossier,
    tous rôles réunis, chacune avec son chemin et UNE ligne de description. Un
    dossier qui dépasse `seuil_jetons` est coupé en tranches, par sous-dossier,
    et chaque tranche est remplie jusqu'au seuil (remplissage glouton) : le
    nombre de fichiers ne dépend que du volume, jamais d'un choix éditorial.

# Facultatif, et c'est voulu

Les quatre autres artefacts sont obligatoires pour un manifeste qui déclare leur
bloc ; celui-ci ne tourne QUE si `genere.carte` existe. Un brain qui ne le
déclare pas n'a ni refus ni écart : l'artefact n'existe pas pour lui. C'est ce
qui laisse intacts les manifestes et les jeux d'épreuve écrits avant lui.

# La description d'une ligne est EXTRAITE, jamais écrite

`genere.carte.descriptions` dit, par rôle, où la lire : un champ du frontmatter,
la première puce ou le premier paragraphe d'une section, ou la ligne qui
commence par un préfixe. Rien n'est stocké dans la page — un champ dérivable ne
se stocke pas. Un rôle sans règle retombe sur le champ `resume_court` du
manifeste ; sans rien à lire, la ligne n'a pas de description, et ne l'invente
pas : « une fiche vide honnêtement vaut mieux qu'une fiche remplie au jugé ».

# Les orphelins : supprimés en écriture, à trois conditions

Un fichier L1 qui n'a plus de source (dossier supprimé, fichier coupé en
« 1 sur 2 » et « 2 sur 2 », ou l'inverse) est toujours rapporté comme ÉCART par
`--check`, qui sort en 2 et ne supprime rien. `--ecrire` le supprime, et
seulement s'il remplit les trois conditions :

  1. il est dans `genere.carte.dossier` — le dossier que cet artefact possède et
     que personne d'autre n'écrit — et directement dedans, pas dans un sous-dossier ;
  2. il porte la marque « Généré par `<signature>` » en tête : un fichier qu'un
     humain a posé là n'est pas le sien, il reste rapporté et `--check` reste
     rouge jusqu'à ce qu'on l'examine ;
  3. le manifeste ne dit pas `genere.carte.supprime_orphelins: false`.

Pourquoi c'est la valeur par défaut. Avant, la suppression « se demandait à un
humain » : deux lots d'un même chantier ont dû faire un `git rm` à la main, parce
que `--ecrire` laissait un fichier que `--check` refusait ensuite. Un générateur
qui produit l'écart et refuse de le fermer oblige à faire à la main ce qu'il sait
faire seul. Le fichier supprimé est dérivé, entièrement reconstructible, et sous
git ; les trois conditions bornent ce que le générateur peut retirer à ce qu'il a
lui-même posé. L'opt-out existe pour un vault dont le dossier de carte abrite
autre chose.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from . import corpus as _corpus
from .prose import Prose
from .sortie import ECART, Pose, Sortie

ARTEFACT = "carte"

SEUIL_JETONS = 8000
CARACTERES_PAR_JETON = 3.5
DESCRIPTION_MAX = 160
LIGNES_MAX = 100

# L en-tete d un fichier L1 (titre, deux lignes de chapeau, liste « Couvre ») n est
# pas dans les blocs qu on remplit : sans cette marge, un fichier rempli a ras du
# seuil le depasserait de l en-tete. Mesure : l en-tete le plus long pese ~60 jetons.
MARGE_ENTETE = 150

RE_WIKILIEN = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
RE_LIEN_MD = re.compile(r"\[([^\]]+)\]\([^)]*\)")
RE_COMMENTAIRE = re.compile(r"<!--.*?-->", re.S)
RE_PUCE = re.compile(r"^\s*[-*]\s+(.*)$")
RE_PHRASE = re.compile(r"^(.+?[.!?])(?=\s|$)")


def decl(mo) -> dict:
    return (mo.m.get("genere") or {}).get("carte") or {}


def declaree(mo) -> bool:
    return bool(decl(mo))


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


# --------------------------------------------------------------------------- #
#  La description d'une ligne
# --------------------------------------------------------------------------- #
def nettoie(texte: str) -> str:
    texte = RE_COMMENTAIRE.sub(" ", texte)
    texte = RE_WIKILIEN.sub(lambda m: m.group(2) or m.group(1), texte)
    texte = RE_LIEN_MD.sub(r"\1", texte)
    texte = re.sub(r"[*_`]", "", texte)
    return " ".join(texte.split())


def une_ligne(texte: str, maximum: int) -> str:
    """La première phrase, coupée au mot si elle dépasse `maximum` caractères."""
    texte = nettoie(texte)
    m = RE_PHRASE.match(texte)
    phrase = m.group(1) if m else texte
    if len(phrase) > maximum:
        phrase = phrase[:maximum].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return phrase


def _premier_paragraphe(corps: str) -> str | None:
    for para in re.split(r"\n\s*\n", corps.strip()):
        para = para.strip()
        if para and not para.startswith(("|", "![[", "<!--", ">", "```", "- ", "* ", "#")):
            return para
    return None


def _premiere_puce(corps: str) -> str | None:
    """Le texte de la première puce, continuations comprises ; sinon le 1er paragraphe."""
    morceau: list[str] = []
    for ligne in corps.splitlines():
        m = RE_PUCE.match(ligne)
        if m and not morceau:
            morceau.append(m.group(1))
        elif m or not ligne.strip():
            if morceau:
                break
        elif morceau:
            morceau.append(ligne.strip())
    return " ".join(morceau) if morceau else _premier_paragraphe(corps)


def brut_de_description(corpus: _corpus.Corpus, e: dict, regle: dict | None) -> str | None:
    """Le texte d'où tirer la ligne, selon la règle du rôle ; None si rien à lire."""
    page = corpus.par_chemin.get(e["path"])
    if regle and page is not None:
        if "champ" in regle:
            v = e.get(regle["champ"])
            return str(v) if v else None
        if "section" in regle:
            titre = nfc(str(regle["section"]))
            corps = next((c for t, c in page.sections.items() if nfc(t) == titre), None)
            if corps is None:
                return None
            if regle.get("forme") == "premier_paragraphe":
                return _premier_paragraphe(corps)
            return _premiere_puce(corps)
        if "ligne" in regle:
            motif = re.compile(r"^>?\s*" + re.escape(str(regle["ligne"])) + r"\s*:?\s*(.+)$")
            for ligne in page.corps.splitlines():
                m = motif.match(ligne.strip())
                if m:
                    return m.group(1)
            return None
    r = corpus.resume(e)
    return r or None


# --------------------------------------------------------------------------- #
#  Le classement en dossiers et sous-dossiers
# --------------------------------------------------------------------------- #
@dataclass
class Ligne:
    entree: dict
    role: str
    texte: str


@dataclass
class Groupe:
    """Un sous-dossier promu, ou le niveau du dossier lui-même (`sous` vide)."""
    sous: str
    lignes: list[Ligne] = field(default_factory=list)


@dataclass
class Dossier:
    nom: str
    groupes: dict[str, Groupe] = field(default_factory=dict)

    @property
    def lignes(self) -> list[Ligne]:
        return [l for g in self.groupes.values() for l in g.lignes]


def _roles_decrits(corpus: _corpus.Corpus) -> list[str]:
    """Les rôles décrits, dans l'ordre du manifeste, hors rôle de hub."""
    hub = corpus.mo.role_de_fonction("hub")
    exclus = set(decl(corpus.mo).get("exclure_roles") or [])
    return [r for r in corpus.mo.roles if r != hub and r not in exclus]


def _libelle(corpus: _corpus.Corpus, role: str, n: int) -> str:
    lib = (corpus.mo.roles.get(role) or {}).get("libelle") or {}
    return str(lib.get("s" if n == 1 else "p") or role)


def classe(corpus: _corpus.Corpus) -> dict[str, Dossier]:
    d = decl(corpus.mo)
    maximum = int(d.get("description_max") or DESCRIPTION_MAX)
    regles = d.get("descriptions") or {}
    decrits = set(_roles_decrits(corpus))
    hub = corpus.mo.role_de_fonction("hub")

    def promu(n1: str, n2: str) -> bool:
        p = corpus.par_chemin.get(f"{n1}/{n2}/{n2}.md")
        return p is not None and p.role == hub

    out: dict[str, Dossier] = {}
    for e in corpus.entrees:
        role = str(e.get(corpus.champ_role) or "")
        if role not in decrits:
            continue
        seg = e["path"].split("/")
        if len(seg) < 2:
            continue
        n1 = nfc(seg[0])
        n2 = nfc(seg[1]) if len(seg) >= 3 and promu(seg[0], seg[1]) else ""
        dossier = out.setdefault(n1, Dossier(n1))
        groupe = dossier.groupes.setdefault(n2, Groupe(n2))
        brut = brut_de_description(corpus, e, regles.get(role))
        groupe.lignes.append(Ligne(e, role, une_ligne(brut, maximum) if brut else ""))

    ordre = {r: i for i, r in enumerate(_roles_decrits(corpus))}
    for dossier in out.values():
        for g in dossier.groupes.values():
            g.lignes.sort(key=lambda l: (ordre.get(l.role, 99),
                                         nfc(corpus.nom(l.entree)).casefold(),
                                         l.entree["path"]))
    return out


# --------------------------------------------------------------------------- #
#  Le rendu, le coût, le remplissage
# --------------------------------------------------------------------------- #
def comptes(corpus: _corpus.Corpus, lignes: list[Ligne]) -> str:
    n: dict[str, int] = {}
    for l in lignes:
        n[l.role] = n.get(l.role, 0) + 1
    return " · ".join(f"{n[r]} {_libelle(corpus, r, n[r])}"
                      for r in _roles_decrits(corpus) if r in n)


def rend_ligne(corpus: _corpus.Corpus, l: Ligne) -> str:
    base = f"- {corpus.lien(l.entree)} · {_libelle(corpus, l.role, 1)} · `{l.entree['path']}`"
    return f"{base} — {l.texte}" if l.texte else base


def jetons(texte: str, cpj: float) -> int:
    return math.ceil(len(texte) / cpj)


@dataclass
class Bloc:
    titre: str
    sous: str
    lignes: list[str]

    def texte(self) -> str:
        return "\n".join([f"## {self.titre}", *self.lignes, ""])


def blocs_du_dossier(corpus: _corpus.Corpus, prose: Prose, dossier: Dossier,
                     seuil: int, cpj: float) -> list[Bloc]:
    """Le niveau du dossier d'abord, puis les sous-dossiers par nom ; un bloc plus
    gros que le seuil à lui seul est coupé en suites, ligne par ligne."""
    ordre = sorted(dossier.groupes, key=lambda s: (s != "", nfc(s).casefold()))
    out: list[Bloc] = []
    for sous in ordre:
        titre = sous or prose.ligne("carte.niveau_dossier")
        rendues = [rend_ligne(corpus, l) for l in dossier.groupes[sous].lignes]
        courant: list[str] = []
        suites = 0
        for r in rendues:
            essai = Bloc(titre, sous, courant + [r])
            if courant and jetons(essai.texte(), cpj) > seuil:
                out.append(Bloc(titre if not suites else prose.ligne("carte.suite", titre=titre), sous, courant))
                suites += 1
                courant = [r]
            else:
                courant.append(r)
        out.append(Bloc(titre if not suites else prose.ligne("carte.suite", titre=titre), sous, courant))
    return out


def remplit(blocs: list[Bloc], seuil: int, cpj: float) -> list[list[Bloc]]:
    """Remplissage glouton : un bloc entre dans la tranche tant que le total tient."""
    tranches: list[list[Bloc]] = []
    courante: list[Bloc] = []
    cout = 0
    for b in blocs:
        t = jetons(b.texte(), cpj)
        if courante and cout + t > seuil:
            tranches.append(courante)
            courante, cout = [], 0
        courante.append(b)
        cout += t
    if courante:
        tranches.append(courante)
    return tranches


def nom_de_fichier(texte: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "-", texte).strip()


def chemin_l1(dossier_l1: str, nom: str, i: int, n: int, prose: Prose) -> str:
    base = nom_de_fichier(nom) if n == 1 else nom_de_fichier(
        prose.ligne("carte.nom_tranche", dossier=nom, i=i, n=n))
    return f"{dossier_l1.rstrip('/')}/{base}.md"


def lien_md(depuis_fichier: str, vers: str) -> str:
    """Lien Markdown relatif et encodé : les espaces d'un nom de dossier le cassent sinon."""
    base = Path(depuis_fichier).parent
    rel = Path(vers).relative_to(base) if str(vers).startswith(str(base) + "/") else Path(vers)
    return "/".join(quote(p) for p in rel.parts)


def l1(corpus: _corpus.Corpus, prose: Prose, dossier: Dossier, tranche: list[Bloc],
       i: int, n: int, signature: str) -> str:
    sous = [b.sous for b in tranche if b.sous]
    nb = sum(len(b.lignes) for b in tranche)
    titre = (prose.ligne("carte.l1_titre", dossier=dossier.nom) if n == 1 else
             prose.ligne("carte.l1_titre_tranche", dossier=dossier.nom, i=i, n=n))
    haut = [f"# {titre}", ""]
    haut += [f"> {x}" for x in prose.lignes("carte.l1_entete", signature=signature, pages=nb)]
    if sous:
        haut.append("> " + prose.ligne("carte.couvre", liste=", ".join(dict.fromkeys(sous))))
    haut.append("")
    return "\n".join(haut + [b.texte() for b in tranche]).rstrip() + "\n"


def l0(corpus: _corpus.Corpus, prose: Prose, dossiers: dict[str, Dossier],
       fichiers: dict[str, list[tuple[str, set[str]]]], fichier: str,
       signature: str, lignes_max: int) -> str:
    total = sum(len(d.lignes) for d in dossiers.values())
    tete = [f"# {prose.ligne('carte.titre')}", ""]
    tete += [f"> {x}" for x in prose.lignes("carte.entete", signature=signature,
                                           pages=total, dossiers=len(dossiers))]
    tete.append("")

    def corps(avec_sous: bool) -> list[str]:
        out: list[str] = []
        for nom in sorted(dossiers, key=lambda s: nfc(s).casefold()):
            d = dossiers[nom]
            cibles = fichiers[nom]
            if len(cibles) == 1:
                liens = f"[{prose.ligne('carte.lien')}]({lien_md(fichier, cibles[0][0])})"
            else:
                liens = " · ".join(f"[{k + 1}/{len(cibles)}]({lien_md(fichier, c[0])})"
                                   for k, c in enumerate(cibles))
            out.append(f"- **{nom}** — {comptes(corpus, d.lignes)} → {liens}")
            if avec_sous:
                for sous in sorted((s for s in d.groupes if s), key=lambda s: nfc(s).casefold()):
                    cible = next((c[0] for c in cibles if sous in c[1]), cibles[0][0])
                    suffixe = (f" → [{prose.ligne('carte.lien')}]({lien_md(fichier, cible)})"
                               if len(cibles) > 1 else "")
                    out.append(f"  - {sous} — {comptes(corpus, d.groupes[sous].lignes)}{suffixe}")
        return out

    complet = corps(True)
    if len(tete) + len(complet) <= lignes_max:
        return "\n".join(tete + complet).rstrip() + "\n"
    compact = corps(False)
    note = ["", f"> {prose.ligne('carte.compact', max=lignes_max)}"]
    return "\n".join(tete + compact + note).rstrip() + "\n"


# --------------------------------------------------------------------------- #
def genere(corpus: _corpus.Corpus, prose: Prose, s: Sortie) -> None:
    d = decl(corpus.mo)
    fichier, dossier_l1 = d.get("fichier"), d.get("dossier")
    if not fichier or not dossier_l1:
        s.refuse("`genere.carte` doit déclarer `fichier` (le L0) et `dossier` "
                 "(les L1) — rien à générer")
        return
    seuil = int(d.get("seuil_jetons") or SEUIL_JETONS)
    cpj = float(d.get("caracteres_par_jeton") or CARACTERES_PAR_JETON)
    lignes_max = int(d.get("lignes_max") or LIGNES_MAX)
    signature = str(d.get("signature") or "brainkit generer --quoi carte")

    dossiers = classe(corpus)
    fichiers: dict[str, list[tuple[str, set[str]]]] = {}
    poses_l1: list[tuple[str, str]] = []
    for nom in sorted(dossiers, key=lambda x: nfc(x).casefold()):
        dos = dossiers[nom]
        utile = max(seuil - MARGE_ENTETE, 1)
        tranches = remplit(blocs_du_dossier(corpus, prose, dos, utile, cpj), utile, cpj)
        fichiers[nom] = []
        for i, tr in enumerate(tranches, 1):
            chemin = chemin_l1(dossier_l1, nom, i, len(tranches), prose)
            fichiers[nom].append((chemin, {b.sous for b in tr}))
            poses_l1.append((chemin, l1(corpus, prose, dos, tr, i, len(tranches), signature)))

    s.pose(fichier, l0(corpus, prose, dossiers, fichiers, fichier, signature, lignes_max), ARTEFACT)
    for chemin, texte in poses_l1:
        s.pose(chemin, texte, ARTEFACT)

    orphelins(prose, s, d, {c for c, _ in poses_l1} | {fichier},
              dossier_l1, signature)


def marque_l1(prose: Prose, signature: str) -> str:
    """La première ligne de l'en-tête d'un L1, telle que `l1()` l'écrit."""
    return "> " + prose.lignes("carte.l1_entete", signature=signature, pages=0)[0]


def porte_la_marque(chemin: Path, marque: str) -> bool:
    """La marque est dans l'en-tête (quelques lignes), pas n'importe où dans le corps."""
    try:
        with chemin.open(encoding="utf-8") as f:
            return any(ligne.rstrip("\r\n") == marque for _, ligne in zip(range(8), f))
    except (OSError, UnicodeDecodeError):
        return False


def orphelins(prose: Prose, s: Sortie, d: dict,
              attendus: set[str], dossier_l1: str, signature: str) -> None:
    """Les fichiers du dossier L1 que la carte ne produit plus : supprimés ou rapportés."""
    dir_l1 = s.racine / dossier_l1
    if not dir_l1.is_dir():
        return
    suppression = d.get("supprime_orphelins", True) is not False
    marque = marque_l1(prose, signature)
    for p in sorted(dir_l1.glob("*.md")):
        rel = p.relative_to(s.racine).as_posix()
        if rel in attendus:
            continue
        if suppression and porte_la_marque(p, marque):
            s.supprime(rel, ARTEFACT,
                       "fichier L1 sans source : sera supprimé par `--ecrire`")
        elif suppression:
            s.poses.append(Pose(rel, ECART, ARTEFACT, "", 1,
                                "fichier sans source ET sans la marque « Généré par » : "
                                "pas à lui, à examiner par un humain"))
        else:
            s.poses.append(Pose(rel, ECART, ARTEFACT, "", 1,
                                "fichier L1 sans source : `supprime_orphelins` est à false, "
                                "à supprimer à la main"))
