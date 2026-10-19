# GB Cartes

Régions hors ligne de [GB Navigation](https://github.com/gb7878w) : moteur d'itinéraire
(Valhalla 3.9) et recherche d'adresses, préparés chaque mois à partir d'OpenStreetMap.
Rien n'est téléchargé tant qu'une région n'est pas ajoutée dans les réglages de l'appli.

- `zones.json` : liste des régions proposées (ajouter une ligne pour une nouvelle région, source Geofabrik).
- `outils/construire.sh` : prépare une région ; `outils/adresses.py` : base de recherche.
- Les fichiers sont publiés dans la version « zones », avec `catalogue.json` que lit l'appli.

Données © les contributeurs d'OpenStreetMap, licence ODbL (https://www.openstreetmap.org/copyright).
