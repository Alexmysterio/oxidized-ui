from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from .errors import AppError
from .models import SystemSettings
from .settings import settings
from .timeutil import parse_oxidized_time

MAX_CONFIG_CONTENT = 5_000_000


@dataclass(slots=True)
class OxidizedNode:
    name: str
    full_name: str
    address: str | None
    group: str | None
    model: str | None
    status: str | None
    last_started: Any | None
    last_finished: Any | None
    last_time: float | None
    mtime: Any | None


@dataclass(slots=True)
class OxidizedVersion:
    oid: str
    time: Any | None
    author: str | None
    message: str | None


def effective_api_url(db: Session | None = None) -> str:
    if db is not None:
        row = db.get(SystemSettings, 1)
        if row and row.oxidized_api_url:
            return row.oxidized_api_url
    return settings.oxidized_api_url


class OxidizedClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.oxidized_api_url).rstrip("/")
        self.timeout = httpx.Timeout(
            settings.oxidized_read_timeout,
            connect=settings.oxidized_connect_timeout,
        )

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            follow_redirects=False,
            headers={"Accept": "application/json"},
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            with self._client() as client:
                response = client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise AppError("oxidized.timeout") from exc
        except httpx.RequestError as exc:
            raise AppError("oxidized.unavailable") from exc
        if response.status_code >= 400:
            raise AppError(
                "oxidized.bad_response",
                params={"status": response.status_code, "operation": path.split("?")[0][:80]},
            )
        return response

    def _json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise AppError("oxidized.bad_response", params={"reason": "invalid_json"}) from exc

    def list_nodes(self) -> list[OxidizedNode]:
        response = self._request("GET", "/nodes.json")
        payload = self._json(response)
        if not isinstance(payload, list):
            raise AppError("oxidized.bad_response", params={"reason": "nodes_not_list"})
        nodes: list[OxidizedNode] = []
        for item in payload:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            last = item.get("last") if isinstance(item.get("last"), dict) else None
            status = last.get("status") if last else None
            nodes.append(
                OxidizedNode(
                    name=str(item.get("name")),
                    full_name=str(item.get("full_name") or item.get("name")),
                    address=str(item["ip"]) if item.get("ip") else None,
                    group=str(item["group"]) if item.get("group") else None,
                    model=str(item["model"]) if item.get("model") else None,
                    status=str(status) if status else None,
                    last_started=parse_oxidized_time(last.get("start")) if last else None,
                    last_finished=parse_oxidized_time(last.get("end")) if last else None,
                    last_time=float(last["time"]) if last and last.get("time") is not None else None,
                    mtime=parse_oxidized_time(item.get("mtime")),
                )
            )
        return nodes

    def reload(self) -> None:
        self._request("GET", "/reload.json")

    def next_node(self, name: str) -> None:
        self._request("GET", f"/node/next/{quote(name, safe='')}.json")

    def fetch_config(self, name: str, group: str | None = None) -> str:
        if group == "default":
            group = None
        if group:
            path = f"/node/fetch/{quote(group, safe='')}/{quote(name, safe='')}.json"
        else:
            path = f"/node/fetch/{quote(name, safe='')}.json"
        response = self._request("GET", path)
        return self._content_from_response(response)

    def versions(self, name: str, group: str | None = None) -> list[OxidizedVersion]:
        if group == "default":
            group = None
        node_full = f"{group}/{name}" if group else name
        response = self._request(
            "GET",
            "/node/version",
            params={"format": "json", "node_full": node_full},
        )
        payload = self._json(response)
        if payload is None:
            return []
        if not isinstance(payload, list):
            return []
        result: list[OxidizedVersion] = []
        for item in payload:
            if not isinstance(item, dict) or not item.get("oid"):
                continue
            author = item.get("author")
            if isinstance(author, dict):
                author = author.get("name") or author.get("email")
            result.append(
                OxidizedVersion(
                    oid=str(item["oid"]),
                    time=parse_oxidized_time(item.get("time")),
                    author=str(author) if author else None,
                    message=str(item["message"]) if item.get("message") else None,
                )
            )
        return result

    def version_content(
        self,
        name: str,
        group: str | None,
        oid: str,
        *,
        epoch: int | None = None,
        num: int | None = None,
    ) -> str:
        if group == "default":
            group = None
        params: dict[str, Any] = {
            "format": "json",
            "node": name,
            "group": group or "",
            "oid": oid,
            "epoch": epoch or 0,
            "num": num or 0,
        }
        response = self._request("GET", "/node/version/view", params=params)
        return self._content_from_response(response)

    def _content_from_response(self, response: httpx.Response) -> str:
        if len(response.content) > MAX_CONFIG_CONTENT:
            raise AppError("config.content_too_large")
        payload = self._json(response)
        if isinstance(payload, list):
            lines = [str(line).rstrip("\n") for line in payload]
            text = "\n".join(lines)
            if text.strip() in {"node not found", "version not found"}:
                reason = text.strip().replace(" ", "_")
                raise AppError("oxidized.bad_response", params={"reason": reason})
            return text + ("\n" if text else "")
        if isinstance(payload, str):
            if payload.strip() in {"node not found", "version not found"}:
                reason = payload.strip().replace(" ", "_")
                raise AppError("oxidized.bad_response", params={"reason": reason})
            return payload
        raise AppError("oxidized.bad_response", params={"reason": "content_not_text"})

    def search_configs(self, query: str) -> list[dict[str, str]]:
        response = self._request(
            "POST",
            "/nodes/conf_search.json",
            data={"search_in_conf_textbox": query},
        )
        payload = self._json(response)
        if not isinstance(payload, list):
            raise AppError("oxidized.bad_response", params={"reason": "search_not_list"})
        result: list[dict[str, str]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            node = item.get("node")
            full_name = item.get("full_name") or node
            if node:
                result.append({"name": str(node), "full_name": str(full_name)})
        return result

    def online(self) -> bool:
        try:
            self.list_nodes()
            return True
        except AppError:
            return False


def client_for(db: Session | None = None) -> OxidizedClient:
    return OxidizedClient(effective_api_url(db))


def find_node(nodes: list[OxidizedNode], name: str) -> OxidizedNode | None:
    return next((node for node in nodes if node.name == name), None)


def get_effective_group(db: Session, name: str) -> str | None:
    node = find_node(client_for(db).list_nodes(), name)
    return node.group if node else None
