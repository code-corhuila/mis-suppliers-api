# ADR-PRV-CORE-001 - Publicar el nucleo de Proveedores

Decision del equipo para publicacion oficial, 2026-10-11. Acompana modelo,
servicio/puertos y pruebas; no publica servidor ni cierra HU-PRV-001.

## Decision y contrato

core.py no importa FastAPI/PyMongo/JWT. NewSupplier valida objetos JSON con campos
documentNumber/name obligatorios y phone/email/address opcionales. Un opcional
omitido es None; enviado como null, no texto o vacio se rechaza. Solo campos conocidos.
Documento ASCII alfanumerico/guion, hasta 40, normalizado a mayusculas; texto recortado,
nombre hasta 160, phone 30, email 254, address 240. Email usa email-validator sin
consulta de entregabilidad y pasa a minusculas. No se registra stock en Proveedores.

La huella SHA-256 usa lista JSON ordenada de los cinco campos normalizados.
El servicio valida Idempotency-Key sensible a mayusculas, sin trim (8..128),
UUID canonico de consulta y paginacion page>=1, limit 1..100 (default 1/20).
Actor/autorizacion los proveera Seguridad; persistencia e idempotencia transaccional
las implementara el adaptador Mongo, no este nucleo. No hay consultas cruzadas SQL.

## Verificacion y limites

Treinta casos unitarios usan puertos simulados y biblioteca de email, sin red/DB.
Comprueban normalizacion, huella, rechazos, clave, pagina, UUID y delegacion.
requirements conserva dependencias locales fijadas para las siguientes etapas,
pero aun no hay API ejecutable ni recepciones publicadas. CI ejecuta pytest en
Python 3.12 sobre develop/qa, con cancelacion y timeout de diez minutos.
