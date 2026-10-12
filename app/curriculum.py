"""Course catalogue the voice tutor teaches from.

This is the content side of the demo: a small, real curriculum — courses, topics,
and a section-by-section lesson plan per topic. The service does not invent the
lesson; it hands the plan to the model (via the session instruction and provider
metadata), which is what lets checkpoints reference real sections and what lets
the offline demo teach something recognisable instead of a placeholder.

The catalogue is deliberately static and dependency-free: no database, no
network, no locale files. A production deployment would source this from the
LERNA course catalogue; the shape here is what that integration must produce.

Topics are language-independent — the tutor speaks the same lesson plan in any of
the ten mandatory languages, so `LOCALISED_GREETINGS` is the only per-language
content this module owns (short, hand-written phrases used by the offline mock,
clearly labelled as demo material — real speech comes from the vendors).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# types
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Section:
    """One teachable step of a lesson, and the groundwork it lays."""

    title: str
    goal: str
    concepts: tuple[str, ...] = ()


@dataclass(frozen=True)
class Topic:
    id: str
    course_id: str
    title: str
    summary: str
    level: str
    minutes: int
    sections: tuple[Section, ...]
    concepts: tuple[str, ...]
    questions: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()

    @property
    def section_titles(self) -> list[str]:
        return [s.title for s in self.sections]

    def lesson_plan(self) -> list[dict[str, str]]:
        """The plan handed to the tutor, and shown in the demo's dev panel."""
        return [{"title": s.title, "goal": s.goal} for s in self.sections]

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "course_id": self.course_id,
            "title": self.title,
            "summary": self.summary,
            "level": self.level,
            "minutes": self.minutes,
            "concepts": list(self.concepts),
            "questions": list(self.questions),
            "prerequisites": list(self.prerequisites),
            "sections": [
                {"title": s.title, "goal": s.goal, "concepts": list(s.concepts)} for s in self.sections
            ],
            "section_titles": self.section_titles,
        }


@dataclass(frozen=True)
class Course:
    id: str
    title: str
    subject: str
    level: str
    description: str
    topics: tuple[Topic, ...] = field(default_factory=tuple)

    def as_dict(self, *, with_topics: bool = True) -> dict:
        data = {
            "id": self.id,
            "title": self.title,
            "subject": self.subject,
            "level": self.level,
            "description": self.description,
            "topic_count": len(self.topics),
        }
        if with_topics:
            data["topics"] = [t.as_dict() for t in self.topics]
        return data


def _t(
    tid: str,
    course: str,
    title: str,
    summary: str,
    *,
    level: str = "beginner",
    minutes: int = 12,
    sections: list[tuple[str, str]],
    concepts: list[str],
    questions: list[str] | None = None,
    prerequisites: list[str] | None = None,
) -> Topic:
    return Topic(
        id=tid,
        course_id=course,
        title=title,
        summary=summary,
        level=level,
        minutes=minutes,
        sections=tuple(Section(t, g) for t, g in sections),
        concepts=tuple(concepts),
        questions=tuple(questions or ()),
        prerequisites=tuple(prerequisites or ()),
    )


# --------------------------------------------------------------------------- #
# the catalogue
# --------------------------------------------------------------------------- #

