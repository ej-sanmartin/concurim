"""threading.Event: runners wait at a starting gate.

No Concurim imports. Three runners call ``gate.wait()`` and block until the
starter calls ``gate.set()``. Setting the event does not run anyone at once:
each runner continues when the scheduler gets to it.
"""

import threading
import time

gate = threading.Event()


def runner(lane: int) -> None:
    """Wait for the gate, then run."""
    gate.wait()
    time.sleep(0.02 * lane)  # the race itself


def main() -> None:
    runners = [
        threading.Thread(target=runner, args=(lane,), name=f"runner-{lane}")
        for lane in (1, 2, 3)
    ]
    for thread in runners:
        thread.start()
    time.sleep(0.15)  # everyone is waiting at the gate
    gate.set()
    for thread in runners:
        thread.join()
    gate.clear()
    # A timed wait on an event nobody sets gives up.
    print("second race started:", gate.wait(timeout=0.05))


if __name__ == "__main__":
    main()
