# Review gates learned from real implementation

Read this reference when reviewing stateful, transactional, editor, queue, workflow, or undoable behavior. Apply only the relevant gates; do not force editor tests onto unrelated code.

## Boundary behavior

Do not verify an operation only in isolation or only adjacent to another operation of the same kind. Test the boundary with the ordinary behavior that occurs immediately before and after it.

For undoable editor transactions, one structural operation must remain one history intent when surrounded by typing:

- typing, then structural operation, then typing;
- undo each step independently in reverse order;
- redo each step independently;
- verify document structure, stable IDs, selection or caret, and preserved opaque content after every step.

For ProseMirror history specifically, `closeHistory(tr)` closes the event before the transaction; it does not by itself prove that immediate following input cannot join the structural event. Require a regression test that demonstrates both sides of the boundary in the actual command integration.

## Adversarial review

Worker-authored green tests are candidate evidence. Codex should identify at least the highest-risk invariant and test a case not supplied by the worker. Useful targets include hidden identifiers inside opaque carriers, validation or allocation performed before applicability is known, no-op commands changing history, and state restored across a complete undo/redo cycle.

Keep the finding open until the repaired diff passes the new regression under independent execution. A repair statement or a rerun of the old suite is not recheck evidence.
