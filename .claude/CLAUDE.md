## authorized edits:
1. always ask when need to do rm -f for any files/folders.

## Implementation Rules
1. If a function or class is used by two or more parts of the logic, please abstract it into an independent component to avoid duplication.
2. Follow the “Don’t Repeat Yourself” principle, but apply it with balance. Avoid splitting very small functions (e.g., with only one or two simple clauses), so the code stays easy for engineers to read and understand.

## Logging Config Rules
1. All print statements must be removed from production code. print blocks the event loop, slows down async execution, and cannot be filtered or routed. Use the project logger for all runtime messages. print is allowed only for temporary local debugging and must not remain in production paths.
2. All HTTP client logs must be classified as DEBUG level.
3. High-level pipeline events must use INFO level. Steps such as starting a job, completing a processing stage, counting fetched items, or summarizing work should be logged at INFO. INFO logs should describe what the system is doing, not how HTTP libraries behave.
4. DEBUG logs should capture detailed internal operations.
5. INFO logs must remain minimal, meaningful, and high-signal.

## Documentation: All saved in "docs/"
### README.md
1. Only have one README.md under the root (repo).
2. README.md shows the overview of this project.
2. Modify as needed to describe the in-use components of this repo, up-to-date.

### Other documentation
1. for each fix, will record all in one MD file "docs/FIX_Database_Docs.md".
2. for each claude session/edition, don't generate extra solo md files. Record everything in "docs/RECORD_Change.md".
3. For all new markdown files, first check if can combine with existed MD files in "docs/". If not, create and save only in "docs/".
4. For all documentation. Keep words precise. Each addition of record will add a one-sentence index indicated with edit time.
5. Documentation should be clear and less redundant that minimizes repeated contents.
6. Everytime a new change happened, add a new date and new index to precisely describe the change. To avoid redundantness, if modified on previous change (like discarded old changes), simply refer to previous index and shorten previous change contents with less details.