# ADR-PRV-RECEIPT-PERSISTENCE-001 - Estados y snapshots de recepciones

Decision del equipo para publicacion oficial, 2026-10-11. Adaptador existente,
decision y pruebas juntos. No publica router/servidor ni cierra HU-WFL-001.

MongoReceipts usa receipts/receipt_requests y consulta el proveedor en la misma
base suppliers. No consulta Catalogo ni cambia stock; Inventario valida medicamento.
Preparar verifica proveedor activo y vencimiento civil America/Bogota, crea PENDING
y respuesta original en una transaccion snapshot/majority. Replay consulta primero
la intencion y no rehace el efecto. Referencia por proveedor y saga son unicas.

Confirmar produce CONFIRMED; anular permite PENDING/CONFIRMED a VOIDED. VOIDED no
puede confirmarse con una intencion nueva. Se conserva createdBy/initiatedBy/trace
original y solo cambia auditoria de transicion. No-op conserva auditoria pero guarda
su intencion. Replay devuelve snapshot historico, no reactiva el estado actual.
Cada operacion tiene su scope actor/operacion/clave y confirma estado+snapshot juntos.

Anular un documento confirmado NO demuestra que su entrada de Inventario sea
reversible: el Workflow debe cancelar primero la entrada y no anular tras ACTIVE.
La API futura restringira mutaciones a la identidad de servicio mis-workflow;
este adaptador no implementa permisos HTTP ni una transaccion entre dominios.

Seis casos unitarios de health/404 y ocho nativos de recepciones cubren ciclo/auditoria,
snapshots, conflicto de clave, unicidad, rechazos y fallo BSON en intencion al preparar
y confirmar. Ambos fallos verifican rollback real. La suite completa pasa 115 casos
en replica set desechable; sin credenciales pasa 103 y omite 12 nativos.
No prueba carreras entre replicas, reinicio, JWT/roles reales ni saga integrada.
