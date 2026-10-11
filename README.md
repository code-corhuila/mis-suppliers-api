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
importar FastAPI, MongoDB ni JWT. El servidor y las capas HTTP/persistencia de recepciones siguen
en la preparacion local y se publicaran despues; este clon aun no ofrece HTTP.

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Treinta casos unitarios, sin DB/JWKS ni secretos. No prueban replay persistente,
roles, transacciones o permisos MongoDB. Dependencias fijadas iguales a la
preparacion local; algunas solo seran utilizadas por los adaptadores posteriores.
Decision y limites: [ADR-PRV-CORE-001](docs/ADR-PRV-CORE-001.md).

## Persistencia MongoDB

app/mongo.py implementa proveedor + snapshot en una transaccion. No crea estructura:
requiere las migraciones oficiales. Decision: [ADR-PRV-PERSISTENCE-001](docs/ADR-PRV-PERSISTENCE-001.md).
pytest sin configuracion omite cuatro casos nativos; CI no usa secretos de DB.
Para ejecutar tambien los nativos con PowerShell 7, Docker y replica set desechable:

```powershell
pwsh -NoProfile -File ./tests/Test-Persistence.ps1 -InfraRoot 'D:\descargas\pago 2\mis-infra-postgres' -MongoInfraRoot 'D:\descargas\pago 2\mis-infra-mongo' -SuppliersDbRoot '<clon-oficial-mis-suppliers-db>'
```

Usar el clon DB publicado que admite MIS_INFRA_MONGO_PATH. El script levanta un
proyecto aleatorio, aplica migraciones y elimina solo sus volumenes al terminar.
No toca datos dev/qa/main ni renueva credenciales. Aun no publica servidor HTTP.

## JWT y middleware HTTP

app/security.py verifica tokens con JWKS/RS256; app/middleware.py aplica correlacion
y lectura acotada. Decision: [ADR-PRV-SECURITY-001](docs/ADR-PRV-SECURITY-001.md).
Las pruebas de esta capa usan RSA temporales,
JWKS simulado y mensajes ASGI; no afirma permisos por ruta ni JWKS remoto probado.
No hay servidor HTTP ejecutable aun: main.py depende tambien de las recepciones,
cuya publicacion se completa antes de integrar el servidor. Despliegue activo intacto.

## Nucleo de recepciones

app/receipts.py publica documento normalizado y puertos de participante para
preparar, consultar, confirmar/anular. No contiene persistencia ni reglas de roles
HTTP y no modifica stock. [Decision](docs/ADR-PRV-RECEIPT-CORE-001.md).
31 casos de dominio/servicio se suman a la suite: 97 passed y cuatro nativos
omitidos al ejecutar pytest sin DB. Las pruebas mezcladas de HTTP locales se
publicaran con servidor/router, sin imports rotos en esta etapa.
La identidad del servicio, estados/auditoria, idempotencia transaccional y saga
requieren sus adaptadores y aceptacion real; este bloque no cierra HU-WFL-001.
