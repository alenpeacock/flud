import asyncio
import os
import socket
from contextlib import contextmanager
from dataclasses import dataclass

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--flud-host",
        action="store",
        default=socket.getfqdn(),
        help="Host name or IP for integration suites that talk to a Flud node.",
    )


@pytest.fixture(scope="session")
def flud_host(request):
    return request.config.getoption("--flud-host")


@dataclass
class FludTarget:
    host: str
    port: int
    node: object
    nku: object


@dataclass
class FludCluster:
    host: str
    port: int
    gateway: object
    client: object
    nodes: list


@contextmanager
def _fludhome(home):
    previous = os.environ.get("FLUDHOME")
    os.environ["FLUDHOME"] = str(home)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("FLUDHOME", None)
        else:
            os.environ["FLUDHOME"] = previous


@pytest.fixture
def flud_node(monkeypatch, tmp_path):
    pytest.importorskip("Cryptodome.Cipher")
    from flud.test._standalone import start_test_node

    monkeypatch.setenv("FLUDHOME", str(tmp_path / ".flud"))
    node = start_test_node()
    try:
        yield node
    finally:
        try:
            node.stop()
        except Exception:
            pass


@pytest.fixture
def flud_target(flud_node, flud_host):
    from flud.protocol.FludCommUtil import getCanonicalIP

    host = getCanonicalIP(flud_host)
    port = flud_node.config.port
    nku = asyncio.run(flud_node.client.async_sendGetID(host, port))
    return FludTarget(host=host, port=port, node=flud_node, nku=nku)


@pytest.fixture(scope="session")
def flud_cluster(tmp_path_factory):
    pytest.importorskip("Cryptodome.Cipher")
    from flud.protocol.FludCommUtil import getCanonicalIP
    from flud.test._standalone import start_test_node

    cluster_size = 12
    base_port = 18080
    tmp_path = tmp_path_factory.mktemp("flud-cluster")
    homes = [tmp_path / f".flud{i}" for i in range(cluster_size)]
    nodes = []
    host = getCanonicalIP("127.0.0.1")

    try:
        with _fludhome(homes[0]):
            gateway = start_test_node(base_port)
        nodes.append(gateway)

        for index, home in enumerate(homes[1:], start=1):
            with _fludhome(home):
                node = start_test_node(base_port + index)
            node._async_tasks.append(
                node.async_runtime.submit(
                    node._async_connectViaGateway(host, gateway.config.port)
                )
            )
            node._async_tasks[-1].result(timeout=60.0)
            nodes.append(node)

        client = nodes[-1]
        for peer in nodes[:-1]:
            asyncio.run(client.client.async_sendGetID(host, peer.config.port))
        yield FludCluster(
            host=host,
            port=gateway.config.port,
            gateway=gateway,
            client=client,
            nodes=nodes,
        )
    finally:
        for node in reversed(nodes):
            try:
                node.stop()
            except Exception:
                pass
