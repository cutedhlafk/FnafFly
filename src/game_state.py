"""Detection of stable UCN terminal states from saved screen templates."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Detection:
    """
    Result of one game-state detection step.

    state:
        Confirmed state. None until the same candidate has been seen
        for enough consecutive frames.

    candidate:
        State that best matches the current frame.

    error:
        Mean absolute image error for the best candidate.

    stable_frames:
        Number of consecutive frames matching the same candidate.
    """

    state: str | None
    candidate: str | None
    error: float
    stable_frames: int


class GameStateDetector:
    """
    Detect menu / win / loss screens using small grayscale templates.

    A state is confirmed only after it matches several consecutive frames.
    This reduces false positives caused by animations and transitional frames.
    """

    VALID_STATES = ("menu", "win", "loss")

    def __init__(
        self,
        templates=None,
        threshold=0.045,
        stable_frames=3,
        size=(64, 36),
    ):
        self.threshold = float(threshold)
        if not np.isfinite(self.threshold) or self.threshold<=0:
            raise ValueError('Template threshold must be positive and finite')
        self.required_stable_frames = max(1, int(stable_frames))
        self.size = tuple(size)

        self.templates = {}

        self._candidate = None
        self._candidate_frames = 0

        if templates:
            self.set_templates(templates)

    def reset(self):
        """Forget temporal detection history."""
        self._candidate = None
        self._candidate_frames = 0

    def template_from_frame(self, frame):
        """
        Convert a PIL frame into the normalized representation used
        both for saved templates and live detection.
        """
        return (
            np.asarray(
                frame.convert("L").resize(self.size),
                dtype=np.float32,
            )
            / 255.0
        )

    def set_template(self, name, template):
        """Add or replace one terminal-state template."""
        if name not in self.VALID_STATES:
            raise ValueError(f"Unsupported game state template: {name}")

        array = np.asarray(template, dtype=np.float32)

        expected_shape = (self.size[1], self.size[0])

        if array.shape != expected_shape:
            raise ValueError(
                f"Invalid template shape for {name}: "
                f"{array.shape}, expected {expected_shape}"
            )

        if not np.isfinite(array).all() or np.any((array<0)|(array>1)):
            raise ValueError('Template pixels must be finite and within 0..1')

        self.templates[name] = array.copy()
        self.reset()

    def set_templates(self, templates):
        """Replace all currently known templates."""
        self.templates = {}

        for name, template in templates.items():
            if name in self.VALID_STATES:
                self.set_template(name, template)

        self.reset()

    def detect(self, frame):
        """
        Analyze one frame.

        Returns a Detection object.

        Detection.state remains None until the same candidate is observed
        for required_stable_frames consecutive calls.
        """
        if frame is None or not self.templates:
            self.reset()

            return Detection(
                state=None,
                candidate=None,
                error=float("inf"),
                stable_frames=0,
            )

        current = self.template_from_frame(frame)

        best_name = None
        best_error = float("inf")

        for name, reference in self.templates.items():
            error = float(np.abs(current - reference).mean())

            if error < best_error:
                best_error = error
                best_name = name

        if best_error >= self.threshold:
            best_name = None

        if best_name is None:
            self._candidate = None
            self._candidate_frames = 0

            return Detection(
                state=None,
                candidate=None,
                error=best_error,
                stable_frames=0,
            )

        if best_name == self._candidate:
            self._candidate_frames += 1
        else:
            self._candidate = best_name
            self._candidate_frames = 1

        confirmed = None

        if self._candidate_frames >= self.required_stable_frames:
            confirmed = self._candidate

        return Detection(
            state=confirmed,
            candidate=self._candidate,
            error=best_error,
            stable_frames=self._candidate_frames,
        )
