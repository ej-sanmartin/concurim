# Reading a run

Open a trace with `uv run concurim view run.concurim`, or from the home
screen. The same event is selected in every view.

**Animation** is the picture: who is running, who is blocked, what each
queue holds, who holds each lock. Click a node to inspect it. Drag to
move, scroll to zoom. **Fit** puts everything back in view.

**Code** puts that picture beside the source. It needs a trace recorded
with `--include-source`. The line a worker is on is lit. A source link
in the Event card opens Code on that line.

**Timeline** is the same run as spans: waits, holds, and work. Click an
event, then show it in the animation.

**Resources** is the same state laid out as a list, which is the easier
place to read a lock cycle.

The explanation under the picture is one sentence for the current event.
If it depended on a guess, the card says inferred. Dashed borders are
inferred. Solid borders were observed.

| Key | Action |
| --- | --- |
| Space | Play or pause |
| Left / Right | One event. Shift moves ten |
| Home / End | First or last event |
| `[` `]` | Slower or faster |
| `f` | Fit the graph. Layout is remembered. **Reset layout** clears it |
| `z` | Fullscreen. Esc leaves it |

Click a thread, task, queue, lock, or item to inspect it. Drag nodes.
Scroll to zoom. In **Event**, a source location opens Code on that line.

**Explain** lingers on blocking events. **Real time** follows the
recorded gaps, and can compress idle time. **Next block** jumps to the
next wait. **Next for selection** jumps to the next event for the
selected actor. **Group workers** collapses groups of four or more
similar actors (automatic above 24). Repeating rows in the **Log** fold
into `×N`.

**Compare** (`concurim compare a.concurim b.concurim`) puts two
recordings on one scale. It compares facts, such as a standard build
and a free-threaded build. It does not invent a GIL timeline.

**Export** writes a clip or PNG frames. The **Export…** button is the
same command.

```bash
uv run concurim export run.concurim -o clip.mp4 --view code --events 5:40
```

The output can be `.mp4`, `.webm`, `.gif`, or a directory of PNG frames.
`--size 1080p` (also `720p`, `square`, or `WxH`), `--motion 0` cuts
straight from event to event, `--hide explanation` and `--hide timeline`
leave those overlays out, and `--no-footer` / `--no-watermark` leave the
chrome off. It needs a Chrome-family browser and ffmpeg
(`concurim[video]` bundles one, once the package is published). The
picture is deterministic for a given trace. Export only reads the trace.
Review a clip before sending it: it shows paths and, in the Code view,
source.
