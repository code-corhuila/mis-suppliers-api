# ADR-PRV-DEPLOYMENT-001 - Despliegue y contratos oficiales

Decision del equipo para publicacion, 2026-10-11. Docker/OpenAPI acompanados de
script de aceptacion real. No acredita QA/main ni reemplaza el servicio activo.
Imagen multietapa, usuario 10001, API sin puertos por defecto; override dev solo
loopback 58083. Espera migraciones/Seguridad; usa suppliers_app en motor compartido.
Claves privadas solo en Seguridad; la prueba recibe JWT existente del Workflow,
no firma tokens ni crea una identidad nueva. TTL/renovacion dependen de Seguridad.

Contrato suppliers para CRUD disponible (crear/consultar/listar, no borrar/editar)
y receipts para preparar/confirmar/anular. JSON Schema valida muestras de respuestas
reales, paginas, errores y auditoria de estados. CI valida ambos OpenAPI y sintaxis;
aceptacion con DB/JWKS no se ejecuta en CI ni se presenta como tal.

Prueba crea proveedor sintetico activo y recepcion con UUID externos sinteticos,
confirma/anula y conserva ambos como evidencia. No prepara entradas ni toca stock;
no representa saga completa ni afirma que medicationId exista en Catalogo.
Instancia de prueba requiere nombre/puerto propios, sin alias suppliers en red.
No borra documentos previos ni volumenes; operador elimina solo contenedor temporal.
Los secretos no se exportan, imprimen ni incluyen en muestras del contrato.
