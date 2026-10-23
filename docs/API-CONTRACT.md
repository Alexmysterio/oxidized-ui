# Contrato de API (Fase 1)

Base path: `/api`. Autenticación por cookie de sesión; todas las respuestas son
JSON salvo descargas y SSE. La API es same-origin: no hay CORS.

Este contrato es la entrada para la fase 2. Cualquier cambio debe actualizar este
documento, el catálogo de códigos de error y las traducciones antes de tocar el
frontend.

## Convenciones

### Autenticación

- Cookie: `oxidized_ui_session` (`HttpOnly`, `SameSite=Lax`, `Path=/`,
  `Secure` si `SESSION_COOKIE_SECURE=true`).
- La cookie contiene un token opaco; la base de datos solo guarda su SHA-256.
- CSRF: cabecera `X-CSRF-Token` obligatoria en `POST`, `PUT`, `PATCH` y `DELETE`
  autenticados. El valor se obtiene en `GET /api/auth/session` (o en la respuesta
  de login/setup).
- Además se valida `Origin`/`Referer` contra el origen de la petición o
  `TRUSTED_ORIGINS`. Un origen ausente en un método no seguro se rechaza.
- Las peticiones no autenticadas (`login`, `setup`) no llevan token CSRF, pero
  sí validación de origen, `Content-Type: application/json` y rate limiting.
- SSE y descargas son `GET`, no requieren CSRF, pero sí sesión.

### Formato de error

```json
{
  "error": {
    "code": "node.duplicate_name",
    "params": { "name": "sw-core-01" },
    "fields": [
      {
        "path": "name",
        "code": "validation.duplicate",
        "params": { "name": "sw-core-01" }
      }
    ],
    "request_id": "8d3a1f..."
  }
}
```

- `code` es estable y está en `app/data/error_codes.json`.
- `params` solo contiene datos necesarios para interpolar. Nunca secretos.
- `fields` aparece en errores de validación. `path` usa notación de puntos.
- El frontend traduce `errors.<code>`; no muestra `message` del backend porque
  no existe.
- Estados HTTP:
  - 400: petición malformada.
  - 401: sin sesión / sesión expirada.
  - 403: autenticado sin permiso, CSRF/origen inválido.
  - 404: recurso inexistente.
  - 409: conflicto (duplicado, estado, job activo).
  - 412: precondition failed (revisión obsoleta, drift).
  - 413: cuerpo demasiado grande.
  - 422: validación de dominio/entrada.
  - 429: rate limit; cabecera `Retry-After`.
  - 502: error de Oxidized/Docker como upstream.
  - 503: dependencia no disponible o app iniciando.

### Paginación

Listados:

```json
{
  "items": [],
  "page": 1,
  "page_size": 25,
  "total": 0,
  "total_pages": 0
}
```

- `page` empieza en 1; `page_size` 1–100 (default 25).
- Ordenaciones y filtros se validan contra allowlists.

### Fechas

ISO-8601 UTC con sufijo `Z`. El frontend formatea con `Intl` en el idioma activo
y la zona horaria configurada o del navegador.

### Capacidades

La sesión devuelve una lista de capacidades para que la UI pueda ocultar
acciones. **El backend no confía en ella**: cada endpoint aplica RBAC.

| Capacidad | admin | operator | viewer |
|---|---:|---:|---:|
| `nodes.read` | ✅ | ✅ | ✅ |
| `nodes.write` | ✅ | ✅ | — |
| `backups.trigger` | ✅ | ✅ | — |
| `versions.read` | ✅ | ✅ | ✅ |
| `config.read` | ✅ | — | — |
| `config.write` | ✅ | — | — |
| `config.apply` | ✅ | — | — |
| `groups.write` | ✅ | ✅ | — |
| `logs.read` | ✅ | ✅ | — |
| `jobs.read` | ✅ | ✅ | — |
| `users.manage` | ✅ | — | — |
| `audit.read` | ✅ | — | — |
| `system.manage` | ✅ | — | — |
| `me.write` | ✅ | ✅ | ✅ |

## 1. Meta, salud y setup

| Método | Ruta | Roles | Descripción |
|---|---|---|---|
| GET | `/meta` | público | `{setup_required, available_languages, default_language, app_version, timezone}`. `timezone` puede ser `null`. |
| GET | `/health` | público | `200` si DB y config writable; `503` si no. No consulta Oxidized. |
| POST | `/setup` | público solo si no hay usuarios | Crea el primer admin y la sesión. |
| POST | `/auth/login` | público | Login. |
| POST | `/auth/logout` | autenticado + CSRF | Revoca la sesión. |
| GET | `/auth/session` | autenticado | Usuario + CSRF token. |
| PATCH | `/me` | autenticado + CSRF | Idioma/tema propios. |
| POST | `/me/password` | autenticado + CSRF | Cambio de contraseña propio. |