_COURSES: tuple[Course, ...] = (
    Course(
        id="algorithms-101",
        title="Algorithms & Data Structures",
        subject="Computer Science",
        level="undergraduate",
        description="How to search, sort and traverse data — and how to reason about the cost.",
        topics=(
            _t(
                "binary-search",
                "algorithms-101",
                "Binary Search",
                "Find a value in a sorted range by halving it, and prove why the cost is logarithmic.",
                sections=[
                    ("The idea of halving", "compare with the middle, discard the half that cannot hold the target"),
                    ("Trace it on a small array", "walk through 16 elements down to 8, 4, 2, 1"),
                    ("Why the cost is logarithmic", "the range halves each step, so the number of steps is log of n"),
                    ("Common mistakes", "unsorted input and the overflow-prone midpoint calculation"),
                ],
                concepts=["sorted input", "midpoint", "halving", "O(log n)", "overflow-safe midpoint"],
                questions=["Why must the array be sorted?", "Why is it O(log n) and not O(n/2)?"],
                prerequisites=["arrays", "comparison"],
            ),
            _t(
                "merge-sort",
                "algorithms-101",
                "Merge Sort",
                "Split, sort, and merge — a stable sort with a guaranteed n log n bound.",
                level="intermediate",
                sections=[
                    ("Divide", "split the array into halves until every piece has one element"),
                    ("Conquer", "a single element is already sorted — so sort the pairs on the way back up"),
                    ("The merge step", "walk two sorted lists with two pointers and take the smaller head"),
                    ("Cost and stability", "n log n comparisons and equal keys keep their original order"),
                ],
                concepts=["divide and conquer", "merging", "two pointers", "O(n log n)", "stability"],
                questions=["Why is merge sort stable?", "Why does it need extra memory?"],
            ),
            _t(
                "recursion",
                "algorithms-101",
                "Recursion and the Call Stack",
                "Solve a problem by solving a smaller copy of it — and understand what the stack is doing.",
                sections=[
                    ("The base case", "the smallest input answered directly, with no further calls"),
                    ("The recursive case", "shrink the input and trust the smaller call to be correct"),
                    ("The stack unwinds", "each frame waits for the one below it and combines the results"),
                    ("When recursion is the wrong tool", "deep inputs overflow the stack; iteration or memoisation may be better"),
                ],
                concepts=["base case", "recursive case", "call stack", "stack overflow", "memoisation"],
                questions=["What happens if a base case is missing?", "When should I prefer a loop?"],
            ),
            _t(
                "hash-tables",
                "algorithms-101",
                "Hash Tables",
                "Constant-time lookup, and what really happens when two keys collide.",
                level="intermediate",
                sections=[
                    ("Hashing", "turn a key into an index with a hash function"),
                    ("Collisions", "two keys can share an index — chaining or open addressing resolves it"),
                    ("Load factor and resizing", "as the table fills, probes get longer, so grow and rehash"),
                    ("Cost in practice", "average O(1) lookup, O(n) in the worst case"),
                ],
                concepts=["hash function", "collision", "open addressing", "chaining", "load factor"],
                questions=["Why is worst-case lookup O(n)?", "What makes a hash function good?"],
            ),
            _t(
                "graph-bfs",
                "algorithms-101",
                "Breadth-First Search",
                "Explore a graph level by level — and get shortest paths in unweighted graphs for free.",
                level="intermediate",
                sections=[
                    ("The queue", "start at the source and enqueue its neighbours"),
                    ("Visiting neighbours", "mark nodes visited so cycles cannot trap you"),
                    ("Levels are distances", "each expansion is one more edge away, which is the shortest path"),
                    ("When BFS is the wrong tool", "weighted edges need Dijkstra, deep searches may prefer DFS"),
                ],
                concepts=["queue", "visited set", "level order", "shortest path", "unweighted graph"],
                questions=["Why does BFS give shortest paths here?", "What changes if the edges have weights?"],
            ),
        ),
    ),
    Course(
        id="calculus-1",
        title="Calculus I",
        subject="Mathematics",
        level="undergraduate",
        description="Limits, derivatives and what they mean about the shape of a function.",
        topics=(
            _t(
                "limits",
                "calculus-1",
                "Limits",
                "What a function approaches — even where it is not defined.",
                sections=[
                    ("What a limit means", "the value the output settles towards as the input closes in"),
                    ("One-sided limits", "approach from the left and the right, and when they disagree"),
                    ("Continuity", "the limit exists, the point exists, and they are equal"),
                    ("Limits at infinity", "end behaviour, and growth compared with other functions"),
                ],
                concepts=["approach", "one-sided limit", "continuity", "asymptote", "indeterminate form"],
                questions=["Can a limit exist where the function is undefined?", "What does a jump discontinuity look like?"],
            ),
            _t(
                "derivatives",
                "calculus-1",
                "Derivatives as Rate of Change",
                "The slope of the tangent line, defined as a limit of average rates.",
                sections=[
                    ("From average to instantaneous", "the secant slope over an interval shrinking to zero"),
                    ("The definition as a limit", "difference quotient and its limit"),
                    ("Rules you can use", "power, sum, product and quotient rules"),
                    ("Reading the sign", "positive slope rising, negative falling, zero at a flat spot"),
                ],
                concepts=["secant", "tangent", "difference quotient", "power rule", "critical point"],
                questions=["Why take a limit instead of dividing by zero?", "What does a zero derivative tell me?"],
            ),
            _t(
                "chain-rule",
                "calculus-1",
                "The Chain Rule",
                "Differentiate a function inside a function without losing the inner rate.",
                level="intermediate",
                sections=[
                    ("Composition", "an inner function feeding an outer one"),
                    ("The rule", "derivative of the outer at the inner, times the inner's derivative"),
                    ("Worked examples", "powers of linear functions, then nested trigonometry"),
                    ("Why it works", "rates multiply along the chain of dependencies"),
                ],
                concepts=["composition", "inner function", "outer function", "rate multiplication"],
                questions=["How do I recognise which part is inner?", "How does this extend to three layers?"],
            ),
            _t(
                "optimization",
                "calculus-1",
                "Optimization",
                "Find the largest and smallest values, and be sure you have found them.",
                level="intermediate",
                sections=[
                    ("Critical points", "where the derivative is zero or undefined"),
                    ("Testing candidates", "first derivative sign changes, or the second derivative"),
                    ("Closed intervals", "compare interior candidates with the endpoints"),
                    ("Word problems", "name the quantity, write it as one variable, then differentiate"),
                ],
                concepts=["critical point", "local maximum", "global maximum", "boundary check"],
                questions=["Why check the endpoints too?", "What if the derivative never reaches zero?"],
            ),
        ),
    ),
    Course(
        id="physics-1",
        title="Mechanics",
        subject="Physics",
        level="undergraduate",
        description="Forces, motion and conservation laws — the toolkit for first-year mechanics.",
        topics=(
            _t(
                "newton-laws",
                "physics-1",
                "Newton's Laws",
                "Three statements that turn a picture of forces into an equation of motion.",
                sections=[
                    ("Inertia", "no net force means constant velocity, not necessarily rest"),
                    ("F equals m a", "net force sets the acceleration, so direction matters more than speed"),
                    ("Action and reaction", "forces come in pairs acting on different bodies"),
                    ("Free-body diagrams", "isolate one object, draw only the forces on it, then sum"),
                ],
                concepts=["net force", "inertia", "free-body diagram", "action-reaction pair"],
                questions=["Why does a moving object not need a force to keep moving?", "Why do the two forces in a pair not cancel?"],
            ),
            _t(
                "projectile-motion",
                "physics-1",
                "Projectile Motion",
                "Horizontal and vertical motion are independent — which is why the parabola appears.",
                sections=[
                    ("Split the axes", "constant horizontal velocity, constant vertical acceleration"),
                    ("Time is shared", "the same clock drives both axes, which couples them"),
                    ("The parabolic path", "combine the two equations and eliminate time"),
                    ("Launch angle", "the range is largest at 45 degrees when there is no air resistance"),
                ],
                concepts=["independence of axes", "range", "trajectory", "launch angle"],
                questions=["Why does the horizontal velocity stay constant?", "Why 45 degrees for maximum range?"],
            ),
            _t(
                "energy-conservation",
                "physics-1",
                "Conservation of Energy",
                "Track the same quantity through a change and skip the forces entirely.",
                sections=[
                    ("Work", "force along the direction of motion transfers energy"),
                    ("Kinetic and potential", "energy stored in motion and in position"),
                    ("Conservation", "in the absence of friction the total stays constant"),
                    ("Friction and dissipation", "lost mechanical energy becomes heat, not nothing"),
                ],
                concepts=["work", "kinetic energy", "potential energy", "conservation", "dissipation"],
                questions=["When can I use energy instead of Newton's laws?", "Where does the energy go with friction?"],
            ),
            _t(
                "momentum-collisions",
                "physics-1",
                "Momentum and Collisions",
                "Total momentum survives a collision even when energy does not.",
                sections=[
                    ("Momentum", "mass times velocity, and it is a vector"),
                    ("Impulse", "force applied over time changes momentum"),
                    ("Elastic and inelastic", "energy changes in inelastic collisions, momentum does not"),
                    ("Solving collisions", "conservation of momentum, plus kinetic energy when elastic"),
                ],
                concepts=["momentum", "impulse", "elastic collision", "inelastic collision"],
                questions=["Why is momentum conserved in a crash?", "Which collisions keep kinetic energy?"],
            ),
        ),
    ),
    Course(
        id="programming-101",
        title="Python Foundations",
        subject="Programming",
        level="beginner",
        description="The parts of Python that every later course assumes you can use fluently.",
        topics=(
            _t(
                "variables-types",
                "programming-101",
                "Variables and Types",
                "Names bound to values, and the four types you will use constantly.",
                sections=[
                    ("Names and values", "a variable is a label pointing at an object, not a box"),
                    ("The core types", "integers, floats, strings and booleans, and how they convert"),
                    ("Dynamic typing", "the value carries the type, so unexpected types break arithmetic"),
                    ("Reading errors", "a type error tells you what the program tried to do"),
                ],
                concepts=["assignment", "int", "float", "str", "bool", "type conversion"],
                questions=["Why does integer division differ between languages?", "What does name error mean?"],
            ),
            _t(
                "control-flow",
                "programming-101",
                "Control Flow",
                "Branch on conditions and repeat work safely.",
                sections=[
                    ("Conditions", "comparisons produce booleans and combine with and, or, not"),
                    ("Branching", "if, elif and else, and why order matters"),
                    ("Loops", "for over a sequence, while on a condition that must eventually fail"),
                    ("Loop control", "break and continue, and avoiding off-by-one errors in ranges"),
                ],
                concepts=["boolean", "if/elif/else", "for", "while", "range", "off-by-one"],
                questions=["When should I use while instead of for?", "Why does range stop early?"],
            ),
            _t(
                "functions",
                "programming-101",
                "Functions",
                "Name a block of work, give it inputs, and return a value.",
                sections=[
                    ("Definition and call", "def names the work; the call runs it"),
                    ("Parameters and arguments", "positional, keyword, and default values"),
                    ("Return values", "returning a result versus printing it"),
                    ("Scope", "names inside a function are local unless declared otherwise"),
                ],
                concepts=["def", "parameter", "argument", "return", "scope"],
                questions=["Why does my function print but return nothing?", "What is the difference between local and global?"],
            ),
            _t(
                "lists-dicts",
                "programming-101",
                "Lists and Dictionaries",
                "The two collections everything else is built from.",
                sections=[
                    ("Lists", "ordered, changeable, indexed from zero"),
                    ("Slicing and iteration", "half-open ranges and looping over items directly"),
                    ("Dictionaries", "keys mapped to values, with fast lookup"),
                    ("Choosing between them", "order with duplicates means a list, lookup by key means a dict"),
                ],
                concepts=["list", "index", "slice", "dictionary", "key-value"],
                questions=["Why is dict lookup faster than scanning a list?", "What happens when I index past the end?"],
            ),
            _t(
                "debugging",
                "programming-101",
                "Reading and Fixing Errors",
                "Work from the traceback backwards, and change one thing at a time.",
                sections=[
                    ("Read the traceback", "the last line is the error, the frames above show the path"),
                    ("Reproduce it", "smallest possible input that still fails"),
                    ("Instrument, do not guess", "print or log the values you assumed"),
                    ("Fix and verify", "change one thing, re-run, and check the case that failed"),
                ],
                concepts=["traceback", "exception", "reproduction", "logging"],
                questions=["Where do I start reading a long traceback?", "Why should I change one thing at a time?"],
            ),
        ),
    ),
    Course(
        id="biology-1",
        title="Cell Biology",
        subject="Biology",
        level="undergraduate",
        description="What a cell is made of, how it divides, and how it stores and uses information.",
        topics=(
            _t(
                "cell-structure",
                "biology-1",
                "Cell Structure",
                "Membranes, organelles and which structures are shared across life.",
                sections=[
                    ("The membrane", "a selectively permeable lipid bilayer that defines inside from outside"),
                    ("Shared machinery", "ribosomes, DNA and cytoplasm in every cell"),
                    ("Eukaryotic additions", "nucleus and membrane-bound organelles"),
                    ("Plant versus animal", "cell wall, chloroplasts and a large vacuole"),
                ],
                concepts=["plasma membrane", "organelle", "prokaryote", "eukaryote", "ribosome"],
                questions=["Why is the membrane called selectively permeable?", "Which structures are in plant cells but not animal cells?"],
            ),
            _t(
                "mitosis",
                "biology-1",
                "Mitosis",
                "One cell becomes two identical cells, in four recognisable stages.",
                sections=[
                    ("Interphase first", "DNA is copied before division begins"),
                    ("Prophase and metaphase", "chromosomes condense and line up on the equator"),
                    ("Anaphase and telophase", "sister chromatids separate and two nuclei re-form"),
                    ("Why it matters", "growth and repair need genetically identical copies"),
                ],
                concepts=["interphase", "chromatid", "metaphase plate", "cytokinesis"],
                questions=["Why must DNA be copied before mitosis?", "How does mitosis differ from meiosis?"],
            ),
            _t(
                "dna-rna",
                "biology-1",
                "DNA, RNA and Protein",
                "Information flows from a stable archive to a working copy to a product.",
                sections=[
                    ("The archive", "base pairing makes DNA stable and copyable"),
                    ("Transcription", "a working RNA copy is made from one gene"),
                    ("Translation", "codons are read into a chain of amino acids"),
                    ("Mutations", "a changed base can change the protein, and often does not"),
                ],
                concepts=["base pairing", "transcription", "translation", "codon", "mutation"],
                questions=["Why is RNA used instead of DNA for the working copy?", "What makes a mutation silent?"],
            ),
            _t(
                "photosynthesis",
                "biology-1",
                "Photosynthesis",
                "Light energy becomes chemical energy, and oxygen is the by-product.",
                sections=[
                    ("Light reactions", "capture photons and split water"),
                    ("Calvin cycle", "use stored energy to fix carbon dioxide into sugar"),
                    ("Inputs and outputs", "carbon dioxide and water in, glucose and oxygen out"),
                    ("Limiting factors", "light, carbon dioxide and temperature each cap the rate"),
                ],
                concepts=["thylakoid", "light reactions", "Calvin cycle", "carbon fixation"],
                questions=["Where exactly does the oxygen come from?", "Why does the rate stop rising with more light?"],
            ),
        ),
    ),
)

