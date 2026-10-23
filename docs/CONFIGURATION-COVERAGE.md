# Cobertura de configuración de Oxidized

Este documento fija qué parámetros se editan en formulario, cuáles se inyectan
como bloques gestionados y cuáles quedan para el editor YAML avanzado. Los
valores por defecto se tomaron de `lib/oxidized/config.rb` y de la documentación
de **Oxidized 0.37.0**; cuando un valor no está documentado se indica.

Principio: **todo parámetro documentado tiene representación**. Si no está
modelado en un formulario, se conserva y se edita en el YAML avanzado. El
formulario y el YAML comparten el mismo modelo estructurado; las claves
desconocidas no se pierden.

Cada campo del catálogo backend tiene:

- `path` técnico (p. ej. `input.ssh.secure`);
- `label_code` y `help_code` para i18n (el nombre técnico no se traduce);
- tipo, default, rango, enum y si es obligatorio;
- `sensitive` (se muestra enmascarado cuando aplica);
- `managed` (no editable; inyectado por la UI);
- nivel (`basic`, `advanced`, `deprecated`, `dangerous`);
- validación de backend y mensaje de error por código.

Nada de esto se hardcodea en los componentes: el frontend renderiza desde el
catálogo y traduce las claves. El test de i18n verifica que todos los
`label_code`/`help_code` existen en es/en.

## 1. Fuente de verdad y bloques gestionados

| Bloque | Editable | Motivo |
|---|---|---|
| General, inputs, outputs, hooks, logger, grupos, models, group_map, model_map | Formulario / YAML | Configuración normal de Oxidized |
| `source.default`, `source.http.url`, `source.http.headers.X-Oxidized-Source-Token`, `source.http.map` | **No** | Son el contrato con la base de datos de nodos |
| `extensions.oxidized-web.load`, `listen`, `port`, `url_prefix` | **No** | Sin ellos la UI no puede hablar con oxidized-web |
| `rest` | **No** (prohibido) | Deprecado; además expone la API interna |
| Claves desconocidas | Sí (YAML) | Cobertura de versiones futuras y opciones no modeladas |

El editor de Source muestra el bloque activo como solo lectura y permite editar
`read_timeout`. Otras fuentes (`csv`, `sql`, `jsonfile`, otro bloque `http`) se
pueden conservar/editar en el YAML avanzado, pero no activar. Si se intenta
cambiar `source.default` o los valores del contrato, el backend devuelve
`config.managed_key_modified` y no escribe nada.

## 2. Pestaña General

| Ruta | Control | Default | Validación / notas |
|---|---|---:|---|
| `username` | texto | `username` | ≤ 128; credencial global por defecto |
| `password` | secreto | `password` | ≤ 512; se guarda dentro del JSON cifrado |
| `model` | selector de modelo | `junos` | Debe ser un modelo conocido o personalizado válido |
| `interval` | número | `3600` | 0–604800 s; 0 desactiva el ciclo automático (Oxidized) |
| `threads` | número | `30` | 1–256 |
| `use_max_threads` | switch | `false` | Si `true`, usa siempre `threads` |
| `timeout` | número | `20` | 1–3600 s |
| `timelimit` | número | `300` | 1–86400 s; se avisa si es menor que `timeout` |
| `retries` | número | `3` | 0–20 |
| `prompt` | texto regex | `^([\w.@-]+[#>]\s?)$` | ≤ 512, sin saltos de línea. Se serializa como `!ruby/regexp`; no se valida semántica Ruby en el backend |
| `next_adds_job` | switch | `false` (UI lo pone `true` en su bootstrap) | Necesario para que `/next` se ejecute antes |
| `resolve_dns` | switch | `true` | Si `false`, se pasa el nombre tal cual |
| `debug` | switch | `false` | Aumenta logs; no confundir con `input.debug` |
| `run_once` | switch | `false` | **Avanzado/peligroso**: Oxidized termina tras un ciclo; el contenedor reiniciará |
| `pid` | texto | `~/.config/oxidized/pid` | ≤ 512; ruta de fichero, no se escribe desde la UI |
| `crash.directory` | texto | `~/.config/oxidized/crashes` | ≤ 512; ruta del contenedor |
| `crash.hostnames` | switch | `false` | Nombre de fichero de crash por hostname o IP |
| `stats.history_size` | número | `10` | 1–100; opción del código de 0.37.0, no está en la guía principal |
| `use_syslog` | switch | no definido | **Deprecado** por Oxidized; se puede migrar a `logger`; warning |
| `log` | texto | no definido | **Deprecado**; warning. Preferir `logger` |
| `logger.level` | select | `:info` | `trace/debug/info/warn/error/fatal`; el nivel se serializa como string `:info` |
| `logger.appenders[]` | lista repetible | `[]` | Cada appender: `type` (`stderr`, `stdout`, `file`, `syslog`), `file`, `level` |
| `extensions.oxidized-web.hide_node_vars` | lista | `[]` | Nombres de vars a ocultar en `/node/show`; la UI no depende de esa ruta |
| `extensions.oxidized-web.vhosts` | lista | `[]` | Debe incluir `oxidized` o quedar vacío; validado |
| `vars` | editor clave/valor | `{}` | Ver catálogo de variables; claves reservadas no se duplican |

