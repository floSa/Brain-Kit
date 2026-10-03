# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""carte.py — le jeu d epreuve de la CARTE DE LECTURE (artefact facultatif).

    uv run tests/carte.py

Huit scenarios, sur le vault abstrait `tests/genere-vert/` recopie hors du depot
(rien n est jamais ecrit dans `tests/`) :

  1. FACULTATIF  — un manifeste qui ne declare pas `genere.carte` n a ni artefact,
                   ni refus, ni ecart a son sujet ; `--quoi carte` demande sans
                   declaration REFUSE. C est ce qui laisse intacts les manifestes
                   ecrits avant l artefact.
  2. EXTRACTION  — la description d une ligne : phrase, puce avec continuation,
                   nettoyage des liens, coupe au mot, rien a lire = rien.
  3. VERT        — `--ecrire` pose le L0 et un L1 par dossier ; `--check` se
                   tait ; une seconde ecriture n ecrit aucun octet (idempotence).
                   Chaque page non-hub apparait EXACTEMENT une fois dans les L1.
  4. GLOUTON     — avec un seuil bas, le dossier se coupe en tranches par
                   sous-dossier, chaque tranche tient sous le seuil, aucune page
                   n est perdue ni dupliquee, le L0 pointe la bonne tranche.
  5. COMPACT     — avec `lignes_max` trop bas, le L0 renonce aux sous-dossiers et
                   le dit.
  6. ECART       — un L1 modifie a la main est rapporte (code 2), et lui seul.
  7. ORPHELIN    — un L1 sans source : `--check` le rapporte (code 2) sans le
                   supprimer ; `--ecrire` le supprime, a trois conditions : il est
                   dans le dossier genere, il porte la marque « Genere par », et
                   `supprime_orphelins` n est pas a false. Hors de ces conditions,
                   jamais.
  8. SCISSION    — le cas qui a motive la regle : un fichier se coupe en
                   « i sur n » (ou l inverse), l ancien est supprime, `--check`
                   revient au vert sans `git rm` a la main.
