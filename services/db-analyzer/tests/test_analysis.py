import textwrap

from app.parsers.schema_parser import parse_schema
from app.services.database_analyzer import analyze_database

LIBRARY = """
-- MySQL dump 10.13  Distrib 8.0.36
/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
DROP TABLE IF EXISTS `authors`;
CREATE TABLE `authors` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `email` varchar(150) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `books` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  `author_id` int NOT NULL,
  `price` decimal(10,2) DEFAULT NULL,
  `published_at` date DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_author` (`author_id`),
  CONSTRAINT `fk_books_author` FOREIGN KEY (`author_id`) REFERENCES `authors` (`id`)
) ENGINE=InnoDB;

LOCK TABLES `books` WRITE;
INSERT INTO `books` VALUES (1,'SQL; the basics',1,10.00,'2020-01-01');
UNLOCK TABLES;
"""


def analyze(sql, dialect="mysql"):
    return analyze_database(textwrap.dedent(sql), dialect)


def issue_types(result):
    return sorted((i["type"], i["table"]) for i in result["issues"])


def test_clean_mysql_dump():
    result = analyze(LIBRARY)
    assert result["total_tables"] == 2
    assert result["issues"] == []
    assert result["normalization_level"] == "BCNF"  # clean schema, no overlapping composite keys
    assert result["overall_db_score"] == 100.0
    books = next(t for t in result["tables"] if t["name"] == "books")
    assert books["primary_key"] == ["id"]
    assert books["foreign_keys"][0]["ref_table"] == "authors"
    assert books["indexes"] == [["author_id"]]
    price = next(c for c in books["columns"] if c["name"] == "price")
    assert (price["base_type"], price["nullable"]) == ("DECIMAL", True)


def test_schema_parser_details():
    schema = parse_schema(
        """
        CREATE TABLE users (id INT PRIMARY KEY, email VARCHAR(50) UNIQUE NOT NULL);
        CREATE TABLE posts (id INT, user_id INT REFERENCES users(id), body TEXT);
        ALTER TABLE posts ADD PRIMARY KEY (id);
        ALTER TABLE posts ADD CONSTRAINT fk_u FOREIGN KEY (user_id) REFERENCES users (id);
        CREATE INDEX idx_body ON posts (body(20));
        """
    )
    users, posts = schema.table("users"), schema.table("posts")
    assert users.primary_key == ["id"] and users.unique == [["email"]]
    assert users.column("email").nullable is False and users.column("email").length == 50
    assert posts.primary_key == ["id"]
    assert len(posts.foreign_keys) == 2  # inline + ALTER
    assert posts.indexes == [["body"]]


def test_key_problems():
    result = analyze(
        """
        CREATE TABLE students (id INT PRIMARY KEY, name VARCHAR(100));
        CREATE TABLE categories (id INT PRIMARY KEY, title VARCHAR(50));
        CREATE TABLE enrollments (student_id INT, course_code VARCHAR(10));
        CREATE TABLE books (
            id INT PRIMARY KEY,
            categoryId INT,
            student_id BIGINT,
            library_id INT,
            FOREIGN KEY (student_id) REFERENCES students(id)
        );
        CREATE TABLE loans (
            id INT PRIMARY KEY,
            member_id INT,
            book_title VARCHAR(255),
            FOREIGN KEY (member_id) REFERENCES members(id),
            FOREIGN KEY (book_title) REFERENCES books(title)
        );
        """
    )
    assert result["missing_primary_keys"] == ["enrollments"]
    missing_fk = {(i["table"], i["columns"][0]) for i in result["missing_foreign_keys"]}
    # library_id has no `libraries` table, so it is not flagged.
    assert missing_fk == {("enrollments", "student_id"), ("books", "categoryId")}
    assert "REFERENCES categories(id)" in next(
        i["suggestion"] for i in result["missing_foreign_keys"] if i["table"] == "books"
    )
    types = issue_types(result)
    assert ("type_mismatch", "books") in types  # BIGINT -> INT
    assert types.count(("broken_reference", "loans")) == 2  # unknown table, unknown column


def test_type_problems():
    result = analyze(
        """
        CREATE TABLE accounts (
            id INT PRIMARY KEY,
            password VARCHAR(32),
            balance FLOAT,
            birth_date VARCHAR(20),
            phone INT,
            is_active VARCHAR(5),
            created_at TIMESTAMP,
            password_hash VARCHAR(255)
        );
        """
    )
    assert issue_types(result) == [
        ("boolean_as_text", "accounts"),
        ("date_as_text", "accounts"),
        ("float_for_money", "accounts"),
        ("phone_as_number", "accounts"),
        ("plaintext_password", "accounts"),
    ]