`use_syslog` y `log` se muestran con badge de deprecación y no se eliminan
silenciosamente si ya existen en un YAML importado. Si se usan simultáneamente
con `logger`, Oxidized emite warnings; la UI también.

**Importante para los logs en vivo:** la pantalla de logs lee stdout/stderr del
contenedor por la API de Docker. Si el admin configura `logger` sin ningún
appender `stdout` o `stderr` (por ejemplo, solo un fichero), Oxidized no emitirá
nada capturable por Docker y la pantalla de logs mostrará un aviso en lugar de
inventar líneas. La UI no fuerza appenders, porque eso limitaría la cobertura
de configuración; lo advierte en el formulario y en la pantalla de logs.

### Credenciales por defecto

`username` y `password` globales son la última prioridad en Oxidized. El
formulario indica la precedencia:

```text
global < modelo < grupo < modelo dentro del grupo < nodo
```

No se muestran credenciales de nodo en esta pantalla.

## 3. Vars globales y por nodo

El editor de variables admite claves conocidas y claves libres. Para las
conocidas ofrece tipo, descripción y validación; las libres se guardan como
string/boolean/number/null y se serializan sin interpretación. Los nombres
técnicos no se traducen.

Catálogo de sugerencias (no exhaustivo; Oxidized y los modelos pueden añadir
más):

- Comunes: `enable`, `remove_secret`, `metadata`, `metadata_top`,
  `metadata_bottom`, `output_store_mode`.
- SSH/SCP: `ssh_port`, `telnet_port`, `ssh_no_exec`, `ssh_no_keepalive`,
  `ssh_keys`, `auth_methods`, `ssh_proxy`, `ssh_proxy_port`, `ssh_kex`,
  `ssh_host_key`, `ssh_hmac`, `ssh_encryption`, `ssh_pubkey_algorithms`.
- Por modelo: `comware_cmdline`, `cumulus_use_nclu`, `cumulus_use_nvue`,
  `cumulus_routing_daemon`, `ftd_api_endpoint`, `ftd_api_port`, `ftd_polls`,
  `ftd_poll_wait`, `ftd_config_filename`, `fortios_autoupdate`,
  `fortigate_autoupdate`, `fullconfig`, `ios_rbac`,
  `lenovonos_remove_unstable_lines`, `openwrt_*`, `realm`, `admin`, etc.

Los nombres mostrados son los que entiende Oxidized; las descripciones se
traducen en `oxidized.vars.<name>.label/help`. Las claves personalizadas sin
traducción muestran su nombre técnico.

Reglas:

- `vars.enable` en un nodo está reservado: la UI usa el campo `enable` y lo
  emite como `vars.enable`.
- El resto de variables son libres; pueden contener secretos. En nodos se
  cifran en bloque. En la configuración global van dentro de la revisión
  cifrada.
- En el formulario de nodo se permite configurar `ssh_port`/`telnet_port` o usar
  el campo «Puerto»; el backend evita duplicados. Si el campo Puerto está
  definido, gana y las variables correspondientes se generan.
- `output_store_mode: on_significant` se ofrece como sugerencia; requiere un
  modelo que implemente `significant_changes`, por lo que la UI muestra un
  warning.

## 4. Credenciales, grupos, group_map y model_map

### Grupos

Rutas en la revisión de configuración:

```yaml
groups:
  <nombre>:
    username: <opcional>
    password: <opcional, secreto>
    vars:
      enable: <secreto opcional>
    models:
      <modelo>:
        username: <opcional>
        password: <secreto opcional>
        vars: {}
```

