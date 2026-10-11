# ADR-PRV-SECURITY-001 - JWT y contexto HTTP

Decision del equipo para publicacion oficial, 2026-10-11. Modulos existentes
con sus pruebas y limites en este PR; no publica servidor ni rutas HTTP.

Tokens exige bearer, RS256, kid, firma, issuer mis-security, audience mis-api,
sub UUID canonico, exp y roles reconocidos no vacios. Tolerancia de reloj 30s.
JWKS usa timeout 2s/cache 300s. Token/clave invalidos producen 401; fallo de
conexion JWKS produce 503, sin exponer detalles. No se firma JWT en Proveedores.
La clave privada solo pertenece a Seguridad. Permisos ADMIN de rutas vendran
con el servidor; autenticar claims por si solo no prueba autorizacion HTTP.

RequestContext propaga correlacion segura o genera UUID. Una correlacion invalida
rechaza 400 con trace seguro. Limita cuerpo a 65536 bytes incluso fragmentado
sin Content-Length; espera lectura hasta 15s (408). Registra metodo/estado/trace,
no cuerpos ni credenciales; errores inesperados previos a respuesta producen 500.

Pruebas RSA temporales cubren firma/claims y rechazo de HMAC/none; JWKS se simula
para probar estados 401/503. Pruebas ASGI directas verifican buffering, correlacion
y limite exacto/excedido. No llaman JWKS remoto ni ejercitan autorizacion por ruta,
revocacion inmediata, timeout bajo carga o arranque integrado. CI ejecuta 66 casos
y omite cuatro nativos de DB sin credencial; no se presenta como promocion QA/main.
