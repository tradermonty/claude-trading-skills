"""Issue #778: constant-attribute and local-delegation timeout proofs.

The collector may accept ``timeout=self.<attr>`` only when the attribute is a
single finite literal assigned in ``__init__`` and nothing in the whole skill
can reassign it. A call into a local module counts as bounded only when that
module itself is fully proven. Anything that cannot be traced stays a gap.
"""

import importlib.util
from pathlib import Path

import pytest

CLIENT = """\
import requests


class Client:
    def __init__(self):
        self.timeout = 30
        self.session = requests.Session()

    def fetch(self, url):
        return self.session.get(url, timeout=self.timeout)
"""


@pytest.fixture
def collector():
    path = Path(__file__).resolve().parents[1] / "backfill_security_review.py"
    spec = importlib.util.spec_from_file_location("security_timeout_proof_collector", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def skill(tmp_path, files):
    root = tmp_path / "skills" / "probe"
    for name, body in files.items():
        target = root / "scripts" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    (root / "requirements.txt").write_text("requests\n", encoding="utf-8")
    return tmp_path


def checks(collector, tmp_path, files):
    return collector.mechanical_checks("probe", skill(tmp_path, files))


# ---------- constant-attribute proof ----------


def test_init_literal_attribute_timeout_is_proven(collector, tmp_path):
    result = checks(collector, tmp_path, {"client.py": CLIENT})

    assert result["network_timeout_findings"] == []
    assert result["network_applicability"] == "network"
    assert all(call["bounded"] for call in result["network_calls"])


@pytest.mark.parametrize(
    "init_line",
    [
        "self.timeout = timeout",
        "self.timeout = None",
        "self.timeout = 0",
        "self.timeout = 1e999",
        "self.timeout = True",
        "self.timeout = (5, None)",
    ],
)
def test_non_literal_or_unbounded_init_value_is_not_proof(collector, tmp_path, init_line):
    body = CLIENT.replace("self.timeout = 30", init_line).replace(
        "def __init__(self):", "def __init__(self, timeout=30):"
    )

    result = checks(collector, tmp_path, {"client.py": body})

    assert result["network_timeout_findings"]


@pytest.mark.parametrize(
    "extra",
    [
        # second assignment in another method
        "\n    def reset(self):\n        self.timeout = None\n",
        # augmented assignment
        "\n    def bump(self):\n        self.timeout += 1\n",
        # deletion
        "\n    def drop(self):\n        del self.timeout\n",
        # dynamic attribute write
        "\n    def poke(self, name):\n        setattr(self, name, None)\n",
        # literal setattr of the same attribute
        "\n    def poke(self):\n        setattr(self, 'timeout', None)\n",
        # instance dict mutation
        "\n    def poke(self):\n        self.__dict__['timeout'] = None\n",
        # property shadowing the attribute name
        "\n    @property\n    def timeout(self):\n        return None\n",
    ],
)
def test_any_other_write_in_the_class_is_not_proof(collector, tmp_path, extra):
    result = checks(collector, tmp_path, {"client.py": CLIENT + extra})

    assert result["network_timeout_findings"]


@pytest.mark.parametrize(
    "consumer",
    [
        "from client import Client\nc = Client()\nc.timeout = None\n",
        "import client\nclient.Client.timeout = None\n",
        "from client import Client\nclass Sub(Client):\n    timeout = None\n",
        "from client import Client\nfor c.timeout in [None]:\n    pass\n",
    ],
)
def test_a_write_anywhere_in_the_skill_is_not_proof(collector, tmp_path, consumer):
    result = checks(collector, tmp_path, {"client.py": CLIENT, "main.py": consumer})

    assert any(f.startswith("scripts/client.py") for f in result["network_timeout_findings"])


def test_unparseable_sibling_blocks_the_attribute_proof(collector, tmp_path):
    result = checks(collector, tmp_path, {"client.py": CLIENT, "broken.py": "def (:\n"})

    assert any(f.startswith("scripts/client.py") for f in result["network_timeout_findings"])


@pytest.mark.parametrize(
    "body",
    [
        # assignment is conditional, not a top-level __init__ statement
        CLIENT.replace(
            "        self.timeout = 30\n", "        if flag:\n            self.timeout = 30\n"
        ),
        # receiver is not self
        CLIENT.replace("timeout=self.timeout", "timeout=other.timeout"),
        # self rebound inside the method
        CLIENT.replace(
            "        return self.session.get",
            "        self = other\n        return self.session.get",
        ),
        # staticmethod: the first parameter is not the instance
        CLIENT.replace("    def fetch(self, url):", "    @staticmethod\n    def fetch(self, url):"),
    ],
)
def test_untraceable_receiver_or_assignment_is_not_proof(collector, tmp_path, body):
    result = checks(collector, tmp_path, {"client.py": body})

    assert result["network_timeout_findings"]


def test_attribute_from_another_class_is_not_proof(collector, tmp_path):
    body = CLIENT + (
        "\n\nclass Other:\n"
        "    def __init__(self):\n"
        "        self.session = requests.Session()\n\n"
        "    def fetch(self, url):\n"
        "        return self.session.get(url, timeout=self.timeout)\n"
    )

    result = checks(collector, tmp_path, {"client.py": body})

    assert any("client.py:" in f for f in result["network_timeout_findings"])


# ---------- local delegation proof ----------

FMP_CLIENT = """\
import requests


class FMPClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.session = requests.Session()

    def get_quote(self, symbol):
        return self.session.get("https://example.invalid", timeout=30)
"""

CONSUMER = "from fmp_client import FMPClient\nclient = FMPClient(key)\nclient.get_quote('X')\n"


def test_delegation_to_a_proven_local_client_is_proven(collector, tmp_path):
    result = checks(collector, tmp_path, {"fmp_client.py": FMP_CLIENT, "screen.py": CONSUMER})

    assert result["network_timeout_findings"] == []
    assert any(call.get("delegated_to") == "fmp_client" for call in result["network_calls"])


def test_module_import_delegation_is_proven(collector, tmp_path):
    consumer = "import fmp_client\nclient = fmp_client.FMPClient(key)\n"

    result = checks(collector, tmp_path, {"fmp_client.py": FMP_CLIENT, "screen.py": consumer})

    assert result["network_timeout_findings"] == []


@pytest.mark.parametrize(
    "client_body",
    [
        FMP_CLIENT.replace(", timeout=30", ""),
        FMP_CLIENT.replace(
            "import requests\n",
            "import importlib\nimport requests\nimportlib.import_module('x')\n",
        ),
        "def make():\n    return __import__('requests')\n",
    ],
)
def test_delegation_to_an_unproven_local_module_stays_a_gap(collector, tmp_path, client_body):
    result = checks(collector, tmp_path, {"fmp_client.py": client_body, "screen.py": CONSUMER})

    assert any(f.startswith("scripts/screen.py") for f in result["network_timeout_findings"])


def test_delegation_to_a_missing_module_stays_a_gap(collector, tmp_path):
    result = checks(collector, tmp_path, {"screen.py": CONSUMER})

    assert any(f.startswith("scripts/screen.py") for f in result["network_timeout_findings"])


def test_reaching_through_a_proven_module_is_not_delegation(collector, tmp_path):
    consumer = "import fmp_client\nfmp_client.requests.get(url)\n"

    result = checks(collector, tmp_path, {"fmp_client.py": FMP_CLIENT, "screen.py": consumer})

    assert any(f.startswith("scripts/screen.py") for f in result["network_timeout_findings"])


def test_ambiguous_local_module_name_stays_a_gap(collector, tmp_path):
    files = {"fmp_client.py": FMP_CLIENT, "sub/fmp_client.py": FMP_CLIENT, "screen.py": CONSUMER}

    result = checks(collector, tmp_path, files)

    assert any(f.startswith("scripts/screen.py") for f in result["network_timeout_findings"])


def test_mutual_delegation_without_requests_stays_a_gap(collector, tmp_path):
    files = {
        "a_fmp_client.py": "from b_fmp_client import B\nB()\n",
        "b_fmp_client.py": "from a_fmp_client import A\nA()\n",
    }

    result = checks(collector, tmp_path, files)

    assert result["network_timeout_findings"]


def test_consumer_mutating_the_delegated_timeout_breaks_both_proofs(collector, tmp_path):
    client = CLIENT.replace("class Client", "class FMPClient")
    consumer = CONSUMER + "client.timeout = None\n"

    result = checks(collector, tmp_path, {"fmp_client.py": client, "screen.py": consumer})

    findings = result["network_timeout_findings"]
    assert any(f.startswith("scripts/fmp_client.py") for f in findings)
    assert any(f.startswith("scripts/screen.py") for f in findings)


# ---------- adversarial review regressions ----------

HTTP_CLIENT = """\
import requests


class FMPClient:
    def __init__(self):
        self.timeout = 30
        self.http = requests.Session()

    def fetch(self, url):
        return self.http.get(url, timeout=self.timeout)
"""


def test_http_client_delegation_baseline_is_proven(collector, tmp_path):
    consumer = "from fmp_client import FMPClient\nc = FMPClient()\nc.fetch('u')\n"

    result = checks(collector, tmp_path, {"fmp_client.py": HTTP_CLIENT, "x.py": consumer})

    assert result["network_timeout_findings"] == []


@pytest.mark.parametrize(
    "prefix, consumer",
    [
        ("from requests import get\n", "from fmp_client import get\nget('http://x')\n"),
        ("from requests import get\n", "import fmp_client\nfmp_client.get('http://x')\n"),
        (
            "from urllib.request import urlopen\n",
            "from fmp_client import urlopen\nurlopen('http://x')\n",
        ),
        ("from requests import Session\n", "import fmp_client\nfmp_client.Session().get('u')\n"),
        (
            "from requests import Session\n",
            "import fmp_client\ns = fmp_client.Session()\ns.get('u')\n",
        ),
    ],
)
def test_re_exported_network_symbol_is_not_delegation(collector, tmp_path, prefix, consumer):
    files = {"fmp_client.py": prefix + HTTP_CLIENT, "x.py": consumer}

    result = checks(collector, tmp_path, files)

    assert any(f.startswith("scripts/x.py") for f in result["network_timeout_findings"])


@pytest.mark.parametrize(
    "consumer",
    [
        "import fmp_client\nc = fmp_client.FMPClient()\nc.http.get('u')\n",
        "from fmp_client import FMPClient\nFMPClient().http.get('u')\n",
        # a parameter of unknown type reaching the provider's client attribute
        "def run(client):\n    return client.http.get('u')\n",
    ],
)
def test_reaching_a_delegated_client_attribute_is_a_gap(collector, tmp_path, consumer):
    files = {"fmp_client.py": HTTP_CLIENT, "x.py": consumer}

    result = checks(collector, tmp_path, files)

    assert any(f.startswith("scripts/x.py") for f in result["network_timeout_findings"])


def test_provider_returning_a_network_module_is_not_proven(collector, tmp_path):
    provider = HTTP_CLIENT + "\n\ndef lib():\n    return requests\n"
    consumer = "import fmp_client\nfmp_client.lib().get('u')\n"

    result = checks(collector, tmp_path, {"fmp_client.py": provider, "x.py": consumer})

    findings = result["network_timeout_findings"]
    assert any(f.startswith("scripts/fmp_client.py") for f in findings)
    assert any(f.startswith("scripts/x.py") for f in findings)


def test_optional_import_availability_check_is_not_an_escape(collector, tmp_path):
    body = "try:\n    import requests\nexcept ImportError:\n    requests = None\n" + (
        "\n\ndef fetch(url):\n    if requests is None or not requests:\n        return None\n"
        "    return requests.get(url, timeout=5)\n"
    )

    result = checks(collector, tmp_path, {"client.py": body})

    assert not any("escapes as a value" in f for f in result["network_timeout_findings"])


def test_type_annotations_are_not_escapes(collector, tmp_path):
    consumer = (
        "from fmp_client import FMPClient\n\n\n"
        "def run(client: FMPClient | None = None) -> FMPClient:\n"
        "    held: FMPClient = client or FMPClient()\n"
        "    held.fetch('u')\n"
        "    return held\n"
    )

    result = checks(collector, tmp_path, {"fmp_client.py": HTTP_CLIENT, "x.py": consumer})

    assert result["network_timeout_findings"] == []


SUBCLASS = "from fmp_client import FMPClient\n\n\nclass My(FMPClient):\n"


def test_subclass_using_only_bounded_base_methods_is_proven(collector, tmp_path):
    consumer = SUBCLASS + "    def go(self, url):\n        return self.fetch(url)\n"

    result = checks(collector, tmp_path, {"fmp_client.py": HTTP_CLIENT, "x.py": consumer})

    assert result["network_timeout_findings"] == []


@pytest.mark.parametrize(
    "body",
    [
        # reaching the base's raw client without a timeout
        "    def go(self, url):\n        return self.http.get(url)\n",
        # attribute-lookup hooks
        "    def __getattr__(self, k):\n        return None\n",
        "    __slots__ = ()\n",
    ],
)
def test_subclass_reaching_or_hooking_the_base_is_a_gap(collector, tmp_path, body):
    result = checks(collector, tmp_path, {"fmp_client.py": HTTP_CLIENT, "x.py": SUBCLASS + body})

    assert any(f.startswith("scripts/x.py") for f in result["network_timeout_findings"])


def test_subclass_metaclass_is_a_gap(collector, tmp_path):
    consumer = "from fmp_client import FMPClient\n\n\nclass My(FMPClient, metaclass=M):\n    pass\n"

    result = checks(collector, tmp_path, {"fmp_client.py": HTTP_CLIENT, "x.py": consumer})

    assert any(f.startswith("scripts/x.py") for f in result["network_timeout_findings"])


def test_closing_a_delegated_session_is_not_a_request(collector, tmp_path):
    consumer = "from fmp_client import FMPClient\nc = FMPClient()\nc.fetch('u')\nc.http.close()\n"

    result = checks(collector, tmp_path, {"fmp_client.py": HTTP_CLIENT, "x.py": consumer})

    assert result["network_timeout_findings"] == []


@pytest.mark.parametrize(
    "consumer",
    [
        "def f(c):\n    s = setattr\n    s(c, 'timeout', None)\n",
        "import builtins\n\n\ndef f(c):\n    builtins.setattr(c, 'timeout', None)\n",
        "def f(c):\n    getattr(__builtins__, 'setattr')(c, 'timeout', None)\n",
        "import functools\nf = functools.partial(setattr, None)\n",
    ],
)
def test_indirect_setattr_poisons_the_attribute_proof(collector, tmp_path, consumer):
    result = checks(collector, tmp_path, {"client.py": CLIENT, "x.py": consumer})

    assert any(f.startswith("scripts/client.py") for f in result["network_timeout_findings"])


def test_package_init_writes_are_in_scope(collector, tmp_path):
    files = {
        "client.py": CLIENT,
        "pkg/__init__.py": "import client\nclient.Client.timeout = None\n",
    }

    result = checks(collector, tmp_path, files)

    assert any(f.startswith("scripts/client.py") for f in result["network_timeout_findings"])


@pytest.mark.parametrize(
    "extra",
    [
        "\n    def __getattribute__(self, k):\n        return object.__getattribute__(self, k)\n",
        "\n    def __getattr__(self, k):\n        return None\n",
        "\n    def __setattr__(self, k, v):\n        pass\n",
        "\n    __slots__ = ('session',)\n",
    ],
)
def test_attribute_hooks_defeat_the_attribute_proof(collector, tmp_path, extra):
    result = checks(collector, tmp_path, {"client.py": CLIENT + extra})

    assert result["network_timeout_findings"]


@pytest.mark.parametrize(
    "header",
    ["class Client(Base):", "class Client(metaclass=Meta):", "@decorate\nclass Client:"],
)
def test_bases_metaclasses_and_decorators_defeat_the_attribute_proof(collector, tmp_path, header):
    body = CLIENT.replace("class Client:", header)

    result = checks(collector, tmp_path, {"client.py": body})

    assert result["network_timeout_findings"]


# ---------- adversarial review round 2 ----------

LITERAL_HTTP_CLIENT = HTTP_CLIENT.replace("timeout=self.timeout", "timeout=30").replace(
    "        self.timeout = 30\n", ""
)
BOUNDED = "import requests\nrequests.get('http://ok', timeout=5)\n"


@pytest.mark.parametrize(
    "body",
    [
        BOUNDED + "(requests or None).get('http://x')\n",
        BOUNDED + "r = requests or None\nr.get('http://x')\n",
        BOUNDED + "r = requests if flag else None\n",
        BOUNDED + "def f(a: (r := requests) = 1):\n    pass\n",
        BOUNDED + "ok = requests == other\n",
    ],
)
def test_network_name_passed_on_through_an_expression_is_a_gap(collector, tmp_path, body):
    result = checks(collector, tmp_path, {"x.py": body})

    assert any("escapes as a value" in f for f in result["network_timeout_findings"])


@pytest.mark.parametrize(
    "consumer",
    [
        "getattr(c, 'ht' + 'tp').get('http://x')\n",
        "getattr(c, 'http').get('http://x')\n",
        "c.__dict__['http'].get('http://x')\n",
        "vars(c)['http'].get('http://x')\n",
        "import operator\noperator.attrgetter('http')(c).get('http://x')\n",
        "from operator import attrgetter\nattrgetter('http')(c).get('http://x')\n",
        "c.http.adapters['https://'].send(None)\n",
        "a = c.http.adapters\na['https://'].send(None)\n",
        "c.http.mount('https://', adapter)\n",
        "name = 'http'\nc.__getattribute__(name).get('http://x')\n",
    ],
)
def test_dynamic_or_adapter_reach_into_a_delegated_client_is_a_gap(collector, tmp_path, consumer):
    prefix = "import fmp_client\nc = fmp_client.FMPClient()\nc.fetch('u')\n"
    files = {"fmp_client.py": LITERAL_HTTP_CLIENT, "x.py": prefix + consumer}

    result = checks(collector, tmp_path, files)

    assert any(f.startswith("scripts/x.py") for f in result["network_timeout_findings"])


@pytest.mark.parametrize(
    "provider_init, consumer_reach",
    [
        ("        self.a = Holder()\n        self.a.b = requests.Session()\n", "c.a.b.get('u')"),
        (
            "        self.pool = {}\n        self.pool['h'] = requests.Session()\n",
            "c.pool['h'].get('u')",
        ),
    ],
)
def test_nested_and_subscript_clients_are_registered(
    collector, tmp_path, provider_init, consumer_reach
):
    provider = (
        "import requests\n\n\nclass FMPClient:\n    def __init__(self):\n"
        + provider_init
        + "\n    def fetch(self, url):\n        return requests.get(url, timeout=30)\n"
    )
    consumer = (
        "import fmp_client\nc = fmp_client.FMPClient()\nc.fetch('u')\n" + consumer_reach + "\n"
    )

    result = checks(collector, tmp_path, {"fmp_client.py": provider, "x.py": consumer})

    assert any(f.startswith("scripts/x.py") for f in result["network_timeout_findings"])


def test_class_body_client_is_checked_in_provider_and_consumer(collector, tmp_path):
    provider = (
        "import requests\n\n\nclass FMPClient:\n    http = requests.Session()\n\n"
        "    def fetch(self, url):\n        return self.http.get(url)\n"
    )
    consumer = "import fmp_client\nc = fmp_client.FMPClient()\nc.http.get('u')\n"

    result = checks(collector, tmp_path, {"fmp_client.py": provider, "x.py": consumer})

    findings = result["network_timeout_findings"]
    assert any(f.startswith("scripts/fmp_client.py") for f in findings)
    assert any(f.startswith("scripts/x.py") for f in findings)


@pytest.mark.parametrize(
    "subclass",
    [
        "class Sub(Client):\n    def __getattribute__(self, k):\n        return None\n",
        "class Sub(Client, metaclass=Meta):\n    pass\n",
    ],
)
def test_hooked_subclass_of_a_proven_class_poisons_the_proof(collector, tmp_path, subclass):
    consumer = "from client import Client\n\n\n" + subclass + "\nSub().fetch('http://x')\n"

    result = checks(collector, tmp_path, {"client.py": CLIENT, "x.py": consumer})

    assert any(f.startswith("scripts/client.py") for f in result["network_timeout_findings"])


def test_literal_getattr_for_a_close_check_is_allowed(collector, tmp_path):
    consumer = (
        "import fmp_client\nc = fmp_client.FMPClient()\nc.fetch('u')\n"
        "close = getattr(c, 'fetch', None)\nc.http.headers['x'] = '1'\nc.http.close()\n"
    )

    result = checks(collector, tmp_path, {"fmp_client.py": LITERAL_HTTP_CLIENT, "x.py": consumer})

    assert result["network_timeout_findings"] == []
