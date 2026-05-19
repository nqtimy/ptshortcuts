"""Particle effects system — Vampire Survivors style explosions."""

import math
import random
import time


class Particle:
    """Standard particle with gravity, fade, and optional trail."""
    __slots__ = ('x', 'y', 'vx', 'vy', 'color', 'size', 'birth', 'lifetime',
                 'gravity', 'friction', 'glow')

    def __init__(self, x, y, vx, vy, color, size=3, lifetime=1.0,
                 gravity=80, friction=0.98, glow=False):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.size = size
        self.birth = time.time()
        self.lifetime = lifetime
        self.gravity = gravity
        self.friction = friction
        self.glow = glow

    def alive(self, now):
        return (now - self.birth) < self.lifetime

    def update(self, dt):
        self.vx *= self.friction
        self.vy *= self.friction
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += self.gravity * dt

    def alpha(self, now):
        age = now - self.birth
        return max(0.0, 1.0 - age / self.lifetime)


class RingParticle:
    """Expanding ring effect for combo milestones."""
    __slots__ = ('x', 'y', 'color', 'birth', 'lifetime', 'max_radius', 'width')

    def __init__(self, x, y, color, max_radius=200, lifetime=0.8, width=3):
        self.x = x
        self.y = y
        self.color = color
        self.birth = time.time()
        self.lifetime = lifetime
        self.max_radius = max_radius
        self.width = width

    def alive(self, now):
        return (now - self.birth) < self.lifetime

    def update(self, dt):
        pass  # Ring just expands based on age

    def progress(self, now):
        return min(1.0, (now - self.birth) / self.lifetime)

    def alpha(self, now):
        p = self.progress(now)
        # Fast fade after 50%
        return max(0.0, 1.0 - p * p)

    def radius(self, now):
        p = self.progress(now)
        # Ease-out expansion
        return self.max_radius * (1.0 - (1.0 - p) ** 3)


class Ripple:
    """Single expanding water-drop ring drawn behind the UI cards.

    Used as ambient feedback for correct answers — one ripple per event, color
    and intensity driven by the current combo. Cheap to render: just one
    `pygame.draw.circle` per frame with a width=N outline, color faded toward
    black via the alpha curve (no SRCALPHA blit required).
    """
    __slots__ = ('x', 'y', 'color', 'birth', 'lifetime', 'max_radius', 'thickness')

    def __init__(self, x, y, color, max_radius=380, lifetime=1.3, thickness=4):
        self.x = x
        self.y = y
        self.color = color
        self.birth = time.time()
        self.lifetime = lifetime
        self.max_radius = max_radius
        self.thickness = thickness

    def alive(self, now):
        return (now - self.birth) < self.lifetime

    def update(self, dt):
        pass  # purely time-driven; no per-frame state

    def progress(self, now):
        return min(1.0, (now - self.birth) / self.lifetime)

    def radius(self, now):
        # Ease-out: ripple expands fast, then slows — water-drop feel.
        p = self.progress(now)
        return self.max_radius * (1.0 - (1.0 - p) ** 2.5)

    def alpha(self, now):
        # Hold full opacity briefly, then quadratic fade.
        p = self.progress(now)
        return max(0.0, 1.0 - p * p)


class ScorePopup:
    """Floating score text that scales down from big."""
    __slots__ = ('text', 'x', 'y', 'color', 'birth', 'lifetime', 'vy',
                 'start_size', 'end_size')

    def __init__(self, text, x, y, color=(255, 255, 255), big=False):
        self.text = text
        self.x = x
        self.y = y
        self.color = color
        self.birth = time.time()
        self.lifetime = 1.5
        self.vy = -50
        # Start big, shrink to normal
        self.start_size = 52 if big else 38
        self.end_size = 24 if big else 22

    def alive(self, now):
        return (now - self.birth) < self.lifetime

    def update(self, dt):
        self.y += self.vy * dt
        self.vy *= 0.97  # Slow down

    def alpha(self, now):
        age = now - self.birth
        # Hold full alpha for 40%, then fade
        if age < self.lifetime * 0.4:
            return 1.0
        return max(0.0, 1.0 - (age - self.lifetime * 0.4) / (self.lifetime * 0.6))

    def current_size(self, now):
        age = now - self.birth
        t = min(1.0, age / 0.3)  # Shrink over 0.3s
        # Ease-out
        t = 1.0 - (1.0 - t) ** 3
        return int(self.start_size + (self.end_size - self.start_size) * t)