### POST /setup

```json
{
  "username": "admin",
  "password": "contraseña-larga",
  "language": "es",
  "theme": "system"
}
```

- Solo si `setup_required=true`; si ya existe admin: `403 setup.completed`.
- Crea el admin con rol `admin`, valida la contraseña y devuelve sesión + CSRF.
- Rate limit de setup.
- Errores: `setup.completed`, `setup.invalid_language`, `validation.failed`.

### POST /auth/login

```json
{ "username": "admin", "password": "..." }
```

Respuesta:

```json
{
  "user": {
    "id": 1,
    "username": "admin",
    "role": "admin",
    "language": "es",
    "theme": "system"
  },
  "csrf_token": "opaque",
  "capabilities": ["config.apply", "config.read"]
}
```

- Error genérico `auth.invalid_credentials` para usuario inexistente, contraseña
  incorrecta o cuenta desactivada (no se revela cuál).
- Rate limit: `429 auth.too_many_attempts`.
- La respuesta nunca incluye hash, sesiones ni último login ajeno.

### PATCH /me

```json
{ "language": "en", "theme": "dark" }
```

- `language` debe estar entre los idiomas disponibles, que el backend descubre
  de los ficheros de traducción.
- `theme`: `light|dark|system`.

### POST /me/password

```json
{ "current_password": "...", "new_password": "..." }
```

- Verifica la actual; no permite igual a la anterior.
- Rota la sesión actual y revoca las demás.
- Errores: `auth.invalid_current_password`, `auth.weak_password`.

## 2. Usuarios (solo admin)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/users?search=&role=&is_active=&page=&page_size=` | Listado paginado. |
| POST | `/users` | Crea usuario. |
| GET | `/users/{id}` | Detalle sin hash. |
| PATCH | `/users/{id}` | Rol, estado, idioma. |
| POST | `/users/{id}/password` | Reset por admin. Revoca sesiones del usuario. |
| DELETE | `/users/{id}` | Borra si no es el último admin ni uno mismo. |

Crear:

```json
{
  "username": "operador1",
  "password": "...",
  "role": "operator",
  "language": "es"
}
```

- `role`: `admin|operator|viewer`.
- Validación de última cuenta admin y auto-borrado.
- La API nunca devuelve `password_hash`; los errores de login no enumeran
  usuarios.
- Errores: `user.duplicate_username`, `user.not_found`, `user.last_admin`,
  `user.self_delete`, `auth.weak_password`.

## 3. Nodos

| Método | Ruta | Roles | Descripción |
|---|---|---|---|
| GET | `/nodes?search=&group=&model=&status=&sort=&order=&page=&page_size=` | todos | Listado paginado. |
| GET | `/nodes/{id}` | todos | Detalle; secretos siempre excluidos. |
| POST | `/nodes` | admin/operator | Crea; recarga Oxidized. |
| PATCH | `/nodes/{id}` | admin/operator | Edita; recarga Oxidized. |
| DELETE | `/nodes/{id}` | admin/operator | Borra; recarga Oxidized. |
| POST | `/nodes/bulk` | admin/operator | Acciones en lote. |
| POST | `/nodes/import` | admin/operator | Importa CSV. |
| GET | `/nodes/export.csv` | admin/operator | Exporta CSV sin secretos. |
| POST | `/nodes/{id}/backup` | admin/operator | Encola backup; devuelve job. |
| GET | `/nodes/{id}/status` | todos | Estado actual y última observación. |

### Serialización de nodo

Para admin/operator:

```json
{
  "id": 42,
  "name": "core-sw-01",
  "address": "10.20.0.11",
  "model": "ios",
  "group_name": "core",
  "input": "ssh",
  "port": 22,
  "username": "oxidized",
  "has_password": true,
  "has_enable": true,
  "vars": { "remove_secret": true, "ssh_port": "22" },
  "output": null,
  "prompt": null,
  "timeout_seconds": null,
  "status": "ok",
  "last_status_raw": "success",
  "last_backup_at": "2026-10-21T16:00:00Z",
  "last_attempt_at": "2026-10-21T16:00:00Z",
  "updated_at": "2026-10-21T15:00:00Z",
  "warnings": []
}
```

