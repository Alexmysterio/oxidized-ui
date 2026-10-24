# Frontend — implementación de la fase 3

Estado: SPA React + TypeScript + Vite construida y verificada contra el backend y
el stack Docker real. FastAPI sirve el build en producción. El Dockerfile
multi-stage y la guía de despliegue están en el [README](../README.md).

## Stack

- React 19, TypeScript, Vite 6, Tailwind CSS 3.4 y componentes shadcn/ui sobre
  Radix.
- TanStack Query para datos de servidor, React Hook Form + Zod para formularios y
  React Router.
- Recharts para actividad, CodeMirror 6 para YAML y configuraciones, lucide-react
  para iconografía y Sonner para notificaciones.
- Inter Variable como tipografía de interfaz y JetBrains Mono para datos
  técnicos, código, fechas y cifras.
- `pnpm` con `node-linker=hoisted` para resolver correctamente las dependencias
  nativas de Vite.

## Dirección visual

La interfaz se aleja del dashboard genérico: sidebar de tinta profunda, superficie
clara con una retícula técnica muy contenida, tipografía Inter de tracking
cerrado y un único acento cobalto. El modo oscuro invierte la superficie pero
mantiene la misma jerarquía. La señal de Oxidized, las métricas y los estados
usan verde/ámbar/rojo solo como semántica operativa, nunca como decoración.

Los detalles deliberados son:

- marca propia de nodos orbitando un núcleo;
- sidebar oscura también en modo claro para anclar la navegación;
- cabecera translúcida, microetiquetas monoespaciadas y números tabulares;
- empty states y tarjetas de error con el mismo lenguaje visual;
- movimiento corto y respetuoso con `prefers-reduced-motion`.

## Rutas

| Ruta | Acceso | Contenido |
| --- | --- | --- |
| `/login` | público | acceso, idioma y tema |
| `/setup` | solo primer arranque | asistente de dos pasos |
| `/` | autenticado | dashboard, salud, actividad, fallos y jobs |
| `/nodes` | autenticado | inventario, filtros, CSV, acciones masivas |
| `/nodes/:id` | autenticado | resumen, config, versiones, diff y acciones |
| `/groups` | operator/admin | credenciales de grupo y borradores |
| `/config` | admin | formulario, YAML, diff, apply e historial |
| `/status` | operator/admin | estado, logs SSE y jobs |
| `/users` | admin | usuarios, roles, altas y reseteos |
| `/audit` | admin | auditoría filtrable y detalle |
| `/profile` | autenticado | idioma, tema y contraseña |
| `/system` | admin | conexión, proxy Docker y comportamiento |
| `/forbidden`, `*` | — | 403/404 |

Las páginas autenticadas se cargan con `React.lazy`; CodeMirror y Recharts
quedan en chunks separados para que login y dashboard inicial no paguen su peso.

## i18n

- Recursos en `frontend/public/locales/es.json` y `en.json`.
- `i18next-http-backend` carga `/locales/{{lng}}.json`; añadir un idioma es
  añadir un JSON y reiniciar el backend para que lo descubra.
- El idioma inicial se decide con la preferencia guardada, el navegador y el
  `default_language` del backend. Después del login manda el idioma del usuario.
- Fechas, horas, números, relativos y unidades usan `Intl`. La zona horaria sale
  de `meta.timezone`; si está vacía, se usa la del navegador.
- Los códigos de error y de auditoría se traducen en el cliente. El backend
  nunca envía texto traducible.
- Comprobación automática:

```bash
cd frontend
node scripts/check-i18n.mjs
```

El script verifica paridad es/en, claves usadas que falten, claves no usadas,
todos los códigos de `error_codes.json` y todas las acciones de
`audit_actions.json`. Las familias dinámicas (`errors.*`, `audit.actions.*`,
`oxidized.*`, `jobs.*`, etc.) están declaradas explícitamente.

## Sesión, CSRF y permisos

- La sesión viaja en cookie HttpOnly; el cliente nunca lee el token.
- El token CSRF que devuelve `/auth/session` se guarda en memoria y se añade en
  cada mutación. Los `GET` y el stream SSE no lo necesitan.
- Un 401 en una llamada protegida limpia la caché, avisa y devuelve al login.
- Los botones y rutas se ocultan o bloquean con las capabilities del backend,
  pero la autorización real sigue siendo del servidor.

## Pantallas y flujos verificados

- primer arranque, login, error de credenciales y sesión;
- dashboard con datos reales del mock, actividad y fallos;
- alta y edición de nodos desde el drawer, con secretos write-only;
- búsqueda global con `Ctrl/Cmd+K` y búsqueda dentro de configuraciones;
- configuración: formulario por secciones, vars conocidas, guardado de borrador,
  diff de una sola línea, aplicación y reinicio con job;
- historial de revisiones y editor YAML de CodeMirror;
- versión de nodo, configuración actual y diff entre versiones;
- logs SSE en vivo, filtros, pausa, descarga y cola de jobs;
- usuarios, RBAC de viewer, auditoría, perfil y ajustes del sistema;
- tema claro/oscuro, cambio es/en, layout móvil y drawer de navegación.

## Verificación local

```bash
cd frontend
pnpm install
pnpm test
pnpm typecheck
pnpm build
node scripts/check-i18n.mjs
```

La suite frontend usa Vitest para utilidades de rutas, validación Zod, formato
`Intl` y traducción de errores. El script i18n comprueba además paridad y claves
usadas/no usadas.

El backend puede servir el build directamente:

Configura `STATIC_DIR` y `LOCALES_DIR` apuntando a `frontend/dist` y
`frontend/dist/locales` en el entorno del backend.

y la SPA queda disponible en `http://127.0.0.1:8000`. En desarrollo, `pnpm dev`
usa el proxy `/api` hacia `127.0.0.1:8000`.

La integración real se validó con `oxidized/oxidized:0.37.0` y el proxy de Docker:
primer arranque sin nodos, alta del primer nodo con recuperación automática,
lectura del inventario por Oxidized, logs SSE reales, aplicación de configuración
con reinicio, contenedor UI no root/read-only y únicamente el puerto de la UI
publicado. El test opcional `backend/tests/test_live_integration.py` se ejecuta
contra un stack arrancado; las instrucciones están en el README.
