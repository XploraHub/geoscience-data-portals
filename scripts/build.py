"""Validate the portal files and write the generated outputs.

    python scripts/build.py          # validate and write
    python scripts/build.py --check  # validate and fail if any output is out of date

Needs PyYAML and jsonschema (with rfc3987, so URIs are checked). Makes no network calls.
"""

import csv
import io
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import quoteattr

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STALE_DAYS = 365

LABELS = {
    "geological-maps": "geological maps", "mineral-occurrences": "mineral occurrences",
    "drillholes": "drillholes", "drillhole-assays": "drillhole assays",
    "surface-geochemistry": "surface geochemistry", "magnetics": "magnetics", "gravity": "gravity",
    "radiometrics": "radiometrics", "electromagnetics": "electromagnetics",
    "magnetotellurics": "magnetotellurics", "seismic": "seismic", "company-reports": "company reports",
    "tenements": "tenements", "remote-sensing": "remote sensing", "geochronology": "geochronology",
    "petrophysics": "petrophysics", "core-library": "core library", "3d-models": "3D models",
    "publications": "publications", "elevation": "elevation",
}
# Readable names for the licence column; anything else shows its id without the LicenseRef- prefix
LICENCES = {
    "unstated": "not stated", "CC0-1.0": "CC0", "CC-BY-4.0": "CC BY 4.0", "CC-BY-3.0-AU": "CC BY 3.0 AU",
    "CC-BY-NC-SA-4.0": "CC BY-NC-SA 4.0 (non-commercial)", "NLOD-1.0": "NLOD 1.0", "NLOD-2.0": "NLOD 2.0",
    "LicenseRef-US-Public-Domain": "public domain (US)", "LicenseRef-OGL-UK-3.0": "OGL UK 3.0",
    "LicenseRef-OGL-Canada-2.0": "OGL Canada 2.0", "LicenseRef-OGL-Alberta": "OGL Alberta",
    "LicenseRef-OGL-Yukon": "OGL Yukon", "LicenseRef-OGL-New-Brunswick": "OGL New Brunswick",
    "LicenseRef-OGL-Nova-Scotia": "OGL Nova Scotia", "LicenseRef-Kings-Printer-Ontario": "Crown copyright (Ontario)",
    "LicenseRef-BC-Access-Only": "access only (BC)", "LicenseRef-MN-State-Noncommercial": "non-commercial (Minnesota)",
    "LicenseRef-GEUS-Terms-of-Use": "GEUS terms (internal use)", "LicenseRef-BGS-Licences": "BGS licences (vary)",
    "LicenseRef-NTGS-Terms-of-Use": "NWT terms (non-commercial)",
}


def licence_label(licence_id):
    return LICENCES.get(licence_id, licence_id.removeprefix("LicenseRef-").replace("-", " "))
METHODS = {
    "viewer": "map viewer", "download": "download", "bulk-download": "bulk download", "wms": "WMS",
    "wfs": "WFS", "wcs": "WCS", "wmts": "WMTS", "arcgis-rest": "ArcGIS REST", "ogc-api": "OGC API",
    "ckan": "CKAN", "stac": "STAC", "ftp": "FTP", "order": "order", "email-request": "by email",
    "api": "API",
}
AUTH = {"none": "", "free-registration": " (free login)", "paid": " (paid)", "restricted": " (restricted)"}