Para viewer se omiten `username`, `vars`, `has_password` y `has_enable`. Se
mantienen nombre, IP, modelo, grupo, input, puerto, estado y fechas. Las
configs/diffs sí se permiten porque el rol viewer tiene lectura de backups (y
las configs pueden contener secretos: es una decisión explícita del enunciado).

- `status` de UI: `ok | failed | pending | never`.
- `last_status_raw` solo si se conoce: `success | no_connection | fail | timelimit
  | unknown`.
- `warnings`: códigos como `node.model_not_in_catalog`,
  `node.port_ignored_for_input`, `oxidized.reload_failed`.

### POST/PATCH nodo

```json
{
  "name": "core-sw-01",
  "address": "10.20.0.11",
  "model": "ios",
  "group_name": "core",
  "input": "ssh",
  "port": 22,
  "username": "oxidized",
  "password": "secreto",
  "enable": "secreto-enable",
  "vars": { "remove_secret": true },
  "output": null,
  "prompt": null,
  "timeout_seconds": null
}
```

Actualización de secretos:

- `password`/`enable` omitidos → se conservan.
- Valor string → se reemplaza.
- `clear_password: true` / `clear_enable: true` → se borra.
- La API no devuelve el valor anterior en ningún caso.

Reglas:

- Nombre único case-insensitive (`node.duplicate_name`).
- Validación de IP/host, modelo, grupo aplicado, input, puerto y vars.
- `vars.enable` está reservado; usar el campo `enable`.
- La respuesta incluye `reload_status` (`ok|failed|recovered|skipped`) y
  `warnings`. El nodo se guarda aunque el reload falle: no se produce un falso
  error de guardado. Si Oxidized estaba caído por 0 nodos, la UI intenta la
  recuperación automática y devuelve `recovered`.
- No se requiere reinicio; solo reload (o recuperación automática si no había
  ningún nodo).

### Acciones en lote

```json
{
  "action": "backup",
  "ids": [1, 2, 3],
  "group_name": null
}
```

Acciones:

- `backup`: crea un job `backup_all` limitado a los IDs. Viewer/operator no
  pueden saltarse el rate limit por lotes; se limita a 1000 IDs.
- `change_group`: requiere `group_name` (o null); actualiza los nodos y hace un
  único reload.
- `delete`: borra los nodos no bloqueados; devuelve conteos y errores por nodo.

Respuesta de cambio/borrado:

```json
{
  "updated": 3,
  "deleted": 0,
  "failed": [{ "id": 9, "code": "node.group_not_found", "params": { "group": "x" } }],
  "reload_status": "ok"
}
```

Para `backup`, `202` con `{ "job_id": 17 }`.

### Import / export CSV

Import:

```http
POST /nodes/import
Content-Type: multipart/form-data
file=<csv>
mode=skip_existing|update_existing
dry_run=true|false
```

- Cabeceras: `name,address,model,group,input,port,username,password,enable,vars`.
- `password`/`enable` vacíos preservan los existentes en `update_existing`.
- `vars` es JSON serializado en una celda.
- Límites: 5 MB, 25 000 filas, 500 errores reportados.
- `dry_run` devuelve el mismo resumen sin escribir.
- Los errores incluyen fila, columna y código; nunca se muestra la contraseña.
- La importación es transaccional por lotes y hace un único reload al final.

Export:

- Mismas columnas, `password` y `enable` siempre vacíos.
- Codificación UTF-8, BOM opcional no; `Content-Disposition: attachment`.
- Neutralización de fórmulas CSV (`=`, `+`, `-`, `@`) para evitar CSV injection.

### Backup y estado

- `POST /nodes/{id}/backup` → `202 {job_id}`.
  - Si `next_adds_job=false`: la UI devuelve warning
    `oxidized.next_adds_job_disabled` en el job.
- `GET /nodes/{id}/status`:

```json
{
  "node_id": 42,
  "status": "failed",
  "last_status_raw": "no_connection",
  "last_started_at": "...",
  "last_finished_at": "...",
  "last_success_at": "...",
  "last_failure_at": "...",
  "observed_at": "...",
  "active_job_id": null
}
```

- Si Oxidized no está disponible, se devuelve la caché con
  `stale: true` y un warning; no se inventa un estado.

## 4. Versiones, configs y diff

