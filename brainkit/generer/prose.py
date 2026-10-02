"""prose.py — les gabarits de phrase des documents generes, et l arbitrage qui les place ici.

# Le probleme, pose net

Trois des quatre artefacts du vault d'origine sont des DOCUMENTS : ils portent des
phrases francaises. « Ne pas editer a la main », « liens sortants », « Tags sans
page concept dediee », « explorer par sous-domaine ». Un generateur qui ecrit un
document ecrit de la prose ; la question n est pas de l eviter, c est de decider
OU elle vit.

Trois places possibles, et une seule tient :

1. **En dur dans le code du generateur** — ce que fait le vault d'origine. Refuse : le
   mot « concept » y est un libelle de la v2, et « sous-domaine » est le libelle
   de l axe de rangement du dev. Le lot interdit exactement ca.
2. **Entierement dans le manifeste** — chaque phrase declaree. Refuse aussi :
   un brain neuf devrait alors ecrire vingt phrases francaises avant que son
   index se genere, et l entretien du lot 6 devrait les demander. §3.5 point 7
   dit le contraire : ce que l utilisateur ne peut pas connaitre, on ne le lui
   demande pas.
3. **Un gabarit par defaut dans le kit, surchargeable par le manifeste.** Retenu.

# Ce que « generique » veut dire ici, precisement

Les gabarits ci-dessous ne portent AUCUNE valeur d instance. Ce qu ils portent :
la langue (`brain.langue: fr`, seule valeur legale en v1, §5.4) et des trous
nommes. Chaque trou est rempli par le manifeste — jamais par le code :

| trou               | d ou il vient                              |
|---|---|
| `{brain}`          | `brain.nom`                                |
| `{signature}`      | `genere.<artefact>.signature`               |
| `{pages}`          | compte                                      |
| `{axe_rangement}`  | `libelles.axe_rangement.s`                  |
| `{axe_transverse}` | `libelles.axe_transverse.<champ>.s`         |
| `{notion}`         | le `libelle.s` du role `fonction: notion`   |
| `{champ_role}`     | le champ dont la `source:` est `roles[].id` |

Le mot « brique » n apparait pas une fois dans ce module, ni « domaine », ni
« famille », ni « comparatif », ni aucun titre de section du vault d'origine.

# La surcharge, et pourquoi elle est NECESSAIRE et pas une commodite

`genere.prose.<cle>` remplace un gabarit. Le le vault d'origine en surcharge QUATRE, et
les quatre sont de la dette v1 que le kit n a aucune raison de porter :

  - `index.entete` — l en-tete de son index annonce encore un « Reservoir v1
    (0 pages Wiki) » dont le dossier a disparu au lot 4 de sa migration ;
  - `index.sans_valeur` — « (sans categorie) » nomme le CHAMP accentue, que la
    derivation ne sait pas produire depuis `categorie` ;
  - `liens.sans_page` et `liens.tags_sans_page` — « page concept » est le mot de
    la v2 pour ce que le vault appelle desormais une notion.

Sans la surcharge, le critere d acceptation du lot serait inatteignable pour
quatre lignes de dette — et le durcir en portant la dette dans le kit serait pire.
C est la meme discipline que le lot 3 : on reproduit le vault a l identique, on
ne le corrige pas, et on ecrit ou vit la bizarrerie.
"""

from __future__ import annotations

from ..valider.manifeste import Modele

