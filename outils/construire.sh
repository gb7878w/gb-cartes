#!/usr/bin/env bash
# Prépare une zone : construire.sh <id>
# Sortie dans sortie/ : <id>-<date>-routes.tar (moteur Valhalla 3.9, comme dans l'appli),
# <id>-<date>-adresses.db (recherche), coupés en parties de 1,9 Go si besoin, et <id>.json.
set -euo pipefail
ID="$1"
SOURCE=$(jq -r --arg id "$ID" '.zones[] | select(.id == $id) | .source' zones.json)
[ -n "$SOURCE" ] && [ "$SOURCE" != null ] || { echo "Zone inconnue : $ID"; exit 1; }
DATE=$(date -u +%Y-%m-%d)
T=travail
mkdir -p "$T" sortie

echo "::group::Téléchargement de $SOURCE"
curl -fsSL --retry 5 -o "$T/zone.osm.pbf" "https://download.geofabrik.de/$SOURCE-latest.osm.pbf"
ls -lh "$T/zone.osm.pbf"
echo "::endgroup::"

# Cadre : celui de zones.json s'il est donné, sinon celui de l'extrait.
CADRE=$(jq -c --arg id "$ID" '.zones[] | select(.id == $id) | .cadre // empty' zones.json)
if [ -z "$CADRE" ]; then
  CADRE=$(osmium fileinfo -g header.boxes "$T/zone.osm.pbf" | head -1 | tr -d '()' | awk -F, '{printf "[%s,%s,%s,%s]", $1, $2, $3, $4}')
fi
echo "Cadre : $CADRE"

echo "::group::Moteur d'itinéraire"
docker run --rm --entrypoint /bin/bash -v "$PWD/$T:/t" -w /t ghcr.io/valhalla/valhalla:3.9.0 -c '
  set -e
  valhalla_build_config --mjolnir-tile-dir /t/tuiles --mjolnir-tile-extract /t/routes.tar \
    --mjolnir-admin /t/admins.sqlite --mjolnir-concurrency $(nproc) > /t/valhalla.json
  valhalla_build_admins -c /t/valhalla.json /t/zone.osm.pbf
  valhalla_build_tiles -c /t/valhalla.json /t/zone.osm.pbf
  valhalla_build_extract -c /t/valhalla.json -v
  rm -rf /t/tuiles'
sudo chown -R "$(id -u)" "$T"
ls -lh "$T/routes.tar"
echo "::endgroup::"

echo "::group::Recherche"
osmium tags-filter --overwrite "$T/zone.osm.pbf" w/highway -o "$T/routes.osm.pbf"
osmium tags-filter --overwrite "$T/routes.osm.pbf" w/name -o "$T/rues.osm.pbf"
osmium tags-filter --overwrite "$T/zone.osm.pbf" n/place nw/amenity nw/shop nw/tourism nw/leisure nw/aeroway=aerodrome \
  nw/railway=station nw/public_transport=station nw/office nw/craft -o "$T/lieux.osm.pbf"
osmium merge --overwrite "$T/rues.osm.pbf" "$T/lieux.osm.pbf" -o "$T/filtre.osm.pbf"
rm -f "$T/routes.osm.pbf" "$T/rues.osm.pbf" "$T/lieux.osm.pbf" "$T/zone.osm.pbf"
python3 outils/adresses.py "$T/filtre.osm.pbf" "$T/adresses.db"
ls -lh "$T/adresses.db"
echo "::endgroup::"

# Fichiers publiés et description de la zone pour le catalogue.
FICHIERS='[]'
for TYPE in routes adresses; do
  case $TYPE in routes) SRC="$T/routes.tar"; NOM="$ID-$DATE-routes.tar";; adresses) SRC="$T/adresses.db"; NOM="$ID-$DATE-adresses.db";; esac
  TAILLE=$(stat -c %s "$SRC")
  SHA=$(sha256sum "$SRC" | cut -d' ' -f1)
  PARTIES='[]'
  if [ "$TAILLE" -gt 1900000000 ]; then
    split -b 1900000000 -d -a 3 "$SRC" "sortie/$NOM."
    rm "$SRC"
    for P in sortie/"$NOM".*; do
      PARTIES=$(jq -c --arg n "$(basename "$P")" --argjson t "$(stat -c %s "$P")" '. + [{nom: $n, taille: $t}]' <<<"$PARTIES")
    done
  else
    mv "$SRC" "sortie/$NOM"
  fi
  FICHIERS=$(jq -c --arg ty "$TYPE" --arg n "$NOM" --argjson t "$TAILLE" --arg s "$SHA" --argjson p "$PARTIES" \
    '. + [{type: $ty, nom: $n, taille: $t, sha256: $s, parties: $p}]' <<<"$FICHIERS")
done
jq -n --arg id "$ID" --arg date "$DATE" --argjson cadre "$CADRE" --argjson f "$FICHIERS" \
  --slurpfile z zones.json '($z[0].zones[] | select(.id == $id)) as $zone
  | {id: $id, nom: $zone.nom, groupe: $zone.groupe, date: $date, cadre: $cadre, fichiers: $f}' > "sortie/$ID.json"
cat "sortie/$ID.json"
rm -rf "$T"
