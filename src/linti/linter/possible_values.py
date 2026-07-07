"""The value model constant propagation reports back through.

:class:`PossibleValues` is the single answer type
:class:`~linti.linter.constant_propagation.ConstantPropagationIndex` returns
and rules read through ``LintContext.possible_values(name, line)``.  It is a
*cascade*: a rule takes exactly the strength it needs, and each stronger
accessor is a refinement of the level below it.

1. **Exactly one value** — :attr:`~PossibleValues.exact` yields the sole
   fully known scalar, or ``None`` in every weaker situation.
2. **All possible values** — :meth:`~PossibleValues.all_of` /
   :meth:`~PossibleValues.any_of` / :attr:`~PossibleValues.values` reason over
   *all* possibilities — a single known value is simply the one-element case,
   so level 1 is contained in level 2.  Arbitrary predicates are decidable
   only on *fully known* values, so a partially known variant never satisfies
   them; for substring questions — the one family that *is* decidable on
   partials — use :meth:`~PossibleValues.all_contain` /
   :meth:`~PossibleValues.any_contains` instead.
3. **Partially known** — :attr:`~PossibleValues.partial` exposes the known
   fragments of a single half-dynamic string, e.g. ``sName = 'prefix_' |
   pDyn;`` keeps ``'prefix_'`` as a :class:`PartialString` rather than
   collapsing to fully unknown.
4. **Written at all** — :attr:`~PossibleValues.assigned` distinguishes "never
   assigned" from "assigned but dynamic".

Every query answers "is this *provable*?": an unknown — a gap in a partial,
an incomplete set, a dynamic value — never counts as evidence, so ``False``
always means "not provable", not "provably false".

This module has no notion of TI syntax or sections; it only defines what a
tracked value can look like and how two values fold together (see
:func:`_normalize_string_segments`, used when concatenating).  Deciding
*when* to fold — e.g. that TI's ``|`` operator means concatenation — is the
interpreter's job, in :mod:`linti.linter.constant_propagation`.
"""

from dataclasses import dataclass
from typing import Optional, Union


class _Unknown:
    """Sentinel for a variable whose value cannot be determined statically."""

    def __repr__(self) -> str:
        return "UNKNOWN"


UNKNOWN = _Unknown()


@dataclass(frozen=True)
class PartialString:
    """A string whose value is only partially known statically.

    A concatenation such as ``'prefix_' | pDyn | '_suffix'`` cannot be folded
    to a single string, but its literal fragments are still worth keeping.
    ``PartialString`` records them as a *normalized* sequence of segments:
    each segment is either a known ``str`` chunk or the :data:`UNKNOWN`
    sentinel (a gap).  Normalization guarantees no two adjacent chunks and no
    two adjacent gaps, and that a partial always contains at least one gap
    (a fully known concatenation folds back to a plain ``str`` instead).
    """

    segments: tuple[Union[str, _Unknown], ...]

    @property
    def known_fragments(self) -> tuple[str, ...]:
        """All known chunks, in order (the unknown gaps omitted)."""
        return tuple(seg for seg in self.segments if isinstance(seg, str))


def _normalize_string_segments(
    segments: list[Union[str, _Unknown]],
) -> Union[str, PartialString, _Unknown]:
    """Smart constructor for a ``|`` concatenation's result.

    *segments* is the two operands' segments concatenated back to back, so
    the boundary between them can leave two known chunks or two gaps sitting
    next to each other; this merges each such pair into one.  It then decides
    what the merged segments represent: a plain ``str`` when fully known, a
    :class:`PartialString` when a mix, or :data:`UNKNOWN` when nothing
    survived.
    """
    merged: list[Union[str, _Unknown]] = []
    for seg in segments:
        if isinstance(seg, str):
            if seg == "":
                continue
            if merged and isinstance(merged[-1], str):
                merged[-1] = merged[-1] + seg
                continue
        elif merged and merged[-1] is UNKNOWN:
            continue
        merged.append(seg)

    if not merged:
        return ""
    if all(isinstance(seg, str) for seg in merged):
        return "".join(seg for seg in merged if isinstance(seg, str))
    if not any(isinstance(seg, str) for seg in merged):
        return UNKNOWN
    return PartialString(tuple(merged))


