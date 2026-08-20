// Opens the shared SQLite file. PRAGMA foreign_keys=ON is mandatory here —
// SQLite defaults it off, which would silently defeat the ON DELETE CASCADE
// in schema.sql (plan.md criterion #2 / cascade delete).
use rusqlite::Connection;

pub fn open(path: &str) -> Result<Connection, rusqlite::Error> {
    let conn = Connection::open(path)?;
    conn.execute_batch("PRAGMA foreign_keys = ON;")?;
    // SQLite only supports one writer at a time; a single connection behind
    // a mutex (see AppState) avoids SQLITE_BUSY under the concurrent
    // workloads this comparison load-tests — same constraint as Go's
    // SetMaxOpenConns(1), expressed explicitly since rusqlite has no pool.
    Ok(conn)
}
