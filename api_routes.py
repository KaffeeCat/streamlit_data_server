import json
from typing import Any, Callable, Optional

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

import data_service
from auth import (
    config_status,
    extract_site_password_from_headers,
    extract_write_key_from_headers,
    is_site_auth_enabled,
    is_write_enabled,
    require_site_password,
    require_write_key,
)
from import_parsers import parse_upload
from schema import validate_actor

data_service.initialize()

Handler = Callable[[Request], Any]


def _json_response(data: Any, *, status: int = 200) -> JSONResponse:
    return JSONResponse({"ok": status < 400, "data": data, "error": None}, status_code=status)


def _error_response(message: str, *, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "data": None, "error": message}, status_code=status)


def _site_password(request: Request) -> Optional[str]:
    return extract_site_password_from_headers(dict(request.headers), dict(request.query_params))


def _write_key(request: Request) -> Optional[str]:
    return extract_write_key_from_headers(dict(request.headers), dict(request.query_params))


def _with_site_auth(handler: Handler) -> Handler:
    async def wrapped(request: Request) -> Response:
        if is_site_auth_enabled():
            try:
                require_site_password(_site_password(request))
            except PermissionError as e:
                return _error_response(str(e), status=401)
        return await handler(request)

    return wrapped


async def _read_json(request: Request) -> dict:
    body = await request.body()
    if not body:
        return {}
    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        raise ValueError("Request body is not valid JSON")


async def _read_json_optional(request: Request) -> dict:
    body = await request.body()
    if not body:
        return {}
    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def _actor_from(payload: dict, params: dict) -> str:
    actor = payload.get("actor") or params.get("actor") or ""
    return validate_actor(str(actor))


async def list_databases(request: Request) -> Response:
    try:
        return _json_response(data_service.list_databases())
    except Exception as e:
        return _error_response(str(e))


async def create_database(request: Request) -> Response:
    try:
        require_write_key(_write_key(request))
        payload = await _read_json(request)
        actor = _actor_from(payload, dict(request.query_params))
        db = data_service.create_database(
            name=payload["name"],
            display_name=payload.get("display_name", payload["name"]),
            actor=actor,
            description=payload.get("description", ""),
        )
        return _json_response(db, status=201)
    except PermissionError as e:
        return _error_response(str(e), status=403)
    except (KeyError, ValueError) as e:
        return _error_response(str(e))
    except Exception as e:
        return _error_response(str(e), status=500)


async def delete_database(request: Request) -> Response:
    try:
        require_write_key(_write_key(request))
        params = dict(request.query_params)
        if params.get("confirm") != "true":
            return _error_response("Delete database requires confirm=true", status=400)
        payload = await _read_json_optional(request)
        actor = _actor_from(payload, params)
        data_service.delete_database(request.path_params["db"], actor=actor)
        return _json_response({"deleted": request.path_params["db"]})
    except PermissionError as e:
        return _error_response(str(e), status=403)
    except ValueError as e:
        return _error_response(str(e))
    except Exception as e:
        return _error_response(str(e), status=500)


async def list_tables(request: Request) -> Response:
    try:
        return _json_response(data_service.list_tables(request.path_params["db"]))
    except ValueError as e:
        return _error_response(str(e), status=404)
    except Exception as e:
        return _error_response(str(e), status=500)


async def create_table(request: Request) -> Response:
    try:
        require_write_key(_write_key(request))
        payload = await _read_json(request)
        actor = _actor_from(payload, dict(request.query_params))
        table = data_service.create_table(
            request.path_params["db"],
            table_name=payload["name"],
            columns=payload.get("columns", []),
            actor=actor,
            max_rows=int(payload.get("max_rows", 0)),
            display_name=payload.get("display_name", payload["name"]),
        )
        return _json_response(table, status=201)
    except PermissionError as e:
        return _error_response(str(e), status=403)
    except (KeyError, ValueError) as e:
        return _error_response(str(e))
    except Exception as e:
        return _error_response(str(e), status=500)


async def delete_table(request: Request) -> Response:
    try:
        require_write_key(_write_key(request))
        params = dict(request.query_params)
        if params.get("confirm") != "true":
            return _error_response("Delete table requires confirm=true", status=400)
        payload = await _read_json_optional(request)
        actor = _actor_from(payload, params)
        data_service.delete_table(
            request.path_params["db"],
            request.path_params["name"],
            actor=actor,
        )
        return _json_response({"deleted": request.path_params["name"]})
    except PermissionError as e:
        return _error_response(str(e), status=403)
    except ValueError as e:
        return _error_response(str(e))
    except Exception as e:
        return _error_response(str(e), status=500)


async def get_schema(request: Request) -> Response:
    try:
        return _json_response(
            data_service.get_table_meta(request.path_params["db"], request.path_params["name"])
        )
    except ValueError as e:
        return _error_response(str(e), status=404)
    except Exception as e:
        return _error_response(str(e), status=500)


async def get_rows(request: Request) -> Response:
    try:
        params = dict(request.query_params)
        result = data_service.query_rows(
            request.path_params["db"],
            request.path_params["name"],
            limit=int(params.get("limit", 100)),
            offset=int(params.get("offset", 0)),
            order=params.get("order", "desc"),
        )
        return _json_response(result)
    except ValueError as e:
        return _error_response(str(e), status=404)
    except Exception as e:
        return _error_response(str(e), status=500)


