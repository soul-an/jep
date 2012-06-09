from decimal import Decimal
import logging
import java.sql
import datetime
import time


log = logging.getLogger('java.sql')

apilevel = '2.0'
paramstyle =  'qmark'
threadsafety = 2


class Warning(StandardError):
    """Exception raised for important warnings like data
    truncations while inserting, etc. It must be a subclass of
    the Python StandardError (defined in the module
    exceptions)."""
    pass

class Error(StandardError):
    """Exception that is the base class of all other error
    exceptions. You can use this to catch all errors with one
    single 'except' statement. Warnings are not considered
    errors and thus should not use this class as base. It must
    be a subclass of the Python StandardError (defined in the
    module exceptions).
    """
    pass

class InterfaceError(Error):
    """Exception raised for errors that are related to the
    database interface rather than the database itself.  It
    must be a subclass of Error."""
    pass

class DatabaseError(Error):
    """Exception raised for errors that are related to the
    database.  It must be a subclass of Error."""
    pass

class DataError(DatabaseError):
    """Exception raised for errors that are due to problems with
    the processed data like division by zero, numeric value
    out of range, etc. It must be a subclass of DatabaseError."""
    pass

class OperationalError(DatabaseError):
    """Exception raised for errors that are related to the
    database's operation and not necessarily under the control
    of the programmer, e.g. an unexpected disconnect occurs,
    the data source name is not found, a transaction could not
    be processed, a memory allocation error occurred during
    processing, etc.  It must be a subclass of DatabaseError."""
    pass

class IntegrityError(DatabaseError):
    """Exception raised when the relational integrity of the
    database is affected, e.g. a foreign key check fails.  It
    must be a subclass of DatabaseError."""
    pass

class InternalError(DatabaseError):
    """Exception raised when the database encounters an internal
    error, e.g. the cursor is not valid anymore, the
    transaction is out of sync, etc.  It must be a subclass of
    DatabaseError."""
    pass

class ProgrammingError(DatabaseError):
    """Exception raised for programming errors, e.g. table not
    found or already exists, syntax error in the SQL
    statement, wrong number of parameters specified, etc.  It
    must be a subclass of DatabaseError."""
    pass

class NotSupportedError(DatabaseError):
    """"Exception raised in case a method or database API was used
    which is not supported by the database, e.g. requesting a
    .rollback() on a connection that does not support
    transaction or has transactions turned off.  It must be a
    subclass of DatabaseError."""
    pass


def Date(year, month, day):
    return java.sql.Date(long(time.mktime(datetime.date(year, month, day).timetuple())) * 1000)

def Time(hour, minute, second):
    return java.sql.Time(hour, minute, second)

def Timestamp(year, month, day, hour, minute, second):
    return java.sql.Timestamp(long(time.mktime(datetime.datetime(year, month, day, hour, minute, second).timetuple())) * 1000)

def DateFromTicks(ticks):
    return Date(*time.localtime(ticks)[:3])

def TimeFromTicks(ticks):
    return Time(*time.localtime(ticks)[3:6])

def TimestampFromTicks(ticks):
    return Timestamp(*time.localtime(ticks)[:6])


def connect(url, user=None, password=None, timeout=0):
    """
    Connect to a JDBC data source using java.sql.DriverManager.
    Returns a java.sql.Connection instance.

    url - JDBC connection url. See your driver's documentation for this value
    user - connection username
    password - optional password
    timeout - time in seconds to wait for a connection.

    Raises ``Error`` for failures.
    """
    try:
        java.sql.DriverManager.setLoginTimeout(timeout)
        return JDBCConnection(java.sql.DriverManager.getConnection(url, user, password))
    except Exception as e:
        raise Error(e.message)


class JDBCConnection(object):

    def __init__(self, conn):
        super(JDBCConnection, self).__init__()
        self.conn = conn

    def close(self):
        try:
            self.conn.close()
        except Exception as e:
            raise DatabaseError(e.message)

    def commit(self):
        try:
            self.conn.commit()
        except Exception as e:
            raise DatabaseError(e.message)

    def rollback(self):
        try:
            self.conn.rollback()
        except Exception as e:
            raise DatabaseError(e.message)

    def cursor(self):
        return JDBCCursor(self)