def test_normalization_levels():
    unf = analyze(
        """
        CREATE TABLE students (id INT PRIMARY KEY, phone1 VARCHAR(20), phone2 VARCHAR(20),
                               courses TEXT);
        """
    )
    assert unf["normalization_level"] == "UNF"
    assert issue_types(unf) == [("multivalued_column", "students"), ("repeating_group", "students")]

    first = analyze(
        """
        CREATE TABLE orders (id INT PRIMARY KEY, customer VARCHAR(50));
        CREATE TABLE products (id INT PRIMARY KEY, name VARCHAR(50), price DECIMAL(8,2));
        CREATE TABLE order_items (
            order_id INT, product_id INT, quantity INT, product_name VARCHAR(50),
            PRIMARY KEY (order_id, product_id),
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
        """
    )
    assert first["normalization_level"] == "1NF"
    partial = [i for i in first["issues"] if i["type"] == "partial_dependency"]
    assert [(i["columns"], "product_id" in i["message"]) for i in partial] == [
        (["product_name"], True)
    ]

    second = analyze(
        """
        CREATE TABLE departments (id INT PRIMARY KEY, name VARCHAR(50), building VARCHAR(20));
        CREATE TABLE employees (
            id INT PRIMARY KEY, full_name VARCHAR(100),
            department_id INT, building VARCHAR(20),
            FOREIGN KEY (department_id) REFERENCES departments(id)
        );
        """
    )
    assert second["normalization_level"] == "2NF"
    assert issue_types(second) == [("transitive_dependency", "employees")]


def test_queries_in_file():
    result = analyze(
        """
        CREATE TABLE t (id INT PRIMARY KEY, a INT);
        SELECT * FROM t;
        SELECT id FROM t WHERE a = 1;
        DELETE FROM t;
        UPDATE t SET a = 2 WHERE id = 1;
        UPDATE t SET a = 3;
        """
    )
    assert sorted(i["type"] for i in result["query_issues"]) == [
        "delete_without_where",
        "select_star",
        "update_without_where",
    ]
    assert {i["line"] for i in result["query_issues"]} == {3, 5, 7}


def test_postgres_missing_index():
    sql = """
        CREATE TABLE users (id SERIAL PRIMARY KEY);
        CREATE TABLE posts (id SERIAL PRIMARY KEY, user_id INT NOT NULL REFERENCES users(id));
        CREATE TABLE likes (user_id INT REFERENCES users(id), post_id INT REFERENCES posts(id),
                            PRIMARY KEY (user_id, post_id));
        CREATE INDEX idx_likes_post ON likes (post_id);
    """
    result = analyze(sql, "postgresql")
    assert [(i["table"], i["columns"]) for i in result["missing_indexes"]] == [
        ("posts", ["user_id"])
    ]
    assert analyze(sql, "mysql")["missing_indexes"] == []  # InnoDB indexes FKs itself


def test_er_diagram():
    diagram = analyze(LIBRARY)["er_diagram_mermaid"]
    assert diagram.startswith("erDiagram\n")
    assert "        int id PK\n" in diagram
    assert "        int author_id FK\n" in diagram
    assert "        varchar email UK\n" in diagram
    assert "    authors ||--o{ books : fk_books_author\n" in diagram


def test_unparsable_and_empty():
    result = analyze(
        "CREATE TABLE ok (id INT PRIMARY KEY);\nCREATE TABLE broken (id INT DEFAULT );"
    )
    assert result["total_tables"] == 1
    assert result["unparsed_statements"][0]["line"] == 2

    empty = analyze("-- nothing here\n")
    assert empty["total_tables"] == 0
    assert empty["normalization_level"] is None
    assert empty["overall_db_score"] == 0.0


def test_prefixed_table_names_and_copied_columns():
    result = analyze(
        """
        CREATE TABLE tbl_users (user_id INT PRIMARY KEY, username VARCHAR(50));
        CREATE TABLE tbl_orders (order_id INT PRIMARY KEY, user_id INT, username VARCHAR(50));
        """
    )
    assert issue_types(result) == [
        ("missing_foreign_key", "tbl_orders"),
        ("transitive_dependency", "tbl_orders"),
    ]
    assert "REFERENCES tbl_users(user_id)" in result["missing_foreign_keys"][0]["suggestion"]


def test_overlapping_composite_keys_are_3nf_not_bcnf():
    sql = """
    CREATE TABLE students (id INT PRIMARY KEY, name VARCHAR(100));
    CREATE TABLE teachers (id INT PRIMARY KEY, name VARCHAR(100));
    CREATE TABLE enrollments (
        student_id INT NOT NULL REFERENCES students(id),
        course_code VARCHAR(10) NOT NULL,
        teacher_id INT NOT NULL REFERENCES teachers(id),
        PRIMARY KEY (student_id, course_code),
        UNIQUE (student_id, teacher_id)
    );
    """
    result = analyze_database(sql)
    assert result["normalization_level"] == "3NF"
    issue = next(i for i in result["issues"] if i["type"] == "possible_bcnf_violation")
    assert issue["table"] == "enrollments" and set(issue["columns"]) == {
        "course_code",
        "teacher_id",
    }