async def insert_row(request: Request) -> Response:
    try:
        require_write_key(_write_key(request))
        payload = await _read_json(request)
        actor = _actor_from(payload, dict(request.query_params))
        row = data_service.insert_row(
            request.path_params["db"],
            request.path_params["name"],
            {k: v for k, v in payload.items() if k != "actor"},
            actor=actor,
        )
        return _json_response(row, status=201)
    except PermissionError as e:
        return _error_response(str(e), status=403)
    except ValueError as e:
        return _error_response(str(e))
    except Exception as e:
        return _error_response(str(e), status=500)


async def update_row(request: Request) -> Response:
    try:
        require_write_key(_write_key(request))
        payload = await _read_json(request)
        actor = _actor_from(payload, dict(request.query_params))
        row = data_service.update_row(
            request.path_params["db"],
            request.path_params["name"],
            int(request.path_params["id"]),
            {k: v for k, v in payload.items() if k != "actor"},
            actor=actor,
        )
        return _json_response(row)
    except PermissionError as e:
        return _error_response(str(e), status=403)
    except ValueError as e:
        return _error_response(str(e))
    except Exception as e:
        return _error_response(str(e), status=500)


async def delete_row(request: Request) -> Response:
    try:
        require_write_key(_write_key(request))
        payload = await _read_json_optional(request)
        actor = _actor_from(payload, dict(request.query_params))
        data_service.delete_row(
            request.path_params["db"],
            request.path_params["name"],
            int(request.path_params["id"]),
            actor=actor,
        )
        return _json_response({"deleted_id": int(request.path_params["id"])})
    except PermissionError as e:
        return _error_response(str(e), status=403)
    except ValueError as e:
        return _error_response(str(e))
    except Exception as e:
        return _error_response(str(e), status=500)


async def import_file(request: Request) -> Response:
    try:
        require_write_key(_write_key(request))
        params = dict(request.query_params)
        form = await request.form()
        upload = form.get("file")
        if upload is None:
            return _error_response("Missing file field")
        content = await upload.read()
        filename = upload.filename or "upload.csv"
        mode = params.get("mode", "create")
        actor = validate_actor(str(params.get("actor", "")))
        max_rows = int(params.get("max_rows", 0))
        df = parse_upload(filename, content)
        result = data_service.import_dataframe(
            request.path_params["db"],
            request.path_params["name"],
            df,
            mode=mode,
            actor=actor,
            max_rows=max_rows,
            source_filename=filename,
        )
        return _json_response(result, status=201)
    except PermissionError as e:
        return _error_response(str(e), status=403)
    except ValueError as e:
        return _error_response(str(e))
    except Exception as e:
        return _error_response(str(e), status=500)


async def export_table(request: Request) -> Response:
    try:
        fmt = dict(request.query_params).get("format", "csv")
        content, mime, filename = data_service.export_table(
            request.path_params["db"],
            request.path_params["name"],
            fmt,
        )
        return Response(
            content,
            media_type=mime,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        return _error_response(str(e), status=404)
    except Exception as e:
        return _error_response(str(e), status=500)


async def run_query(request: Request) -> Response:
    try:
        payload = await _read_json(request)
        sql = payload.get("sql", "")
        key = _write_key(request)
        allow_write = False
        try:
            require_write_key(key)
            allow_write = True
        except PermissionError:
            allow_write = False
        actor = payload.get("actor")
        if actor:
            validate_actor(str(actor))
        result = data_service.execute_sql(
            request.path_params["db"],
            sql,
            allow_write=allow_write,
            actor=str(actor) if actor else None,
        )
        return _json_response(result)
    except PermissionError as e:
        return _error_response(str(e), status=403)
    except ValueError as e:
        return _error_response(str(e))
    except Exception as e:
        return _error_response(str(e), status=500)


async def recent_uploads(request: Request) -> Response:
    try:
        limit = int(dict(request.query_params).get("limit", 20))
        return _json_response(data_service.get_recent_uploads(limit))
    except Exception as e:
        return _error_response(str(e), status=500)


async def health(request: Request) -> Response:
    return _json_response(config_status() | {"databases": len(data_service.list_databases())})


def build_api_routes() -> list[Route]:
    routes = [
        ("/api/health", health, ["GET"]),
        ("/api/databases", list_databases, ["GET"]),
        ("/api/databases", create_database, ["POST"]),
        ("/api/databases/{db}", delete_database, ["DELETE"]),
        ("/api/databases/{db}/tables", list_tables, ["GET"]),
        ("/api/databases/{db}/tables", create_table, ["POST"]),
        ("/api/databases/{db}/tables/{name}", delete_table, ["DELETE"]),
        ("/api/databases/{db}/tables/{name}/schema", get_schema, ["GET"]),
        ("/api/databases/{db}/tables/{name}/rows", get_rows, ["GET"]),
        ("/api/databases/{db}/tables/{name}/rows", insert_row, ["POST"]),
        ("/api/databases/{db}/tables/{name}/rows/{id}", update_row, ["PATCH"]),
        ("/api/databases/{db}/tables/{name}/rows/{id}", delete_row, ["DELETE"]),
        ("/api/databases/{db}/import/{name}", import_file, ["POST"]),
        ("/api/databases/{db}/export/{name}", export_table, ["GET"]),
        ("/api/databases/{db}/query", run_query, ["POST"]),
        ("/api/uploads/recent", recent_uploads, ["GET"]),
    ]
    return [Route(path, _with_site_auth(handler), methods=methods) for path, handler, methods in routes]
