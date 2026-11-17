"""Holt den Markt-Prospekt für rewerichter.de, genau wie ihn die REWE-Marktseite zeigt.

Quelle ist derselbe Publitas-Viewer, den rewe.de unter „Prospekt anzeigen“ einbettet:
https://services.publitas.com/rewe/publications?week=<KW>&wwident=<Marktnummer>

Aufruf:
    python tools/prospekt_holen.py --ziel <Website-Ordner> [--woche 48] [--markt 441708]

Welche Woche: sonntags die Folgewoche (Vorschau ab Sonntag 0 Uhr), sonst die laufende
Woche, jeweils nach deutscher Zeit. Die Seiten werden unverändert gespeichert
(<ziel>/prospekt/seite-01.jpg …, groß unter <ziel>/prospekt/gross/) und in
<ziel>/prospekt/prospekt.json beschrieben. Nur Standardbibliothek, läuft so auch in GitHub Actions.

Rückgabewert: 0 = geholt, 2 = für diese Woche noch kein Prospekt online (alter Stand bleibt),
1 = sonstiger Fehler.
"""
import argparse
import json
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

MARKT = "441708"  # REWE Richter, Frohlinder Str. 12, Dortmund
SERVICE = "https://services.publitas.com/rewe/publications?week={kw}&wwident={markt}"
KLEIN, GROSS = "at800", "at1200"  # Leiste / Vergrößerung beim Antippen
UA = {"User-Agent": "Mozilla/5.0 (rewerichter.de Prospekt-Abruf)"}


def jetzt_berlin(now=None):
    """Deutsche Zeit ohne tzdata: MEZ, MESZ vom letzten So im März bis letzten So im Oktober (1 Uhr UTC)."""
    now = now or datetime.now(timezone.utc)

    def letzter_sonntag(jahr, monat):
        d = date(jahr, monat, 31)
        return d - timedelta(days=(d.weekday() + 1) % 7)

    j = now.year
    beginn = datetime.combine(letzter_sonntag(j, 3), datetime.min.time(), timezone.utc) + timedelta(hours=1)
    ende = datetime.combine(letzter_sonntag(j, 10), datetime.min.time(), timezone.utc) + timedelta(hours=1)
    return now + timedelta(hours=2 if beginn <= now < ende else 1)


def ziel_montag(heute):
    """Sonntag -> Montag danach, sonst Montag der laufenden Woche."""
    if heute.weekday() == 6:
        return heute + timedelta(days=1)
    return heute - timedelta(days=heute.weekday())


def holen(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.geturl(), r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ziel", required=True, help="Website-Ordner, darin entsteht prospekt/")
    ap.add_argument("--woche", type=int, help="Kalenderwoche erzwingen (sonst automatisch)")
    ap.add_argument("--markt", default=MARKT)
    a = ap.parse_args()

    montag = ziel_montag(jetzt_berlin().date())
    jahr, kw, _ = montag.isocalendar()
    if a.woche:
        kw = a.woche
        montag = date.fromisocalendar(jahr, kw, 1)

    try:
        viewer, html = holen(SERVICE.format(kw=kw, markt=a.markt))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"KW {kw}: Prospekt noch nicht online (404). Alter Stand bleibt.")
            return 2
        raise

    m = re.search(r"rewe_(\d{4})_wk(\d+)_(\d+)", viewer)
    if not m or (int(m.group(1)), int(m.group(2)), m.group(3)) != (jahr, kw, a.markt):
        print(f"Unerwarteter Prospekt: {viewer} (erwartet {jahr}, KW {kw}, Markt {a.markt})")
        return 1
    basis = viewer.split("?")[0].rstrip("/") + "/"
    html = html.decode("utf-8", "replace")
    pdf = re.search(r"https://view\.publitas\.com/[^\"' ]+?\.pdf\?[^\"' ]+", html)

    _, roh = holen(basis + "spreads.json")
    seiten = sorted((p for s in json.loads(roh) for p in s["pages"]), key=lambda p: p["number"])
    if not seiten:
        print("Keine Seiten gefunden.")
        return 1

    ziel = Path(a.ziel) / "prospekt"
    tmp = Path(tempfile.mkdtemp(prefix="prospekt-", dir=Path(a.ziel)))
    try:
        (tmp / "gross").mkdir()
        liste = []
        for p in seiten:
            nr = int(p["number"])
            name = f"seite-{nr:02d}.jpg"
            for groesse, ordner in ((KLEIN, tmp), (GROSS, tmp / "gross")):
                _, bild = holen("https://view.publitas.com" + p["images"][groesse])
                (ordner / name).write_bytes(bild)
            liste.append({"nr": nr, "klein": f"prospekt/{name}", "gross": f"prospekt/gross/{name}"})
        info = {
            "jahr": jahr, "kw": kw, "markt": a.markt,
            "gueltig_von": montag.isoformat(),
            "gueltig_bis": (montag + timedelta(days=5)).isoformat(),  # Samstag
            "seiten": liste,
            "pdf": pdf.group(0).replace("&amp;", "&") if pdf else None,
            "quelle": basis,
            "geholt": jetzt_berlin().strftime("%Y-%m-%dT%H:%M"),
        }
        (tmp / "prospekt.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        # Inhalt austauschen statt Ordner löschen (unter Windows kann der Ordner selbst gesperrt sein)
        ziel.mkdir(exist_ok=True)
        for alt in ziel.iterdir():
            shutil.rmtree(alt) if alt.is_dir() else alt.unlink()
        for neu in tmp.iterdir():
            shutil.move(str(neu), str(ziel / neu.name))
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"KW {kw}/{jahr}: {len(liste)} Seiten nach {ziel} geholt, gültig {info['gueltig_von']} bis {info['gueltig_bis']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
