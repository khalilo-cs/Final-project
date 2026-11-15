import textwrap

from app.quality.dead_code import java_dead_code, python_dead_code
from app.quality.duplication import find_duplicates

BLOCK = """
def total_for(order, tax_rate):
    subtotal = 0
    for line in order.lines:
        if line.quantity <= 0:
            continue
        subtotal += line.price * line.quantity
    discount = order.discount or 0
    return round((subtotal - discount) * (1 + tax_rate), 2)
"""
RENAMED = (
    BLOCK.replace("total_for", "invoice_sum").replace("order", "cart").replace("subtotal", "acc")
    .replace("line", "item").replace("discount", "promo").replace("tax_rate", "vat")
)  # fmt: skip


def test_copy_paste_found_even_after_renaming():
    result = find_duplicates({"shop/orders.py": BLOCK, "shop/invoices.py": RENAMED,
                              "shop/other.py": "def f():\n    return 1\n"})  # fmt: skip
    (block,) = result["duplicate_blocks"]
    assert {block["file"], block["other_file"]} == {"shop/orders.py", "shop/invoices.py"}
    assert result["code_duplication_percentage"] > 30


def test_a_single_copy_is_not_a_duplicate():
    assert find_duplicates({"a.py": BLOCK})["duplicate_blocks"] == []


def test_python_dead_code_is_conservative():
    sources = {
        "app.py": textwrap.dedent(
            """
            from flask import Flask
            from helpers import used_helper
            app = Flask(__name__)

            @app.route("/")
            def index():          # called by Flask: decorated, never reported
                return used_helper()

            def forgotten():      # nobody calls this
                return 1

            class Service:
                def __init__(self):   # dunder
                    self.ready = True

                def save(self):       # called through an attribute elsewhere
                    return True

                def legacy(self):     # never referenced
                    return False

            def lookup_by_name():     # used through getattr("lookup_by_name")
                return 2
            """
        ),
        "helpers.py": "def used_helper():\n    return getattr(None, 'lookup_by_name', None)\n",
        "jobs.py": "def run_job(service):\n    service.save()\n",
        "test_app.py": "def test_index():\n    assert True\n",
    }
    names = {(d["file"], d["name"]) for d in python_dead_code(sources)}
    # Service itself is never instantiated anywhere in this sample, so it is reported too.
    assert names == {("app.py", "forgotten"), ("app.py", "legacy"), ("app.py", "Service"),
                     ("jobs.py", "run_job")}  # fmt: skip


def test_java_private_methods_never_called():
    source = """
    class Dao {
        public void save() { validate(); }
        private void validate() { }
        private void unused() { }
        @Scheduled private void cron() { }
        private int asRef() { return 1; }
        java.util.function.Supplier<Integer> s = this::asRef;
    }
    """
    assert [d["name"] for d in java_dead_code("Dao.java", source)] == ["unused"]
