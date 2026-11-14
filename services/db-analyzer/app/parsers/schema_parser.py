"""Build a Schema from a SQL file (MySQL, PostgreSQL or SQLite dialect)."""

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError

from app.parsers.schema import Column, ForeignKey, QueryStatement, Schema, Table
from app.parsers.sql_splitter import split_statements

DIALECTS = {"mysql": "mysql", "postgresql": "postgres", "sqlite": "sqlite"}

# Only these statements matter for schema and query analysis; INSERT data in a dump
# can be megabytes and is skipped without parsing.
_RELEVANT = re.compile(
    r"^\s*(CREATE\s+(?:TEMPORARY\s+)?TABLE|CREATE\s+(?:UNIQUE\s+)?INDEX|ALTER\s+TABLE|"
    r"SELECT|UPDATE|DELETE|WITH)\b",
    re.IGNORECASE,
)


def _name(node: exp.Expression | str | None) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, exp.Ordered):
        return _name(node.this)
    if isinstance(node, exp.Anonymous):  # MySQL prefix index: msg(10)
        return _name(node.this)
    if isinstance(node, (exp.Identifier, exp.Column, exp.Table)):
        return node.name
    return node.name or node.sql()


def _names(nodes) -> list[str]:
    return [_name(node).lower() for node in nodes or []]


class _Builder:
    def __init__(self, dialect: str) -> None:
        self.dialect = dialect
        self.schema = Schema(dialect=dialect)

    def add(self, statement: exp.Expression, line: int) -> None:
        if isinstance(statement, exp.Create):
            kind = (statement.args.get("kind") or "").upper()
            if kind == "TABLE" and isinstance(statement.this, exp.Schema):
                self.create_table(statement.this, line)
            elif kind == "INDEX" and isinstance(statement.this, exp.Index):
                self.create_index(statement.this, bool(statement.args.get("unique")))
        elif isinstance(statement, exp.Alter):
            self.alter_table(statement, line)
        elif isinstance(statement, (exp.Select, exp.Union, exp.Update, exp.Delete)):
            self.query(statement, line)

    # -- DDL -----------------------------------------------------------------------------

    def create_table(self, node: exp.Schema, line: int) -> None:
        table = Table(name=_name(node.this), line=line)
        self.schema.tables[table.key] = table
        for item in node.expressions:
            if isinstance(item, exp.ColumnDef):
                self.column(table, item, line)
            else:
                self.constraint(table, item, line)

    def column(self, table: Table, node: exp.ColumnDef, line: int) -> None:
        kind = node.args.get("kind")
        type_sql = kind.sql(dialect=self.dialect).upper() if kind else "UNKNOWN"
        base = type_sql.split("(")[0].strip()
        length = None
        if kind is not None and kind.expressions:
            first = kind.expressions[0]
            literal = first.this if isinstance(first, exp.DataTypeParam) else first
            if isinstance(literal, exp.Literal) and not literal.is_string:
                try:
                    length = int(literal.this)
                except ValueError:
                    length = None
        column = Column(name=_name(node.this), type=type_sql, base_type=base, length=length)
        table.columns[column.key] = column

        for constraint in node.constraints:
            value = constraint.args.get("kind")
            if isinstance(value, exp.NotNullColumnConstraint):
                column.nullable = bool(value.args.get("allow_null"))
            elif isinstance(value, exp.PrimaryKeyColumnConstraint):
                table.primary_key = [column.key]
                column.nullable = False
            elif isinstance(value, exp.UniqueColumnConstraint):
                table.unique.append([column.key])
            elif isinstance(value, (exp.AutoIncrementColumnConstraint,)):
                column.auto_increment = True
            elif isinstance(value, exp.Reference):
                self.foreign_key(table, [column.key], value, None, line)
        if base in ("SERIAL", "BIGSERIAL", "SMALLSERIAL"):
            column.auto_increment = True

    def constraint(self, table: Table, node: exp.Expression, line: int) -> None:
        if isinstance(node, exp.Constraint):
            for inner in node.expressions:
                self.constraint_inner(table, inner, _name(node.this) or None, line)
        else:
            self.constraint_inner(table, node, None, line)

    def constraint_inner(
        self, table: Table, node: exp.Expression, name: str | None, line: int
    ) -> None:
        if isinstance(node, exp.PrimaryKey):
            table.primary_key = _names(node.expressions)
            for key in table.primary_key:
                if column := table.columns.get(key):
                    column.nullable = False
        elif isinstance(node, exp.ForeignKey):
            reference = node.args.get("reference")
            if reference is not None:
                self.foreign_key(table, _names(node.expressions), reference, name, line)
        elif isinstance(node, exp.UniqueColumnConstraint):
            target = node.this
            columns = target.expressions if isinstance(target, exp.Schema) else node.expressions
            if columns:
                table.unique.append(_names(columns))
        elif isinstance(node, exp.IndexColumnConstraint):
            columns = _names(node.expressions)
            if columns:
                kind = str(node.args.get("kind") or "").upper()
                (table.unique if kind == "UNIQUE" else table.indexes).append(columns)

    def foreign_key(
        self,
        table: Table,
        columns: list[str],
        reference: exp.Reference,
        name: str | None,
        line: int,
    ) -> None:
        target = reference.this
        if isinstance(target, exp.Schema):
            ref_table, ref_columns = _name(target.this), _names(target.expressions)
        else:
            ref_table, ref_columns = _name(target), []
        table.foreign_keys.append(ForeignKey(columns, ref_table, ref_columns, name, line))

    def create_index(self, node: exp.Index, unique: bool) -> None:
        table = self.schema.table(_name(node.args.get("table")))
        params = node.args.get("params")
        if table is None or params is None:
            return
        columns = _names(params.args.get("columns"))
        if columns:
            (table.unique if unique else table.indexes).append(columns)

    def alter_table(self, node: exp.Alter, line: int) -> None:
        table = self.schema.table(_name(node.this))
        if table is None:
            return
        for action in node.args.get("actions") or []:
            if isinstance(action, exp.AddConstraint):
                for item in action.expressions:
                    self.constraint(table, item, line)
            elif isinstance(action, exp.ColumnDef):
                self.column(table, action, line)

    # -- queries -------------------------------------------------------------------------

    def query(self, node: exp.Expression, line: int) -> None:
        kind = {exp.Update: "UPDATE", exp.Delete: "DELETE"}.get(type(node), "SELECT")
        selects_star = any(
            isinstance(projection, exp.Star)
            or (isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star))
            for select in node.find_all(exp.Select)
            for projection in select.expressions
        )
        sql = node.sql(dialect=self.dialect)
        self.schema.queries.append(
            QueryStatement(
                kind=kind,
                sql=sql if len(sql) <= 200 else sql[:197] + "...",
                line=line,
                has_where=node.args.get("where") is not None,
                selects_star=selects_star,
            )
        )


def parse_schema(sql: str, dialect: str = "mysql") -> Schema:
    if dialect not in DIALECTS:
        raise ValueError(f"unsupported dialect: {dialect}")
    builder = _Builder(DIALECTS[dialect])
    for statement in split_statements(sql):
        if not _RELEVANT.match(statement.text):
            continue
        try:
            parsed = sqlglot.parse_one(statement.text, read=builder.dialect)
        except (ParseError, TokenError) as exc:
            builder.schema.unparsed.append(
                {"line": statement.line, "error": str(exc).splitlines()[0][:200]}
            )
            continue
        if parsed is not None:
            builder.add(parsed, statement.line)
    return builder.schema
