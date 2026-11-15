"""Hand-written project sources used by the tests."""

LIBRARY = {
    "library/loans.py": '''
from datetime import date


class LoanService:
    """Handles borrowing and returning books."""

    def __init__(self, repository, clock=date.today):
        self.repository = repository
        self.clock = clock

    def borrow(self, student_id, book_id):
        book = self.repository.find_book(book_id)
        if book is None:
            raise ValueError("unknown book")
        if book.copies_available <= 0:
            raise RuntimeError("no copies left")
        active = self.repository.active_loans(student_id)
        if len(active) >= 3:
            raise RuntimeError("loan limit reached")
        book.copies_available -= 1
        return self.repository.create_loan(student_id, book_id, self.clock())

    def calculate_fine(self, loan, rate=50):
        days_late = (self.clock() - loan.due_date).days
        if days_late <= 0:
            return 0
        total = 0
        for day in range(days_late):
            if day < 7:
                total += rate
            elif day < 30:
                total += rate * 2
            else:
                total += rate * 3
        return total
''',
    "library/search.py": """
def search_books(books, text, available_only=False):
    words = [w.lower() for w in text.split() if w]
    results = []
    for book in books:
        title = book.title.lower()
        score = sum(1 for w in words if w in title)
        if score == 0:
            continue
        if available_only and book.copies_available == 0:
            continue
        results.append((score, book))
    results.sort(key=lambda pair: (-pair[0], pair[1].title))
    return [book for _, book in results]
""",
}

# The same project, disguised: every identifier renamed, comments changed, reformatted.
LIBRARY_DISGUISED = {
    "src/borrowing.py": """
from datetime import date


class BorrowManager:
    # manages the lending of items
    def __init__(self, store, today=date.today):
        self.store = store
        self.today = today

    def lend(self, member, item):
        obj = self.store.get_item(item)
        if obj is None:
            raise ValueError("not found")
        if obj.stock <= 0:
            raise RuntimeError("out of stock")
        current = self.store.open_loans(member)
        if len(current) >= 3:
            raise RuntimeError("too many loans")
        obj.stock -= 1
        return self.store.new_loan(member, item, self.today())

    def penalty(self, record, price=50):
        overdue = (self.today() - record.deadline).days
        if overdue <= 0:
            return 0
        amount = 0
        for d in range(overdue):
            if d < 7:
                amount += price
            elif d < 30:
                amount += price * 2
            else:
                amount += price * 3
        return amount
""",
    "src/finder.py": """
def find(catalog, query, only_free=False):
    terms = [t.lower() for t in query.split() if t]
    found = []
    for entry in catalog:
        name = entry.title.lower()
        hits = sum(1 for t in terms if t in name)
        if hits == 0:
            continue
        if only_free and entry.copies_available == 0:
            continue
        found.append((hits, entry))
    found.sort(key=lambda p: (-p[0], p[1].title))
    return [entry for _, entry in found]
""",
}

UNRELATED = {
    "shop/cart.java": """
public class Cart {
    private final java.util.Map<String, Integer> items = new java.util.HashMap<>();

    public void add(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        items.merge(sku, quantity, Integer::sum);
    }

    public int count() {
        int total = 0;
        for (int q : items.values()) {
            total += q;
        }
        return total;
    }

    public double total(java.util.Map<String, Double> prices) {
        double sum = 0;
        for (java.util.Map.Entry<String, Integer> e : items.entrySet()) {
            Double price = prices.get(e.getKey());
            if (price == null) {
                throw new IllegalStateException("missing price for " + e.getKey());
            }
            sum += price * e.getValue();
        }
        return Math.round(sum * 100) / 100.0;
    }
}
""",
}
