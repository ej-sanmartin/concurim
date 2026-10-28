# Teaching

The home screen examples are real recordings. Opening one does not run
anything. Start with these.

| Open this | To see |
| --- | --- |
| Producer-consumer | A shared queue, jobs moving, workers blocking |
| Bounded queue backpressure | A producer stuck because the queue is full |
| Lock contention | One lock, one holder, everyone else waiting |
| Lock ordering (wait cycle) | Two threads each holding the lock the other wants |
| Semaphore limit | Two permits, five threads |
| threading.Barrier | The first arrivals wait for the last one |
| ThreadPoolExecutor | Tasks waiting, then running on a worker |
| CPU-bound threads | A run to record twice and open with Compare |
| Asyncio task switching | One thread, tasks taking turns |
| asyncio.Queue | The same full-queue wait, on tasks |

The lock-order example waits out a real cycle and then times out, so the
program can finish. The viewer says the cycle appeared and then cleared.
A program that never times out is the stuck-run case in
[limitations](limitations.md): the picture ends on the last observed
event.

Source for every example is behind **View source** on the card, and
under `src/concurim/samples/`.