"""

from __future__ import annotations

import copy
import math
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

RACINE_KIT = Path(__file__).resolve().parents[1]
if str(RACINE_KIT) not in sys.path:
    sys.path.insert(0, str(RACINE_KIT))

from brainkit.generer import ARTEFACTS, charge_corpus, genere_tout, par_defaut    # noqa: E402
from brainkit.generer import carte                                                # noqa: E402
from brainkit.generer.sortie import CHECK, ECRIRE, SORTIE                                # noqa: E402
from brainkit.generer.orchestre import imprime                                    # noqa: E402
from brainkit.valider.manifeste import Modele                                     # noqa: E402

MANIFESTE = RACINE_KIT / "tests" / "generation.brain.yml"
VERT = RACINE_KIT / "tests" / "genere-vert"

BLOC = {
    "fichier": "AI/index/carte.md",
    "dossier": "AI/index/carte",
    "signature": "brainkit generer --quoi carte",
    "descriptions": {
        "unite": {"champ": "apport"},
        "notion": {"section": "Aperçu", "forme": "premiere_puce"},
    },
}


class Journal:
    def __init__(self) -> None:
        self.echecs: list[str] = []

    def verifie(self, nom: str, ok: bool, detail: str = "") -> None:
        print(f"  {'OK    ' if ok else 'ÉCHEC '} {nom}")
        if not ok:
            self.echecs.append(nom)
            for ligne in detail.splitlines():
                print(f"         {ligne}")


def manifeste(**surcharge) -> Modele:
    brut = yaml.safe_load(MANIFESTE.read_text(encoding="utf-8"))
    brut["genere"]["carte"] = {**copy.deepcopy(BLOC), **surcharge}
    return Modele(brut, MANIFESTE)


def sans_carte() -> Modele:
    return Modele(yaml.safe_load(MANIFESTE.read_text(encoding="utf-8")), MANIFESTE)


def imprime_code(s, mo: Modele, racine: Path) -> int:
    """Le code de sortie du CLI, rapport muet."""
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        return imprime(s, mo, racine)


def copie() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="carte-"))
    shutil.copytree(VERT, tmp / "vault")
    return tmp / "vault"


def jetons(texte: str) -> int:
    return math.ceil(len(texte) / carte.CARACTERES_PAR_JETON)


def pages_non_hub(mo: Modele, racine: Path) -> set[str]:
    c = charge_corpus(mo, racine)
    hub = mo.role_de_fonction("hub")
    return {e["path"] for e in c.entrees if e.get(c.champ_role) != hub
            and "/" in e["path"]}


def chemins_cites(racine: Path, dossier: str) -> list[str]:
    out: list[str] = []
    for f in sorted((racine / dossier).glob("*.md")):
        for l in f.read_text(encoding="utf-8").splitlines():
            if l.startswith("- ") and "`" in l:
                out.append(l.split("`")[1])
    return out


# --------------------------------------------------------------------------- #
def scenario_facultatif(j: Journal) -> None:
    print("\n1. FACULTATIF — sans déclaration, l'artefact n'existe pas")
    mo = sans_carte()
    j.verifie("les artefacts par défaut sont les quatre", par_defaut(mo) == ARTEFACTS)
    s = genere_tout(mo, VERT, mode=CHECK)
    j.verifie("aucune pose, aucun refus à propos de la carte",
              not [p for p in s.poses if p.artefact == "carte"]
              and not [r for r in s.refus if "carte" in r])
    s = genere_tout(mo, VERT, mode=CHECK, quoi=("carte",))
    j.verifie("`--quoi carte` sans déclaration REFUSE",
              any("genere.carte" in r for r in s.refus), f"refus : {s.refus}")
    j.verifie("déclarée, la carte entre dans les artefacts par défaut",
              par_defaut(manifeste()) == ARTEFACTS + ("carte",))


def scenario_extraction(j: Journal) -> None:
    print("\n2. EXTRACTION — la description d'une ligne")
    j.verifie("la première phrase seulement",
              carte.une_ligne("Un outil. Et un second propos.", 160) == "Un outil.")
    j.verifie("liens et emphases nettoyés",
              carte.une_ligne("Voir [[Page|ce lien]] et **gras** et `code`.", 160)
              == "Voir ce lien et gras et code.")
    longue = "mot " * 80
    c = carte.une_ligne(longue, 40)
    j.verifie("coupe au mot, avec points de suspension",
              c.endswith("…") and len(c) <= 41 and not c[:-1].endswith(" mot m"), c)
    corps = "\n- Première puce\n  qui continue.\n- Seconde puce.\n"
    j.verifie("la première puce, continuations comprises",
              carte._premiere_puce(corps) == "Première puce qui continue.")
    j.verifie("sans puce, le premier paragraphe",
              carte._premiere_puce("Un paragraphe simple.\n\nUn autre.") == "Un paragraphe simple.")
    j.verifie("rien à lire, rien", carte._premiere_puce("") is None
              and carte._premier_paragraphe("| a | b |\n") is None)


def scenario_vert(j: Journal) -> Path:
    print("\n3. VERT — écrire, vérifier, réécrire")
    racine = copie()
    mo = manifeste()
    s = genere_tout(mo, racine, mode=ECRIRE, quoi=("carte",))
    j.verifie("l'écriture ne refuse rien", not s.refus, f"refus : {s.refus}")
    l0 = (racine / BLOC["fichier"]).read_text(encoding="utf-8")
    j.verifie("le L0 existe et tient en moins de cent lignes",
              0 < len(l0.splitlines()) < carte.LIGNES_MAX)
    j.verifie("le L0 nomme chaque dossier décrit",
              all(f"**{d}**" in l0 for d in ("Domaine A", "Domaine B")))
    attendu = pages_non_hub(mo, racine)
    cites = chemins_cites(racine, BLOC["dossier"])
    j.verifie("chaque page non-hub est citée EXACTEMENT une fois dans les L1",
              sorted(cites) == sorted(attendu),
              f"manquantes {sorted(attendu - set(cites))} ; doublons "
              f"{sorted(c for c in set(cites) if cites.count(c) > 1)}")
    j.verifie("aucun hub dans les L1", not [c for c in cites if c.endswith("Domaine A/Domaine A.md")])
    j.verifie("la description d'une unité vient de son champ",
              "La première unité du premier domaine." in
              (racine / BLOC["dossier"] / "Domaine A.md").read_text(encoding="utf-8"))
    j.verifie("celle d'une notion vient de la section « Aperçu »",
              "Ce qu'il faut comprendre du segment" in
              (racine / BLOC["dossier"] / "Domaine A.md").read_text(encoding="utf-8"))
    s = genere_tout(mo, racine, mode=CHECK, quoi=("carte",))
    j.verifie("`--check` se tait après l'écriture", not s.ecarts() and not s.refus)
    s = genere_tout(mo, racine, mode=ECRIRE, quoi=("carte",))
    j.verifie("une seconde écriture n'écrit aucun octet (idempotence)",
              all(p.etat == "identique" for p in s.poses), f"{[(p.chemin, p.etat) for p in s.poses if p.etat != 'identique']}")
    return racine


def scenario_glouton(j: Journal) -> None:
    print("\n4. GLOUTON — un seuil bas coupe par sous-dossier")
    racine = copie()
    seuil = carte.MARGE_ENTETE + 70
    mo = manifeste(seuil_jetons=seuil)
    s = genere_tout(mo, racine, mode=ECRIRE, quoi=("carte",))
    fichiers = sorted(p.name for p in (racine / BLOC["dossier"]).glob("*.md"))
    coupes = [f for f in fichiers if " sur " in f]
    j.verifie("au moins un dossier est coupé en tranches « i sur n »", bool(coupes), str(fichiers))
    attendu = pages_non_hub(mo, racine)
    cites = chemins_cites(racine, BLOC["dossier"])
    j.verifie("aucune page perdue ni dupliquée", sorted(cites) == sorted(attendu))
    utile = seuil - carte.MARGE_ENTETE
    trop = []
    for f in (racine / BLOC["dossier"]).glob("*.md"):
        blocs = f.read_text(encoding="utf-8").split("\n## ")[1:]
        if len(blocs) > 1 and sum(jetons("## " + b) for b in blocs) > utile:
            trop.append(f.name)
    j.verifie("une tranche à plusieurs blocs tient sous le seuil utile", not trop, str(trop))
    l0 = (racine / BLOC["fichier"]).read_text(encoding="utf-8")
    j.verifie("le L0 pointe chaque tranche (« 1/n · 2/n »)", "[1/" in l0 and "[2/" in l0, l0[:400])
    j.verifie("`--check` se tait", not genere_tout(mo, racine, mode=CHECK, quoi=("carte",)).ecarts())


def scenario_compact(j: Journal) -> None:
    print("\n5. COMPACT — un L0 trop long renonce aux sous-dossiers")
    racine = copie()
    complet = manifeste()
    genere_tout(complet, racine, mode=ECRIRE, quoi=("carte",))
    long = (racine / BLOC["fichier"]).read_text(encoding="utf-8")
    court_max = len(long.splitlines()) - 2
    genere_tout(manifeste(lignes_max=court_max), racine, mode=ECRIRE, quoi=("carte",))
    l0 = (racine / BLOC["fichier"]).read_text(encoding="utf-8")
    j.verifie("les lignes de sous-dossier ont disparu", "\n  - " not in l0)
    j.verifie("la note dit pourquoi", "ne sont pas détaillés" in l0, l0[-200:])
    sous = long.count("\n  - ")
    j.verifie("il perd les lignes de sous-dossier et gagne les deux de la note",
              len(l0.splitlines()) == len(long.splitlines()) - sous + 2,
              f"{len(l0.splitlines())} lignes contre {len(long.splitlines())} - {sous} + 2")


def scenario_ecart(j: Journal, racine: Path) -> None:
    print("\n6. ÉCART — un L1 modifié à la main")
    mo = manifeste()
    cible = racine / BLOC["dossier"] / "Domaine B.md"
    cible.write_text(cible.read_text(encoding="utf-8") + "\n- ajout à la main\n", encoding="utf-8")
    s = genere_tout(mo, racine, mode=CHECK, quoi=("carte",))
    j.verifie("exactement ce fichier est en écart",
              {p.chemin for p in s.ecarts()} == {f"{BLOC['dossier']}/Domaine B.md"},
              f"{[p.chemin for p in s.ecarts()]}")
    genere_tout(mo, racine, mode=ECRIRE, quoi=("carte",))
    j.verifie("`--ecrire` le répare", not genere_tout(mo, racine, mode=CHECK, quoi=("carte",)).ecarts())


def marque(racine: Path) -> str:
    """Un vrai fichier L1 du vault, dont le contenu porte la marque « Généré par »."""
    return (racine / BLOC["dossier"] / "Domaine B.md").read_text(encoding="utf-8")


def scenario_orphelin(j: Journal, racine: Path) -> None:
    print("\n7. ORPHELIN — un L1 sans source, signalé par `--check`, supprimé par `--ecrire`")
    mo = manifeste()
    dossier = racine / BLOC["dossier"]
    orphelin = dossier / "Dossier disparu.md"
    orphelin.write_text(marque(racine), encoding="utf-8")      # porte la marque
    manuel = dossier / "Note à la main.md"
    manuel.write_text("# écrit par un humain\n", encoding="utf-8")   # ne la porte pas
    dehors = racine / "AI" / "index" / "Autre.md"
    dehors.write_text(marque(racine), encoding="utf-8")        # marque, mais hors du dossier

    s = genere_tout(mo, racine, mode=CHECK, quoi=("carte",))
    j.verifie("`--check` rapporte l'orphelin marqué comme écart",
              any(p.chemin.endswith("Dossier disparu.md") and "sans source" in p.extrait
                  for p in s.ecarts()))
    j.verifie("`--check` sort en 2", imprime_code(s, mo, racine) == 2)
    j.verifie("`--check` ne supprime rien", orphelin.exists() and manuel.exists())

    s = genere_tout(mo, racine, mode=SORTIE, dossier=racine.parent / "sortie", quoi=("carte",))
    j.verifie("`--sortie` ne supprime rien dans le vault", orphelin.exists())

    s = genere_tout(mo, racine, mode=ECRIRE, quoi=("carte",))
    j.verifie("`--ecrire` supprime l'orphelin marqué", not orphelin.exists())
    j.verifie("`--ecrire` le dit (état « supprimé »)",
              any(p.chemin.endswith("Dossier disparu.md") and p.etat == "supprimé"
                  for p in s.poses), f"{[(p.chemin, p.etat) for p in s.poses]}")
    j.verifie("`--ecrire` ne touche pas un fichier sans la marque", manuel.exists())
    j.verifie("`--ecrire` ne touche pas un fichier hors du dossier généré", dehors.exists())
    j.verifie("le fichier sans marque reste rapporté, donc `--check` reste rouge",
              {p.chemin for p in genere_tout(mo, racine, mode=CHECK, quoi=("carte",)).ecarts()}
              == {f"{BLOC['dossier']}/Note à la main.md"})
    manuel.unlink()
    j.verifie("sans orphelin, `--check` se tait",
              not genere_tout(mo, racine, mode=CHECK, quoi=("carte",)).ecarts())

    ferme = manifeste(supprime_orphelins=False)
    orphelin.write_text(marque(racine), encoding="utf-8")
    genere_tout(ferme, racine, mode=ECRIRE, quoi=("carte",))
    j.verifie("`supprime_orphelins: false` rend l'ancien comportement (rien n'est supprimé)",
              orphelin.exists())
    orphelin.unlink()
    dehors.unlink()


def scenario_scission(j: Journal) -> None:
    print("\n8. SCISSION — un fichier coupé en « i sur n » laisse l'ancien orphelin, puis le seuil remonte")
    racine = copie()
    seuil = carte.MARGE_ENTETE + 70
    genere_tout(manifeste(), racine, mode=ECRIRE, quoi=("carte",))
    avant = {f.name for f in (racine / BLOC["dossier"]).glob("*.md")}
    genere_tout(manifeste(seuil_jetons=seuil), racine, mode=ECRIRE, quoi=("carte",))
    coupe = {f.name for f in (racine / BLOC["dossier"]).glob("*.md")}
    j.verifie("la scission supprime l'ancien fichier entier",
              any(n in avant and n not in coupe for n in avant), f"{sorted(avant)} -> {sorted(coupe)}")
    j.verifie("`--check` est vert après la scission",
              not genere_tout(manifeste(seuil_jetons=seuil), racine, mode=CHECK, quoi=("carte",)).ecarts())
    genere_tout(manifeste(), racine, mode=ECRIRE, quoi=("carte",))
    apres = {f.name for f in (racine / BLOC["dossier"]).glob("*.md")}
    j.verifie("la fusion supprime les « i sur n » devenus orphelins", apres == avant,
              f"{sorted(apres)} contre {sorted(avant)}")
    j.verifie("`--check` est vert après la fusion",
              not genere_tout(manifeste(), racine, mode=CHECK, quoi=("carte",)).ecarts())


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):        # pragma: no cover
        pass
    print("épreuve — la carte de lecture")
    j = Journal()
    scenario_facultatif(j)
    scenario_extraction(j)
    racine = scenario_vert(j)
    scenario_glouton(j)
    scenario_compact(j)
    scenario_ecart(j, racine)
    scenario_orphelin(j, racine)
    scenario_scission(j)
    print()
    if j.echecs:
        print(f"{len(j.echecs)} vérification(s) en échec :")
        for e in j.echecs:
            print(f"  - {e}")
        return 1
    print("OK — le jeu d'épreuve de la carte passe en entier.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
