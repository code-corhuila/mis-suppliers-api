# ADR-PRV-HTTP-001 - Componer servidor y participante HTTP

Decision del equipo para publicacion oficial, 2026-10-11. main/router y pruebas
HTTP juntos; contratos Docker/OpenAPI y aceptacion real siguen pendientes.

FastAPI compone Tokens, MongoSuppliers y MongoReceipts. Startup/health verifican
ambos adaptadores; no crean estructura. Cliente suppliers_app: pool 10, esperas
2s, socket/operaciones 5s, rs0/tz-aware. Requiere SUPPLIERS_MONGO_HOST,
SUPPLIERS_MONGO_PASSWORD y SUPPLIERS_JWKS_URL; el cliente se cierra al terminar.
Docs interactivos deshabilitados. Errores JSON/correlacion sin detalles de DB.

Crear proveedor exige ADMIN/clave; consultas aceptan roles validados por Tokens.
Preparar/confirmar/anular recepcion exige claim service=mis-workflow + INVENTORY;
ningun header concede identidad. ADMIN/INVENTORY/SUPERVISOR leen recepciones;
CONSULTATION no. Transiciones admiten cuerpo ausente o {}, no campos de estado.
Location y 201/200 siguen resultado del puerto; no se modifica stock por HTTP.

TestClient compone middleware/guards reales con identidad/persistencia simuladas.
Casos verifican 401/403, headers falsos, correlacion, cuerpo acotado, validacion,
Location, acciones desconocidas y fail-closed si falta puerto en un test inyectado.
No prueban aqui firma JWT remota + DB en el mismo recorrido, disponibilidad JWKS,
reinicio ni saga. Suite: 120 passed, 12 skipped sin DB. Aviso de deprecacion
TestClient/httpx registrado, sin fallos; dependencias fijadas no se cambian aqui.