# --------------------------------------------------------------------------- #
# Les gabarits par defaut. Langue : `fr`. Aucune valeur d instance.
# --------------------------------------------------------------------------- #
DEFAUTS: dict[str, str | list[str]] = {
    # --- l index ------------------------------------------------------------
    "index.titre": "Index — {brain}",
    "index.entete": ["Généré par `{signature}`. Ne pas éditer à la main.",
                     "{pages} pages actives."],
    "index.sans_valeur": "(sans {axe_rangement})",
    "index.vide": "—",
    # --- la carte des liens -------------------------------------------------
    # --- la carte de lecture (artefact facultatif) ---------------------------
    "carte.titre": "Carte — {brain}",
    "carte.entete": ["Généré par `{signature}`. Ne pas éditer à la main.",
                     "{pages} pages décrites dans {dossiers} dossiers. À lire "
                     "d'abord : le fichier du dossier voulu détaille chaque page."],
    "carte.lien": "détail",
    "carte.compact": "Les sous-dossiers ne sont pas détaillés ici : la carte "
                     "dépasserait {max} lignes.",
    "carte.niveau_dossier": "Au niveau du dossier",
    "carte.suite": "{titre} (suite)",
    "carte.nom_tranche": "{dossier} - {i} sur {n}",
    "carte.l1_titre": "{dossier} — carte",
    "carte.l1_titre_tranche": "{dossier} — carte ({i} sur {n})",
    "carte.l1_entete": ["Généré par `{signature}`. Ne pas éditer à la main.",
                        "{pages} pages, chacune avec son chemin et une ligne."],
    "carte.couvre": "Couvre : {liste}.",

    "liens.titre": "Carte des liens — {brain}",
    "liens.entete": ["Généré par `{signature}`. Ne pas éditer à la main.",
                     "{pages} pages actives."],
    "liens.par_page": "Par page",
    "liens.etiquette_tags": "tags",
    "liens.etiquette_sortants": "liens sortants",
    "liens.etiquette_entrants": "liens entrants",
    "liens.tags_vers_pages": "Tags → pages",
    "liens.a_creer": "À créer (gaps)",
    "liens.non_resolus": "**Liens non résolus** (cibles inexistantes) :",
    "liens.non_resolu": "- depuis [[{page}]] → `{cible}`",
    "liens.aucun": "- aucun",
    "liens.sans_page": "  — pas de page {notion} dédiée",
    "liens.tags_sans_page": "**Tags sans page {notion} dédiée** "
                            "(sujets candidats à créer) :",
    "liens.tag_porte_par": "- `{tag}` (porté par : {pages})",
    "liens.vide": "—",
    # --- les hubs -----------------------------------------------------------
    "hubs.dossier_vide": "*(dossier vide)*",
    "hubs.aucune_page": "*(aucune page `{champ_role}: {role}`)*",
    "transverse.intro": "Axe {axe_transverse} **{libelle}** (`{cle}`) — explorer "
                        "par sous-{axe_rangement}, puis descendre via le graphe "
                        "local.",
    "transverse.puce": "- [[{cible}]] — {n} page(s)",
}


class Prose:
    """Les gabarits resolus pour UN manifeste : defauts du kit, surcharges lues."""

    def __init__(self, mo: Modele):
        self.mo = mo
        self.surcharges: dict = (mo.m.get("genere") or {}).get("prose") or {}
        rid_notion = mo.role_de_fonction("notion")
        libelle_notion = (mo.roles.get(rid_notion) or {}).get("libelle") or {}
        self.commun = {
            "brain": mo.brain.get("nom") or "",
            "axe_rangement": mo.libelle_rangement.get("s") or "",
            "axe_rangement_p": mo.libelle_rangement.get("p") or "",
            "notion": libelle_notion.get("s") or (rid_notion or ""),
            "champ_role": champ_du_role(mo),
        }

    # ------------------------------------------------------------------ #
    def brut(self, cle: str, /):
        """Le gabarit, surcharge si le manifeste en declare un."""
        if cle in self.surcharges:
            return self.surcharges[cle]
        if cle not in DEFAUTS:
            raise KeyError(f"aucun gabarit de prose pour `{cle}`")
        return DEFAUTS[cle]

    def ligne(self, cle: str, /, **trous) -> str:
        gabarit = self.brut(cle)
        if isinstance(gabarit, list):           # une cle multi-lignes lue en une
            gabarit = "\n".join(str(x) for x in gabarit)
        return str(gabarit).format(**{**self.commun, **trous})

    def lignes(self, cle: str, /, **trous) -> list[str]:
        gabarit = self.brut(cle)
        if not isinstance(gabarit, list):
            gabarit = [gabarit]
        return [str(x).format(**{**self.commun, **trous}) for x in gabarit]

    def libelle_transverse(self, champ: str) -> str:
        """Le mot que la prose emploie pour UN axe transverse.

        `libelles.axe_transverse.<champ>.s`. A defaut, le nom du champ : un
        libelle absent est un manque de manifeste, pas une raison de se taire.
        """
        table = self.mo.libelles.get("axe_transverse") or {}
        return ((table.get(champ) or {}).get("s")) or champ


def champ_du_role(mo: Modele) -> str:
    """Le nom du champ qui porte le role, RESOLU par sa source, jamais par son nom.

    C est la meme discipline que le validateur : le moteur ne reconnait jamais un
    champ a son nom. Ici la source est `roles[].id` — le seul champ dont le
    vocabulaire est la liste des roles.
    """
    for nom, d in mo.champs.items():
        if str(d.get("source") or "").strip() == "roles[].id":
            return nom
    return "role"
