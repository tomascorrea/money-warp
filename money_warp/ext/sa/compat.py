# ruff: noqa: A003
"""Dialect-aware SQL function wrappers for SQLite and PostgreSQL.

Each wrapper is a :class:`~sqlalchemy.sql.expression.FunctionElement` subclass
with ``@compiles`` overrides.  The default compilation targets SQLite; a
``"postgresql"`` override emits the equivalent PostgreSQL syntax.  Bridge code
calls these wrappers instead of raw ``func.*`` so that SQLAlchemy's compiler
dispatches to the correct SQL at query compile time.
"""

from sqlalchemy import Float, Integer
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import FunctionElement

# ---------------------------------------------------------------------------
# mw_julianday — date to fractional day number
# ---------------------------------------------------------------------------


class mw_julianday(FunctionElement):
    """Convert a date/timestamp to a fractional day number.

    Only the *difference* between two ``mw_julianday`` calls matters, so
    the absolute epoch (Julian vs Unix) is irrelevant.

    SQLite:  ``julianday(expr)``
    PG:      ``EXTRACT(EPOCH FROM expr::timestamp) / 86400.0``
    """

    type = Float()
    inherit_cache = True
    name = "mw_julianday"


@compiles(mw_julianday)
def _julianday_default(element, compiler, **kw):
    return f"julianday({compiler.process(element.clauses, **kw)})"


@compiles(mw_julianday, "postgresql")
def _julianday_pg(element, compiler, **kw):
    arg = compiler.process(element.clauses, **kw)
    return f"(EXTRACT(EPOCH FROM ({arg})::timestamp) / 86400.0)"


# ---------------------------------------------------------------------------
# mw_json_extract — top-level key from a JSON column
# ---------------------------------------------------------------------------


class mw_json_extract(FunctionElement):
    """Extract a top-level key from a JSON column.

    *key* is the bare field name (e.g. ``"rate"``), **not** the SQLite
    ``$.rate`` path syntax — the compiler adds the appropriate prefix.

    SQLite:  ``json_extract(col, '$.key')``
    PG:      ``(col)::jsonb->>'key'``
    """

    inherit_cache = True
    name = "mw_json_extract"

    def __init__(self, col, key: str):
        self._json_key = key
        super().__init__(col)


@compiles(mw_json_extract)
def _json_extract_default(element, compiler, **kw):
    col_sql = compiler.process(element.clauses, **kw)
    return f"json_extract({col_sql}, '$.{element._json_key}')"


@compiles(mw_json_extract, "postgresql")
def _json_extract_pg(element, compiler, **kw):
    col_sql = compiler.process(element.clauses, **kw)
    return f"(({col_sql})::jsonb->>'{element._json_key}')"


# ---------------------------------------------------------------------------
# mw_json_array_values — iterate JSON array elements (table-valued)
# ---------------------------------------------------------------------------


class mw_json_array_values(FunctionElement):
    """Expand a JSON array into rows of text values.

    Use with ``.table_valued(column("value", String))`` to create a
    table-valued alias whose ``value`` column holds each element.

    SQLite:  ``json_each(col)``   (returns rows with a ``value`` column)
    PG:      ``jsonb_array_elements_text(col::jsonb)``  (single unnamed column,
             aliased to ``value`` by the ``table_valued`` wrapper)
    """

    inherit_cache = True
    name = "mw_json_array_values"


@compiles(mw_json_array_values)
def _json_array_values_default(element, compiler, **kw):
    return f"json_each({compiler.process(element.clauses, **kw)})"


@compiles(mw_json_array_values, "postgresql")
def _json_array_values_pg(element, compiler, **kw):
    col_sql = compiler.process(element.clauses, **kw)
    return f"jsonb_array_elements_text(({col_sql})::jsonb)"


# ---------------------------------------------------------------------------
# mw_json_array_length — length of a JSON array
# ---------------------------------------------------------------------------


class mw_json_array_length(FunctionElement):
    """Return the number of elements in a JSON array.

    SQLite:  ``json_array_length(col)``
    PG:      ``jsonb_array_length(col::jsonb)``
    """

    type = Integer()
    inherit_cache = True
    name = "mw_json_array_length"


@compiles(mw_json_array_length)
def _json_array_length_default(element, compiler, **kw):
    return f"json_array_length({compiler.process(element.clauses, **kw)})"


@compiles(mw_json_array_length, "postgresql")
def _json_array_length_pg(element, compiler, **kw):
    col_sql = compiler.process(element.clauses, **kw)
    return f"jsonb_array_length(({col_sql})::jsonb)"


# ---------------------------------------------------------------------------
# mw_instr — find substring position
# ---------------------------------------------------------------------------


class mw_instr(FunctionElement):
    """Return the 1-based position of *sub* in *string* (0 if absent).

    SQLite:  ``instr(string, sub)``
    PG:      ``strpos(string, sub)``
    """

    type = Integer()
    inherit_cache = True
    name = "mw_instr"


@compiles(mw_instr)
def _instr_default(element, compiler, **kw):
    return f"instr({compiler.process(element.clauses, **kw)})"


@compiles(mw_instr, "postgresql")
def _instr_pg(element, compiler, **kw):
    return f"strpos({compiler.process(element.clauses, **kw)})"


# ---------------------------------------------------------------------------
# mw_greatest — scalar maximum of two values
# ---------------------------------------------------------------------------


class mw_greatest(FunctionElement):
    """Return the larger of two values (scalar, not aggregate).

    SQLite:  ``max(a, b)``  (SQLite's ``max()`` acts as scalar with 2+ args)
    PG:      ``GREATEST(a, b)``
    """

    inherit_cache = True
    name = "mw_greatest"


@compiles(mw_greatest)
def _greatest_default(element, compiler, **kw):
    return f"max({compiler.process(element.clauses, **kw)})"


@compiles(mw_greatest, "postgresql")
def _greatest_pg(element, compiler, **kw):
    return f"GREATEST({compiler.process(element.clauses, **kw)})"