def load():
    schema = json.loads((ROOT / "schema" / "portal.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    places = yaml.safe_load((DATA / "jurisdictions.yaml").read_text())
    if not all(isinstance(code, str) for code in places):
        sys.exit("data/jurisdictions.yaml: quote every code, or YAML reads NO (Norway) as false")
    portals, errors = [], []
    for path in sorted(DATA.glob("*/*.yaml")):
        rel = path.relative_to(ROOT)
        entry = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(entry, dict):
            errors.append(f"{rel}: must be a YAML mapping of fields, not {type(entry).__name__}")
            continue
        if isinstance(entry, dict) and isinstance(entry.get("last_verified"), date):
            entry["last_verified"] = entry["last_verified"].isoformat()  # YAML reads bare dates as dates
        problems = [f"{rel}: {e.message}" for e in validator.iter_errors(entry)]
        if not problems:
            if entry["id"] != path.stem:
                problems.append(f"{rel}: id '{entry['id']}' must match the file name")
            if entry["jurisdiction"] != path.parent.name:
                problems.append(f"{rel}: jurisdiction '{entry['jurisdiction']}' must match the folder")
            if entry["jurisdiction"] not in places:
                problems.append(f"{rel}: add '{entry['jurisdiction']}' to data/jurisdictions.yaml")
            # A day's slack: a contributor in Australia is a day ahead of CI, which runs on UTC
            try:
                if date.fromisoformat(entry["last_verified"]) > date.today() + timedelta(days=1):
                    problems.append(f"{rel}: last_verified is in the future")
            except ValueError:
                problems.append(f"{rel}: last_verified '{entry['last_verified']}' is not a real date")
        errors += problems
        entry["_file"] = str(rel).replace("\\", "/")
        portals.append(entry)
    ids = [p.get("id") for p in portals]
    errors += [f"duplicate id '{i}'" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for p in portals:
        if p.get("superseded_by") and p["superseded_by"] not in ids:
            errors.append(f"{p['_file']}: superseded_by '{p['superseded_by']}' is not a portal id")
    order = list(places)
    portals.sort(key=lambda p: (order.index(p["jurisdiction"]) if p.get("jurisdiction") in order else 999, p.get("name", "")))
    return portals, places, errors


def safe_cell(value):
    """Stop spreadsheet programs reading a cell as a formula."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def to_csv(rows, header):
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([safe_cell(v) for v in row])
    return buf.getvalue()


def portals_csv(portals, places):
    rows = [[
        p["id"], p["name"], p["agency"], p["jurisdiction"], places[p["jurisdiction"]]["name"], p["level"],
        p["status"], p["homepage"], ";".join(p["data_types"]), ";".join(sorted({a["method"] for a in p["access"]})),
        p["licence"]["id"], p.get("open_file_after", ""), p["last_verified"], p["summary"],
    ] for p in portals]
    return to_csv(rows, ["id", "name", "agency", "jurisdiction", "place", "level", "status", "homepage",
                         "data_types", "access_methods", "licence", "open_file_after", "last_verified", "summary"])


def endpoints_csv(portals):
    rows = [[p["id"], a["method"], a["url"], a["auth"], a.get("notes", "")] for p in portals for a in p["access"]]
    return to_csv(rows, ["portal_id", "method", "url", "auth", "notes"])


def geojson(portals, places):
    features = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [places[p["jurisdiction"]]["lon"], places[p["jurisdiction"]]["lat"]]},
        "properties": {
            "id": p["id"], "name": p["name"], "agency": p["agency"], "jurisdiction": p["jurisdiction"],
            "status": p["status"], "homepage": p["homepage"], "data_types": p["data_types"],
            "licence": p["licence"]["id"], "last_verified": p["last_verified"],
        },
    } for p in portals]
    return json.dumps({"type": "FeatureCollection", "features": features}, indent=1, ensure_ascii=False) + "\n"


def short(notes, limit=60):
    """First clause of an access note, cut at a word, to name a QGIS connection."""
    text = notes.split(";")[0].strip()
    if len(text) <= limit:
        return text
    return re.sub(r",?\s+(and|or)$", "", text[:limit].rsplit(" ", 1)[0].rstrip(",")) + "…"


def qgis(portals, method, root_tag, item_tag):
    lines = ["<!DOCTYPE connections>", f'<{root_tag} version="1.0">']
    seen = set()  # one connection per service, even when several portals list it
    for p in portals:
        for i, a in enumerate(x for x in p["access"] if x["method"] == method):
            if a["url"] in seen:
                continue
            seen.add(a["url"])
            name = p["name"] if i == 0 else f"{p['name']}: {short(a['notes'])}" if a.get("notes") else f"{p['name']} ({i + 1})"
            lines.append(f"  <{item_tag} name={quoteattr(name)} url={quoteattr(a['url'])} />")
    lines.append(f"</{root_tag}>")
    return "\n".join(lines) + "\n"


def readme_section(portals, places):
    out = []
    countries = [c for c in places if "-" not in c]
    for country in countries:
        group = [p for p in portals if p["jurisdiction"].split("-")[0] == country]
        if not group:
            continue
        out += [f"### {places[country]['name']}", "",
                "| Portal | Holds | Access | Licence | Checked |", "|---|---|---|---|---|"]
        for p in group:
            place = places[p["jurisdiction"]]["name"]
            title = f"[{p['name']}]({p['homepage']})" + ("" if p["jurisdiction"] == country else f" ({place})")
            if p["status"] != "active":
                title += f" *{p['status']}*"
            holds = ", ".join(LABELS[d] for d in p["data_types"])
            access = ", ".join(dict.fromkeys(METHODS[a["method"]] + AUTH[a["auth"]] for a in p["access"]))
            out.append(f"| {title} | {holds} | {access} | {licence_label(p['licence']['id'])} | [{p['last_verified']}]({p['_file']}) |")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def readme(portals, places):
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    start, end = "<!-- portals:start -->\n", "<!-- portals:end -->"
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    head = re.sub(r"<!-- count:start -->\d*<!-- count:end -->", f"<!-- count:start -->{len(portals)}<!-- count:end -->", head)
    return head + start + readme_section(portals, places) + end + tail


def main():
    check = "--check" in sys.argv
    portals, places, errors = load()
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    outputs = {
        "portals.csv": portals_csv(portals, places),
        "endpoints.csv": endpoints_csv(portals),
        "portals.geojson": geojson(portals, places),
        "qgis/wms-connections.xml": qgis(portals, "wms", "qgsWMSConnections", "wms"),
        "qgis/wfs-connections.xml": qgis(portals, "wfs", "qgsWFSConnections", "wfs"),
        "README.md": readme(portals, places),
    }
    stale = [name for name, content in outputs.items()
             if not (ROOT / name).exists() or (ROOT / name).read_text(encoding="utf-8") != content]
    if check:
        if stale:
            print("Out of date, run python scripts/build.py: " + ", ".join(stale))
            sys.exit(1)
    else:
        for name in stale:
            (ROOT / name).parent.mkdir(parents=True, exist_ok=True)
            (ROOT / name).write_text(outputs[name], encoding="utf-8", newline="\n")
    old = [p["_file"] for p in portals if (date.today() - date.fromisoformat(p["last_verified"])).days > STALE_DAYS]
    if old:
        print(f"Not checked in the last {STALE_DAYS} days:\n  " + "\n  ".join(old))
    print(f"{len(portals)} portals OK" + ("" if check else f", wrote {len(stale)} files"))


if __name__ == "__main__":
    main()
