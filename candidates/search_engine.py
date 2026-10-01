"""
Search engine: natural language query -> SQL -> results -> summary.
Dialect-aware: generates correct SQL for SQLite or PostgreSQL.
"""

import json
import logging

from .database import Database
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

SQL_GENERATION_PROMPT = """You are a SQL query generator for a CV/resume database.
Given a natural language query, generate a {dialect}-compatible SELECT query.

Database schema:
{schema}

Rules:
- Return ONLY the SQL query, no markdown, no explanation, no backticks
- Only generate SELECT statements (never INSERT, UPDATE, DELETE, DROP, etc.)
- Use JOINs when querying across tables
- {like_instruction}
- Use GROUP BY and HAVING when counting or aggregating
- The technologies table has one row per technology per candidate
- Always include candidate name in results for identification
- {case_instruction}"""

SUMMARIZATION_PROMPT = """You are a helpful assistant summarizing CV database search results.

The user asked: "{query}"
The SQL query executed: {sql}
The raw results: {results}

Provide a concise, natural language summary of the findings.
If no results were found, say so clearly.
Mention specific candidate names and relevant details."""


class SearchEngine:
    def __init__(self, llm_client: LLMClient, database: Database, sql_llm_client: LLMClient = None):
        self.llm_client = llm_client
        self.sql_llm_client = sql_llm_client or llm_client
        self.database = database

    def search(self, natural_language_query: str) -> dict:
        """Full search pipeline. Returns dict with sql, raw_results, and summary."""
        sql = self._generate_sql(natural_language_query)
        logger.info(f"Generated SQL: {sql}")

        try:
            raw_results = self.database.execute_query(sql)
        except ValueError as e:
            return {
                "sql": sql,
                "raw_results": [],
                "summary": f"Error: Generated query was rejected - {e}",
            }
        except Exception as e:
            logger.error(f"SQL execution failed: {e}")
            return {
                "sql": sql,
                "raw_results": [],
                "summary": f"Error executing query: {e}",
            }

        summary = self._summarize_results(natural_language_query, sql, raw_results)

        return {
            "sql": sql,
            "raw_results": raw_results,
            "summary": summary,
        }

    def _generate_sql(self, query: str) -> str:
        """Ask LLM to translate natural language to SQL."""
        schema = self.database.get_schema_description()
        dialect = self.database.dialect

        if dialect == "PostgreSQL":
            like_instruction = "Use ILIKE with % for case-insensitive partial text matching"
            case_instruction = "Use ILIKE for case-insensitive comparisons"
        else:
            like_instruction = "Use LIKE with % for partial text matching"
            case_instruction = "Use LOWER() function for case-insensitive comparisons"

        system_prompt = SQL_GENERATION_PROMPT.format(
            dialect=dialect,
            schema=schema,
            like_instruction=like_instruction,
            case_instruction=case_instruction,
        )
        sql = self.sql_llm_client.send_message(system_prompt, query)
        return sql.strip().strip("`").strip()

    def _summarize_results(self, query: str, sql: str, results: list[dict]) -> str:
        """Ask LLM to summarize the raw SQL results in natural language."""
        prompt = SUMMARIZATION_PROMPT.format(
            query=query,
            sql=sql,
            results=json.dumps(results, indent=2),
        )
        return self.llm_client.send_message(
            "You are a helpful assistant that summarizes search results concisely.",
            prompt,
        )