COURSES: tuple[Course, ...] = _COURSES
TOPICS: tuple[Topic, ...] = tuple(t for c in COURSES for t in c.topics)
_TOPICS_BY_ID: dict[str, Topic] = {t.id: t for t in TOPICS}
_COURSES_BY_ID: dict[str, Course] = {c.id: c for c in COURSES}

#: Short phrases the offline mock speaks in the student's language. The lesson
#: content itself is language-independent; real speech comes from the vendors.
LOCALISED_GREETINGS: dict[str, str] = {
    "en": "Hello, let's begin.",
    "ar": "مرحبًا بك، لنبدأ الدرس.",
    "ar-eg": "أهلًا بيك يا فندم، يلا نبدأ الدرس.",
    "fr": "Bonjour, commençons la leçon.",
    "sw": "Habari, tuanze somo.",
    "am": "ሰላም፣ ትምህርቱን እንጀምር።",
    "ha": "Sannu, bari mu fara darasi.",
    "so": "Salaan, aan bilowno casharka.",
    "yo": "Ẹ n lẹ, ẹ jẹ́ ká bẹ̀rẹ̀ ẹ̀kọ́.",
    "ig": "Ndeewo, ka anyị malite ihe ọmụmụ.",
    "zu": "Sawubona, ake siqale isifundo.",
}