| Método | Ruta | Roles | Descripción |
|---|---|---|---|
| GET | `/nodes/{id}/config` | todos | Config actual del nodo (texto). |
| GET | `/nodes/{id}/versions` | todos | Lista de versiones. |
| GET | `/nodes/{id}/versions/{oid}` | todos | Contenido de una versión. |
| GET | `/nodes/{id}/diff?from_oid=&to_oid=` | todos | Diff calculado en backend. |
| GET | `/nodes/{id}/download?oid=` | todos | Descarga la config o versión. |
| POST | `/search/configs` | todos | Búsqueda en configs. |

- El `group` que se envía a oxidized-web para versiones, config actual y diff es
  el **grupo efectivo** observado en `/nodes.json`, no necesariamente el
  `group_name` de la UI: la configuración puede tener `group_map`. El backend
  resuelve el nodo por nombre y usa el grupo vivo. Si Oxidized no está
  disponible, estas rutas devuelven `502 oxidized.unavailable` (no hay forma
  segura de adivinar el grupo efectivo). El grupo implícito `default` se omite:
  oxidized-web lo devuelve en `/nodes.json`, pero `/node/fetch` y
  `/node/version` lo interpretan como un grupo real inexistente y responderían
  `node not found` o una lista vacía.
- `GET /nodes/{id}/versions`:
  - `200` con `{ available: true, versions: [{oid,time,author,message}] }` cuando
    el output soporta versiones;
  - `200` con `{ available: false, reason: "output_unsupported" }` para
    file/http;
  - `502 oxidized.upstream_error` si la API falla de verdad.
- `GET /nodes/{id}/versions/{oid}` devuelve texto. `oid` se valida con
  `^[A-Za-z0-9._-]{4,128}$`; no se aceptan rutas.
- `GET /nodes/{id}/diff` devuelve:

```json
{
  "node_id": 42,
  "from": { "oid": "...", "time": "..." },
  "to": { "oid": "...", "time": "..." },
  "unified": "--- a/...\n+++ b/...\n...",
  "side_by_side": [
    { "left": { "line": 1, "text": "..." }, "right": { "line": 1, "text": "..." }, "type": "same" },
    { "left": { "line": 2, "text": "..." }, "right": null, "type": "removed" }
  ],
  "stats": { "additions": 3, "deletions": 1 }
}
```

- El endpoint de diff HTML de oxidized-web no se usa (solo HTML).
- Límite de contenido: 5 MiB por versión; si se supera,
  `config.content_too_large`.
- Descarga con `Content-Disposition: attachment` y nombre seguro.
- `POST /search/configs`:

```json
{ "query": "interface Gi0/1" }
```

  - Reenvía a `POST /nodes/conf_search` de oxidized-web con el campo
    `search_in_conf_textbox`.
  - Límite 200 caracteres. El patrón se interpreta como regex por Oxidized;
    la UI muestra una nota y el backend limita el tiempo de la llamada.
  - Respuesta: `[{ "node_id": 42, "name": "...", "full_name": "...", "group_name": "..." }]`.

## 5. Grupos

Los grupos son la sección `groups` del JSON de configuración. Los cambios de
operator crean un borrador; solo admin aplica.

| Método | Ruta | Roles | Descripción |
|---|---|---|---|
| GET | `/groups` | admin/operator | Lista de grupos aplicados y borradores. |
| GET | `/groups/{name}` | admin/operator | Detalle con secretos enmascarados. |
| POST | `/groups` | admin/operator | Crea grupo en un nuevo borrador. |
| PATCH | `/groups/{name}` | admin/operator | Edita credenciales/vars/models. |
| DELETE | `/groups/{name}` | admin/operator | Borra si no está en uso. |

Respuesta de lista:

```json
{
  "groups": [
    {
      "name": "core",
      "node_count": 12,
      "username": "oxidized",
      "has_password": true,
      "has_enable": true,
      "state": "applied",
      "draft": false
    }
  ],
  "draft_revision_id": 17,
  "requires_admin_apply": true
}
```

Detalle (secretos enmascarados):

```json
{
  "name": "core",
  "username": "oxidized",
  "has_password": true,
  "has_enable": true,
  "vars": { "ssh_no_keepalive": true },
  "models": {
    "ios": { "username": "netops", "has_password": true, "vars": {} }
  },
  "state": "draft",
  "requires_admin_apply": true
}
```

- `enable` se extrae de `vars.enable` para mostrarlo como `has_enable`; al
  guardarlo se serializa de nuevo en `vars`.