class JDBCCursor(object):
    def __init__(self, jconn):
        super(JDBCCursor, self).__init__()
        self.connection = jconn
        self.statement = None     # jdbc Statement
        self.rs = None            # jdbc ResultSet
        self.meta_data = None     # jdbc ResultSetMetaData
        self.columns = None       # column count

        self.description = ()
        self.rowcount = None
        self.arraysize = 1

    def execute(self, operation, *args):
        try:
            if log.isEnabledFor(logging.DEBUG):
                log.debug('%s -- %s', operation.strip(), str(args))
            self.statement = self.connection.conn.prepareStatement(operation)

            for index, arg in enumerate(args):
                index += 1

                if isinstance(arg, int):
                    self.statement.setLong(index, arg)
                elif isinstance(arg, float):
                    self.statement.setDouble(index, arg)
                elif isinstance(arg, basestring):
                    self.statement.setString(index, arg)
                else:
                    self.statement.setObject(index, arg)

            is_update = not operation.lower().strip().startswith('select')
            if is_update:
                self.rowcount = self.statement.executeUpdate()
            else:
                self.rs = self.statement.executeQuery()
                self.meta_data = self.rs.getMetaData()
                self.columns = self.meta_data.getColumnCount()

                desc = []
                for col in range(1, self.columns + 1):
                    desc.append((
                        self.meta_data.getColumnName(col),
                        self.meta_data.getColumnType(col),
                        self.meta_data.getColumnDisplaySize(col),
                        self.meta_data.getColumnDisplaySize(col),
                        self.meta_data.getPrecision(col),
                        self.meta_data.getScale(col),
                        bool(self.meta_data.isNullable(col)),
                    ))
                self.description = tuple(desc)

        except Exception as e:
            raise DatabaseError(e.message)

    def fetchone(self):
        if not self.rs.next():
            return None

        def map_type(col):
            try:
                sql_type = self.description[col - 1][1]

                # see http://docs.oracle.com/javase/6/docs/api/constant-values.html#java.sql.Types.VARCHAR
                if self.rs.getString(col) is None:
                    return None
                if sql_type in (-5, -7, 4, 5, -6):
                    return self.rs.getLong(col)
                if sql_type in (8, 6, 7):
                    return self.rs.getDouble(col)
                if sql_type in (-1, 1, 0, 12, -16, -9, -15):
                    return self.rs.getString(col)
                if sql_type in (16,):
                    return self.rs.getBoolean(col)
                if sql_type in (2, 3,):
                    return Decimal(self.rs.getString(col))

                return self.rs.getObject(col)
            except Exception as e:
                log.exception("Failed to map ResultSet type")
                raise DatabaseError(e.message)

            #public static final int 	BLOB 	2004
            #public static final int 	CLOB 	2005
            #public static final int 	DATALINK 	70
            #public static final int 	DATE 	91
            #public static final int 	DISTINCT 	2001
            #public static final int 	JAVA_OBJECT 	2000
            #public static final int 	LONGVARBINARY 	-4
            #public static final int 	NCLOB 	2011
            #public static final int 	OTHER 	1111
            #public static final int 	REF 	2006
            #public static final int 	ROWID 	-8
            #public static final int 	SQLXML 	2009
            #public static final int 	STRUCT 	2002
            #public static final int 	TIME 	92
            #public static final int 	TIMESTAMP 	93
            #public static final int 	VARBINARY 	-3

        return tuple(map(map_type, range(1, self.columns + 1)))

    def fetchall(self):
        return list(iter(self.fetchone, None))

    def close(self):
        try:
            self.rs.close()
        except Exception as e:
            log.exception('Ignored error')
        try:
            self.statement.close()
        except Exception as e:
            log.exception('Ignored error')

    def nextset(self):
        raise ProgrammingError("Not Implemented")