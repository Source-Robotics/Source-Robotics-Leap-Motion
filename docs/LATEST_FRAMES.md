**Latest-frame acquisition and tracking health — 0.1.0b2**

These features are available in the published
[0.1.0b2 package on PyPI](https://pypi.org/project/source-robotics-leap-motion/0.1.0b2/).
The runtime engine, models, driver, frame data model,
and recording format are unchanged; b2 reuses the pinned b1 runtime download.

Use `Tracker(mode="latest", max_frame_age=0.1)` when application work runs slower
than tracking. Use the default `Tracker()` when each frame matters, for example
recording a complete session. `Tracker.demo(mode="latest")` provides paced synthetic
data without hardware. An unpaced demo is rejected in latest mode.

```python
from source_robotics_leap_motion import ConnectionError, Tracker, TrackingTimeoutError

with Tracker(mode="latest", max_frame_age=0.1) as tracker:
    try:
        frame = tracker.read(timeout=0.25)
        print(frame.right_hand)
    except TrackingTimeoutError:  # Includes StaleFrameError.
        print("No fresh tracking frame", tracker.health.to_dict())
    except ConnectionError:
        print("Device or service disconnected", tracker.health.to_dict())
```

The background reader opens, polls, and closes the source on one thread, including
native sources. It keeps one pending immutable frame and a bounded statistics window
of 120 arrival times. It replaces unread frames as newer frames arrive. Calling
`read()` consumes the slot; another read waits for the next distinct frame. It does
not return the same cached frame repeatedly. Multiple consumers share this one
slot; applications needing independent streams should open separate trackers.

The age limit applies to local receipt time. Expired pending frames are discarded,
and `read()` waits up to its timeout for a fresh replacement. A deadline with no
frames ever received raises `TrackingTimeoutError`. A deadline after the last
distinct frame has become too old raises `StaleFrameError`, a subclass of that
exception. Exact consecutive duplicate frame identities do not refresh freshness.
Disconnections invalidate any pending frame and propagate the source error. A finite
source can deliver its last fresh pending frame before `StopIteration`.

Context exit wakes blocked consumers and joins the worker. Normal reads poll with
a 50 ms bound. Custom `FrameSource` implementations must honor `read(timeout)` and
return `None` on a polling timeout. A source that ignores deadlines can prevent
shutdown: after five seconds, close raises `ConnectionError` and reopening is refused
while the old worker is alive. The package never closes a native handle concurrently
with its owning reader. `reconnect()` explicitly closes and opens a new session;
there is no automatic reconnect or robot motion restart.

`tracker.health` is a thread-safe immutable `TrackingHealth` snapshot. It is also
available in sequential mode. Reading it never polls hardware.

| Field | Meaning |
| --- | --- |
| `status` | `closed`, `starting`, `waiting`, `streaming`, `stale`, `disconnected`, `ended`, or `error` |
| `received_frames` | Valid frame packets received in this session, including exact consecutive duplicates |
| `delivered_frames` | Frames returned to application reads |
| `skipped_frames` | Frames deliberately omitted by latest mode: replacements, duplicates, expirations, or discarded pending data on failure/close |
| `duplicate_frames` | Consecutive packets with the same clock domain, device ID, frame ID, and timestamp |
| `read_timeouts` | Application reads that reached their deadline; internal polling timeouts are excluded |
| `timestamp_resets` | Regressing source timestamps within the same clock domain and device |
| `received_fps` | Distinct local arrivals per second over at most 120 frames; zero when not streaming |
| `last_frame_age_s` | Monotonic time since Python received the last distinct frame; `None` before the first |
| `last_frame_id`, `last_frame_timestamp_us`, `device_id`, `clock_domain` | Last distinct frame identity |
| `last_hand_count` | Hands in the last distinct frame; zero is valid tracking data |
| `last_error` | Latest session error text, retained after close |

Counts reset on opening or reconnecting. They remain available after close. Closed
snapshots report zero current FPS. In latest mode, at a synchronized instant,
received frames equal delivered plus skipped plus the optional pending frame.
Skipped counts are **not** a measure of camera or network packet loss. Sequential
mode preserves delivery of duplicates and reports zero deliberately skipped frames.

`streaming` becomes `stale` when the local age exceeds `max_frame_age`, in both modes.
Sequential mode reports this observation but preserves its existing read behavior;
it does not reject queued frames. A camera streaming empty-hand frames remains
`streaming`. `last_hand_count` is historical during a stale or disconnected period;
readers must examine status as well as hand count.

Frame timestamps belong to the named service clock. They are never subtracted from
Python's monotonic clock to invent an absolute latency. Local receipt age cannot
prove when exposure happened or detect all upstream buffering. Latest mode drains
the connection continuously, but it is not a hard real-time or robot safety system.

The CLI accepts `--latest`, `--max-frame-age SECONDS`, and `--health` for monitoring
and recording. Latest-mode recordings intentionally omit overwritten frames. Replay
remains sequential and also accepts `--health`. Health snapshots are JSON records
under `tracking_health` on stderr, roughly once per second while streaming and on
exit after tracking opens. Frame JSON on stdout and recording files remain unchanged.

```powershell
.\.venv\Scripts\source-leap.exe --latest --health --duration 10
.\.venv\Scripts\python.exe tools\benchmark_latest.py --duration 10 --consumer-rate 20
```

**Live validation, 5 November 2026.** On this PC's Original Leap Motion Controller
and existing legacy service, two application consumers ran at 20 Hz for ten seconds.
Latest mode received 783 packets and delivered 200. At the final in-session snapshot,
582 were skipped and one was pending. No duplicates, read timeouts, timestamp resets,
or tracking errors were recorded. The recent arrival rate was about 80 FPS.

The latest stream's receipt age at sampling was **6.40 ms median, 12.07 ms p95,
27.36 ms maximum**. The sequential reader accumulated a **7.39-second timestamp
gap** behind the latest reader by the last sample, comparing the same service clock.
Combined CPU time for both Python clients was about 0.78% of one core for this run.
No hands were visible, so this validates queue behavior and camera streaming, not
full-skeleton processing cost, improved accuracy, or absolute camera latency.
Raw results are kept locally in `.tools/latest-benchmark-b2.json`.

A separate one-minute slow-consumer run received 4,749 frames (including startup
warmup), with no duplicates, read timeouts, clock resets, or tracking errors. Close
joined the worker and left received counts equal to delivered plus skipped. Python
allocations traced during the measured minute peaked below 9 KB; this excludes
pre-existing allocations and native/service memory. No hands were visible in this
run either. Results are in `.tools/latest-soak-b2.json`.

The built b2 wheel passed **107 tests on each of CPython 3.10.11, 3.11.9, 3.12.10,
3.13.17, 3.14.10, and 3.15.2** in separate Windows venvs. Each installed wheel received
30 live sequential frames and 30 live latest-mode frames, closed its worker, passed
dependency checks, and round-tripped the previously recorded full-hand session.
Results are in `.tools/compatibility-results-0.1.0b2.json`.

Automated tests exercise frame replacement, duplicate freshness, expiration,
connection failures, EOF, source thread ownership, startup cleanup, shutdown,
reconnection, invalid options, bounded health history, and CLI recording/JSON output.
The b1 hardware and platform limits in [beta validation](BETA_VALIDATION.md) still
apply. Linux/macOS controller tests and clean-Windows driver setup remain pending.
