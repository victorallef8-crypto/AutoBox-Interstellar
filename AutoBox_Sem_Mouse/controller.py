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

def detection_area(config, viewport):
    if config.get("full_map", False):
        top = max(0, min(int(config["map"]["top"]), viewport["height"]-1))
        return {"left":config["map"]["left"], "top":top, "width":config["map"]["width"], "height":viewport["height"]-top}
    return dict(config["map"])

def visible_box(point, config):
    # Objetos no minimapa nao sao boxes do espaco.
    return not (config.get("minimap") and inside(point, config["minimap"], margin=3))

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
    velocity: tuple = (0., 0.)

class CollectionState:
    def __init__(self, ship):
        self.ship = dict(ship)
        self.origin = center(ship)
        self.arrival_radius = 22
        self.target = None
        self.blocked = []

    def allowed(self, point):
        # Preserva boxes ao lado e embaixo da nave; protege apenas o centro.
        return distance(point, self.origin) > 7

    def choose(self, candidates, now):
        self.blocked = [(point, until) for point, until in self.blocked if until > now]
        available = [p for p in candidates if self.allowed(p[:2])]
        if not available:
            return None
        nearest = min(available, key=lambda p: (distance(p[:2], self.origin), -p[2]))[:2]
        # Nao pula o mais proximo para voar ate outro enquanto aguarda reverificacao.
        if any(distance(nearest, point) <= 18 for point, _ in self.blocked):
            return None
        return nearest

    def acquire(self, point, now):
        self.target = Target(point, now, now, now, distance(point, self.origin))

    def clicked(self, point, now):
        self.target.point = point
        self.target.last_click = now
        self.target.clicks += 1

    def predicted(self, now):
        target = self.target
        elapsed = min(.6, max(0, now-target.last_seen))
        return (target.point[0] + target.velocity[0]*elapsed,
                target.point[1] + target.velocity[1]*elapsed)

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
            if (target.missing >= 3 and target.best_distance <= self.arrival_radius
                    and now - target.last_seen >= .6):
                return "departed"
            return "failed" if now - target.last_seen >= 3 else "wait"
        elapsed = now-target.last_seen
        if .04 <= elapsed <= 2:
            vx = (point[0]-target.point[0])/elapsed
            vy = (point[1]-target.point[1])/elapsed
            target.velocity = (vx,vy)
        target.point = point
        target.last_seen = now
        target.missing = 0
        current_distance = distance(point, self.origin)
        if current_distance < target.best_distance - 4:
            target.best_distance = current_distance
            target.last_progress = now
        if now - target.last_progress >= 6:
            return "failed"
        correction_delay = .3 if current_distance < 100 else .9
        if self.allowed(point) and target.clicks < 6 and now - target.last_click >= correction_delay:
            return "aim"
        return "wait"

    def finish(self, now, failed=False):
        if self.target:
            self.blocked.append((self.target.point, now + (2 if failed else .8)))
        self.target = None
