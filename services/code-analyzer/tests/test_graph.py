from tests.test_api import make_zip, upload

SHOP = {
    "src/payment/PaymentMethod.java": """
package shop.payment;
public interface PaymentMethod {
    double pay(double amount);
}
""",
    "src/payment/CardPayment.java": """
package shop.payment;
public class CardPayment implements PaymentMethod {
    public double pay(double amount) { return amount * 1.02; }
}
""",
    "src/payment/CashPayment.java": """
package shop.payment;
public class CashPayment implements PaymentMethod {
    public double pay(double amount) { return amount; }
}
""",
    "src/payment/PaymentFactory.java": """
package shop.payment;
public class PaymentFactory {
    public PaymentMethod createPayment(String type) {
        if (type.equals("card")) { return new CardPayment(); }
        return new CashPayment();
    }
}
""",
    "src/db/Database.java": """
package shop.db;
public class Database {
    private static Database instance;
    private Database() {}
    public static Database getInstance() {
        if (instance == null) { instance = new Database(); }
        return instance;
    }
    public void execute(String sql) {}
}
""",
    "src/db/OrderRepository.java": """
package shop.db;
public class OrderRepository {
    public void saveOrder(int id, double total) {
        Database.getInstance().execute("INSERT INTO orders (id, total) VALUES (?, ?)");
    }
    public double totalFor(int customer) {
        Database.getInstance().execute("SELECT sum(total) FROM orders o JOIN customers c ON c.id = o.customer_id");
        return 0;
    }
}
""",
    "src/OrderService.java": """
package shop;
import shop.db.OrderRepository;
import shop.payment.PaymentFactory;
public class OrderService {
    public double checkout(int id, double amount, String type) {
        OrderRepository repository = new OrderRepository();
        EmailService email = new EmailService();
        double paid = new PaymentFactory().createPayment(type).pay(amount);
        repository.saveOrder(id, paid);
        email.sendReceipt(id);
        return paid;
    }
    public String describe(Object item) {
        if (item instanceof String) return "text";
        if (item instanceof Integer) return "number";
        if (item instanceof Double) return "decimal";
        if (item instanceof Boolean) return "flag";
        return "other";
    }
}
""",
    "src/EmailService.java": """
package shop;
public class EmailService {
    public void sendReceipt(int orderId) {}
}
""",
    "src/ReadOnlyRepository.java": """
package shop;
import shop.db.OrderRepository;
public class ReadOnlyRepository extends OrderRepository {
    public void saveOrder(int id, double total) {
        throw new UnsupportedOperationException("read only");
    }
}
""",
    "tools/a.py": "from tools import b\n\ndef first():\n    return b.second()\n",
    "tools/b.py": "from tools import a\n\ndef second():\n    return a.first()\n",
    "tools/__init__.py": "",
}


def graph():
    return upload(make_zip(SHOP)).json()["code"]["graph"]


def test_nodes_and_edges():
    g = graph()
    assert g["stats"]["nodes"]["class"] == 9
    assert g["stats"]["nodes"]["table"] == 2
    edges = {
        (e["source"].split(":")[-1], e["target"].split(":")[-1], e["type"]) for e in g["edges"]
    }
    assert ("CardPayment", "PaymentMethod", "implements") in edges
    assert ("ReadOnlyRepository", "OrderRepository", "extends") in edges
    assert ("OrderService.checkout", "OrderRepository.saveOrder", "calls") in edges
    assert ("OrderService.checkout", "EmailService", "creates") in edges
    assert ("OrderRepository.totalFor", "customers", "uses_table") in edges
    # `execute` is too generic to link... unless there is only one: Database.execute
    assert ("OrderRepository.saveOrder", "Database.getInstance", "calls") in edges


def test_dependencies():
    deps = graph()["dependencies"]
    assert ["tools/a.py", "tools/b.py"] in [sorted(c) for c in deps["file_cycles"]]
    key = {k["name"]: k["used_by"] for k in deps["key_components"]}
    assert key["Database.getInstance"] == 2
    assert {t["table"]: t["used_by"] for t in deps["tables"]}["orders"] == [
        "OrderRepository.saveOrder", "OrderRepository.totalFor",
    ]  # fmt: skip
    service = next(c for c in deps["coupling"] if c["class"] == "OrderService")
    assert service["efferent"] >= 3 and service["instability"] == 1.0


def test_design_patterns():
    patterns = {(p["pattern"], p["classes"][0]) for p in graph()["design_patterns"]}
    assert ("Singleton", "Database") in patterns
    assert ("Factory", "PaymentFactory") in patterns
    assert ("Repository", "OrderRepository") in patterns
    assert ("Strategy / Polymorphism", "PaymentMethod") in patterns
    assert not any(p[0] == "Singleton" and p[1] != "Database" for p in patterns)


def test_solid():
    result = graph()["solid"]
    assert result["counts"] == {"DIP": 1, "LSP": 1, "OCP": 1}
    issues = {(i["principle"], i["where"]) for i in result["issues"]}
    assert ("DIP", "OrderService") in issues  # creates OrderRepository and EmailService
    assert ("LSP", "ReadOnlyRepository.saveOrder") in issues
    assert ("OCP", "OrderService.describe") in issues
    assert all(i["evidence_ar"] and "weight" not in i for i in result["issues"])


def test_python_and_javascript_projects():
    files = {
        "app/models.py": "class Student:\n    def __init__(self, name):\n        self.name = name\n",
        "app/views.py": "from app.models import Student\n\ndef register(name):\n    s = Student(name)\n"
        "    db.execute('INSERT INTO students (name) VALUES (?)', (name,))\n    return s\n",
        "web/api.js": "import { fmt } from './util';\nexport function show(x) { return fmt(x); }\n",
        "web/util.js": "export function fmt(x) { return String(x); }\n",
    }
    g = upload(make_zip(files)).json()["code"]["graph"]
    edges = {
        (e["source"].split(":")[-1], e["target"].split(":")[-1], e["type"]) for e in g["edges"]
    }
    assert ("register", "Student", "creates") in edges
    assert ("register", "students", "uses_table") in edges
    assert "web/views.py" not in str(edges)
    sources = {(e["source"], e["target"]) for e in g["edges"] if e["type"] == "imports"}
    assert ("file:app/views.py", "file:app/models.py") in sources
    assert ("file:web/api.js", "file:web/util.js") in sources
    assert ("show", "fmt", "calls") in edges
