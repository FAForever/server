from PySide import QtSql
from PySide.QtSql import QSqlQuery
from passwords import DB_SERVER, DB_PORT, DB_LOGIN, DB_PASSWORD, DB_TABLE
import logging

# Object to wrap a database connection and provide some vaguely handy utilities.
_logger = logging.getLogger(__name__)

# Open the database connection. when the module is first touched...
_db = QtSql.QSqlDatabase("QMYSQL")
_db.setHostName(DB_SERVER)
_db.setPort(DB_PORT)

_db.setDatabaseName(DB_TABLE)
_db.setUserName(DB_LOGIN)
_db.setPassword(DB_PASSWORD)

_db.setConnectOptions("MYSQL_OPT_RECONNECT=1")

if not _db.open():
    _logger.error(_db.lastError().text())
    raise RuntimeError

# A cache of prepared queries, keyed by SQL string. Allows reuse of prepared queries.
_prepared_queries = {}

def get_query_object(query_string, *query_params):
    """
    Get a QSqlQuery object configured for the given query string and parameters. Used by the
    various query function to do common setup work.
    """
    if query_string in _prepared_queries:
        query = _prepared_queries[query_string]
    else:
        query = QSqlQuery(_db)

        # This ostensibly is very good for performance, and iterating resultsets backwards is a
        # pretty strong antipattern at the best of times...
        query.setForwardOnly(True)

        query.prepare(query_string)
        _prepared_queries[query_string] = query

    # Bind the arguments to the query.
    for i, arg in query_params:
        query.addBindValue(arg)

    return query


def exec(query_string, *query_params):
    """
    Run a query for which you don't care about the returned result (such as an insert).
     """
    with get_query_object(query_string, query_params) as query:
        if not query.exec_():
            _logger.error(query.lastError().text())
            raise RuntimeError(query.lastError().text())


def query(query_string, *query_parameters):
    """
    Run a select query (or other query for which a resultset you care about is returned).
    This function behaves as a generator function for the ensuing resultset.
    If the resultset is not iterated in its entirety, it is the responsibility of the caller to
    call finish() on the query object.
    Nothing is returned if the resultset is empty.
    """
    query = get_query_object(query_string, query_parameters)
    if query.exec_():
        while query.next():
            yield query
    else:
        _logger.error(query.lastError().text())
        raise RuntimeError(query.lastError().text())

    query.finish()


def singlerow_query(query_string, *query_parameters):
    """
    Special case of query when you only care about the first row of the returned results (a fairly
    common pattern). Returns that row as a tuple.
    If the result is the empty set, returns False.
    """
    query = get_query_object(query_string, query_parameters)
    if query.exec_():
        if not  query.first():
            query.finish()
            return False
        columns = []
        # There's not an efficient way to find the number of columns, so we appear to be stuck with
        # this rather inelegant expression.
        column = 0
        while True:
            value = query.value(column)
            if not value.isValid():
                break
            columns.append(value)
            column += 1

        query.finish()
        return tuple(columns)
    else:
        _logger.error(query.lastError().text())
        query.finish()
        raise RuntimeError(query.lastError().text())