# ---------------------------------------------------------------------------
# Spawn functions
# ---------------------------------------------------------------------------

def spawn_explosion(x, y, color, count=40):
    """Big omnidirectional explosion — main correct answer effect."""
    particles = []
    for _ in range(count):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(80, 350)
        vx = math.cos(angle) * speed
        vy = math.sin(angle) * speed - 60
        size = random.uniform(2, 6)
        lifetime = random.uniform(0.4, 1.4)
        # Slight color variation
        r = max(0, min(255, color[0] + random.randint(-30, 30)))
        g = max(0, min(255, color[1] + random.randint(-30, 30)))
        b = max(0, min(255, color[2] + random.randint(-30, 30)))
        glow = random.random() < 0.3  # 30% chance of glow particle
        particles.append(Particle(
            x + random.randint(-5, 5), y + random.randint(-5, 5),
            vx, vy, (r, g, b), size, lifetime, gravity=120, glow=glow
        ))
    return particles


def spawn_sparks(x, y, color, count=20, direction=None):
    """Directional spark shower — sharp, fast particles."""
    particles = []
    base_angle = direction if direction is not None else -math.pi / 2  # default: upward
    for _ in range(count):
        angle = base_angle + random.uniform(-0.8, 0.8)
        speed = random.uniform(200, 500)
        vx = math.cos(angle) * speed
        vy = math.sin(angle) * speed
        size = random.uniform(1, 3)
        lifetime = random.uniform(0.3, 0.8)
        particles.append(Particle(
            x, y, vx, vy, color, size, lifetime,
            gravity=40, friction=0.95, glow=True
        ))
    return particles


def spawn_firework_ring(x, y, color, count=60):
    """Ring burst for combo milestones — particles in a circle."""
    particles = []
    ring = RingParticle(x, y, color, max_radius=250, lifetime=0.7, width=3)
    particles.append(ring)
    # Also spawn particles along the ring
    for i in range(count):
        angle = (2 * math.pi * i) / count + random.uniform(-0.1, 0.1)
        speed = random.uniform(150, 350)
        vx = math.cos(angle) * speed
        vy = math.sin(angle) * speed
        size = random.uniform(2, 5)
        lifetime = random.uniform(0.6, 1.2)
        r = max(0, min(255, color[0] + random.randint(-40, 40)))
        g = max(0, min(255, color[1] + random.randint(-40, 40)))
        b = max(0, min(255, color[2] + random.randint(-40, 40)))
        particles.append(Particle(
            x, y, vx, vy, (r, g, b), size, lifetime,
            gravity=30, friction=0.96, glow=True
        ))
    return particles


def spawn_embers(x, y, w, count=3):
    """Ambient floating embers — continuous during high streaks."""
    particles = []
    for _ in range(count):
        px = x + random.uniform(-w / 2, w / 2)
        py = y + random.uniform(-20, 20)
        vx = random.uniform(-30, 30)
        vy = random.uniform(-80, -30)
        colors = [(255, 160, 40), (255, 200, 60), (255, 120, 30), (200, 100, 255)]
        color = random.choice(colors)
        size = random.uniform(1.5, 3.5)
        lifetime = random.uniform(1.0, 2.5)
        particles.append(Particle(
            px, py, vx, vy, color, size, lifetime,
            gravity=-15, friction=0.99, glow=True
        ))
    return particles


def spawn_ripple(x, y, color, intensity=1.0):
    """Single water-drop ripple, scaled by combo intensity.

    intensity ~ 0.9 (light) → 4.0 (combo 25+, full-screen). Affects max radius,
    lifetime, and stroke thickness so high-combo ripples feel "heavier".
    """
    intensity = max(0.5, min(intensity, 4.0))
    return Ripple(
        x, y, color,
        max_radius=int(340 + 130 * intensity),  # intensity 4.0 → 860px
        lifetime=0.95 + 0.35 * intensity,
        thickness=max(2, int(2 + intensity)),
    )


def spawn_wrong_burst(x, y, count=15):
    """Sharp red burst for wrong answers."""
    particles = []
    for _ in range(count):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(100, 250)
        vx = math.cos(angle) * speed
        vy = math.sin(angle) * speed - 30
        size = random.uniform(2, 5)
        lifetime = random.uniform(0.3, 0.7)
        r = random.randint(180, 255)
        g = random.randint(30, 80)
        b = random.randint(30, 80)
        particles.append(Particle(
            x, y, vx, vy, (r, g, b), size, lifetime,
            gravity=200, friction=0.96
        ))
    return particles
