# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""Les generateurs d artefacts derives de BrainKit, en ligne de commande.

    uv run brainkit/generer/__main__.py                        # --check, n ecrit rien
    uv run brainkit/generer/__main__.py --sortie /tmp/travail  # ecrit A COTE du vault
    uv run brainkit/generer/__main__.py --ecrire               # ecrit DANS le vault
    uv run brainkit/generer/__main__.py --quoi bandeau,hubs
    uv run brainkit/generer/__main__.py --manifeste <brain.yml> --vault <dossier>

# Le mode par defaut n ecrit rien, et ce n est pas negociable

`--check` regenere tout en memoire et compare. Il sort en **2** s il reste un
artefact a poser ou a rafraichir, en **1** sur un refus, en **0** si tout
concorde. C est la forme verifiable du contrat « ce qui est genere n est jamais
edite a la main », et c est la regle `bandeau_a_jour` du validateur, que le
manifeste declare deleguee a cette commande.

Ecrire se DEMANDE. `--sortie` pose les artefacts dans un arbre de travail
separe — refuse s il vit sous le vault — et `--ecrire` les pose dans le vault
lui-meme, uniquement la ou l octet change.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RACINE_KIT = Path(__file__).resolve().parents[2]
if str(RACINE_KIT) not in sys.path:
    sys.path.insert(0, str(RACINE_KIT))

from brainkit.generer import ARTEFACTS, FACULTATIFS, genere_tout, imprime, par_defaut      # noqa: E402
from brainkit.generer.sortie import CHECK, ECRIRE, SORTIE         # noqa: E402
from brainkit import defauts                                      # noqa: E402
from brainkit.valider import charge                               # noqa: E402


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):        # pragma: no cover
        pass
    ap = argparse.ArgumentParser(
        description="Régénère les artefacts dérivés d'un vault depuis son manifeste.")
    ap.add_argument("--manifeste", type=Path, default=None,
                    help="défaut : le `brain.yml` du vault visé")
    ap.add_argument("--vault", type=Path, default=None,
                    help="défaut : le dossier courant s'il porte un `brain.yml`")
    ap.add_argument("--sortie", type=Path, default=None,
                    help="arbre de travail où poser les artefacts, HORS du vault")
    ap.add_argument("--ecrire", action="store_true",
                    help="écrire dans le vault lui-même (à demander explicitement)")
    ap.add_argument("--check", action="store_true",
                    help="mode par défaut : n'écrit rien, sort en 2 s'il reste un écart")
    ap.add_argument("--quoi", default=None,
                    help="les artefacts à régénérer : " + ", ".join(ARTEFACTS)
                    + ". Facultatif (si le manifeste le déclare, il tourne par "
                    "défaut) : " + ", ".join(FACULTATIFS))
    ap.add_argument("--detail", type=int, default=12,
                    help="nombre d'écarts et de trous détaillés dans le rapport")
    ns = ap.parse_args()

    if ns.ecrire and ns.sortie is not None:
        print("--ecrire et --sortie s'excluent : l'un écrit dans le vault, "
              "l'autre à côté.")
        return 1
    vault = ns.vault if ns.vault is not None else defauts.vault_par_defaut()
    if not vault.is_dir():
        print(f"vault introuvable : {vault}")
        return 2
    manifeste, dits = defauts.resout(ns.manifeste, vault)
    for ligne in dits:
        print(ligne)
    if manifeste is None:
        return 2
    if not manifeste.exists():
        print(f"manifeste introuvable : {manifeste}")
        return 2
    if dits:
        print()
    ns.manifeste, ns.vault = manifeste, vault

    mo = charge(ns.manifeste)
    if ns.quoi is None:
        quoi = par_defaut(mo)
    else:
        quoi = tuple(x.strip() for x in ns.quoi.split(",") if x.strip())
    connus = ARTEFACTS + FACULTATIFS
    inconnus = [x for x in quoi if x not in connus]
    if inconnus:
        print(f"artefact(s) inconnu(s) : {', '.join(inconnus)} — "
              f"connus : {', '.join(connus)}")
        return 1

    mode = ECRIRE if ns.ecrire else (SORTIE if ns.sortie is not None else CHECK)
    racine = ns.vault.resolve()
    s = genere_tout(mo, racine, mode=mode, dossier=ns.sortie, quoi=quoi)
    return imprime(s, mo, racine, detail=ns.detail)


if __name__ == "__main__":
    raise SystemExit(main())
