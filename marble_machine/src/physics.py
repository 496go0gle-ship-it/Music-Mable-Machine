"""physics.py — Phase 4: pymunk world, balls, key segments, collisions.

Keys are static segments; balls are dynamic circles dropped down their lane.
A collision callback records every ball->key contact so we can both react to
hits and detect the "balls tunnel through keys" failure described in the
ERROR HANDLING rules.  Physics is sub-stepped to avoid tunneling at speed.
"""

from __future__ import annotations

import pymunk

from config import BALL_RADIUS, GRAVITY, KEY_WIDTH

BALL_CT = 1   # collision_type for balls
KEY_CT = 2    # collision_type for keys

SUBSTEPS = 4  # physics sub-steps per rendered frame (anti-tunneling)


class PhysicsWorld:
    def __init__(self, key_elasticity: float = 0.5):
        self.space = pymunk.Space()
        self.space.gravity = (0, GRAVITY)
        self.key_elasticity = key_elasticity
        self.collision_count = 0
        # ball shape -> True once it has struck a key (one-shot per ball)
        self._struck: set[int] = set()
        self.last_hits: list[object] = []   # key bodies hit since last drain
        self._register_handler()

    def _register_handler(self) -> None:
        def begin(arbiter, space, data):
            self.collision_count += 1
            ball_shape, key_shape = arbiter.shapes
            bid = id(ball_shape)
            if bid not in self._struck:
                self._struck.add(bid)
                self.last_hits.append(key_shape.body)

        self.space.on_collision(BALL_CT, KEY_CT, begin=begin)

    def create_ball(self, pos) -> pymunk.Body:
        body = pymunk.Body(mass=1, moment=pymunk.moment_for_circle(1, 0, BALL_RADIUS))
        body.position = pos
        shape = pymunk.Circle(body, BALL_RADIUS)
        shape.elasticity = 0.6
        shape.friction = 0.4
        shape.collision_type = BALL_CT
        self.space.add(body, shape)
        return body

    def create_key_segment(self, x, y, width=KEY_WIDTH) -> pymunk.Body:
        body = pymunk.Body(body_type=pymunk.Body.STATIC)
        body.position = (x, y)
        # radius 6 segment: thick enough to resist tunneling, thin visually.
        shape = pymunk.Segment(body, (-width / 2, 0), (width / 2, 0), 6)
        shape.elasticity = self.key_elasticity
        shape.friction = 0.3
        shape.collision_type = KEY_CT
        self.space.add(body, shape)
        return body

    def step(self, dt: float) -> None:
        sub = dt / SUBSTEPS
        for _ in range(SUBSTEPS):
            self.space.step(sub)

    def drain_hits(self) -> list[object]:
        """Return key bodies struck since the last call and clear the buffer."""
        hits, self.last_hits = self.last_hits, []
        return hits

    def remove_ball(self, body: pymunk.Body) -> None:
        for shape in list(body.shapes):
            self._struck.discard(id(shape))
            self.space.remove(shape)
        self.space.remove(body)
