"""Split a SQL dump into statements.

Handles what real `mysqldump` / phpMyAdmin exports contain and generic parsers trip
over: `DELIMITER` blocks (procedures, triggers), `/*!40101 ... */` conditional
comments, `--` / `#` comments, and delimiters inside quoted strings.
"""

from collections.abc import Iterator
from dataclasses import dataclass


@dataclass
class Statement:
    text: str
    line: int  # 1-based line where the statement starts


def split_statements(sql: str) -> Iterator[Statement]:
    delimiter = ";"
    buffer: list[str] = []
    start_line = 1
    line = 1
    i, n = 0, len(sql)

    def flush() -> Statement | None:
        text = "".join(buffer).strip()
        buffer.clear()
        return Statement(text, start_line) if text else None

    while i < n:
        char = sql[i]

        # DELIMITER directive: only valid at the start of a statement.
        if not "".join(buffer).strip() and sql.startswith(("DELIMITER", "delimiter"), i):
            end = sql.find("\n", i)
            end = n if end == -1 else end
            delimiter = sql[i + len("DELIMITER") : end].strip() or ";"
            i = end
            continue

        if char == "\n":
            line += 1
            buffer.append(char)
            i += 1
            continue

        if char in "'\"`":
            j = i + 1
            while j < n:
                if sql[j] == "\\" and char != "`":
                    j += 2
                    continue
                if sql[j] == char:
                    if j + 1 < n and sql[j + 1] == char:  # doubled quote escape
                        j += 2
                        continue
                    break
                j += 1
            chunk = sql[i : j + 1]
            line += chunk.count("\n")
            buffer.append(chunk)
            i = j + 1
            continue

        is_dash_comment = sql.startswith("--", i) and (i + 2 >= n or sql[i + 2] in " \t\r\n")
        if is_dash_comment or char == "#":
            end = sql.find("\n", i)
            i = n if end == -1 else end
            continue

        if sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            end = n if end == -1 else end + 2
            line += sql.count("\n", i, end)
            buffer.append(" ")
            i = end
            continue

        if sql.startswith(delimiter, i):
            statement = flush()
            if statement:
                yield statement
            i += len(delimiter)
            start_line = line
            continue

        if not buffer or not "".join(buffer).strip():
            start_line = line
        buffer.append(char)
        i += 1

    statement = flush()
    if statement:
        yield statement