# --------------------------------------------------------------------------- #
# lookup helpers
# --------------------------------------------------------------------------- #


def list_courses(*, with_topics: bool = True) -> list[dict]:
    return [c.as_dict(with_topics=with_topics) for c in COURSES]


def list_topics() -> list[dict]:
    return [t.as_dict() for t in TOPICS]


def get_course(course_id: str) -> Course | None:
    return _COURSES_BY_ID.get(course_id)


def get_topic(topic_id: str) -> Topic | None:
    if not topic_id:
        return None
    return _TOPICS_BY_ID.get(topic_id.strip().lower())


def find_topic_by_title(title: str) -> Topic | None:
    """Resolve free text ('Binary Search', 'binary search') to a catalogued topic."""
    wanted = (title or "").strip().lower()
    if not wanted:
        return None
    for topic in TOPICS:
        if topic.title.lower() == wanted:
            return topic
    for topic in TOPICS:
        if wanted in topic.title.lower() or topic.title.lower() in wanted:
            return topic
    return None


def resolve(topic_id: str | None = None, topic: str | None = None) -> Topic | None:
    """Best-effort resolution of a catalogue id or free-text topic name."""
    return get_topic(topic_id or "") or find_topic_by_title(topic or "")


def stats() -> dict:
    return {
        "courses": len(COURSES),
        "topics": len(TOPICS),
        "sections": sum(len(t.sections) for t in TOPICS),
        "levels": sorted({t.level for t in TOPICS}),
    }
