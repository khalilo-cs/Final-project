from app.parsers.sql_splitter import split_statements


def texts(sql):
    return [s.text for s in split_statements(sql)]


def test_basic_and_comments():
    sql = "-- header\nSELECT 1; # note\n/*!40101 SET NAMES utf8 */;\nSELECT 'a;b' ;\n"
    assert texts(sql) == ["SELECT 1", "SELECT 'a;b'"]


def test_quotes_and_escapes():
    sql = "INSERT INTO t VALUES ('it''s; ok', \"x\\\";y\", `we;ird`);SELECT 2;"
    assert texts(sql) == [
        "INSERT INTO t VALUES ('it''s; ok', \"x\\\";y\", `we;ird`)",
        "SELECT 2",
    ]


def test_delimiter_blocks():
    sql = (
        "CREATE TABLE a (id INT);\n"
        "DELIMITER ;;\n"
        "CREATE TRIGGER t BEFORE INSERT ON a FOR EACH ROW BEGIN SET NEW.id = 1; END ;;\n"
        "DELIMITER ;\n"
        "CREATE TABLE b (id INT);\n"
    )
    result = texts(sql)
    assert result[0] == "CREATE TABLE a (id INT)"
    assert result[1].startswith("CREATE TRIGGER") and result[1].endswith("END")
    assert result[2] == "CREATE TABLE b (id INT)"


def test_line_numbers():
    sql = "SELECT 1;\n\n-- c\nCREATE TABLE x (\n  id INT\n);\n"
    assert [s.line for s in split_statements(sql)] == [1, 4]


def test_double_dash_needs_space():
    # MySQL: `--` starts a comment only when followed by whitespace.
    assert texts("SELECT 5--1;") == ["SELECT 5--1"]
