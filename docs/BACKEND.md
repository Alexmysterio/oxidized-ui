# Backend — implementación de la fase 2

Estado: backend funcional, migraciones, autenticación, RBAC, nodos, configuración,
clientes de Oxidized/Docker, auditoría, jobs, SSE de logs y tests. La SPA y el
Dockerfile multi-stage se entregaron en las fases 3–4; la puesta en marcha completa
está en el [README](../README.md).

## Módulos

```text
backend/
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/c9bc9122d335_initial_schema.py
├── pyproject.toml
├── app/
│   ├── main.py                 # app, middleware CSRF/seguridad, lifespan
│   ├── settings.py             # Pydantic Settings + rutas
│   ├── db.py                   # engine, sesión, PRAGMAs
│   ├── models.py               # 12 tablas SQLAlchemy
│   ├── schemas.py              # validación de entrada
│   ├── errors.py               # AppError + códigos + handlers
│   ├── security.py             # Argon2id, sesión, CSRF, ámbito
│   ├── auth_deps.py            # dependencias de sesión/RBAC
│   ├── auth_service.py         # login, setup, bootstrap, password
│   ├── user_service.py
│   ├── node_service.py         # CRUD, CSV, source payload, bulk
│   ├── backup_service.py
│   ├── status_service.py
│   ├── poller.py               # observación de estado/actividad
│   ├── oxidized.py             # cliente HTTP de oxidized-web
│   ├── docker_api.py           # proxy Docker + demux de logs
│   ├── diffing.py
│   ├── version_service.py
│   ├── config_model.py         # modelo YAML/JSON, defaults, invariantes
│   ├── yaml_codec.py           # YAML + !ruby/regexp
│   ├── config_service.py       # revisiones, apply, drift, grupos
│   ├── catalog.py              # metadatos de campos/modelos/vars/hooks
│   ├── audit.py
│   ├── jobs.py
│   ├── log_service.py
│   ├── search_service.py
│   ├── serializers.py
│   ├── timeutil.py
│   ├── routers/
│   │   ├── auth.py, users.py, nodes.py, versions.py, groups.py
│   │   ├── config.py, status.py, logs.py, audit.py, system.py
│   │   ├── search.py, meta.py, internal.py
│   └── data/
│       ├── error_codes.json
│       ├── audit_actions.json
│       └── oxidized_models.json
└── tests/
    ├── conftest.py
    ├── test_auth.py
    ├── test_nodes.py
    ├── test_config.py
    ├── test_rbac.py
    ├── test_integrations.py
    └── test_catalogs.py
```

## Ejecutar en local

Requisitos: Python 3.12 y dependencias del `pyproject.toml`.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Configura las variables de entorno obligatorias (`SECRET_KEY`, `FERNET_KEY`,
`OXIDIZED_SOURCE_TOKEN`) y las rutas de datos. Para desarrollo:

```powershell
$env:APP_ENV = "development"
$env:SECRET_KEY = "..."
$env:FERNET_KEY = "..."        # Fernet.generate_key()
$env:OXIDIZED_SOURCE_TOKEN = "..."
$env:DATA_DIR = "$PWD\.local\data"
$env:OXIDIZED_CONFIG_DIR = "$PWD\.local\config"
$env:OXIDIZED_API_URL = "http://127.0.0.1:8888"
$env:DOCKER_PROXY_URL = "http://127.0.0.1:2375"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`AUTO_MIGRATE=true` (por defecto) aplica Alembic al arrancar. Para hacerlo
manualmente:

```powershell
alembic upgrade head
```

En `APP_ENV=development`, `/api/docs` y `/api/openapi.json` están disponibles.
En producción están desactivados. La raíz devuelve un JSON mínimo hasta que la
fase 3 copie el build del frontend.

## Tests y lint

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest
..\.venv\Scripts\ruff.exe check app tests
..\.venv\Scripts\ruff.exe format --check app tests
```

Cobertura actual: **31 tests unitarios/de integración simulada**, más un test
opcional contra el stack Docker real (`test_live_integration.py`).

- setup/login/logout, sesión, CSRF, origen, rate limit, rotación de contraseña;
- RBAC admin/operator/viewer y último admin;
- CRUD de nodos, secretos write-only, cifrado, source interno con token, CSV y
  acciones masivas;
- validación YAML, tags `!ruby/regexp`, grupos, draft/apply/restart, rollback,
  revisión histórica y fallo de reinicio visible;
- cliente de oxidized-web con respuestas simuladas (sin secretos en `/nodes.json`);
- demux de logs Docker, SSE, descargas, versiones y diff;
- catálogo de errores/auditoría y metadatos i18n.

La integración real contra `oxidized/oxidized:0.37.0` está verificada con el stack
Docker: el source interno entrega el nodo, el grupo, `ssh_port`, `enable` y las
variables personalizadas, y oxidized-web los expone en su inventario. El test
opcional `tests/test_live_integration.py` comprueba salud, login, estado online,
inventario, configuración aplicada y logs contra un stack ya arrancado.

## Decisiones de implementación

- Un solo worker de Uvicorn. SQLite, locks en proceso y el poller no están
  preparados para multi-worker.
- El startup aplica migraciones y, si no hay fichero de configuración, genera
  uno con source HTTP, oxidized-web y output git. Si ya existe un fichero, no lo
  sobrescribe: intenta adoptarlo; si no parsea, conserva snapshot y marca drift.
- El source interno (`/api/internal/source/nodes`) no usa cookies; exige
  `X-Oxidized-Source-Token`. El mapa incluye `vars` y los overrides avanzados de
  nodo.
- La configuración editable se cifra en cada revisión. El token del source se
  inyecta al renderizar y se enmascara en las respuestas.
- El apply es un job asíncrono: escribe el fichero de forma atómica, marca la
  revisión, hace backup y reinicia el contenedor. Si el reinicio falla, deja la
  revisión aplicada y el job fallido, sin ocultar el estado real. No se hace
  rollback automático ni health-check bloqueante en esta versión.
- Los logs usan la API de Docker con demux del stream. La búsqueda y el nivel se
  filtran en el backend; el texto se conserva sin traducir.
- El rate limit de login vive en SQLite y es persistente entre reinicios.

## Frontend (fase 3)

Implementado. La SPA sirve `/`, consume la API, mantiene el catálogo de campos
desde `/api/config/catalog` y añade las traducciones completas es/en. La
arquitectura, rutas, verificación y decisiones visuales están en
[FRONTEND.md](FRONTEND.md).
