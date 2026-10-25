"""Decisoes da coleta; nao depende de imagem, navegador ou mouse do Windows."""
from dataclasses import dataclass
from math import hypot

def inside(point, area, margin=0):
    x, y = point
    return (area["left"] - margin <= x <= area["left"] + area["width"] + margin
            and area["top"] - margin <= y <= area["top"] + area["height"] + margin)

def center(area):
    return area["left"] + area["width"] / 2, area["top"] + area["height"] / 2

def distance(a, b):
    return hypot(a[0] - b[0], a[1] - b[1])

def track(candidates, point, radius=60):
    nearby = sorted((candidate for candidate in candidates if distance(candidate[:2], point) <= radius),
                    key=lambda candidate: distance(candidate[:2], point))
    if not nearby:
        return None
    if len(nearby) > 1 and distance(nearby[1][:2], point) - distance(nearby[0][:2], point) < 12:
        return None
    return nearby[0][:2]

@dataclass
class Target:
    point: tuple
    started: float
    last_seen: float
    last_progress: float
    best_distance: float
    last_click: float = -100
    clicks: int = 0
    missing: int = 0

class CollectionState:
    def __init__(self, ship):
        self.ship = dict(ship)
        self.origin = center(ship)
        self.arrival_radius = max(65, hypot(ship["width"] / 2, ship["height"] / 2) + 30)
        self.target = None
        self.blocked = []

    def allowed(self, point):
        return not inside(point, self.ship, margin=4)

    def choose(self, candidates, now):
        self.blocked = [(point, until) for point, until in self.blocked if until > now]
        available = [p for p in candidates if self.allowed(p[:2])
                     and all(distance(p[:2], point) > 18 for point, _ in self.blocked)]
        if not available:
            return None
        return min(available, key=lambda p: (distance(p[:2], self.origin), -p[2]))[:2]

    def acquire(self, point, now):
        self.target = Target(point, now, now, now, distance(point, self.origin))

    def clicked(self, point, now):
        self.target.point = point
        self.target.last_click = now
        self.target.clicks += 1

    def observe(self, point, now, reward=False):
        target = self.target
        if target is None:
            return "search"
        if reward:
            return "confirmed"
        if now - target.started >= 30:
            return "failed"
        if point is None:
            target.missing += 1
            if (target.missing >= 2 and target.best_distance <= self.arrival_radius
                    and now - target.last_seen >= .5):
                return "departed"
            return "failed" if now - target.last_seen >= 1.8 else "wait"
        target.point = point
        target.last_seen = now
        target.missing = 0
        current_distance = distance(point, self.origin)
        if current_distance < target.best_distance - 4:
            target.best_distance = current_distance
            target.last_progress = now
        if now - target.last_progress >= 6:
            return "failed"
        if self.allowed(point) and target.clicks < 6 and now - target.last_click >= .9:
            return "aim"
        return "wait"

    def finish(self, now, failed=False):
        if self.target:
            self.blocked.append((self.target.point, now + (2 if failed else .8)))
        self.target = None
