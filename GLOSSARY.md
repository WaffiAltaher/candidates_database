# Candidates Database

A CV management and search system for recruiters, and the way work on it is planned and delivered.

## Language

### Delivery

**Ticket**:
One unit of planned work, kept on the issue tracker.
_Avoid_: Task, story, local ticket

**Agent ticket**:
A **Ticket** that a cloud agent implements, fully specified and needing no account access.
_Avoid_: Queue issue, AFK ticket

**Orchestrator ticket**:
A **Ticket** that the **Orchestrator** carries out itself because it needs account access or local tools.
_Avoid_: Local ticket

**Human ticket**:
A **Ticket** that only the user can carry out, such as a step needing a phone, a password or a judgement call.
_Avoid_: Manual ticket, HITL ticket

**Orchestrator**:
The local Claude session that plans the work, writes the **Tickets**, reviews and merges the work of cloud agents, and carries out **Orchestrator tickets**.
_Avoid_: Coordinator, main session

**Queue**:
The mechanism that hands **Agent tickets** to cloud agents one at a time, skipping any whose blockers are still open.
_Avoid_: Pipeline, dispatcher
