# Curriculum and Lesson Plans

The voice service teaches **from a plan**, not from a bare topic string. A plan
gives the tutor an order, gives checkpoints something real to name, and lets the
student resume mid-topic without repeating what they already understood.

The catalogue lives in `app/curriculum.py`:

| Course | Topics | Example |
|---|---|---|
| Algorithms & Data Structures | 5 | Binary Search, Merge Sort, Recursion, Hash Tables, BFS |
| Calculus I | 4 | Limits, Derivatives, The Chain Rule, Optimization |
| Mechanics | 4 | Newton's Laws, Projectile Motion, Energy, Momentum |
| Python Foundations | 5 | Variables & Types, Control Flow, Functions, Lists & Dicts, Debugging |
| Cell Biology | 4 | Cell Structure, Mitosis, DNA/RNA, Photosynthesis |

22 topics, 88 lesson steps.

> **Scope note.** This catalogue is *standalone demo content* for the service. It
> is deliberately static (no database, no network) so the service runs with no
> LERNA backend. A production deployment replaces it with the LERNA course
> catalogue — the data shape below is the integration contract.

## Shape of a topic

```python
Topic(
    id="binary-search",            # what clients pass as topic_id
    course_id="algorithms-101",
    title="Binary Search",
    summary="Find a value in a sorted range by halving it…",
    level="intermediate",          # beginner | intermediate
    minutes=12,
    sections=[                     # the teachable plan, in order
        Section("The idea of halving", "compare with the middle, discard the half that cannot hold the target"),
        Section("Trace it on a small array", "walk through 16 elements down to 8, 4, 2, 1"),
        …
    ],
    concepts=["sorted input", "midpoint", "halving", "O(log n)"],
    questions=["Why must the array be sorted?", …],   # suggested student questions
    prerequisites=["arrays", "comparison"],
)
```

## How the plan reaches the tutor

1. **Client** picks a topic from `GET /curriculum/courses` (or the `/topics`
   page) and creates a session with `topic_id`.
2. **Session** resolves it (`curriculum.resolve`, which also accepts a free-text
   topic name), sets `current_topic`, `topic_id`, `course_id` and `lesson_id`,
   and stores `lesson_plan` on the session state.
3. **System instruction** gets the plan rendered as an ordered list plus the
   instruction *"teach the plan in order, one step at a time, checking
   understanding between steps; do not restart a step the student already
   understood."*
4. **Provider metadata** carries `topic_title` and `sections` for composed
   pipelines, where the component that generates the words is not the realtime
   provider that received the session config. `LLMProvider.stream_reply` takes an
   optional `metadata` argument for exactly this, and `CascadePipelineProvider`
   forwards it. Real vendors ignore it — their instruction already contains the
   plan.
5. **State API** returns `topic_id` and `lesson_plan`, so a client (or the demo's
   dev panel) can show the steps.

Checkpoints then reference real sections: interrupting during step 3 produces a
checkpoint whose `section` is that step's title, and a resume continues from it.

## Languages

Topics are language-independent — the same plan is taught in any of the ten
mandatory languages (see `LANGUAGES.md`). The only per-language content in the
catalogue is `LOCALISED_GREETINGS`, ten short hand-written phrases used by the
offline mock so a demo session audibly confirms the chosen language. Real speech
comes from the vendors; with Gemini Live (`realtime:gemini`) the model handles
all nine catalogue languages natively, and Igbo composes
`cascade:elevenlabs+gemini+gemini`.

## Adding a topic

```python
_t("dijkstra", "algorithms-101", "Dijkstra's Algorithm", "Shortest paths with weights.",
   sections=[("The greedy choice", "always settle the closest unsettled node"), …],
   concepts=["weighted graph", "priority queue", "relaxation"])
```

Add it to the relevant `Course(topics=(…))` tuple. It appears immediately in
`/curriculum/topics`, in the `/topics` picker, and in any session created with
its id. Keep three or more sections per topic — the plan is what makes
checkpoints meaningful — and keep section goals to one short clause, since they
are spoken aloud.
