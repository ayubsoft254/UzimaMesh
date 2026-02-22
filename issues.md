# Planned Improvements & Issues

## [Issue #1] Conversation Persistence
**Goal**: Ensure patients can continue their chat after a page refresh or server restart.
- [ ] Add `thread_id` field to the `Patient` or `TriageSession` model.
- [ ] Update `triage/views.py` to retrieve the existing `thread_id` from the database.
- [ ] Implement logic to associate sessions with authenticated users or unique device identifiers.

## [Issue #2] Agent Orchestration & Coordination
**Goal**: Enable seamless handoffs and cross-agent communication.
- [ ] Implement automatic handoff from `Intake Agent` to `Analysis Agent` once data is collected.
- [ ] Create a "Switchboard" logic in `services.py` to route messages between agents.
- [ ] Update agents to be aware of each other's capabilities.

## [Issue #3] Refined Intake Agent Flow
**Goal**: Improve the user experience with personal greetings and step-by-step information collection.
- [ ] Update `instructions` in `Uzima-Intake-Agent.agent.yaml`.
- [ ] Implement step-by-step logic (Greeting -> Name -> Symptoms -> etc.).
- [ ] Connect `Intake Agent` to `Analysis/Guardian` agents for urgency determination.
