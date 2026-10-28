# Concepts

Concurim records one schedule: the one this process actually ran. It
does not search for other interleavings, and it does not show who held
the GIL.

**Observed** facts come from an event. A solid border, a queue's
contents, and "blocked on this lock" are observed. **Inferred** facts
are a guess the viewer labels as such. A dashed border means the actor
is treated as running because nothing has said it is blocked. The
explanation card says when a sentence is inferred.

Recording changes timing. The picture is faithful to the instrumented
run, which is a bit slower than the same program with Concurim absent.

A file that does not compile is not a run. A program that starts and
then raises is a run, and the exception is in the trace. A program that
gets stuck is a run that ends at the last observed event. If threads are
waiting on locks one another holds, the viewer says so. That cycle is
read off this run. Queues and events do not name who has to move next,
so they are not drawn as a cycle.

Anything the chosen observability level cannot see is listed as not
observed. It is not filled in. The full list is in
[limitations](limitations.md).