- `password`/`enable` se actualizan con semántica de reemplazo, igual que nodos.
- `GET /groups` solo devuelve grupos de la revisión aplicada, más una marca de
  cambios pendientes; los grupos que solo existen en borrador no se pueden
  asignar a nodos hasta aplicar.
- Crear/editar/borrar devuelve el `revision_id` del nuevo borrador y
  `requires_admin_apply=true`. Usa `expected_revision_id` para no pisar cambios
  de otro admin/operator.
- `DELETE` falla con `group.in_use` si hay nodos con ese grupo.
- Renombrar no está soportado (nombre inmutable).
- Los secretos de grupo nunca se devuelven en crudo por esta API; solo al
  editor de configuración global (admin).
- `vars` enviado en un PATCH sustituye las variables visibles del grupo; la
  clave reservada `enable` se conserva salvo que se envíe `enable` o
  `clear_enable`.
- Para eliminar un override de modelo: `{ "models": { "ios": { "remove": true } } }`.
- El detalle de nodo de un viewer incluye `input`, `port`, `output`, `prompt` y
  `timeout_seconds`, pero no `username`, `vars` ni metadatos de credenciales.

## 6. Configuración de Oxidized

Todas las rutas son solo admin.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/config` | Estado de la config y revisiones activas. |
| GET | `/config/catalog` | Catálogo de campos, modelos, inputs, vars y enums. |
| POST | `/config/validate` | Valida JSON/YAML sin guardar. |
| POST | `/config/draft` | Crea una revisión borrador. |
| GET | `/config/revisions?page=&page_size=` | Historial. |
| GET | `/config/revisions/{id}` | Detalle de una revisión. |
| GET | `/config/revisions/{id}/diff?against=` | Diff entre revisiones. |
| POST | `/config/revisions/{id}/restore` | Crea borrador desde una versión. |
| POST | `/config/apply` | Aplica y reinicia (job asíncrono). |

### GET /config

```json
{
  "applied": {
    "id": 12,
    "created_at": "...",
    "applied_at": "...",
    "status": "applied"
  },
  "draft": {
    "id": 13,
    "created_at": "...",
    "origin": "form",
    "note": null
  },
  "config": {},
  "editable_yaml": "interval: 3600\n# ...",
  "effective_yaml_preview": "# source token enmascarado\n...",
  "managed_keys": [
    "source.default",
    "source.http.url",
    "source.http.headers.X-Oxidized-Source-Token",
    "source.http.map",
    "extensions.oxidized-web.load",
    "extensions.oxidized-web.listen",
    "extensions.oxidized-web.port",
    "extensions.oxidized-web.url_prefix"
  ],
  "drift": {
    "detected": false,
    "expected_sha256": "...",
    "observed_sha256": "..."
  },
  "requires_apply": true
}
```

- `config` es el JSON canónico editable (el bloque source activo gestionado no
  se incluye). Los secretos globales van desencriptados porque el usuario es
  admin y esta es la pantalla de edición.
- `editable_yaml` es la representación editable sin bloques gestionados. El
  editor avanzado trabaja sobre esto.
- `effective_yaml_preview` es el YAML completo que se aplicará, con el token del
  source enmascarado. Es lo que se usa para el diff de vista previa.
- `drift.detected=true` si el fichero del volumen no coincide con el hash de la
  revisión aplicada. La UI muestra una banda de advertencia y permite capturar
  una instantánea antes de aplicar.

### POST /config/validate

```json
{
  "config": {},
  "yaml": null,
  "expected_revision_id": 13
}
```

- Se envía `config` o `yaml`, nunca ambos (o `yaml` con `config` nulo).
- Devuelve config normalizada, YAML editable, preview efectiva y diff frente a
  la aplicada, o errores `validation.failed`/`config.invalid_yaml`.
- No escribe ni crea revisión.

### POST /config/draft

```json
{
  "config": {},
  "yaml": null,
  "expected_revision_id": 13,
  "note": "Ajuste de threads",
  "origin": "form"
}
```

- `origin`: `form` o `yaml`. `restore` y `groups` usan endpoints propios.
- Crea una revisión `draft` cifrada; descarta el borrador anterior.
- Devuelve `revision_id`, `diff` y `requires_apply=true`.
- `412 config.stale_draft` si cambió el borrador.
- `409 config.no_changes` si el contenido es idéntico al aplicado (no crea
  revisión).
- `422 config.validation_failed` con campos.
- Los cambios en claves gestionadas: `config.managed_key_modified`.
- `origin=yaml` no puede incluir bloques gestionados.

### POST /config/apply

```json
{ "revision_id": 13, "restart": true }
```

- Solo se puede aplicar el borrador activo; `409 config.not_draft`.
- `restart` debe ser `true`: Oxidized no ofrece recarga de configuración y
  aplicar sin reiniciar dejaría el fichero y el proceso divergentes. Si se envía
  `false`: `422 config.restart_required`.
- Crea un job `config_apply` y responde `202 {job_id}`. La UI sigue el job.
- El job:
  1. valida de nuevo y comprueba drift/locks;
  2. captura el fichero anterior si hace falta;
  3. escribe de forma atómica;
  4. marca la revisión aplicada;
  5. reinicia Oxidized vía Docker;
  6. registra auditoría y finaliza.
- En esta versión **no hay health-check bloqueante ni rollback automático tras
  el reinicio**. Si Oxidized no vuelve a estar disponible, la UI lo detecta en
  `/status` y el operador puede restaurar una revisión anterior desde el
  historial. Se documenta así para no prometer una recuperación que no existe.
- Si el fichero se escribe pero el reinicio falla, la revisión queda `applied`
  (el fichero está en disco) y el job acaba `failed` con
  `oxidized.restart_failed`; la UI permite reintentar el reinicio. No se oculta
  el estado real.
- `409 config.apply_busy` si ya hay un apply en curso.
- Aplicar una config que deje nodos con grupos inexistentes devuelve
  `config.group_in_use` (validación previa).

### Revisiones

- `GET /config/revisions` paginado, sin YAML ni secretos.
- `GET /config/revisions/{id}` devuelve metadatos, config desencriptada, YAML
  editable y preview con token enmascarado. Solo admin.
- `GET /config/revisions/{id}/diff?against=<id>`: diff `from=against`,
  `to=id`; si se omite `against`, contra la revisión aplicada.
- `POST /config/revisions/{id}/restore` crea un borrador nuevo con el contenido
  de la revisión indicada. No aplica. Devuelve `revision_id` nuevo.
- El historial no se borra desde la API.

## 7. Estado, jobs y logs

| Método | Ruta | Roles | Descripción |
|---|---|---|---|
| GET | `/status` | todos | Estado agregado del dashboard. |
| GET | `/jobs?status=&kind=&page=&page_size=` | admin/operator | Lista de jobs de la UI. |
| GET | `/jobs/{id}` | admin/operator | Detalle de job. |
| POST | `/backups/all` | admin/operator | Encola backup de todos. |
| POST | `/oxidized/reload` | admin/operator | Recarga nodos manualmente. |
| POST | `/oxidized/restart` | admin | Reinicia Oxidized (job). |
| GET | `/logs?tail=&since=&level=&q=` | admin/operator | Snapshot de logs. |
| GET | `/logs/stream?level=&q=&tail=` | admin/operator | SSE de logs en vivo. |
| GET | `/logs/download?since=&until=&level=&q=` | admin/operator | Descarga de logs. |
| GET | `/search?q=` | todos | Búsqueda global de nodos/grupos. |

### GET /status

```json
{
  "oxidized": {
    "state": "online|offline|degraded|starting",
    "api_online": true,
    "container_state": "running",
    "last_seen_at": "...",
    "version": null
  },
  "nodes": {
    "total": 42,
    "ok": 35,
    "failed": 3,
    "pending": 1,
    "never": 3
  },
  "backups": {
    "last_success_at": "...",
    "last_failure_at": "...",
    "active_jobs": 1
  },
  "activity": [
    { "date": "2026-10-20", "success": 40, "failed": 2 }
  ],
  "warnings": ["oxidized.next_adds_job_disabled"]
}
```

- `activity` se agrega de `backup_runs` (observación).
- `state=degraded` si el contenedor está running pero la API no responde.
- `starting` durante un reinicio.

### Jobs

```json
{
  "id": 17,
  "kind": "backup_all",
  "status": "running",
  "progress": { "done": 12, "total": 42 },
  "node_id": null,
  "created_by": { "id": 1, "username": "admin" },
  "created_at": "...",
  "started_at": "...",
  "finished_at": null,
  "error": null,
  "result": null
}
```

- `kind`: `backup_node`, `backup_all`, `oxidized_reload`, `oxidized_restart`,
  `config_apply`.
- `status`: `queued|running|succeeded|failed|cancelled`.
- `error` = `{code, params}`; nunca stack traces.
- `result` incluye conteos (`requested`, `queued`, `failed`), no credenciales.
- Al reiniciar la UI, jobs no terminados se marcan `failed` con
  `job.interrupted`.
- `POST /backups/all` responde `202 {job_id}`. El job es de encolado; el estado
  final de cada backup se sigue por `/nodes` y `backup_runs`.

### Logs

Snapshot:

```json
{
  "lines": [
    {
      "seq": 1234,
      "timestamp": "2026-10-21T16:00:00.123Z",
      "stream": "stdout",
      "level": "info",
      "text": "2026-10-21 ... I [pid:tid] ..."
    }
  ],
  "truncated": false
}
```

- `level`: `trace|debug|info|warn|error|fatal|unknown`.
- `text` es la línea original, sin traducir y sin eliminar contenido.
- `tail`: 1–5000, default de sistema; `q` ≤ 200; `since`: ISO o duración
  aceptada por Docker.
- El endpoint usa la API de Docker; si falla devuelve
  `502 docker.logs_unavailable` con params no sensibles.
- SSE:
  - `Content-Type: text/event-stream`.
  - Eventos: `ready` (con `{follow:true}`), `log`, `error`, `ping` cada 15 s.
  - `id` incremental por conexión; no se garantiza replay completo en
    reconexión, pero se reabre con `tail`.
  - El frontend usa `EventSource` con cookies; no hay tokens en la URL.
- Descarga:
  - Texto plano, límite de 50 MB / 100 000 líneas.
  - `Content-Disposition: attachment; filename="oxidized-logs-YYYYMMDD-HHMMSS.txt"`.
- Viewer recibe 403 (`auth.forbidden`).

### Búsqueda global

`GET /search?q=...` devuelve hasta 10 nodos y 10 grupos accesibles para el
usuario, para el command palette/topbar. No busca dentro de configs (eso es
`POST /search/configs`). Viewer recibe resultados sin credenciales.

## 8. Auditoría

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/audit?actor=&action=&target_type=&from=&to=&page=&page_size=` | admin | Eventos paginados. |