def _as_segments(value: "Value") -> list[Union[str, _Unknown]]:
    """Promote a tracked value to a segment list for concatenation."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, PartialString):
        return list(value.segments)
    # Numbers and the UNKNOWN sentinel contribute an opaque gap.
    return [UNKNOWN]


#: A single (possibly partial) value: string, number, or partial string.
AtomicValue = Union[str, float, PartialString]


def _definitely_contains(value: AtomicValue, substring: str) -> bool:
    """True when *value* certainly contains *substring*, whatever its gaps hold.

    Three-valued at heart: an exact string answers definitely; a
    :class:`PartialString` is definite only when a *known fragment* contains the
    substring (fragments appear verbatim in the final value) — otherwise the
    substring might still hide in a gap or span a fragment boundary, which is
    "maybe" and never counts as evidence.  Numbers contain no text.
    """
    if isinstance(value, str):
        return substring in value
    if isinstance(value, PartialString):
        return any(substring in fragment for fragment in value.known_fragments)
    return False


#: A tracked value: an atomic value or the UNKNOWN sentinel.
Value = Union[AtomicValue, _Unknown]


@dataclass(frozen=True)
class PossibleValues:
    """The set of values a variable may hold at a program point.

    This is the single answer type of the constant propagation API.  See the
    module docstring for the full cascade (:attr:`exact` → :meth:`all_of` /
    :meth:`any_of` → :attr:`partial` → :attr:`assigned`).

    ``values`` are the concrete (possibly partial) possibilities; ``complete``
    says whether they enumerate *every* possibility.  When ``complete`` is
    ``False`` the variable may additionally hold some fully dynamic value that
    could not be represented — so ``values`` can still show that a value is
    *possible* (∃), but not that something holds for *every* case (∀).
    """

    values: frozenset  # of AtomicValue; never contains the UNKNOWN sentinel
    #: Whether ``values`` enumerates every possibility, or the variable may
    #: additionally hold some dynamic value not represented in the set.
    complete: bool
    #: False only for a variable that was never written at all.  A variable
    #: that was written but is dynamic (:data:`TOP`) is still ``assigned``.
    #: The only construction that sets this ``False`` is :data:`UNASSIGNED`,
    #: which pairs it with empty ``values`` — no other call site touches it.
    assigned: bool = True

    @property
    def is_unknown(self) -> bool:
        """True when nothing at all is known about the value."""
        return not self.values and not self.complete

    def _sole(self) -> Optional[AtomicValue]:
        """The one value in ``values``, when it is complete and holds exactly one."""
        if self.complete and len(self.values) == 1:
            (only,) = self.values
            return only
        return None

    @property
    def exact(self) -> Optional[Union[str, float]]:
        """The single, fully known ``str``/``float`` value, or ``None``.

        Non-``None`` only when the variable holds exactly one statically known
        scalar — never for multi-variant, partial, or dynamic values.
        """
        only = self._sole()
        return only if isinstance(only, (str, float)) else None

    @property
    def partial(self) -> Optional[PartialString]:
        """The sole value when it is a :class:`PartialString`, else ``None``.

        Fully known values (use :attr:`exact`), fully unknown values, and
        multi-variant values all return ``None``.
        """
        only = self._sole()
        return only if isinstance(only, PartialString) else None

    def _all(self, holds_for) -> bool:
        """True iff *holds_for* is provable for every possible value (∀).

        The set must be complete and non-empty: a dynamic possibility
        (``complete is False``) could violate *holds_for*, which alone rules
        out a universal guarantee.
        """
        return (
            self.complete
            and bool(self.values)
            and all(holds_for(value) for value in self.values)
        )

    def _any(self, holds_for) -> bool:
        """True iff *holds_for* is provable for at least one possible value (∃)."""
        return any(holds_for(value) for value in self.values)

    def all_of(self, predicate) -> bool:
        """Check whether *predicate* provably holds for every possible value (∀).

        *predicate* receives only fully known ``str``/``float`` values; a
        partially known variant can't decide an arbitrary predicate, so its
        presence alone rules out a universal guarantee.
        """
        return self._all(lambda v: isinstance(v, (str, float)) and predicate(v))

    def any_of(self, predicate) -> bool:
        """Check whether *predicate* provably holds for at least one value (∃).

        *predicate* receives only fully known ``str``/``float`` values; a
        partially known variant is never proof that the predicate holds, so it
        is skipped rather than counted.
        """
        return self._any(lambda v: isinstance(v, (str, float)) and predicate(v))

    def all_contain(self, substring: str) -> bool:
        """Check whether *substring* is certainly present in every value (∀).

        The substring-aware counterpart of :meth:`all_of`: a partially known
        variant counts when one of its *known fragments* contains *substring*,
        because that fragment appears verbatim in the final value.
        """
        return self._all(lambda v: _definitely_contains(v, substring))

    def any_contains(self, substring: str) -> bool:
        """Check whether *substring* is certainly present in at least one value (∃).

        A partially known variant counts when one of its known fragments
        contains *substring*; a gap that merely *might* contain it does not
        count as proof.
        """
        return self._any(lambda v: _definitely_contains(v, substring))


#: The fully unknown value of a *written* variable: could be anything.
TOP = PossibleValues(frozenset(), False)

#: The value of a variable that was never assigned: unknown and unwritten.
UNASSIGNED = PossibleValues(frozenset(), False, assigned=False)


def _single(value: AtomicValue) -> PossibleValues:
    """A PossibleValues holding exactly one known value."""
    return PossibleValues(frozenset({value}), True)
