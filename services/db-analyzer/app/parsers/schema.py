"""A dialect-independent model of a database schema."""

from dataclasses import dataclass, field


@dataclass
class Column:
    name: str
    type: str  # as written, normalized: "VARCHAR(255)"
    base_type: str  # "VARCHAR"
    length: int | None = None
    nullable: bool = True
    auto_increment: bool = False

    @property
    def key(self) -> str:
        return self.name.lower()


@dataclass
class ForeignKey:
    columns: list[str]
    ref_table: str
    ref_columns: list[str]
    name: str | None = None
    line: int = 0


@dataclass
class Table:
    name: str
    line: int
    columns: dict[str, Column] = field(default_factory=dict)  # keyed by lower-case name
    primary_key: list[str] = field(default_factory=list)  # lower-case names
    unique: list[list[str]] = field(default_factory=list)
    indexes: list[list[str]] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)

    @property
    def key(self) -> str:
        return self.name.lower()

    def column(self, name: str) -> Column | None:
        return self.columns.get(name.lower())

    def fk_for(self, column: str) -> ForeignKey | None:
        column = column.lower()
        return next((fk for fk in self.foreign_keys if column in fk.columns), None)

    def is_indexed(self, columns: list[str]) -> bool:
        """True when some index (incl. PK / unique) starts with exactly these columns."""
        width = len(columns)
        candidates = [self.primary_key, *self.unique, *self.indexes]
        return any(candidate[:width] == columns for candidate in candidates)


@dataclass
class QueryStatement:
    kind: str  # SELECT / UPDATE / DELETE
    sql: str
    line: int
    has_where: bool
    selects_star: bool


@dataclass
class Schema:
    dialect: str
    tables: dict[str, Table] = field(default_factory=dict)  # keyed by lower-case name
    queries: list[QueryStatement] = field(default_factory=list)
    unparsed: list[dict] = field(default_factory=list)

    def table(self, name: str) -> Table | None:
        return self.tables.get(name.lower())
