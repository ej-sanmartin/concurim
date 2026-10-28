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
| `f` | Fit the graph |
| `z` | Fullscreen. Esc leaves it |

**Explain** lingers on blocking events. **Real time** follows the
recorded gaps. **Next block** jumps to the next wait. **Group workers**
collapses groups of four or more similar actors.

**Compare** (`concurim compare a.concurim b.concurim`) puts two
recordings on one scale. It compares facts, such as a standard build
and a free-threaded build. It does not invent a GIL timeline.

**Export** (`concurim export run.concurim -o clip.mp4`) writes a clip or
PNG frames of the picture. The **Export…** button in the viewer is the
same thing. Review a clip before sending it: it shows whatever the
picture shows, including paths and, in the Code view, source.
