"""Instagram-Raster und „Teddy kocht“ für rewerichter.de aus dem Social-Repo befüllen.

Quelle ist das öffentliche Repo ReweRichter/rewe-richter-social (lokal im Ordner social/):
  queue/<eintrag>/item.json   was gepostet wird (Angebote tragen „angebot_bis“)
  state/published.json        was wirklich auf Instagram ist, mit Link

Aufruf:  python tools/website_social.py --social social --ziel <Website-Ordner>

Schreibt:
  <ziel>/instagram/instagram.json + Bilder: die neuesten veröffentlichten Beiträge OHNE Angebote
      (keine Storys, nichts mit „angebot_bis“, nichts, was auf Instagram gelöscht wurde),
      jede Kachel verlinkt auf den Beitrag.
  <ziel>/rezepte/rezepte.json + Bilder: die Rezept-Karussells, auch schon eingeplante.
      Die Seite zeigt nur die, deren Zeitpunkt vorbei ist, davon die neuesten vier.
Nur Standardbibliothek und Pillow, läuft so auch im Website-Workflow.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from PIL import Image

INSTA_ANZAHL = 6
REZEPT_ANZAHL = 8  # vier sichtbare + Puffer für eingeplante


def bild_von(ordner, item):
    if item.get("cover"):
        return ordner / item["cover"]
    if item.get("datei") and not item["datei"].endswith(".mp4"):
        return ordner / item["datei"]
    if item.get("dateien"):
        return ordner / item["dateien"][0]
    return None


def speichern(quelle, ziel):
    im = Image.open(quelle).convert("RGB")
    im.thumbnail((540, 675), Image.LANCZOS)
    im.save(ziel, quality=82)


def erste_zeile(caption):
    zeile = (caption or "").strip().splitlines()[0] if caption else ""
    return re.sub(r"[^\w\s.,:;!?&()\-–’'„“\"/äöüÄÖÜß]", "", zeile).strip()


def aufraeumen(ordner, behalten):
    for alt in ordner.glob("*.webp"):
        if alt.stem not in behalten:
            alt.unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--social", required=True, help="Ordner des Social-Repos")
    ap.add_argument("--ziel", required=True)
    a = ap.parse_args()

    social = Path(a.social)
    veroeffentlicht = json.loads((social / "state" / "published.json").read_text(encoding="utf-8"))
    eintraege = []
    for item_json in (social / "queue").glob("*/item.json"):
        item = json.loads(item_json.read_text(encoding="utf-8"))
        eintraege.append((item_json.parent.name, item_json.parent, item))
    eintraege.sort(key=lambda e: e[2]["zeit"], reverse=True)

    # --- Instagram: veröffentlicht, kein Angebot, keine Story ---
    ziel_i = Path(a.ziel) / "instagram"
    ziel_i.mkdir(parents=True, exist_ok=True)
    insta = []
    for name, ordner, item in eintraege:
        st = veroeffentlicht.get(name, {})
        if item.get("typ") == "story" or "angebot_bis" in item or st.get("status") != "veröffentlicht" or not st.get("link"):
            continue
        quelle = bild_von(ordner, item)
        if not quelle or not quelle.exists():
            continue
        speichern(quelle, ziel_i / f"{name}.webp")
        insta.append({"bild": f"instagram/{name}.webp", "link": st["link"], "typ": item["typ"],
                      "text": erste_zeile(item.get("caption")), "zeit": item["zeit"]})
        if len(insta) == INSTA_ANZAHL:
            break
    aufraeumen(ziel_i, {Path(e["bild"]).stem for e in insta})
    (ziel_i / "instagram.json").write_text(json.dumps(insta, ensure_ascii=False, indent=1), encoding="utf-8")

    # --- Rezepte: alle Rezept-Karussells, auch eingeplante ---
    ziel_r = Path(a.ziel) / "rezepte"
    ziel_r.mkdir(parents=True, exist_ok=True)
    rezepte = []
    for name, ordner, item in eintraege:
        m = re.search(r"-rezept-(.+)$", name)
        if not m or item.get("typ") != "carousel" or veroeffentlicht.get(name, {}).get("status") == "nicht mehr vorhanden":
            continue
        slug = m.group(1)
        speichern(ordner / item["dateien"][0], ziel_r / f"{slug}.webp")
        cap = item.get("caption", "")
        titel = erste_zeile(cap).removeprefix("Teddy kocht:").strip()
        info = next((l for l in cap.splitlines() if "⏱" in l), "")
        info = re.sub(r"\s+", " ", re.sub(r"[⏱🍽·]", " ", info)).strip().replace(" Portionen", " Portionen").replace(". ", "., ", 1)
        rezepte.append({"slug": slug, "name": titel, "url": f"https://www.rewe.de/rezepte/{slug}/",
                        "zeit": item["zeit"], "bild": f"rezepte/{slug}.webp", "info": info})
        if len(rezepte) == REZEPT_ANZAHL:
            break
    aufraeumen(ziel_r, {e["slug"] for e in rezepte})
    (ziel_r / "rezepte.json").write_text(json.dumps(rezepte, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"Instagram: {len(insta)} Beiträge ohne Angebote, Rezepte: {len(rezepte)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
