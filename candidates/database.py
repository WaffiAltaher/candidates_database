"""
Database layer with dual SQLite/PostgreSQL support for storing structured CV data.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, database_url: str = None, db_path: str = None):
        if database_url and database_url.startswith("postgres"):
            import psycopg2
            import psycopg2.extras

            self.backend = "postgresql"
            self.placeholder = "%s"
            self.conn = psycopg2.connect(database_url)
            self.conn.autocommit = False
        else:
            self.backend = "sqlite"
            self.placeholder = "?"
            path = db_path or "cvs.db"
            self.conn = sqlite3.connect(path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")

    @property
    def dialect(self) -> str:
        return "PostgreSQL" if self.backend == "postgresql" else "SQLite"

    def _execute(self, sql, params=None):
        """Execute a query, handling cursor creation per backend."""
        cursor = self.conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return cursor

    def _executemany(self, sql, params_list):
        cursor = self.conn.cursor()
        cursor.executemany(sql, params_list)
        return cursor

    def initialize(self):
        """Create tables if they don't exist."""
        p = self.placeholder
        if self.backend == "postgresql":
            ddl = """
                CREATE TABLE IF NOT EXISTS candidates (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    date_of_birth TEXT,
                    university TEXT,
                    degree_field TEXT,
                    job_title TEXT,
                    years_experience REAL,
                    final_verdict TEXT
                );

                CREATE TABLE IF NOT EXISTS technologies (
                    id SERIAL PRIMARY KEY,
                    candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
                    technology_name TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS experiences (
                    id SERIAL PRIMARY KEY,
                    candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
                    company TEXT,
                    role TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    description TEXT
                );

                CREATE TABLE IF NOT EXISTS interviews (
                    id SERIAL PRIMARY KEY,
                    candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
                    interview_number INTEGER NOT NULL,
                    interviewer_name TEXT NOT NULL,
                    comments TEXT,
                    verdict TEXT,
                    interview_date TEXT
                );

                CREATE TABLE IF NOT EXISTS proposed_customers (
                    id SERIAL PRIMARY KEY,
                    candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
                    customer_name TEXT NOT NULL
                );
            """
            cursor = self.conn.cursor()
            cursor.execute(ddl)
            self.conn.commit()
        else:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    date_of_birth TEXT,
                    university TEXT,
                    degree_field TEXT,
                    job_title TEXT,
                    years_experience REAL,
                    final_verdict TEXT
                );

                CREATE TABLE IF NOT EXISTS technologies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id INTEGER NOT NULL,
                    technology_name TEXT NOT NULL,
                    FOREIGN KEY (candidate_id) REFERENCES candidates(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS experiences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id INTEGER NOT NULL,
                    company TEXT,
                    role TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    description TEXT,
                    FOREIGN KEY (candidate_id) REFERENCES candidates(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS interviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id INTEGER NOT NULL,
                    interview_number INTEGER NOT NULL,
                    interviewer_name TEXT NOT NULL,
                    comments TEXT,
                    verdict TEXT,
                    interview_date TEXT,
                    FOREIGN KEY (candidate_id) REFERENCES candidates(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS proposed_customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id INTEGER NOT NULL,
                    customer_name TEXT NOT NULL,
                    FOREIGN KEY (candidate_id) REFERENCES candidates(id) ON DELETE CASCADE
                );
            """)
            self.conn.commit()

    def upsert_candidate(self, data: dict) -> tuple[int, bool]:
        """Insert or update a candidate. Returns (candidate_id, was_replaced)."""
        p = self.placeholder

        existing = self.execute_query(
            f"SELECT id FROM candidates WHERE LOWER(name) = LOWER({p})", (data["name"],)
        )
        was_replaced = len(existing) > 0

        self._execute(
            f"DELETE FROM candidates WHERE LOWER(name) = LOWER({p})", (data["name"],)
        )

        if self.backend == "postgresql":
            cursor = self._execute(
                f"""INSERT INTO candidates (name, date_of_birth, university, degree_field, job_title, years_experience)
                   VALUES ({p}, {p}, {p}, {p}, {p}, {p}) RETURNING id""",
                (
                    data["name"],
                    data.get("date_of_birth"),
                    data.get("university"),
                    data.get("degree_field"),
                    data.get("job_title"),
                    data.get("years_experience"),
                ),
            )
            candidate_id = cursor.fetchone()[0]
        else:
            cursor = self._execute(
                f"""INSERT INTO candidates (name, date_of_birth, university, degree_field, job_title, years_experience)
                   VALUES ({p}, {p}, {p}, {p}, {p}, {p})""",
                (
                    data["name"],
                    data.get("date_of_birth"),
                    data.get("university"),
                    data.get("degree_field"),
                    data.get("job_title"),
                    data.get("years_experience"),
                ),
            )
            candidate_id = cursor.lastrowid

        self.conn.commit()
        return candidate_id, was_replaced

    def add_technologies(self, candidate_id: int, technologies: list[str]):
        """Bulk insert technologies for a candidate."""
        p = self.placeholder
        self._executemany(
            f"INSERT INTO technologies (candidate_id, technology_name) VALUES ({p}, {p})",
            [(candidate_id, tech) for tech in technologies],
        )
        self.conn.commit()

    def add_experiences(self, candidate_id: int, experiences: list[dict]):
        """Bulk insert work experiences for a candidate."""
        p = self.placeholder
        self._executemany(
            f"""INSERT INTO experiences (candidate_id, company, role, start_date, end_date, description)
               VALUES ({p}, {p}, {p}, {p}, {p}, {p})""",
            [
                (
                    candidate_id,
                    exp.get("company"),
                    exp.get("role"),
                    exp.get("start_date"),
                    exp.get("end_date"),
                    exp.get("description"),
                )
                for exp in experiences
            ],
        )
        self.conn.commit()

    def get_all_candidates(self) -> list[dict]:
        """Return all candidates with their technologies."""
        p = self.placeholder
        candidates = self.execute_query("SELECT * FROM candidates ORDER BY name")
        for c in candidates:
            techs = self.execute_query(
                f"SELECT technology_name FROM technologies WHERE candidate_id = {p}",
                (c["id"],),
            )
            c["technologies"] = [t["technology_name"] for t in techs]
        return candidates

    def get_candidate(self, candidate_id: int) -> dict | None:
        """Return a single candidate with all related data."""
        p = self.placeholder
        rows = self.execute_query(
            f"SELECT * FROM candidates WHERE id = {p}", (candidate_id,)
        )
        if not rows:
            return None
        candidate = rows[0]
        techs = self.execute_query(
            f"SELECT technology_name FROM technologies WHERE candidate_id = {p}",
            (candidate_id,),
        )
        candidate["technologies"] = [t["technology_name"] for t in techs]
        exps = self.execute_query(
            f"SELECT * FROM experiences WHERE candidate_id = {p} ORDER BY start_date DESC",
            (candidate_id,),
        )
        candidate["experiences"] = exps
        interviews = self.execute_query(
            f"SELECT * FROM interviews WHERE candidate_id = {p} ORDER BY interview_number",
            (candidate_id,),
        )
        candidate["interviews"] = interviews
        customers = self.execute_query(
            f"SELECT * FROM proposed_customers WHERE candidate_id = {p}",
            (candidate_id,),
        )
        candidate["proposed_customers"] = customers
        return candidate

    def add_interview(self, candidate_id: int, interview_number: int, interviewer_name: str,
                      comments: str, verdict: str | None = None,
                      interview_date: str | None = None) -> int:
        """Add an interview record. Returns the interview id."""
        p = self.placeholder
        if self.backend == "postgresql":
            cursor = self._execute(
                f"""INSERT INTO interviews (candidate_id, interview_number, interviewer_name, comments, verdict, interview_date)
                   VALUES ({p}, {p}, {p}, {p}, {p}, {p}) RETURNING id""",
                (candidate_id, interview_number, interviewer_name, comments, verdict, interview_date),
            )
            return cursor.fetchone()[0]
        else:
            cursor = self._execute(
                f"""INSERT INTO interviews (candidate_id, interview_number, interviewer_name, comments, verdict, interview_date)
                   VALUES ({p}, {p}, {p}, {p}, {p}, {p})""",
                (candidate_id, interview_number, interviewer_name, comments, verdict, interview_date),
            )
            self.conn.commit()
            return cursor.lastrowid

    def get_interview(self, interview_id: int) -> dict | None:
        """Return a single interview."""
        p = self.placeholder
        rows = self.execute_query(
            f"SELECT * FROM interviews WHERE id = {p}", (interview_id,)
        )
        return rows[0] if rows else None

    def update_interview(self, interview_id: int, interview_number: int, interviewer_name: str,
                         comments: str, verdict: str | None = None,
                         interview_date: str | None = None):
        """Update an existing interview."""
        p = self.placeholder
        self._execute(
            f"""UPDATE interviews SET interview_number = {p}, interviewer_name = {p},
               comments = {p}, verdict = {p}, interview_date = {p}
               WHERE id = {p}""",
            (interview_number, interviewer_name, comments, verdict, interview_date, interview_id),
        )
        self.conn.commit()

    def delete_interview(self, interview_id: int):
        """Delete an interview."""
        p = self.placeholder
        self._execute(f"DELETE FROM interviews WHERE id = {p}", (interview_id,))
        self.conn.commit()

    def update_final_verdict(self, candidate_id: int, final_verdict: str | None):
        """Update the final verdict for a candidate."""
        p = self.placeholder
        self._execute(
            f"UPDATE candidates SET final_verdict = {p} WHERE id = {p}",
            (final_verdict, candidate_id),
        )
        self.conn.commit()

    def add_proposed_customer(self, candidate_id: int, customer_name: str) -> int:
        """Add a proposed customer for a candidate. Returns the id."""
        p = self.placeholder
        if self.backend == "postgresql":
            cursor = self._execute(
                f"INSERT INTO proposed_customers (candidate_id, customer_name) VALUES ({p}, {p}) RETURNING id",
                (candidate_id, customer_name),
            )
            row = cursor.fetchone()
            self.conn.commit()
            return row[0]
        else:
            cursor = self._execute(
                f"INSERT INTO proposed_customers (candidate_id, customer_name) VALUES ({p}, {p})",
                (candidate_id, customer_name),
            )
            self.conn.commit()
            return cursor.lastrowid

    def delete_proposed_customer(self, proposed_customer_id: int):
        """Delete a proposed customer entry."""
        p = self.placeholder
        self._execute(
            f"DELETE FROM proposed_customers WHERE id = {p}", (proposed_customer_id,)
        )
        self.conn.commit()

    def get_proposed_customer(self, proposed_customer_id: int) -> dict | None:
        """Return a single proposed customer."""
        p = self.placeholder
        rows = self.execute_query(
            f"SELECT * FROM proposed_customers WHERE id = {p}",
            (proposed_customer_id,),
        )
        return rows[0] if rows else None

    def execute_query(self, sql: str, params=None) -> list[dict]:
        """Execute a SQL query and return results as list of dicts.

        When params is None and the query comes from LLM-generated SQL,
        only safe SELECT statements are allowed.
        """
        if params is None:
            stripped = sql.strip().upper()
            if not stripped.startswith("SELECT"):
                raise ValueError("Only SELECT queries are allowed")
            # Block dangerous keywords that could appear after SELECT
            dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
                         "TRUNCATE", "GRANT", "REVOKE", "COPY", "INTO OUTFILE",
                         "INTO DUMPFILE", "LOAD_FILE", "EXEC", "EXECUTE", "CALL"]
            # Remove string literals before checking to avoid false positives
            import re
            sql_no_strings = re.sub(r"'[^']*'", "''", stripped)
            for keyword in dangerous:
                if keyword in sql_no_strings:
                    raise ValueError(f"Forbidden keyword in query: {keyword}")
            # Block multiple statements (semicolon followed by more SQL)
            if ";" in sql_no_strings.rstrip(";").rstrip():
                raise ValueError("Multiple statements are not allowed")

        cursor = self._execute(sql, params)
        if cursor.description is None:
            return []
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_schema_description(self) -> str:
        """Return a human-readable schema description for LLM prompt construction."""
        return """
Tables:

1. candidates
   - id: INTEGER PRIMARY KEY
   - name: TEXT (unique, candidate full name)
   - date_of_birth: TEXT (YYYY-MM-DD format)
   - university: TEXT (graduation university)
   - degree_field: TEXT (field of study)
   - job_title: TEXT (current/most recent job title)
   - years_experience: REAL (total years of professional experience)
   - final_verdict: TEXT (overall hiring decision across all interviews)

2. technologies
   - id: INTEGER PRIMARY KEY
   - candidate_id: INTEGER (FK -> candidates.id)
   - technology_name: TEXT (e.g. "Python", "React", "PostgreSQL")
   One row per technology per candidate.

3. experiences
   - id: INTEGER PRIMARY KEY
   - candidate_id: INTEGER (FK -> candidates.id)
   - company: TEXT
   - role: TEXT (job title at that company)
   - start_date: TEXT (YYYY-MM or YYYY format)
   - end_date: TEXT (YYYY-MM or YYYY format, or "present")
   - description: TEXT (brief description of responsibilities)
   One row per work experience per candidate.

4. interviews
   - id: INTEGER PRIMARY KEY
   - candidate_id: INTEGER (FK -> candidates.id)
   - interview_number: INTEGER (1st, 2nd, 3rd interview etc.)
   - interviewer_name: TEXT (name of the person who conducted the interview)
   - comments: TEXT (interviewer's comments/notes)
   - verdict: TEXT (interviewer's verdict for this interview)
   - interview_date: TEXT (YYYY-MM-DD format)
   One row per interview per candidate.

5. proposed_customers
   - id: INTEGER PRIMARY KEY
   - candidate_id: INTEGER (FK -> candidates.id)
   - customer_name: TEXT (name of the customer this candidate was proposed to)
   One row per customer per candidate.
""".strip()

    def is_connected(self) -> bool:
        """Check if the database connection is alive."""
        try:
            self._execute("SELECT 1")
            return True
        except Exception:
            return False

    def reconnect(self, database_url: str):
        """Reconnect to PostgreSQL (for serverless cold starts)."""
        if self.backend == "postgresql":
            import psycopg2

            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = psycopg2.connect(database_url)
            self.conn.autocommit = False

    def close(self):
        """Close the database connection."""
        self.conn.close()