Respuesta:

```json
{
  "items": [
    {
      "id": 991,
      "actor": { "user_id": 1, "username": "admin", "role": "admin" },
      "action_code": "node.updated",
      "action_params": { "name": "core-sw-01", "changed_fields": ["group_name"] },
      "target_type": "node",
      "target_id": "42",
      "ip": "192.0.2.10",
      "created_at": "..."
    }
  ],
  "page": 1,
  "page_size": 25,
  "total": 1,
  "total_pages": 1
}
```

- `action_code` y `action_params` los traduce el frontend.
- Sin secretos, YAML, diffs ni cuerpos.
- Filtros por rango de fechas con límite máximo de 366 días.
- Orden descendente por defecto.

## 9. Ajustes del sistema

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/system/settings` | admin | Ajustes efectivos y valores de entorno. |
| PATCH | `/system/settings` | admin | Actualiza ajustes de UI/conexión. |
| POST | `/system/test` | admin | Prueba conexión con Oxidized o Docker. |

Ajustes editables:

```json
{
  "oxidized_api_url": "http://oxidized:8888",
  "oxidized_container_name": "oxidized",
  "docker_proxy_url": "http://docker-socket-proxy:2375",
  "timezone": "Europe/Madrid",
  "activity_retention_days": 90,
  "poll_interval_seconds": 30,
  "log_tail_default": 500,
  "config_backup_keep": 50
}
```

- `timezone=null` significa zona del navegador.
- Validación: URLs http(s) internas, nombre de contenedor seguro, timezone IANA.
- Los valores sensibles (tokens, claves) no se editan aquí.
- `POST /system/test` con `{target:"oxidized"}` o `{target:"docker"}`.
  Respuesta `{ok:true, latency_ms:12}` o error de dominio.
- Cambiar la URL/API de Oxidized no cambia el source HTTP (es interno); se
  valida con el test.

## 10. Endpoint interno del source HTTP

No forma parte de la API de administración. No se documenta en OpenAPI público.

```http
GET /api/internal/source/nodes
GET /api/internal/source/nodes/{node_want}
X-Oxidized-Source-Token: <token>
Cache-Control: no-store
```

- Respuesta 200: array JSON de nodos con credenciales descifradas.
- 401 `internal_source.unauthorized` si el token falta o no coincide (comparación
  en tiempo constante).
- Solo `GET`. Nunca se registra el cuerpo ni la cabecera.
- No requiere cookie ni CSRF.
- Los nodos devueltos incluyen `name`, `ip`, `model`, `group`, `input`,
  `username`, `password`, `vars` (con `enable` incluido si existe) y los campos
  avanzados soportados.
- No se expone en la UI ni en la documentación pública.
- Si el token no está configurado, la aplicación falla al arrancar (no arranca
  con un source sin autenticación).

## 11. Catálogo de códigos de error inicial

El catálogo definitivo vive en `app/data/error_codes.json` y se comparte con el
test de i18n. Códigos previstos:

### Autenticación / setup / usuarios

`auth.invalid_credentials`, `auth.account_disabled`, `auth.session_expired`,
`auth.csrf_failed`, `auth.origin_rejected`, `auth.too_many_attempts`,
`auth.invalid_current_password`, `auth.weak_password`, `auth.forbidden`,
`auth.unauthenticated`, `auth.last_admin`, `setup.completed`,
`setup.invalid_language`, `setup.rate_limited`, `user.not_found`,
`user.duplicate_username`, `user.last_admin`, `user.self_delete`,
`user.password_reset_failed`.

### Nodos / grupos

`node.not_found`, `node.duplicate_name`, `node.invalid_name`,
`node.invalid_address`, `node.invalid_model`, `node.invalid_input`,
`node.invalid_port`, `node.group_not_found`, `node.group_not_applied`,
`node.invalid_vars`, `node.reserved_var`, `node.credentials_read_only`,
`node.import_invalid`, `node.import_too_large`, `node.export_failed`,
`node.bulk_too_large`, `node.backup_failed`, `node.model_not_in_catalog`,
`node.port_ignored_for_input`, `group.not_found`, `group.duplicate_name`,
`group.in_use`, `group.invalid_name`, `group.name_immutable`,
`group.password_change_failed`.

### Configuración

`config.invalid_yaml`, `config.validation_failed`, `config.managed_key_modified`,
`config.restart_required`, `config.stale_draft`, `config.no_changes`,
`config.not_draft`, `config.apply_busy`, `config.apply_failed`,
`config.drift_detected`, `config.revision_not_found`, `config.group_in_use`,
`config.content_too_large`, `config.secret_token_exposed`,
`config.unsupported_source`, `config.unsupported_extension`.

### Oxidized / Docker / jobs / logs

`oxidized.unavailable`, `oxidized.timeout`, `oxidized.bad_response`,
`oxidized.reload_failed`, `oxidized.restart_failed`,
`oxidized.next_adds_job_disabled`, `oxidized.output_unsupported`,
`oxidized.auto_recovery_failed`, `docker.unavailable`,
`docker.container_not_found`, `docker.logs_unavailable`,
`docker.restart_failed`, `job.not_found`, `job.interrupted`,
`job.already_running`, `logs.stream_failed`, `logs.too_large`,
`search.query_invalid`, `search.upstream_failed`, `internal_source.unauthorized`.

### Sistema / validación genérica

`system.invalid_setting`, `system.connection_failed`, `system.unavailable`,
`validation.failed`, `validation.required`, `validation.min`,
`validation.max`, `validation.invalid_type`, `validation.invalid_choice`,
`validation.invalid_format`, `validation.duplicate`, `validation.too_long`,
`app.rate_limited`, `app.payload_too_large`, `app.not_found`,
`app.internal_error`.

Cada uno de estos códigos debe tener clave en `errors.<code>` de es/en y una
prueba que lo compruebe.

## 12. Reglas transversales del backend

- No se aceptan `GET` con efectos secundarios salvo los endpoints de Oxidized
  que se invocan internamente; la API pública usa POST para acciones.
- No se reenvían cuerpos de error de Oxidized al cliente. Se mapean a códigos.
- Todos los IDs de recursos se validan como enteros; los nombres, contra su
  patrón y longitud.
- La autorización se comprueba antes de resolver el recurso para no filtrar
  existencia en endpoints admin.
- Los listados aplican un máximo de 100 elementos.
- Los filtros de búsqueda tienen longitud limitada; los `sort` se validan con
  una allowlist.
- Las respuestas no incluyen secretos, rutas internas del host, variables de
  entorno ni trazas.
- Cualquier acción destructiva (borrar usuario/nodo/grupo, aplicar config,
  `clean_obsolete_nodes`, backup masivo) requiere CSRF y rol, y se audita.
- La API desactiva `/api/docs` y `/api/openapi.json` en producción salvo
  `APP_ENV=development`.