- El grupo es la unidad de credenciales y variables compartidas.
- La pantalla «Grupos y credenciales» es la editora principal de esta sección.
- Un operator puede crear/editar grupos; los cambios se guardan como borrador.
  Un admin debe aplicarlos (ver tensión de roles en ARCHITECTURE).
- Los nombres de grupo se validan: ≤ 128, sin `/`, `\`, `..`, controles ni
  punto inicial. Son inmutables una vez creados; renombrar exige mover los
  nodos y aplicar; la UI no ofrece rename directo en esta versión.
- Borrar un grupo en uso se bloquea con `group.in_use`.
- Las contraseñas de grupo se enmascaran en la pantalla de grupos. El editor de
  configuración global (solo admin) puede verlas porque es el editor del YAML.

### group_map

Se representa como lista de entradas para soportar claves string y regex:

```yaml
group_map:
  alias1: groupA
  alias2: groupA
  !ruby/regexp /specialgroup/: groupS
```

| Campo | Validación |
|---|---|
| `match` | ≤ 128, no vacío |
| `is_regex` | boolean |
| `target` | nombre de grupo existente o alias permitido, ≤ 128 |

La UI advierte si se usa una regex cuando no es necesario. La validación de la
sintaxis Ruby es estructural (no se ejecuta Ruby).

### models

Rutas:

```yaml
models:
  <modelo>:
    username: <opcional>
    password: <opcional, secreto>
    vars: {}
```

Formulario repetible con selector de modelo, credenciales opcionales y vars. Se
usa para credenciales por modelo. No confundir con el catálogo de modelos del
selector de nodos.

### model_map

Misma estructura que `group_map`, con destino a un modelo conocido:

```yaml
model_map:
  cisco: ios
  juniper: junos
  !ruby/regexp /procurve/: procurve
