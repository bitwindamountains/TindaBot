"""Validate the checked-in Render Blueprint against Render's published schema."""

import hashlib
import json
from pathlib import Path

import httpx
import jsonschema
import yaml


def main():
    source = "https://render.com/schema/render.yaml.json"
    response = httpx.get(source, timeout=20, follow_redirects=True)
    response.raise_for_status()
    schema = response.json()
    document = yaml.safe_load(Path("render.yaml").read_text(encoding="utf-8"))
    jsonschema.validate(document, schema)
    for group in document.get("envVarGroups", []):
        if any(variable.get("sync") is False for variable in group.get("envVars", [])):
            raise ValueError(
                "Render ignores sync:false inside environment groups; configure shared secrets manually"
            )
    report = {
        "valid": True,
        "schema_source": source,
        "schema_sha256": hashlib.sha256(response.content).hexdigest(),
        "blueprint_sha256": hashlib.sha256(Path("render.yaml").read_bytes()).hexdigest(),
        "scope": "Static schema validation only; no services were provisioned",
    }
    target = Path("docs/validation/render-blueprint.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "PASS: Render Blueprint matches the published schema; shared secrets require dashboard configuration."
    )


if __name__ == "__main__":
    main()
