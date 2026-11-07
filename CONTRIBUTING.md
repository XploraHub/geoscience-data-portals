# Contributing

Thank you for helping keep this catalogue right.

## Report a problem

The quickest way is an issue: [correction](../../issues/new?template=correction.yml), [new portal](../../issues/new?template=new-portal.yml) or [portal down](../../issues/new?template=portal-down.yml). You don't need to edit any files.

## Edit a portal

Each portal is one file, `data/<code>/<id>.yaml`, where `<code>` is the ISO 3166 code of the country or state (`AU-WA`, `CA-BC`, `US-NV`, `SE`). Mind the codes that look like states: `SA` is Saudi Arabia (South Australia is `AU-SA`), and `CA-NT` is the Northwest Territories (the Northern Territory is `AU-NT`). Quote new codes in `data/jurisdictions.yaml`, or YAML reads `NO` (Norway) as false. The fields are defined in [`schema/portal.schema.json`](schema/portal.schema.json). Copy an existing file as a starting point.

Rules:

- **State only what a source shows.** Put the page in `sources`. If a portal names no licence, write `unstated`.
- **Open the pages yourself** and set `last_verified` to that day and `verified_by` to your GitHub name. Entries checked by the XploraHub team say `XploraHub`.
- **Service addresses must be the service itself.** A `wms` or `wfs` entry needs the address QGIS would use, not a catalogue page about it.
- **Caveats are facts users need,** such as "no quality control on assays". If the portal states how long company reports stay confidential, put the years in `open_file_after`.
- **Never delete a portal.** Set `status` to `deprecated` or `superseded` (with `superseded_by`).

Then run:

```
pip install pyyaml jsonschema rfc3987
python scripts/build.py
```

This checks every file and rewrites the README tables and the generated files. Commit them with your change. Pull requests are checked the same way.

`python scripts/check_services.py` asks every WMS, WFS and ArcGIS REST service for its capabilities. It runs every night too.

## Conduct

Be kind and stick to the facts.
