# Integración con Oxidized

Este documento fija el contrato entre Oxidized UI y Oxidized. Todo lo marcado
como **verificado** se comprobó en la documentación oficial o en el código fuente
de la versión fijada. Lo que no está documentado se señala explícitamente.

## Versiones de referencia

| Componente | Versión / imagen | Motivo |
|---|---|---|
| Oxidized | `oxidized/oxidized:0.37.0` | Versión estable usada para verificar rutas y comportamiento |
| oxidized-web | el empaquetado por la imagen 0.37.0 | API REST y UI interna |
| docker-socket-proxy | `tecnativa/docker-socket-proxy:v0.5.0` | Proxy del socket de Docker |

La imagen oficial de Oxidized está documentada como `oxidized/oxidized` (no
`ytti/oxidized`) en [docs/Docker.md](https://github.com/ytti/oxidized/blob/master/docs/Docker.md).
Se fija la etiqueta `0.37.0` en el `Dockerfile` y en la imagen publicada en lugar de
`latest` para que el contrato no cambie por una actualización silenciosa.

## Hechos verificados de la imagen oficial

- El directorio de configuración es **`/home/oxidized/.config/oxidized`**.
  El fichero principal se llama **`config`**. Es la ruta que monta el volumen
  compartido `oxidized_config`.
- Oxidized corre con **UID/GID 30000** (`oxidized:oxidized`) dentro de la imagen.
  El supervisor `runit` arranca como root, hace `chown -R` del directorio de
  configuración y ejecuta Oxidized con `gosu oxidized`. La UI también se ejecuta
  con UID/GID 30000 para poder escribir el fichero de configuración de forma
  atómica en el volumen compartido sin privilegios.
- La imagen no publica ningún puerto por sí sola (`EXPOSE 8888/tcp`), pero
  `oxidized-web` escucha en `127.0.0.1:8888` por defecto. En este despliegue se
  genera `extensions.oxidized-web.listen: 0.0.0.0` y el puerto **no se publica**
  al host.
- La configuración de `oxidized-web` se hace con `extensions.oxidized-web`
  (la clave antigua `rest` está deprecada y no se usa).
- La imagen incluye un servicio `auto-reload-config` que, si se define
  `CONFIG_RELOAD_INTERVAL`, llama periódicamente a `/reload?format=json`.
  **Ese endpoint recarga la lista de nodos, no el fichero de configuración**
  (comprobado en `extra/auto-reload-config.runit` y en `Core#reload`). No se
  usa ese servicio: la UI llama a `/reload` cuando corresponde.
- No existe un endpoint REST oficial para recargar la configuración desde
  disco, reiniciar Oxidized, consultar jobs internos, listar modelos o validar
  un YAML. El reinicio se hace con la API de Docker a través del proxy.

## API REST de oxidized-web usada por la UI

Rutas verificadas en el código de `oxidized-web`
([`webapp.rb`](https://github.com/ytti/oxidized-web/blob/master/lib/oxidized/web/webapp.rb))
y en la documentación de Oxidized. `oxidized-web` **no tiene autenticación
propia**; por eso solo es accesible desde la red Docker `backend` y nunca se
publica su puerto.

| Uso | Método y ruta | Parámetros / respuesta |
|---|---|---|
| Estado y listado de nodos | `GET /nodes.json` | Array de nodos. Cada nodo incluye `name`, `full_name`, `ip`, `group`, `model`, `last` (`start`, `end`, `status`, `time`), `vars`, `mtime`. `last` puede ser `null`. **`vars` puede contener credenciales**: la UI solo extrae los campos de estado y descarta `vars`; nunca los persiste ni los reenvía. |
| Filtrar por grupo | `GET /nodes/group/<group>.json` | `group` puede contener `/`; nuestro modelo restringe nombres de grupo por seguridad. |
| Filtrar por modelo | `GET /nodes/model/<model>.json` | — |
| Configuración actual de un nodo | `GET /node/fetch/<node>.json` o `GET /node/fetch/<group>/<node>.json` | Devuelve un array JSON de líneas cuando se usa `.json`. En caso de error devuelve texto dentro del JSON. |
| Forzar backup | `GET /node/next/<node>.json` | Mueve el nodo al principio de la cola. Devuelve `"ok"`. Con `next_adds_job: true` además incrementa los jobs para ejecutarlo cuanto antes. |
| Recargar nodos | `GET /reload.json` | Recarga la lista desde el source. Devuelve un string JSON. |
| Versiones de un nodo | `GET /node/version?format=json&node_full=<group/name>` | Array de `{oid, time, ...}` para outputs git/gitcrypt. Para output `file` devuelve una lista vacía. |
| Contenido de una versión | `GET /node/version/view?format=json&node=<name>&group=<group>&oid=<oid>&epoch=<unix>&num=<n>` | Array JSON de líneas. `epoch` y `num` se usan para la vista; el dato real se selecciona por `oid`. |
| Diff renderizado | `GET /node/version/diffs?...` | **Solo HTML**; no ofrece JSON estable. No se usa. |
| Buscar en configuraciones | `POST /nodes/conf_search.json` | Form field `search_in_conf_textbox`. Devuelve nodos que hacen match. |
| Estadísticas | `GET /nodes/stats.json` | Ruta existente pero sin documentación oficial ni contrato JSON estable. **No se usa como fuente de verdad.** |

### Decisiones derivadas

- **Diff lado a lado**: el endpoint oficial de diff no devuelve JSON. La UI pide
  el contenido de las dos versiones con `node/version/view` y calcula el diff en
  el backend con `difflib`. Así no se parsea HTML de oxidized-web y el resultado
  es estable. El endpoint HTML de diff no se proxya.
- **Estadísticas y actividad**: `nodes/stats.json` no se considera contrato
  público. La UI guarda observaciones de los estados de `/nodes.json` en
  `backup_runs`/`node_status_cache` y calcula el dashboard con esos datos.
- **Jobs**: Oxidized no expone su cola de trabajos. La pantalla de jobs muestra
  los trabajos lanzados por la UI (backups en lote, reloads, reinicios) y el
  estado observado de los nodos. No se presenta como una cola interna de
  Oxidized.
- **Modelos**: Oxidized no expone un endpoint de modelos. El selector usa un
  catálogo estático generado a partir de la versión fijada (`0.37.0`) y permite
  escribir un modelo personalizado.

## Los seis endpoints que hay que verificar en integración real

Los siguientes detalles se comprobaron leyendo el código, pero deben cubrirse
con un test de contrato contra un contenedor real antes de dar la integración
por cerrada:

1. La forma exacta del JSON de `/nodes.json` y de `last.status`.
2. Que `/node/fetch/...` con `.json` devuelva un array de líneas.
3. Que `/node/version?format=json` y `/node/version/view?...&format=json`
   devuelvan JSON (no HTML) para el output git.
4. Que `/node/next/<node>.json` funcione con nombres con puntos y que no haya
   ambigüedad entre grupos (la UI impone nombres de nodo únicos globalmente).
5. Que el source HTTP acepte el objeto `vars` mapeado (ver más abajo).
6. Que el formato de logs de SemanticLogger permita extraer el nivel sin alterar
   la línea original.

El test de contrato se ejecutará opcionalmente con el stack de `docker-compose`
y no será necesario para los tests unitarios. Si falla algún punto, la UI debe
mostrar un error de integración explícito, no ocultarlo.

## Contrato del source HTTP

La UI expone una ruta interna:

```http
GET http://oxidized-ui:8080/api/internal/source/nodes
X-Oxidized-Source-Token: <OXIDIZED_SOURCE_TOKEN>
Cache-Control: no-store
```

Responde un array JSON. Ejemplo:

```json
[
  {
    "name": "core-sw-01",
    "ip": "10.20.0.11",
    "model": "ios",
    "group": "core",
    "input": "ssh",
    "username": "oxidized",
    "password": "plaintext-only-inside-the-container",
    "vars": {
      "enable": "privileged-secret",
      "ssh_port": "2222",
      "remove_secret": true
    }
  }
]
```

- El token se compara en tiempo constante y nunca se registra en logs ni se
  devuelve por la API pública.
- La ruta admite el sufijo opcional `/<node_want>` que Oxidized añade cuando
  recarga un nodo concreto. En ese caso devuelve un array de un solo elemento.
- El endpoint se sirve en el mismo puerto que la UI, pero no está enlazado en el
  frontend ni figura en la navegación. La autorización real es el token; además
  el puerto expuesto es solo el de la UI y el token no se muestra en la API de
  administración.
- La configuración generada usa esta sección (la UI la inyecta y la marca como
  gestionada):

```yaml
source:
  default: http
  http:
    url: http://oxidized-ui:8080/api/internal/source/nodes
    read_timeout: 30
    headers:
      X-Oxidized-Source-Token: <token>
    map:
      name: name
      ip: ip
      model: model
      group: group
      input: input
      username: username
      password: password
      vars: vars
      output: output
      prompt: prompt
      timeout: timeout
    # Explícito para que transform_json no dependa del comportamiento de
    # Asetus cuando vars_map está ausente. Vacío = no sobrescribir
    # el objeto vars mapeado arriba.
    vars_map: {}
```

### Nota importante sobre `map: vars`

La documentación oficial de
[Sources.md](https://github.com/ytti/oxidized/blob/master/docs/Sources.md)
documenta `map` para los campos estándar y `vars_map` para variables sueltas,
pero **no documenta mapear un objeto `vars` completo**. El código de
`Oxidized::Source::JSONFile#transform_json` de 0.37.0 sí admite una clave
arbitraria en `map` y asigna el objeto resultante a `keys[:vars]` si no hay
`vars_map`; eso permite soportar variables por nodo arbitrarias sin regenerar la
configuración al añadir una variable nueva.

Esta decisión es deliberada y se marca como **dependencia de una capacidad no
documentada**, no como un parámetro inventado. Se fija la imagen 0.37.0 y se
añadirá un test de contrato. Si una versión futura deja de soportarlo, la
alternativa es generar un `vars_map` estático con el catálogo de variables
conocidas y limitar las variables libres por nodo; no se hará silenciosamente.

### Mapeo de campos de nodo

| Campo UI | Destino en el source | Notas |
|---|---|---|
| Nombre | `name` | Único globalmente. Debe ser un nombre de host seguro. |
| IP / host | `ip` | Si está vacío Oxidized resuelve el nombre. |
| Modelo | `model` | Catálogo estático de 0.37.0; se acepta un modelo personalizado. |
| Grupo | `group` | Vacío = grupo por defecto de Oxidized. Debe existir en la configuración aplicada. |
| Input | `input` | Lista separada por comas (p. ej. `ssh, telnet`), validada. |
| Puerto | `vars.ssh_port` y/o `vars.telnet_port` | Según los inputs efectivos. Oxidized no tiene un campo `port` genérico: SSH/SCP leen `ssh_port`, Telnet lee `telnet_port`. |
| Usuario | `username` | Override del nodo. |
| Contraseña | `password` | Se descifra solo al construir la respuesta del source. |
| Enable | `vars.enable` | Se descifra solo al construir la respuesta del source. |
| Vars | `vars` | Objeto libre; el editor de nodo ofrece catálogo y permite claves personalizadas. |

En el JSON de la UI, la contraseña y el enable **nunca** aparecen. La API expone
`has_password` / `has_enable`; para modificarlos hay que enviar un valor nuevo
(sección de seguridad del modelo de datos).

`group_map` se aplica dentro de Oxidized después de leer el source, por lo que el
grupo efectivo de un nodo puede diferir del `group_name` guardado en la UI. Para
llamar a `/node/fetch`, `/node/version` y `/node/version/view`, el backend usa el
campo `group` que devuelve `/nodes.json` (grupo efectivo), nunca el grupo crudo
de SQLite. Los nodos se identifican por nombre único, que no cambia con el map.
Si `group_map` apunta a un grupo sin credenciales, la UI lo muestra como warning
de configuración; no reescribe el map.

## Ciclo de vida de los nodos

1. La UI valida y guarda el nodo en SQLite dentro de una transacción.
2. Inmediatamente hace `GET {OXIDIZED_API_URL}/reload.json` con timeout corto.
3. Si Oxidized está online, ya consume la nueva lista; no se reinicia.
4. Si Oxidized está caído por no tener ningún nodo, la UI puede hacer una
   recuperación automática: reinicia el contenedor (vía Docker API) para que
   arranque con el primer nodo. Esta recuperación no se ofrece como acción de
   rol: es una reparación del sistema y se audita como
   `oxidized.auto_recovered`.
5. Si el reload falla, el nodo queda guardado y la UI muestra un aviso
   `oxidized.reload_failed`; el siguiente cambio o una acción manual de reload
   puede recuperar el estado. Nunca se revierte el cambio de nodo de forma
   silenciosa.

## Backups forzados

- Nodo individual: `GET /node/next/<name>.json`.
- Todos: la UI recorre todos los nodos y llama al mismo endpoint para cada uno,
  registrando un job de tipo `backup_all` y su progreso. Las llamadas se hacen
  con concurrencia limitada y se reportan los fallos parciales.
- Oxidized solo ejecutará el backup de inmediato si `next_adds_job: true`. La
  configuración inicial que genera la UI lo activa. Si un administrador lo
  desactiva, la UI muestra `oxidized.next_adds_job_disabled` y explica que el
  nodo se ha movido al principio de la cola pero esperará a un worker.
- `next` no acepta grupo. Por eso la UI exige nombres de nodo únicos
  globalmente y no permite `/` en el nombre.

## Fichero de configuración y escritura atómica

La UI y Oxidized comparten el volumen `oxidized_config`:

```text
UI:       /oxidized-config/config
Oxidized: /home/oxidized/.config/oxidized/config
```

Generación y aplicación:

1. La configuración editable vive en SQLite como JSON estructurado
   (revisiones inmutables y cifradas).
2. Al aplicar, el backend construye el YAML efectivo con
   `ruamel.yaml`: configuración editable + bloques gestionados (source HTTP y
   `extensions.oxidized-web`).
3. Se valida el YAML y los invariantes de integración.
4. Se guarda una copia del fichero anterior en la base de datos y en
   `/oxidized-config/.ui-backups/` (cifrada en BD, con permisos restrictivos en
   disco).
5. Se escribe un temporal en el **mismo directorio**, se hace `fsync`, y se
   sustituye el fichero con `os.replace` (atómico en el mismo filesystem).
6. Se actualiza la revisión aplicada y se reinicia Oxidized si el usuario lo
   pidió, con la API de Docker.
7. Como Oxidized no tiene endpoint de recarga de configuración, el cambio de
   configuración **siempre** se aplica con reinicio. La UI separa explícitamente
   «Guardar» (solo borrador en BD) de «Guardar y aplicar (reiniciar Oxidized)».

La copia del fichero anterior permite rollback incluso si el fichero fue editado
manualmente fuera de la UI. La UI detecta drift comparando el SHA-256 del fichero
con el de la revisión activa y muestra un aviso; no sobrescribe un fichero
desconocido sin dejar una copia.

## Bloques gestionados por la UI

Para que la UI siga funcionando, ciertas claves no se pueden romper desde el
editor YAML:

- `source.default: http`.
- La URL interna, cabecera del token y `map` del source HTTP.
- `extensions.oxidized-web.load: true`, su `listen`, `port` y `url_prefix`
  (la UI los necesita para hablar con la API).

El formulario de Source permite editar las opciones no gestionadas del bloque
`source.http` (por ejemplo `read_timeout`). Otras fuentes pueden existir en el
YAML avanzado, pero no se pueden activar sin romper la integración; el backend
rechaza el cambio de `source.default` con `config.managed_key_modified`. Esta es
una restricción consciente para garantizar que la base de datos de la UI sea la
fuente de verdad de los nodos.

Del mismo modo, `extensions.oxidized-web` se muestra como configuración
gestionada y se permiten `hide_node_vars` y `vhosts` solo si no bloquean al
cliente interno. Si se introducen cambios incompatibles, la aplicación falla en
la validación antes de escribir.

## Logs y estado

- No hay endpoint REST oficial de logs ni de jobs.
- Los logs se leen del contenedor de Oxidized con la API de Docker:
  `GET /containers/<name>/logs?stdout=1&stderr=1&timestamps=1&follow=1&tail=...`
  a través de `docker-socket-proxy`. La UI hace de proxy SSE y conserva las
  líneas originales (sin traducir).
- El estado de Oxidized se obtiene combinando:
  - `GET /nodes.json` con timeout corto (API online/offline). La respuesta
    contiene `vars` (posiblemente credenciales); el backend descarta ese campo y
    solo conserva los datos de estado. No se cachea ni se reenvía al frontend.
  - Inspección del contenedor (`GET /containers/<name>/json`) para saber si está
    running/restarting/unhealthy.
- Los estados de backup observados se guardan en `backup_runs` para el gráfico
  de actividad. Un job interno de Oxidized puede escaparse entre dos sondeos:
  el gráfico es una observación periódica, no un contador exacto de jobs.

## Docker API usada

Solo estas tres llamadas, a través del proxy:

| Uso | Llamada |
|---|---|
| Inspeccionar contenedor | `GET /containers/{OXIDIZED_CONTAINER_NAME}/json` |
| Leer logs (follow/no follow) | `GET /containers/{OXIDIZED_CONTAINER_NAME}/logs?...` |
| Reiniciar | `POST /containers/{OXIDIZED_CONTAINER_NAME}/restart` |

`docker-compose.secure.yml` habilita en el proxy `CONTAINERS=1`, `POST=1` y
`ALLOW_RESTARTS=1`, y desactiva el resto de secciones. El proxy no se publica y
solo está en la red interna `docker_api`, compartida únicamente con la UI.

Limitación conocida: la configuración por variables de
`tecnativa/docker-socket-proxy` no permite limitar el nombre del contenedor en
las rutas; un compromiso total de la UI podría reiniciar otros contenedores. El
riesgo residual se reduce con la red aislada, el token de sesión, la ausencia de
ejecución de comandos (`EXEC=0`) y la superficie mínima. Una alternativa futura
es una plantilla HAProxy propia que fije el nombre del contenedor.

## Invariantes de integración

El backend comprueba estas condiciones antes de aplicar una configuración:

1. El YAML parsea y no contiene claves prohibidas (`rest`).
2. `source.default == "http"` y el source HTTP apunta a la URL interna con el
   token.
3. `extensions.oxidized-web.load == true` y el puerto/escucha son los que
   Oxidized UI espera.
4. `output.git.repo` u `output.file.directory` no se validan contra el host de
   la UI; viven dentro del contenedor de Oxidized. La UI avisa de que cambiarlos
   puede dejar inaccesible el historial previo.
5. El fichero de configuración se escribe bajo el path fijo del volumen; nunca se
   acepta una ruta del usuario para escribirlo.
6. No se construyen comandos de shell con datos del usuario. Oxidized ejecutará
   `exec` hooks si un admin los configura; la UI solo los persiste como YAML y
   muestra una advertencia de seguridad.

## Referencias

- [Oxidized: Docker](https://github.com/ytti/oxidized/blob/master/docs/Docker.md)
- [Oxidized: Configuration](https://github.com/ytti/oxidized/blob/master/docs/Configuration.md)
- [Oxidized: Sources](https://github.com/ytti/oxidized/blob/master/docs/Sources.md)
- [Oxidized: Outputs](https://github.com/ytti/oxidized/blob/master/docs/Outputs.md)
- [Oxidized: Hooks](https://github.com/ytti/oxidized/blob/master/docs/Hooks.md)
- [oxidized-web: WebApp](https://github.com/ytti/oxidized-web/blob/master/lib/oxidized/web/webapp.rb)
- [tecnativa/docker-socket-proxy](https://github.com/Tecnativa/docker-socket-proxy)
