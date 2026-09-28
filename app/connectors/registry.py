"""Platform -> connector lookup."""

from __future__ import annotations

from app.connectors.ashby import AshbyConnector
from app.connectors.base import Connector
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.lever import LeverConnector
from app.connectors.workday import WorkdayConnector

CONNECTORS: dict[str, Connector] = {
    "greenhouse": GreenhouseConnector(),
    "lever": LeverConnector(),
    "ashby": AshbyConnector(),
    # A large global tenant (Accenture, NVIDIA, ...) can have thousands of postings;
    # the connector caps out at 500 (see MAX_PAGES), taken in whatever order Workday
    # returns them, so an unfiltered fetch can miss India postings entirely on big
    # tenants. "India" (not "Pune") keeps the query broad enough to still catch
    # remote-India postings — the prefilter's own location check narrows to
    # Pune/remote-India from there, same as it always has.
    "workday": WorkdayConnector(search_text="India"),
}


def connector_for(platform: str) -> Connector | None:
    return CONNECTORS.get(str(platform))
