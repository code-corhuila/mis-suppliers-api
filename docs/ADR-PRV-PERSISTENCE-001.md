# ADR-PRV-PERSISTENCE-001 - Persistencia transaccional de Proveedores

Decision del equipo para publicacion oficial, 2026-10-11. Adaptador existente,
decision y pruebas publicados juntos. No incluye recepciones ni servidor HTTP.

MongoSuppliers usa exclusivamente suppliers/creation_requests en la base propia.
Replica set obligatorio; snapshot, majority, PRIMARY y plazo global de 5 segundos.
Proveedor y respuesta original se confirman juntos. Actor/operacion/clave delimitan
la intencion; huella distinta produce 409. Tras DuplicateKeyError se consulta
intencion confirmada; si solo el documento esta ocupado, 422 sin consumir clave.
No se prometen reintentos ilimitados ni resultados si Mongo permanece indisponible.

Snapshot original se conserva aunque cambie el proveedor. El recurso oculta _id
y createdBy, fecha UTC con Z y opcionales null. Listado/total comparten snapshot,
orden por createdAt/_id descendente. Health exige primario, colecciones e indices
previos; no crea estructura ni modifica migraciones oficiales.

Siete pruebas unitarias simulan Mongo; cuatro nativas usan suppliers_app sobre
un replica set desechable. Intencion BSON invalida provoca error 121 y ausencia
del proveedor, verificando el aborto real con el adaptador y PyMongo. Tambien se
prueban replay/conflicto, documento duplicado sin clave consumida, salud/consulta.
No prueban carreras entre replicas, reinicios, JWT ni QA/main. Sin credencial de
test, pytest omite las cuatro nativas; CI no las presenta como ejecutadas.
