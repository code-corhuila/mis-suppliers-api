import json
from pathlib import Path
import sys
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate

root = Path(__file__).resolve().parents[1]
contracts = {name: yaml.safe_load((root / "docs" / f"{name}.openapi.yaml").read_text(encoding="utf-8"))
             for name in ("suppliers", "receipts")}
for contract in contracts.values():
    validate(contract)
if len(sys.argv) > 1:
    for sample in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")):
        contract = contracts[sample["contract"]]
        schema = {"$ref": "#/components/schemas/" + sample["schema"], "components": contract["components"]}
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(sample["body"])
print("PASS: contratos OpenAPI y muestras suministradas validos.")
