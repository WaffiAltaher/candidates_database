# Candidates Database

A small web app for managing candidate CVs. Upload a PDF CV and the app extracts
the candidate's details into a database. You can then search candidates in plain
language (for example "Python developers in Amsterdam with 5+ years"), and keep
track of interviews, verdicts and customers.

It runs as a FastAPI container with a vanilla JavaScript frontend and PostgreSQL,
hosted on Scaleway. AI features use Claude.

For development and deployment details, see [CLAUDE.md](CLAUDE.md) and
[docs/](docs/).