```

`cisco → ios` y `juniper → junos` son defaults de Oxidized. Se muestran y se
pueden editar.

## 5. Pestaña Input

### Opciones globales

| Ruta | Control | Default | Validación / notas |
|---|---|---:|---|
| `input.default` | multi-select ordenado | `ssh, telnet` | Solo inputs disponibles; se serializa como `ssh, telnet` |
| `input.debug` | multi-select / switch | `false` | `text`, `yaml`, `library`, `true`/`false`; se serializa como string o bool |
| `input.ssh.secure` | switch | `false` | Verificación estricta de host key |
| `input.ftp.passive` | switch | `true` | Modo pasivo de FTP |
| `input.http.scheme` | select | — | `http`/`https`; opción de modelo HTTP |
| `input.http.ssl_verify` | switch | `false` (código) | Verificación TLS del input HTTP |
| `input.http.timeout` | número | — | 1–3600 s; opción del input HTTP, no siempre documentada |
| `input.utf8_encoded` | switch | `true` | Codificación de la config |

Los módulos disponibles en 0.37.0 son **ssh, telnet, ftp, http, tftp, exec y
scp**. Sus opciones específicas viven, en su mayor parte, en variables de nodo o
en el modelo, no en un bloque global. La UI muestra una ficha por input con:

- nombre técnico y descripción traducida;
- variables relevantes (`ssh_port`, `telnet_port`, `ssh_secure`, etc.);
- notas de soporte.

No se inventan opciones de configuración que Oxidized no tenga. En el YAML
avanzado se pueden añadir claves de input no modeladas.

### Notas de validación

- `ssh`, `scp`, `telnet`, `ftp`, `http`, `tftp`, `exec` se validan contra esta
  lista. Un input desconocido solo puede venir por YAML avanzado y se conserva.
- `exec` como input ejecuta comandos definidos en el modelo. Es inherentemente
  peligroso; solo admin puede aplicar configuración con él.
- El debug de input puede generar ficheros de simulación en el contenedor; no se
  sirven desde la UI.

## 6. Pestaña Output

| Ruta | Control | Default | Validación / notas |
|---|---|---:|---|
| `output.default` | select | `file` (el bootstrap de la UI usa `git`) | `file`, `git`, `gitcrypt`, `http` |
| `output.clean_obsolete_nodes` | switch | no definido | Borra configuraciones de nodos ausentes; confirmación fuerte y warning |
| `output.file.directory` | texto | — | ≤ 1024; ruta dentro del contenedor; recomendar `/var/lib/oxidized/configs` |
| `output.git.user` | texto | — | Nombre de commit |
| `output.git.email` | email | — | Email de commit |
| `output.git.repo` | texto | — | Ruta bare repo; recomendar `/var/lib/oxidized/devices.git` |
| `output.git.single_repo` | switch | `false` (Oxidized) | Un repo para todos los grupos |
| `output.git.type_as_directory` | switch | no definido | Avanzado; cambia la ruta de los "output types" |
| `output.gitcrypt.user` | texto | — | Requiere `git-crypt` en la imagen |
| `output.gitcrypt.email` | email | — | — |
| `output.gitcrypt.repo` | texto | — | Ruta del repo |
| `output.gitcrypt.users` | lista | `[]` | IDs GPG; requerido por git-crypt |
| `output.gitcrypt.single_repo` | switch | `false` | — |
| `output.http.url` | URL | — | http(s); se valida |
| `output.http.user` | texto | — | Basic auth opcional |
| `output.http.password` | secreto | — | Basic auth opcional |
| `output.http.ssl_verify` | switch | `false` (código) | Verificación TLS |
| `output.http.headers` | editor clave/valor | `{}` | Cabeceras extra |

Consideraciones:

- **Git** es el output por defecto recomendado en la UI porque habilita
  versiones/diffs. `file` y `http` no tienen historial: la UI muestra un aviso y
  desactiva esas vistas.
- La imagen oficial 0.37.0 instala `git` pero **no** instala `git-crypt`. La
  opción `gitcrypt` se puede configurar, pero la UI muestra un warning de que
  requiere una imagen derivada con `git-crypt` instalado. No se inventa soporte.
- `clean_obsolete_nodes` puede borrar ficheros; solo admin y con confirmación
  explícita. El YAML y Oxidized aplican la semántica real.
- `output.http` envía configuraciones a un tercero; warning de privacidad.
- Si se cambia el repo/directorio, el historial anterior deja de ser visible
  desde la API; la UI avisa antes de aplicar.

## 7. Pestaña Source

### Bloque activo (gestionado + opciones seguras)

| Ruta | Control | Default | Estado |
|---|---|---:|---|
| `source.default` | solo lectura `http` | `http` | Gestionado |
| `source.http.url` | solo lectura | URL interna | Gestionado |
| `source.http.headers.X-Oxidized-Source-Token` | solo lectura/enmascarado | token env | Gestionado |
| `source.http.map` | solo lectura | `name/ip/model/group/input/username/password/vars` | Gestionado |
| `source.http.vars_map` | solo lectura | `{}` | Gestionado; se mantiene vacío para no sobrescribir el objeto `vars` |
| `source.http.read_timeout` | número | 60 s (Oxidized si no se define) | Editable; 5–300; la UI emite 30 |
| `source.http.pagination` | switch | `false` | No se usa; desactivado/avanzado |
| `source.http.hosts_location` | texto | no definido | Avanzado; solo si se usa paginación/estructura anidada |

La UI no permite editar manualmente la URL, token, cabecera ni map, porque son
el contrato con el source de nodos. El token se muestra como `••••` en la vista
previa y no se devuelve por la API pública de configuración.

### Otras fuentes

Oxidized documenta `csv`, `jsonfile`, `sql` (MySQL/SQLite/PostgreSQL y Sequel) y
`http`. La UI permite conservar bloques de otras fuentes en el YAML avanzado,
con sus map/vars_map, pero **no puede activarlas** sin romper la fuente de verdad
de nodos. Esto se muestra en la pestaña Source como «fuentes inactivas»:

- CSV: `file`, `delimiter` (`!ruby/regexp`), `gpg`, `gpg_password`, `map`,
  `vars_map`.
- JSONFile: `file`, `gpg`, `gpg_password`, `map`, `vars_map`.
- SQL: `adapter`, `database`, `table`, `user`, `password`, `query`,
  `with_ssl`, `ssl_mode`, `ssl_ca`, `ssl_cert`, `ssl_key`, `map`, `vars_map`.
- HTTP (otra instancia): `url`, `scheme`, `delimiter`, `user`, `pass`,
  `read_timeout`, `secure`, `headers`, `map`, `vars_map`, `pagination`,
  `pagination_key_name`, `hosts_location`.

La validación de estas fuentes se limita a tipos y sintaxis YAML; no se prueba
la conexión porque no son la fuente activa. Si en el futuro se quiere cambiar de
fuente, hace falta un modo de despliegue distinto que desactive la gestión de
nodos de la UI.

## 8. Pestaña Hooks

Estructura común:

```yaml
hooks:
  <nombre>:
    type: <tipo>
    events: [node_success, node_fail, post_store, nodes_done]
    <parámetros del tipo>
