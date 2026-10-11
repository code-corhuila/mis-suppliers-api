# mis-suppliers-api

> suppliers bounded context: service API

Part of the **Medicine Inventory System** distributed system — team `medicine-inventory-system`, Grupo 1.
Governance and documentation live in [`mis-docs`](https://github.com/code-corhuila/mis-docs).

## Branching

Three permanent branches. **None of them accepts a direct commit** — you enter through a child
branch and leave through a Pull Request.

```
develop  <--PR--  feat/... fix/... chore/...
qa       <--PR--  qa/...
main     <--PR--  release/...  hotfix/...
```

Promotion happens **by re-application** (`git cherry-pick -x`), never by merging one permanent
branch into another: `merge develop -> qa` and `merge qa -> main` do not exist in this model.

`main` requires **1 approval from `ariel5253`**. On `develop` and `qa` the team sets its own review
rule.

Full policy: `00-governance/branching-policy.md` in `mis-docs`.

## Publicacion inicial del nucleo HU-PRV-001

Python 3.12. app/core.py publica validacion, normalizacion, huella y puertos sin
importar FastAPI, MongoDB ni JWT. El servidor, persistencia y recepciones siguen
en la preparacion local y se publicaran despues; este clon aun no ofrece HTTP.

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Treinta casos unitarios, sin DB/JWKS ni secretos. No prueban replay persistente,
roles, transacciones o permisos MongoDB. Dependencias fijadas iguales a la
preparacion local; algunas solo seran utilizadas por los adaptadores posteriores.
Decision y limites: [ADR-PRV-CORE-001](docs/ADR-PRV-CORE-001.md).
