#!/usr/bin/env python3
"""Fichier de recherche hors ligne de GB Navigation : villes, lieux nommés et rues d'une région.

Entrée : un extrait OpenStreetMap déjà filtré (voir construire.sh). Sortie : une base SQLite
avec une table plein texte « lieux(cle, nom, detail, lat, lon) » que l'appli lit telle quelle.
La clé est en minuscules sans accents, ce qui permet le découpage « simple » de SQLite,
présent sur tous les téléphones Android.
"""
import math
import sqlite3
import sys
import unicodedata

import osmium

TYPES_LIEUX = {"city": 0, "town": 1, "village": 2, "suburb": 3, "hamlet": 4, "locality": 5, "isolated_dwelling": 6}
NOMS_LIEUX = {"city": "Ville", "town": "Ville", "village": "Village", "suburb": "Quartier", "hamlet": "Hameau",
              "locality": "Lieu-dit", "isolated_dwelling": "Lieu-dit"}
COMMUNES = {"city", "town", "village"}
CLES_POI = ("amenity", "shop", "tourism", "leisure", "aeroway", "railway", "public_transport", "office", "craft")
NOMS_POI = {
    "fuel": "Station-service", "charging_station": "Borne de recharge", "parking": "Parking", "hospital": "Hôpital",
    "pharmacy": "Pharmacie", "restaurant": "Restaurant", "cafe": "Café", "bar": "Bar", "fast_food": "Restauration rapide",
    "supermarket": "Supermarché", "bakery": "Boulangerie", "townhall": "Mairie", "school": "École", "post_office": "Poste",
    "police": "Police", "hotel": "Hôtel", "museum": "Musée", "station": "Gare", "aerodrome": "Aéroport",
    "bank": "Banque", "doctors": "Médecin", "camp_site": "Camping", "attraction": "Attraction", "viewpoint": "Point de vue",
}
ROUTES_IGNOREES = {"proposed", "construction", "abandoned", "platform", "raceway", "bus_stop", "elevator"}


def cle(*textes):
    t = " ".join(x for x in textes if x).lower()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join("".join(c if c.isalnum() and c.isascii() else " " for c in t).split())


class Lecteur(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.lieux = []   # (rang, nom, type, lat, lon)
        self.pois = []    # (nom, genre, lat, lon)
        self.rues = []    # (nom, lat, lon)

    def node(self, n):
        nom = n.tags.get("name")
        if not nom or not n.location.valid():
            return
        place = n.tags.get("place")
        if place in TYPES_LIEUX:
            self.lieux.append((TYPES_LIEUX[place], nom, place, n.location.lat, n.location.lon))
            return
        genre = self.genre(n.tags)
        if genre is not None:
            self.pois.append((nom, genre, n.location.lat, n.location.lon))

    def way(self, w):
        nom = w.tags.get("name")
        if not nom:
            return
        points = [(nd.lat, nd.lon) for nd in w.nodes if nd.location.valid()]
        if not points:
            return
        hw = w.tags.get("highway")
        if hw and hw not in ROUTES_IGNOREES and w.tags.get("area") != "yes":
            lat, lon = points[len(points) // 2]
            self.rues.append((nom, lat, lon))
            return
        genre = self.genre(w.tags)
        if genre is not None:
            lat = sum(p[0] for p in points) / len(points)
            lon = sum(p[1] for p in points) / len(points)
            self.pois.append((nom, genre, lat, lon))

    @staticmethod
    def genre(tags):
        for k in CLES_POI:
            v = tags.get(k)
            if v and v != "no":
                return NOMS_POI.get(v, "")
        return None


class Grille:
    """Commune la plus proche d'un point (cases de 0,1°)."""

    def __init__(self, communes):
        self.cases = {}
        for nom, lat, lon in communes:
            self.cases.setdefault((int(lat * 10), int(lon * 10)), []).append((nom, lat, lon))

    def proche(self, lat, lon):
        i, j = int(lat * 10), int(lon * 10)
        meilleur, d_min = None, 1e18
        for r in range(0, 4):
            for di in range(-r, r + 1):
                for dj in range(-r, r + 1):
                    if max(abs(di), abs(dj)) != r:
                        continue
                    for nom, la, lo in self.cases.get((i + di, j + dj), ()):
                        d = (la - lat) ** 2 + ((lo - lon) * math.cos(math.radians(lat))) ** 2
                        if d < d_min:
                            meilleur, d_min = nom, d
            if meilleur is not None and r >= 1:
                break
        return meilleur or ""


def main(entree, sortie):
    lecteur = Lecteur()
    lecteur.apply_file(entree, locations=True, idx="flex_mem")
    communes = [(nom, lat, lon) for _, nom, place, lat, lon in lecteur.lieux if place in COMMUNES]
    grille = Grille(communes)

    db = sqlite3.connect(sortie)
    db.execute("PRAGMA page_size = 4096")
    db.execute("CREATE VIRTUAL TABLE lieux USING fts4(cle, nom, detail, lat, lon, notindexed=nom, notindexed=detail, "
               "notindexed=lat, notindexed=lon, tokenize=simple)")
    lignes = []
    vus = set()

    def ajouter(nom, detail, lat, lon, commune=""):
        k = (nom, detail)
        if k in vus:
            return
        vus.add(k)
        lignes.append((cle(nom, commune), nom, detail, round(lat, 6), round(lon, 6)))

    for rang, nom, place, lat, lon in sorted(lecteur.lieux):
        commune = "" if place in COMMUNES else grille.proche(lat, lon)
        ajouter(nom, NOMS_LIEUX[place] + (" · " + commune if commune else ""), lat, lon, commune)
    for nom, genre, lat, lon in lecteur.pois:
        commune = grille.proche(lat, lon)
        ajouter(nom, " · ".join(x for x in (genre, commune) if x), lat, lon, commune)
    for nom, lat, lon in lecteur.rues:
        commune = grille.proche(lat, lon)
        ajouter(nom, commune, lat, lon, commune)

    db.executemany("INSERT INTO lieux VALUES (?, ?, ?, ?, ?)", lignes)
    db.execute("INSERT INTO lieux(lieux) VALUES ('optimize')")
    db.commit()
    db.execute("VACUUM")
    db.close()
    print(f"{len(lecteur.lieux)} lieux, {len(lecteur.pois)} points d'intérêt, {len(lecteur.rues)} tronçons de rue -> {len(lignes)} entrées")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
