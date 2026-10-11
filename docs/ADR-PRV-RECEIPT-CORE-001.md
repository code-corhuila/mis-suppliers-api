# ADR-PRV-RECEIPT-CORE-001 - Nucleo de recepciones

Decision del equipo para publicacion oficial, 2026-10-11. Modelo y puertos
existentes acompanados de pruebas; dependencia de HU-WFL-001, no cierre de la saga.

NewReceipt exige supplierId, medicationId, workflowId e initiatedBy UUID canonicos,
reference/lotNumber ASCII alfanumerico o guion, 1..40, recortados y en mayusculas;
expiresOn fecha civil ISO valida y quantity entero exacto 1..1000000 (no bool).
Rechaza campos faltantes/desconocidos y cuerpos no objeto. Huella SHA-256 de
JSON ordenado del documento normalizado. fresh(today) rechaza vencimiento <=today;
el adaptador elegira fecha civil y momento de comprobarla, sin invalidar replay.

ReceiptService valida clave idempotente sin trim (8..128), UUID de consulta y
acciones confirm/void. Otras acciones producen 404 sin llamar al puerto. Actor y
trace se propagan sin sustituirlos; su autenticacion/correlacion viene de HTTP/JWT.
Este nucleo no lee DB ni modifica stock. Preparar/consultar/transicionar pertenecen
al puerto Receipts; estados persistidos, auditoria y snapshots son del adaptador.
Proveedor activo, unicidad, permisos y coordinacion con Inventario no se demuestran
con un puerto simulado ni se convierten en una transaccion entre dominios.

Treinta y un casos unitarios de recepciones verifican validacion, normalizacion,
huella, vencimiento civil, clave, UUID y delegacion. Se separan del archivo local
que mezclaba dominio con HTTP, preservando pruebas del nucleo sin importar main.
La suite actual ejecuta 97 casos y omite cuatro nativos de MongoDB sin credenciales.
Faltan persistencia de recepciones, servidor/roles HTTP, contrato y aceptacion real.
