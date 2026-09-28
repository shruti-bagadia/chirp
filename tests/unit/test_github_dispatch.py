import httpx
import pytest

from app.core.config import Settings
from app.services import github_dispatch


def _settings(**over) -> Settings:
    fields = {"github_repo": "shruti/chirp", "github_dispatch_token": "tok", **over}
    return Settings(**fields)


def test_is_configured_true_when_both_set():
    assert github_dispatch.is_configured(_settings())


def test_is_configured_false_when_missing_repo():
    assert not github_dispatch.is_configured(_settings(github_repo=""))


def test_is_configured_false_when_missing_token():
    assert not github_dispatch.is_configured(_settings(github_dispatch_token=""))


def test_dispatch_find_raises_without_config():
    with pytest.raises(github_dispatch.DispatchError):
        github_dispatch.dispatch_find(Settings())


def test_dispatch_find_success(monkeypatch):
    seen = {}

    def fake_post(url, json, headers, timeout):
        seen["url"], seen["json"], seen["headers"] = url, json, headers
        return httpx.Response(204, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    github_dispatch.dispatch_find(_settings())
    assert seen["url"] == (
        "https://api.github.com/repos/shruti/chirp/actions/workflows/find.yml/dispatches"
    )
    assert seen["json"] == {"ref": "main"}
    assert seen["headers"]["Authorization"] == "Bearer tok"


def test_dispatch_find_raises_on_non_204(monkeypatch):
    def fake_post(url, json, headers, timeout):
        return httpx.Response(404, request=httpx.Request("POST", url), text="not found")

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(github_dispatch.DispatchError):
        github_dispatch.dispatch_find(_settings())
