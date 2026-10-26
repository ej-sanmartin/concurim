"""A three-stage pipeline whose items are traced back to their source.

Each stage turns one item into new ones: a page becomes sentences, and a
sentence becomes a word count. Passing ``derived_from=item.object_id`` to
``put`` records that link, so the viewer's Lineage tab can walk from a
count back to the page it came from. Run it directly, record it with
``concurim record``, or open it from the gallery in ``concurim``.
"""

import queue

from concurim import TracedQueue, TracedThread

PAGES = ["Threads share memory. Queues move work.", "Tasks yield. Locks guard."]


def split_pages(pages: TracedQueue, sentences: TracedQueue) -> None:
    """Turn every page into one item per sentence."""
    while True:
        try:
            page = pages.get_with_id()
        except queue.ShutDown:
            sentences.shutdown()
            return
        for text in page.value.split(". "):
            sentences.put(text.strip("."), derived_from=page.object_id)
        pages.task_done(page.object_id)


def count_words(sentences: TracedQueue, counts: TracedQueue) -> None:
    """Turn every sentence into a word count."""
    while True:
        try:
            sentence = sentences.get_with_id()
        except queue.ShutDown:
            counts.shutdown()
            return
        words = len(sentence.value.split())
        counts.put(words, derived_from=sentence.object_id)
        sentences.task_done(sentence.object_id)


def main() -> None:
    pages = TracedQueue(name="Pages")
    sentences = TracedQueue(name="Sentences")
    counts = TracedQueue(name="Counts")
    stages = [
        TracedThread(target=split_pages, args=(pages, sentences), name="split"),
        TracedThread(
            target=count_words, args=(sentences, counts), name="count"
        ),
    ]
    for stage in stages:
        stage.start()
    for page in PAGES:
        pages.put(page)
    pages.shutdown()
    total = 0
    while True:
        try:
            total += counts.get()
        except queue.ShutDown:
            break
    for stage in stages:
        stage.join()
    print(f"{total} words in {len(PAGES)} pages")


if __name__ == "__main__":
    main()
