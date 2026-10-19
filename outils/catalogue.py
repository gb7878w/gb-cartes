#!/usr/bin/env python3
"""Rassemble les descriptions <id>.json en catalogue.json, dans l'ordre de zones.json.
Usage : catalogue.py zones.json dossier_des_descriptions catalogue.json"""
import json
import os
import sys

zones = json.load(open(sys.argv[1]))["zones"]
sortie = []
for z in zones:
    chemin = os.path.join(sys.argv[2], z["id"] + ".json")
    if os.path.exists(chemin):
        sortie.append(json.load(open(chemin)))
json.dump({"version": 1, "zones": sortie}, open(sys.argv[3], "w"), ensure_ascii=False, indent=1)
print(f"{len(sortie)} zones sur {len(zones)} dans le catalogue")