```

Eventos documentados: `node_success`, `node_fail`, `post_store`, `nodes_done`.
(`source_node_transform` existe en el código de 0.37.0 pero no está en la guía
de Hooks; se deja para YAML avanzado.)

Tipos y campos modelados:

| Tipo | Campos | Notas |
|---|---|---|
| `exec` | `cmd` (requerido), `timeout` (default 60), `async` (default false) | **Peligroso**: ejecuta shell en el contenedor de Oxidized. Solo admin; advertencia visible. |
| `githubrepo` | `remote_repo` (string o mapa por grupo), `username`, `password`, `privatekey`, `publickey` | El remoto no puede coincidir con un repo local de output. Claves en formato PEM legacy. `OXIDIZED_SSH_PASSPHRASE` no se configura desde la UI. |
| `awssns` | `region` (requerido), `topic_arn` (requerido) | Credenciales AWS en `~/.aws/credentials`, fuera de la UI. |
| `slackdiff` | `token` (secreto), `channel` (ID), `diff` (bool), `message`, `proxy` | Pensado para `post_store`; requiere output con diff (git/gitcrypt). |
| `ciscosparkdiff` | `accesskey` (secreto), `space`, `diff`, `message`, `proxy` | Requiere gem `cisco_spark`; la imagen oficial la instala. |
| `xmppdiff` | `jid`, `password` (secreto), `channel`, `nick` | Requiere `xmpp4r`; la imagen oficial lo instala. |

- `events` es una lista no vacía; la UI sugiere `post_store` para hooks de diff.
- Los hooks desconocidos se conservan y se editan en YAML avanzado.
- Los secretos de hooks se guardan en la revisión cifrada. No se muestran en
  auditoría ni toasts.
- La UI no ejecuta los hooks ni permite testear `exec` desde el backend.
- `githubrepo`, `slackdiff`, etc. tienen dependencias que la imagen oficial ya
  incluye en 0.37.0; si una versión futura las quita, el error se refleja en los
  logs de Oxidized, no se simula.

## 9. Pestaña Modelos

Además de `models` y `model_map` descritos arriba, esta pestaña muestra el
catálogo estático de modelos de Oxidized 0.37.0:

- Nombre técnico y vendor/OS (desde `Supported-OS-Types.md` cuando está
  disponible).
- Búsqueda y filtro.
- Enlace a notas del modelo si existe (solo documentación; no se sirve contenido
  remoto).
- Los modelos personalizados que existan en el volumen de configuración no se
  descubren automáticamente (Oxidized tampoco los expone por API). El selector
  permite escribir el nombre técnico.
- Editar `models` (credenciales por modelo) y `model_map`.

El catálogo se genera con `scripts/generate_oxidized_catalog.py` desde la
versión fijada. No se consulta Internet en tiempo de ejecución.

## 10. REST / Extensiones

`extensions.oxidized-web`:

| Ruta | Control | Default | Estado |
|---|---|---:|---|
| `extensions.oxidized-web.load` | solo lectura true | false | Gestionado; sin esto no hay API |
| `extensions.oxidized-web.listen` | solo lectura | `127.0.0.1` | Gestionado a `0.0.0.0` para la red Docker |
| `extensions.oxidized-web.port` | solo lectura | `8888` | Gestionado; coincide con `OXIDIZED_API_URL` |
| `extensions.oxidized-web.url_prefix` | solo lectura | vacío | Gestionado |
| `extensions.oxidized-web.vhosts` | lista | `[]` | Editable con validación |
| `extensions.oxidized-web.hide_node_vars` | lista | `[]` | Editable; la UI no usa `/node/show` |

No se ofrece la clave deprecada `rest`. La UI avisa de que la API de
oxidized-web no tiene autenticación propia y que nunca se publica su puerto.
Cualquier otra extensión de Oxidized se conserva en YAML avanzado; no se inventa
soporte para extensiones que no existen.

## 11. YAML avanzado

- Editor completo con CodeMirror, validación de sintaxis YAML y del esquema
  conocido.
- Muestra el diff contra la revisión aplicada antes de guardar/aplicar.
- Permite editar cualquier clave no gestionada, incluidas las que una versión
  futura añada.
- Conserva tags `!ruby/regexp`; no permite tags Ruby arbitrarios ni constructores
  peligrosos.
- Rechaza `rest`; rechaza modificar los bloques gestionados.
- Preserva claves desconocidas al volver al formulario. Los comentarios del YAML
  no se conservan al pasar por el modelo estructurado; se avisa. Para conservar
  comentarios, el usuario debe usar el YAML como fuente de trabajo y no alternar
  con formularios sin revisar el diff.
- El token del source se muestra enmascarado en la vista previa; nunca se
  escribe en la respuesta HTTP.
- No se ejecuta Ruby para validar expresiones regulares ni el YAML. La
  validación es estructural y de esquema. Oxidized no ofrece un endpoint de
  dry-run; por eso la UI aplica con reinicio, comprueba salud y deja preparado un
  rollback.

## 12. Cobertura de campos de nodo

| Campo UI | Requerido | Validación | Se envía a Oxidized |
|---|---|---|---|
| Nombre | Sí | 1–253, sin `/`, `\`, controles, `..`, `.json` final; único case-insensitive | `name` |
| IP / host | No | IP o hostname; longitud; no URLs | `ip` (vacío = resolver por nombre) |
| Modelo | Sí | catálogo o texto técnico válido | `model` |
| Grupo | No | grupo existente en config aplicada | `group` |
| Input | No | lista de inputs conocidos, ordenada | `input` |
| Puerto | No | 1–65535 | `vars.ssh_port`/`vars.telnet_port` |
| Usuario | No | ≤ 128 | `username` |
| Contraseña | No | ≤ 512; write-only | `password` descifrado solo en source |
| Enable | No | ≤ 512; write-only | `vars.enable` |
| Vars | No | objeto; claves reservadas prohibidas; valores JSON/YAML | `vars` |
| Output (avanzado) | No | output conocido | `output` |
| Prompt (avanzado) | No | ≤ 512, sin saltos de línea | `prompt` |
| Timeout (avanzado) | No | 1–3600 | `timeout` |

Los campos avanzados de nodo no aparecen en la tabla principal; se editan en un
desplegable para no sobrecargar el formulario. No se inventan campos que Oxidized
no soporte.

## 13. Matriz de cobertura de documentación oficial

| Bloque fuente | Formulario | Avanzado YAML | Gestión UI |
|---|---:|---:|---:|
| General / top-level | ✅ | ✅ | — |
| Credenciales globales | ✅ | ✅ | — |
| vars globales | ✅ | ✅ | — |
| groups (credenciales, vars, models) | ✅ pantalla Grupos | ✅ | — |
| group_map / model_map | ✅ | ✅ | — |
| input global y por input | ✅ (opciones documentadas) | ✅ | — |
| output file/git/gitcrypt/http | ✅ | ✅ | — |
| source http activo | parcial (solo opciones seguras) | limitado | bloqueado |
| sources csv/jsonfile/sql/otro http | ❌ | ✅ | inactivas |
| hooks exec/githubrepo/awssns/slackdiff/ciscosparkdiff/xmppdiff | ✅ | ✅ | — |
| logger/crash/stats/pid | parcial | ✅ | — |
| extensions oxidized-web | parcial | limitado | bloqueado |
| extensiones futuras | ❌ | ✅ | — |

Leyenda: ✅ modelado; ❌ solo YAML; «bloqueado» = no editable por contrato.

## 14. Parámetros y defaults que no se deben inventar

- No existe `port` genérico de nodo en Oxidized: SSH/SCP y Telnet usan variables
  distintas. La UI lo explica.
- FTP no acepta puerto en su input actual.
- `use_syslog` y `log` están deprecados; se mantienen por compatibilidad.
- `rest` está deprecado y además chocaría con la integración.
- `gitcrypt` requiere el binario `git-crypt`, que la imagen oficial 0.37.0 no
  incluye.
- No hay endpoint de modelos, jobs, validación de config ni recarga de
  config; la UI no los simula.
- Los detalles de `map: vars` y de los endpoints de oxidized-web están en
  [OXIDIZED-INTEGRATION.md](OXIDIZED-INTEGRATION.md), con sus incertidumbres
  marcadas.
