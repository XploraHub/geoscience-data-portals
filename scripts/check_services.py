"""Ask every WMS, WFS and ArcGIS REST service for its capabilities.

    python scripts/check_services.py [report.md]

Prints one line per service and writes a Markdown report of the failures.
Exits 1 if any service failed, so a workflow can open an issue.
Needs PyYAML. Uses only the standard library for HTTP.
"""

import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

import yaml

ROOT = Path(__file__).resolve().parent.parent
QUERY = {
    "wms": {"service": "WMS", "request": "GetCapabilities"},
    "wfs": {"service": "WFS", "request": "GetCapabilities"},
    "arcgis-rest": {"f": "json"},
}
TIMEOUT = 45


def with_query(url, extra):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query.update(extra)
    return urlunsplit(parts._replace(query=urlencode(query)))


def check(service):
    portal, method, url = service
    request = urllib.request.Request(with_query(url, QUERY[method]), headers={"User-Agent": "geoscience-data-portals service check"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read(4000).decode("utf-8", "replace")
            landed = urlsplit(response.url).hostname
    except Exception as error:  # timeouts, HTTP errors, certificate failures
        return service, f"no answer ({type(error).__name__}: {error})"[:200]
    if landed != urlsplit(url).hostname:  # sent somewhere else, such as a login page
        return service, f"redirected to {landed}"
    if method == "arcgis-rest":
        ok = body.lstrip().startswith("{") and '"error"' not in body
    else:
        ok = "capabilities" in body.lower()
    return service, None if ok else "answered, but not with capabilities"


def main():
    services, seen = [], set()
    for path in sorted((ROOT / "data").glob("*/*.yaml")):
        entry = yaml.safe_load(path.read_text(encoding="utf-8"))
        for access in entry.get("access", []):
            # Several portals can list the same service; ask it once
            if access["method"] in QUERY and (access["method"], access["url"]) not in seen:
                seen.add((access["method"], access["url"]))
                services.append((entry["id"], access["method"], access["url"]))
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(check, services))
    failed = [(s, why) for s, why in results if why]
    for (portal, method, url), why in results:
        print(f"{'FAIL' if why else 'ok  '} {portal} {method} {url}" + (f"  {why}" if why else ""))
    if len(sys.argv) > 1:
        lines = [f"{len(failed)} of {len(services)} services did not answer with their capabilities.", ""]
        lines += [f"- `{portal}` {method}: {url}  \n  {why}" for (portal, method, url), why in failed]
        lines += ["", "One failed night can be a blip. Mark an entry `uncertain` only after several."]
        Path(sys.argv[1]).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(services) - len(failed)} of {len(services)} services answered")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
