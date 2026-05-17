import hashlib
import json
import math
import os
import random
import secrets
import sys

import pygame

from multiplayer import MultiplayerManager


WIDTH, HEIGHT = 1000, 700
CAMERA_ZOOM = 2.5  # >1 zooms in (smaller world viewport)
FPS = 60
BG_PIXEL_SCALE = 5.5
PARTICLE_SIZE_SCALE = 2.5

# Night oval — darker grass / dirt so sparks read clearly.
GRASS = (18, 42, 32)
DIRT_TRACK = (48, 36, 28)
DIRT_INFIELD = (32, 26, 20)
TRACK_RIM_DARK = (26, 30, 38)
TRACK_RIM_LIGHT = (72, 78, 88)
START_LINE_NIGHT = (185, 178, 148)
LIGHT_GRAY = (195, 195, 195)
DARK_GRAY = (85, 85, 85)
WHITE = (240, 240, 240)
# Car paint: black/white pick freely; other colors swap with the opponent who had them.
CAR_PAINT_BLACK = (28, 28, 30)
RED = (220, 50, 50)
PAINT_SWATCH_PX = 38
PAINT_SWATCH_GAP = 10
YELLOW = (240, 210, 55)
BLUE = (70, 130, 230)
DIRT_PARTICLE_COLORS = [(149, 126, 68), (133, 115, 60), (116, 101, 50)]
DIRT_DUST_RGB_DARKEN = 80  # drift + collision dust vs base palette
SPARK_COLORS = [(255, 252, 210), (255, 220, 120), (255, 175, 72), (255, 140, 55), (240, 238, 255)]
# Visual scale only; velocity/acceleration in update_vehicle are unchanged.
CAR_DRAW_SIZE_MULT = 2.7 / 1.5
CAR_SCALE = 0.5 * CAR_DRAW_SIZE_MULT
# Nose–tail in procedural shape space (width unchanged): vs legacy ±20, then ÷1.2, then ×1.05.
CAR_BODY_LENGTH_SCALE = (1 / 1.2) * 1.05
# Mesh half-extents in shape space after length scale; tightened 1.35× vs that footprint.
CAR_HITBOX_RADIUS = (
    math.hypot(20 * CAR_BODY_LENGTH_SCALE * CAR_SCALE, 10 * CAR_SCALE) / 1.35
)
# Scales AI target speeds (cruise / corners / risky zone); capped by update_vehicle forward limit.
AI_SPEED_MULT = 1.22
# Off-track / grass slowdown per frame: higher divisor = weaker penalty (2.3 = 2.3× less effective).
SLOWDOWN_ZONE_EFFECT_DIV = 2.3
OFF_TRACK_SLOW_PLAYER = 0.92
OFF_TRACK_SLOW_AI = 0.90
PLAYER_FORWARD_CAP_BASE = 300.0
# Unified dynamics scale for every car (player + AI): accel, caps, thresholds, and AI targets.
CAR_SPEED_SCALE = 1.25 / 1.4
SPEED_UPGRADE_MAX = 35
# Forward-cap bonus per purchased tier (was 1.0; 2 = twice as much top speed per upgrade).
SPEED_UPGRADE_FORWARD_PER_TIER = 2
RACE_PRIZE_MONEY = 1000
SPEED_UPGRADE_BASE_PRICE = 500
SPEED_UPGRADE_PRICE_STEP = 25
# Difficulty 1–8: AI forward speed cap (Standard = normal). Player base cap matches Standard before shop tiers.
DIFFICULTY_AI_FORWARD_CAP = (
    285.0,  # Easy
    300.0,  # Standard — keep equal to PLAYER_FORWARD_CAP_BASE
    303.0,  # Novice
    305.0,  # Amateur
    310.0,  # Mad Max
    315.0,  # Speedrun
    320.0,  # Daredevil
    325.0,  # Demon
)
DIFFICULTY_LEVEL_DEFAULT = 2
DIFFICULTY_LEVEL_COUNT = 8
DIFFICULTY_LABELS = (
    "Easy",
    "Standard",
    "Novice",
    "Amateur",
    "Mad Max",
    "Speedrun",
    "Daredevil",
    "Demon",
)
# Same logic for every opponent; distinct body colors.
AI_BOT_COLORS = [
    (188, 34, 40),
    (72, 132, 228),
    (238, 196, 48),
    (168, 72, 218),
    (52, 206, 142),
    (236, 118, 52),
    (118, 208, 238),
    (218, 82, 158),
]

# Decals: extra body graphics (style id + color). 0 = none.
DECAL_NUM_STYLES = 6
DECAL_STYLE_LABELS = ("None", "Bar", "Twin", "Sills", "Chev", "Plate")
DECAL_PALETTE = [
    (255, 220, 60),
    (55, 210, 255),
    (255, 85, 165),
    (120, 255, 110),
    (255, 135, 45),
    (200, 200, 220),
    WHITE,
    CAR_PAINT_BLACK,
    (175, 95, 255),
    (255, 115, 105),
]

# Chassis pick in lobby Cars tab. Optional cost (coins), speed (0–100, default 70).
NUM_CAR_CHASSIS = 7
CAR_CHASSIS = (
    {"name": "Stock", "grip": 70, "accel": 70, "preview": RED},
    {"name": "Round Nose", "grip": 84, "accel": 56, "preview": BLUE},
    {"name": "Wide Track", "grip": 78, "accel": 62, "preview": (52, 206, 142)},
    {"name": "Wedge", "grip": 54, "accel": 86, "preview": YELLOW},
    {"name": "Hatch", "grip": 66, "accel": 74, "preview": (168, 72, 218)},
    {"name": "Muscle", "grip": 90, "accel": 50, "preview": (236, 118, 52)},
    {
        "name": "School Bus",
        "grip": 80,
        "accel": 62,
        "speed": 100,
        "preview": (224, 186, 48),
    },
)
WHEEL_TIRE_COLOR = (42, 42, 48)

AUTH_ACCOUNTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounts.json")
AUTH_USERNAME_MIN = 3
AUTH_USERNAME_MAX = 16
AUTH_PASSCODE_MIN = 4
AUTH_PASSCODE_MAX = 32
AUTH_ERROR_COLOR = (255, 120, 120)
AUTH_OK_COLOR = (140, 230, 160)


def load_accounts():
    if not os.path.isfile(AUTH_ACCOUNTS_PATH):
        return {}
    try:
        with open(AUTH_ACCOUNTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_accounts(accounts):
    with open(AUTH_ACCOUNTS_PATH, "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=2)


def normalize_username(name):
    return name.strip().lower()


def validate_username(name):
    name = normalize_username(name)
    if len(name) < AUTH_USERNAME_MIN or len(name) > AUTH_USERNAME_MAX:
        return False, f"Username must be {AUTH_USERNAME_MIN}–{AUTH_USERNAME_MAX} characters."
    if not name.replace("_", "").isalnum():
        return False, "Username: letters, numbers, and underscores only."
    return True, name


def hash_passcode(passcode, salt_hex):
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", passcode.encode("utf-8"), salt, 120_000)
    return digest.hex()


def register_account(username, passcode):
    ok, user_or_msg = validate_username(username)
    if not ok:
        return False, user_or_msg
    user = user_or_msg
    if len(passcode) < AUTH_PASSCODE_MIN or len(passcode) > AUTH_PASSCODE_MAX:
        return False, f"Passcode must be {AUTH_PASSCODE_MIN}–{AUTH_PASSCODE_MAX} characters."
    accounts = load_accounts()
    if user in accounts:
        return False, "Username already taken."
    salt = secrets.token_bytes(16)
    accounts[user] = {"salt": salt.hex(), "hash": hash_passcode(passcode, salt.hex())}
    save_accounts(accounts)
    return True, user


def login_account(username, passcode):
    ok, user_or_msg = validate_username(username)
    if not ok:
        return False, user_or_msg
    user = user_or_msg
    accounts = load_accounts()
    record = accounts.get(user)
    if not record:
        return False, "No account with that username."
    expected = hash_passcode(passcode, record["salt"])
    if expected != record.get("hash"):
        return False, "Incorrect passcode."
    return True, user


def shade_color(color, delta):
    return (
        max(0, min(255, color[0] + delta)),
        max(0, min(255, color[1] + delta)),
        max(0, min(255, color[2] + delta)),
    )


CAR_DRAW_RGB_DARKEN = 75


def darken_rgb(color, delta=CAR_DRAW_RGB_DARKEN):
    """Applied when drawing cars so paint reads darker on screen."""
    return (
        max(0, int(color[0]) - delta),
        max(0, int(color[1]) - delta),
        max(0, int(color[2]) - delta),
    )


def draw_poly(surface, points, angle, x, y, color):
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    transformed = []
    for px, py in points:
        rx = px * cos_a - py * sin_a
        ry = px * sin_a + py * cos_a
        transformed.append((x + rx, y + ry))
    pygame.draw.polygon(surface, color, transformed)


def decal_shape_polys(style_id):
    """Car-local polygons (+x forward, +y left); same pre-scale space as draw_car body."""
    if style_id <= 0:
        return []
    if style_id == 1:
        return [[(6, -1.25), (16.5, -1.25), (16.5, 1.25), (6, 1.25)]]
    if style_id == 2:
        return [
            [(7, -5.2), (16, -5.2), (16, -3.4), (7, -3.4)],
            [(7, 3.4), (16, 3.4), (16, 5.2), (7, 5.2)],
        ]
    if style_id == 3:
        return [
            [(-11, 6.2), (9, 6.2), (9, 9.2), (-11, 9.2)],
            [(-11, -9.2), (9, -9.2), (9, -6.2), (-11, -6.2)],
        ]
    if style_id == 4:
        return [[(15.5, 0.0), (7.5, 5.5), (7.5, -5.5)]]
    if style_id == 5:
        return [[(9.5, -4.2), (17, -4.2), (17, 4.2), (9.5, 4.2)]]
    return []


def car_chassis_shapes(chassis_id):
    """Body parts in car-local space (+x forward). Returns body, hood, roof, glass×2, extras."""
    cid = max(0, min(NUM_CAR_CHASSIS - 1, int(chassis_id)))
    if cid == 0:
        body = [
            (20, -10),
            (20, 10),
            (14, 10),
            (-14, 10),
            (-20, 10),
            (-20, -10),
            (-14, -10),
            (14, -10),
        ]
        hood = [(17, -8), (17, 8), (11, 8), (0, 8), (-2, 0), (0, -8), (11, -8)]
        roof = [(7, -7), (-8, -7), (-10, -2), (-10, 2), (-8, 7), (7, 7), (9, 2), (9, -2)]
        windshield = [(10, -4), (4, -6), (0, -6), (0, -2), (8, -2)]
        rear_window = [(-2, -6), (-8, -6), (-10, -2), (-3, -2)]
        extras = []
    elif cid == 1:
        body = [
            (19, -10),
            (20, -6),
            (20, 6),
            (19, 10),
            (12, 10),
            (-14, 10),
            (-20, 10),
            (-20, -10),
            (-14, -10),
            (12, -10),
        ]
        hood = [(18, -7), (19, -2), (19, 2), (18, 7), (10, 7), (2, 4), (2, -4), (10, -7)]
        roof = [(6, -6), (-7, -6), (-10, -1), (-10, 1), (-7, 6), (6, 6), (8, 1), (8, -1)]
        windshield = [(11, -3), (5, -5), (1, -4), (1, -1), (9, -1)]
        rear_window = [(-1, -5), (-7, -5), (-10, -1), (-2, -1)]
        extras = []
    elif cid == 2:
        body = [
            (20, -8),
            (20, 8),
            (12, 9),
            (-12, 9),
            (-20, 8),
            (-20, -8),
            (-12, -9),
            (12, -9),
        ]
        hood = [(17, -6), (17, 6), (9, 6), (0, 5), (-2, 0), (0, -5), (9, -6)]
        roof = [(7, -5), (-8, -5), (-10, -1), (-10, 1), (-8, 5), (7, 5), (9, 1), (9, -1)]
        windshield = [(10, -3), (4, -4), (0, -4), (0, -1), (8, -1)]
        rear_window = [(-2, -4), (-8, -4), (-10, -1), (-3, -1)]
        extras = [
            [(14, -12), (17, -12), (17, -9), (14, -9)],
            [(14, 9), (17, 9), (17, 12), (14, 12)],
            [(-12, -12), (-9, -12), (-9, -9), (-12, -9)],
            [(-12, 9), (-9, 9), (-9, 12), (-12, 12)],
        ]
    elif cid == 3:
        body = [
            (20, 0),
            (16, -10),
            (10, -10),
            (-14, -10),
            (-20, -9),
            (-20, 9),
            (-14, 10),
            (10, 10),
            (16, 10),
        ]
        hood = [(19, -2), (14, -7), (6, -7), (2, -3), (2, 3), (6, 7), (14, 7), (19, 2)]
        roof = [(5, -5), (-7, -5), (-9, 0), (-7, 5), (5, 5), (7, 0)]
        windshield = [(9, -2), (4, -4), (1, -2), (1, 2), (7, 2)]
        rear_window = [(-1, -4), (-7, -4), (-9, 0), (-2, 0)]
        extras = []
    elif cid == 4:
        body = [
            (16, -9),
            (16, 9),
            (10, 10),
            (-10, 10),
            (-18, 8),
            (-18, -8),
            (-10, -10),
            (10, -10),
        ]
        hood = [(15, -7), (15, 7), (8, 7), (2, 6), (0, 0), (2, -6), (8, -7)]
        roof = [(5, -6), (-6, -6), (-8, -1), (-8, 3), (-5, 6), (5, 6), (7, 2), (7, -2)]
        windshield = [(9, -3), (3, -5), (0, -3), (0, 0), (7, 0)]
        rear_window = [(-2, -5), (-7, -5), (-8, -1), (-3, -1)]
        extras = []
    elif cid == 5:
        body = [
            (20, -9),
            (20, 9),
            (14, 11),
            (4, 12),
            (-10, 12),
            (-20, 10),
            (-20, -10),
            (-10, -12),
            (4, -12),
            (14, -11),
        ]
        hood = [(18, -7), (18, 7), (12, 8), (2, 7), (-2, 0), (2, -7), (12, -8)]
        roof = [(6, -5), (-6, -5), (-9, 0), (-6, 5), (6, 5), (8, 0)]
        windshield = [(10, -3), (3, -5), (0, -2), (0, 2), (8, 2)]
        rear_window = [(-1, -5), (-7, -5), (-9, 0), (-2, 0)]
        extras = [
            [(-16, -11), (-11, -11), (-11, -8), (-16, -8)],
            [(-16, 8), (-11, 8), (-11, 11), (-16, 11)],
        ]
    else:
        body = [
            (23, -7),
            (24, -4),
            (24, 4),
            (23, 7),
            (16, 9),
            (8, 10),
            (-10, 10),
            (-18, 9),
            (-23, 7),
            (-24, 4),
            (-24, -4),
            (-23, -7),
            (-18, -9),
            (-10, -10),
            (8, -10),
            (16, -9),
        ]
        hood = [(22, -5), (23, -1), (23, 1), (22, 5), (14, 6), (6, 5), (2, 2), (2, -2), (6, -5), (14, -6)]
        roof = [(10, -6), (-4, -6), (-14, -3), (-16, 0), (-14, 3), (-4, 6), (10, 6), (12, 2), (12, -2)]
        windshield = [(14, -4), (6, -5), (2, -3), (2, 0), (10, 0)]
        rear_window = [(-2, -5), (-10, -5), (-14, -2), (-4, -2)]
        extras = [
            [(18, -8), (20, -8), (20, -6), (18, -6)],
            [(18, 6), (20, 6), (20, 8), (18, 8)],
        ]
    return body, hood, roof, windshield, rear_window, extras


def chassis_unlock_cost(chassis_id):
    c = CAR_CHASSIS[max(0, min(NUM_CAR_CHASSIS - 1, int(chassis_id)))]
    return int(c.get("cost", 0))


def chassis_is_unlocked(chassis_id, unlocked_ids):
    return chassis_unlock_cost(chassis_id) <= 0 or int(chassis_id) in unlocked_ids


def chassis_physics_modifiers(chassis_id):
    """Map chassis grip/accel/speed stats (0–100) to physics multipliers."""
    c = CAR_CHASSIS[max(0, min(NUM_CAR_CHASSIS - 1, int(chassis_id)))]
    g = max(0.0, min(1.0, c["grip"] / 100.0))
    a = max(0.0, min(1.0, c["accel"] / 100.0))
    sp = max(0.0, min(100.0, float(c.get("speed", 70))))
    base_grip = 5.4 + g * 4.2
    accel_scale = 0.78 + a * 0.34
    forward_cap_bonus = max(0.0, (sp - 70.0) * 1.2)
    return base_grip, accel_scale, forward_cap_bonus


def draw_car(
    surface,
    x,
    y,
    angle,
    color,
    pix_zoom=1.0,
    decal_style=1,
    decal_color=None,
    chassis_id=0,
):
    ls = CAR_BODY_LENGTH_SCALE
    color = darken_rgb(color)

    def shorten_shape(points):
        return [(px * ls, py) for px, py in points]

    body, hood, roof, windshield, rear_window, extras = car_chassis_shapes(chassis_id)
    body = shorten_shape(body)
    hood = shorten_shape(hood)
    roof = shorten_shape(roof)
    windshield = shorten_shape(windshield)
    rear_window = shorten_shape(rear_window)

    all_shapes = [
        (body, color),
        (hood, shade_color(color, 25)),
        (roof, shade_color(color, -20)),
        (windshield, darken_rgb((95, 140, 185))),
        (rear_window, darken_rgb((80, 120, 165))),
    ]
    tire_col = darken_rgb(WHEEL_TIRE_COLOR, 25)
    for ex in extras:
        all_shapes.append((shorten_shape(ex), tire_col))

    scale = CAR_SCALE * pix_zoom
    for shape, shape_color in all_shapes:
        scaled_shape = [(px * scale, py * scale) for px, py in shape]
        draw_poly(surface, scaled_shape, angle, x, y, shape_color)

    if decal_color is not None:
        dcol = darken_rgb(decal_color)
    else:
        dcol = shade_color(color, 38)
    for raw_poly in decal_shape_polys(decal_style):
        spoly = shorten_shape(raw_poly)
        scaled_shape = [(px * scale, py * scale) for px, py in spoly]
        draw_poly(surface, scaled_shape, angle, x, y, dcol)


def difficulty_ai_forward_cap(level):
    """Forward speed cap for AI only at difficulty level 1–8."""
    lvl = int(level)
    lvl = max(1, min(DIFFICULTY_LEVEL_COUNT, lvl))
    return float(DIFFICULTY_AI_FORWARD_CAP[lvl - 1])


def track_speed_draw_jitter(speed_mag, wx, wy):
    """Visual-only rumble at high speed (dirt texture); does not affect physics."""
    ds = CAR_SPEED_SCALE
    thresh = 96 * ds
    if speed_mag < thresh:
        return 0.0, 0.0
    t = pygame.time.get_ticks() / 1000.0
    excess = speed_mag - thresh
    mag = (min(5.2, 0.62 + excess * 0.014)) * (0.5 / 1.3)
    ph = t * (43.0 + min(68.0, speed_mag * 0.13)) * 1.5
    ox = math.sin(ph + wx * 0.027) * mag * 0.47
    oy = math.cos(ph * 1.08 + wy * 0.025) * mag * 0.45
    ox += random.uniform(-mag * 0.36, mag * 0.36)
    oy += random.uniform(-mag * 0.36, mag * 0.36)
    return ox, oy


def update_vehicle(
    x,
    y,
    angle,
    vel_x,
    vel_y,
    throttle_value,
    brake_value,
    steer,
    dt,
    base_grip=7.0,
    drift_grip=2.8,
    forward_cap_high=PLAYER_FORWARD_CAP_BASE,
    forward_accel_bonus=0.0,
    accel_scale=1.0,
):
    current_speed = math.hypot(vel_x, vel_y)
    angle += steer * 2.2 * dt * (0.25 + min(1.0, current_speed / 170.0))

    forward_x = math.cos(angle)
    forward_y = math.sin(angle)
    right_x = -forward_y
    right_y = forward_x

    accel_force = (
        260.0 * throttle_value - 320.0 * brake_value + forward_accel_bonus
    ) * CAR_SPEED_SCALE * accel_scale
    vel_x += forward_x * accel_force * dt
    vel_y += forward_y * accel_force * dt

    forward_speed = vel_x * forward_x + vel_y * forward_y
    side_speed = vel_x * right_x + vel_y * right_y
    grip_threshold = 80.0 * CAR_SPEED_SCALE
    grip = drift_grip if steer and abs(forward_speed) > grip_threshold else base_grip
    side_speed -= side_speed * min(1.0, grip * dt)
    forward_speed *= 0.988
    cap_hi = forward_cap_high * CAR_SPEED_SCALE
    forward_speed = max(-120.0 * CAR_SPEED_SCALE, min(cap_hi, forward_speed))

    vel_x = forward_x * forward_speed + right_x * side_speed
    vel_y = forward_y * forward_speed + right_y * side_speed
    x += vel_x * dt
    y += vel_y * dt

    return {
        "x": x,
        "y": y,
        "angle": angle,
        "vel_x": vel_x,
        "vel_y": vel_y,
        "forward_x": forward_x,
        "forward_y": forward_y,
        "right_x": right_x,
        "right_y": right_y,
        "forward_speed": forward_speed,
        "side_speed": side_speed,
    }


def spawn_drift_particles(particles, x, y, forward_x, forward_y, right_x, right_y, vel_x, vel_y, side_speed, forward_speed):
    ds = CAR_SPEED_SCALE
    drifting = abs(side_speed) > 45 * ds and abs(forward_speed) > 60 * ds
    if not drifting:
        return

    rf = 12 * CAR_DRAW_SIZE_MULT
    rs = 8 * CAR_DRAW_SIZE_MULT
    rear_x = x - forward_x * rf
    rear_y = y - forward_y * rf
    wheel_left = (rear_x - right_x * rs, rear_y - right_y * rs)
    wheel_right = (rear_x + right_x * rs, rear_y + right_y * rs)
    emit_count = 2 if abs(side_speed) < 90 * CAR_SPEED_SCALE else 4

    for wx, wy in (wheel_left, wheel_right):
        for _ in range(emit_count):
            particles.append(
                {
                    "x": wx + random.uniform(-2, 2),
                    "y": wy + random.uniform(-2, 2),
                    "vx": -vel_x * 0.25 + random.uniform(-65, 65),
                    "vy": -vel_y * 0.25 + random.uniform(-65, 65),
                    "life": random.uniform(0.20, 0.45),
                    "size": random.choice((1, 1, 2)),
                    "color": darken_rgb(random.choice(DIRT_PARTICLE_COLORS), DIRT_DUST_RGB_DARKEN),
                }
            )


def spawn_collision_sparks(particles, mx, my, nx, ny, closing_speed, overlap):
    """Bright sparks at contact; scales with how hard cars hit."""
    if overlap < 1.2 and closing_speed < 28:
        return
    burst = int(5 + min(22, overlap * 1.1 + closing_speed * 0.07))
    tx, ty = -ny, nx
    base_speed = 155 + min(220, overlap * 5.5 + closing_speed * 0.85)
    for _ in range(burst):
        tang_sign = random.choice((-1.0, 1.0))
        fx = tx * tang_sign * random.uniform(0.35, 1.0) + nx * random.uniform(-0.55, 0.85)
        fy = ty * tang_sign * random.uniform(0.35, 1.0) + ny * random.uniform(-0.55, 0.85)
        fm = math.hypot(fx, fy)
        if fm > 1e-6:
            fx /= fm
            fy /= fm
        sp = base_speed * random.uniform(0.55, 1.08)
        particles.append(
            {
                "x": mx + random.uniform(-4, 4),
                "y": my + random.uniform(-4, 4),
                "vx": fx * sp + random.uniform(-55, 55),
                "vy": fy * sp + random.uniform(-55, 55),
                "life": random.uniform(0.06, 0.20),
                "size": random.choice((1, 1, 2, 2)),
                "color": random.choice(SPARK_COLORS),
            }
        )


def spawn_collision_dirt(particles, mx, my, nx, ny, closing_speed, overlap):
    """Flying dirt kicked up when cars hit each other."""
    if overlap < 0.7 and closing_speed < 10:
        return
    n_dirt = int(8 + min(34, overlap * 2.4 + closing_speed * 0.12))
    tx, ty = -ny, nx
    base = 72 + min(175, overlap * 3.8 + closing_speed * 0.62)
    for _ in range(n_dirt):
        fx = tx * random.uniform(-1.35, 1.35) + nx * random.uniform(-0.4, 1.05)
        fy = ty * random.uniform(-1.35, 1.35) + ny * random.uniform(-0.4, 1.05)
        fm = math.hypot(fx, fy)
        if fm > 1e-6:
            fx /= fm
            fy /= fm
        sp = base * random.uniform(0.28, 1.12)
        particles.append(
            {
                "x": mx + random.uniform(-8, 8),
                "y": my + random.uniform(-8, 8),
                "vx": fx * sp + random.uniform(-82, 82),
                "vy": fy * sp + random.uniform(-82, 82),
                "life": random.uniform(0.38, 0.92),
                "size": random.choice((1, 2, 2, 2, 3)),
                "color": darken_rgb(random.choice(DIRT_PARTICLE_COLORS), DIRT_DUST_RGB_DARKEN),
            }
        )


def ellipse_metric(dx, dy, rx, ry):
    return (dx / rx) ** 2 + (dy / ry) ** 2


def circle_overlaps_rect(cx, cy, r, rect):
    closest_x = max(rect.left, min(cx, rect.right))
    closest_y = max(rect.top, min(cy, rect.bottom))
    return math.hypot(cx - closest_x, cy - closest_y) < r


def slow_zone_velocity_mult(base_mult, effect_div=SLOWDOWN_ZONE_EFFECT_DIV):
    """Weaker off-track slowdown: per-frame speed loss is (1 − base_mult) / effect_div."""
    loss = (1.0 - base_mult) / effect_div
    return 1.0 - loss


def car_off_track(cx, cy, hitbox_r, tcx, tcy, outer_rx, outer_ry, inner_rx, inner_ry):
    orx = max(1e-6, outer_rx - hitbox_r)
    ory = max(1e-6, outer_ry - hitbox_r)
    irx = inner_rx + hitbox_r
    iry = inner_ry + hitbox_r
    dx, dy = cx - tcx, cy - tcy
    eo = ellipse_metric(dx, dy, orx, ory)
    ei = ellipse_metric(dx, dy, irx, iry)
    return eo > 1.0 or ei < 1.0


def nearest_point_on_mid_oval(px, py, tcx, tcy, outer_rx, outer_ry, inner_rx, inner_ry):
    mx = (outer_rx + inner_rx) * 0.5
    my = (outer_ry + inner_ry) * 0.5
    dx, dy = px - tcx, py - tcy
    denom = math.sqrt(ellipse_metric(dx, dy, mx, my))
    if denom < 1e-9:
        return tcx + mx, tcy
    k = 1.0 / denom
    return tcx + dx * k, tcy + dy * k


def resolve_two_car_circles(
    x1, y1, vx1, vy1, ang1, x2, y2, vx2, vy2, ang2, diameter_sum, restitution=0.68
):
    """Equal-mass disks: normal impulse + separation; heading unchanged on impact."""
    _bounce_vel_scale = (0.5 / 4.5) / 11.0  # rebound along normal; ÷11 vs prior collision travel speed
    _sep_travel_scale = 2.0  # 2× more positional separation per overlap
    dx = x2 - x1
    dy = y2 - y1
    d = math.hypot(dx, dy)
    if d >= diameter_sum - 1e-6 or d < 1e-9:
        return x1, y1, vx1, vy1, ang1, x2, y2, vx2, vy2, ang2, None
    nx, ny = dx / d, dy / d
    overlap = diameter_sum - d
    mx = (x1 + x2) * 0.5
    my = (y1 + y2) * 0.5
    move = (overlap * 0.62 + 0.12) * _sep_travel_scale
    x1 -= nx * move
    y1 -= ny * move
    x2 += nx * move
    y2 += ny * move
    rvx = vx2 - vx1
    rvy = vy2 - vy1
    vel_along = rvx * nx + rvy * ny
    # Relative speed along 1→2 normal; positive = already separating along that axis.
    if vel_along < 0:
        rvn_target = -restitution * vel_along * _bounce_vel_scale
    else:
        rvn_target = vel_along
    # Minimum outbound relative normal while intersecting (handles grazing / resting contacts).
    bounce_floor = (24.0 + overlap * 9.0) * _bounce_vel_scale
    rvn_target = max(rvn_target, bounce_floor)
    j = (rvn_target - vel_along) * 0.5
    vx1 -= j * nx
    vy1 -= j * ny
    vx2 += j * nx
    vy2 += j * ny
    damp = 0.982
    vx1 *= damp
    vy1 *= damp
    vx2 *= damp
    vy2 *= damp
    closing = max(0.0, -vel_along, j * 1.05)
    spark_info = (mx, my, nx, ny, closing, overlap)
    return x1, y1, vx1, vy1, ang1, x2, y2, vx2, vy2, ang2, spark_info


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Basic Helicopter Rally")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 28)
    small_font = pygame.font.SysFont(None, 22)
    title_font = pygame.font.SysFont(None, 56)
    mp = MultiplayerManager()
    multiplayer_race = False
    mp_notice = ""
    mp_notice_timer = 0.0
    sync_host_car = None
    bg_w = max(1, int(WIDTH / BG_PIXEL_SCALE))
    bg_h = max(1, int(HEIGHT / BG_PIXEL_SCALE))
    bg_surface = pygame.Surface((bg_w, bg_h))
    bg_specks = []
    for _ in range(180):
        bg_specks.append(
            {
                "x": random.randint(0, bg_w - 1),
                "y": random.randint(0, bg_h - 1),
                "color": random.choice(((38, 58, 44), (44, 62, 52), (32, 48, 58))),
            }
        )

    # Oval ring: outer / inner axis-aligned ellipses (same bounding rects as pygame ellipses).
    TRACK_SIZE_MULT = 1.2
    TRACK_CX = 500
    TRACK_CY = 350
    OUTER_RX = 400 * TRACK_SIZE_MULT
    OUTER_RY = 270 * TRACK_SIZE_MULT
    INNER_RX = 250 * TRACK_SIZE_MULT
    INNER_RY = 150 * TRACK_SIZE_MULT
    outer = pygame.Rect(TRACK_CX - OUTER_RX, TRACK_CY - OUTER_RY, OUTER_RX * 2, OUTER_RY * 2)
    inner = pygame.Rect(TRACK_CX - INNER_RX, TRACK_CY - INNER_RY, INNER_RX * 2, INNER_RY * 2)
    MID_RX = (OUTER_RX + INNER_RX) * 0.5
    MID_RY = (OUTER_RY + INNER_RY) * 0.5

    ai_waypoints = []
    for k in range(20):
        deg = 180.0 - k * (360.0 / 20)
        t = math.radians(deg)
        ai_waypoints.append((TRACK_CX + MID_RX * math.cos(t), TRACK_CY + MID_RY * math.sin(t)))
    wx0, wy0 = ai_waypoints[0]
    wx1, wy1 = ai_waypoints[1]
    SPAWN_ANGLE = math.atan2(wy1 - wy0, wx1 - wx0)
    sf = math.sin(SPAWN_ANGLE)
    cf = math.cos(SPAWN_ANGLE)

    # 3×3 starting grid (player + 8 opponents); lateral/up-track offsets only — anchor placed behind line below.
    GRID_FWD_SPACING = 26.0
    GRID_LAT_SPACING = 22.0
    PLAYER_GRID_ROW = 1
    PLAYER_GRID_COL = 1

    def grid_spawn_xy(row, col, ax, ay, ang):
        cfa = math.cos(ang)
        sfa = math.sin(ang)
        rtx, rty = -sfa, cfa
        df = (row - PLAYER_GRID_ROW) * GRID_FWD_SPACING
        dl = (col - PLAYER_GRID_COL) * GRID_LAT_SPACING
        return ax + df * cfa + dl * rtx, ay + df * sfa + dl * rty

    sl_half_h = int(round(62 * TRACK_SIZE_MULT))
    # Same west-side center as before; strip rotated 90° around center → horizontal bar (thin vertically).
    mid_line_x = TRACK_CX - MID_RX
    half_span = sl_half_h
    start_line = pygame.Rect(
        int(round(mid_line_x - half_span)),
        int(round(TRACK_CY - 5)),
        max(1, half_span * 2),
        10,
    )

    # Entire grid sits −race direction from the line (>½ grid depth + clearance past widest hitboxes).
    GRID_ANCHOR_BACK = 95.0
    lc_x = float(start_line.centerx)
    lc_y = float(start_line.centery)
    spawn_ax = lc_x - GRID_ANCHOR_BACK * cf
    spawn_ay = lc_y - GRID_ANCHOR_BACK * sf

    PLAYER_SPAWN_X, PLAYER_SPAWN_Y = grid_spawn_xy(
        PLAYER_GRID_ROW, PLAYER_GRID_COL, spawn_ax, spawn_ay, SPAWN_ANGLE
    )

    LAPS_TO_WIN = 8

    def build_ai_bots():
        bots = []
        color_i = 0
        for r in range(3):
            for c in range(3):
                if r == PLAYER_GRID_ROW and c == PLAYER_GRID_COL:
                    continue
                sx, sy = grid_spawn_xy(r, c, spawn_ax, spawn_ay, SPAWN_ANGLE)
                # Spread opponents across track width while driving (pixels, perpendicular to waypoint chord).
                line_lat = (color_i - 3.5) * 12.5
                bots.append(
                    {
                        "x": sx,
                        "y": sy,
                        "angle": SPAWN_ANGLE,
                        "vel_x": 0.0,
                        "vel_y": 0.0,
                        "waypoint_index": 0,
                        "forward_speed": 0.0,
                        "side_speed": 0.0,
                        "forward_x_now": cf,
                        "forward_y_now": sf,
                        "right_x_now": -sf,
                        "right_y_now": cf,
                        "lap": 0,
                        "next_checkpoint_index": 0,
                        "ready_to_finish_lap": False,
                        "crossed_line_last_frame": False,
                        "color": AI_BOT_COLORS[color_i],
                        "line_lateral": line_lat,
                    }
                )
                color_i += 1
        return bots

    ai_bots = build_ai_bots()
    saved_bot_colors = [tuple(AI_BOT_COLORS[i]) for i in range(8)]
    saved_bot_decals = [
        (random.randint(0, DECAL_NUM_STYLES - 1), tuple(random.choice(DECAL_PALETTE)))
        for _ in range(8)
    ]
    player_car_color = RED
    player_decal_style = 1
    player_decal_color = DECAL_PALETTE[0]

    def apply_saved_colors_to_bots():
        for i, bot in enumerate(ai_bots):
            if i < len(saved_bot_colors):
                bot["color"] = saved_bot_colors[i]

    def apply_saved_decals_to_bots():
        for i, bot in enumerate(ai_bots):
            if i < len(saved_bot_decals):
                ds, dc = saved_bot_decals[i]
                bot["decal_style"] = int(ds)
                bot["decal_color"] = (int(dc[0]), int(dc[1]), int(dc[2]))

    apply_saved_colors_to_bots()
    apply_saved_decals_to_bots()

    car_x = PLAYER_SPAWN_X
    car_y = PLAYER_SPAWN_Y
    car_angle = SPAWN_ANGLE
    vel_x = 0.0
    vel_y = 0.0
    forward_speed = 0.0
    side_speed = 0.0
    forward_x = cf
    forward_y = sf
    right_x = -sf
    right_y = cf

    lap = 0
    particles = []

    crossed_line_last_frame = False
    checkpoints = [
        (start_line.centerx, start_line.centery),
        (
            TRACK_CX + MID_RX * math.cos(math.radians(90)),
            TRACK_CY + MID_RY * math.sin(math.radians(90)),
        ),
        (TRACK_CX + MID_RX, TRACK_CY),
        (
            TRACK_CX + MID_RX * math.cos(math.radians(270)),
            TRACK_CY + MID_RY * math.sin(math.radians(270)),
        ),
    ]
    next_checkpoint_index = 0
    ready_to_finish_lap = False
    checkpoint_radius = 30 * 1.8 * 1.15 * 1.2

    winner_text = ""
    game_state = "auth"
    auth_mode = "login"
    auth_username = ""
    auth_passcode = ""
    auth_confirm = ""
    auth_focus = "username"
    auth_message = ""
    auth_message_is_error = True
    logged_in_user = ""
    _auth_field_w = 360
    _auth_field_h = 40
    _auth_field_x = WIDTH // 2 - _auth_field_w // 2
    auth_user_field = pygame.Rect(_auth_field_x, HEIGHT // 2 - 88, _auth_field_w, _auth_field_h)
    auth_pass_field = pygame.Rect(_auth_field_x, HEIGHT // 2 - 28, _auth_field_w, _auth_field_h)
    auth_confirm_field = pygame.Rect(_auth_field_x, HEIGHT // 2 + 32, _auth_field_w, _auth_field_h)
    _auth_tab_w = 150
    _auth_tab_h = 36
    _auth_tab_gap = 12
    _auth_tab_row = 2 * _auth_tab_w + _auth_tab_gap
    _auth_tab_x0 = WIDTH // 2 - _auth_tab_row // 2
    auth_tab_login_rect = pygame.Rect(_auth_tab_x0, HEIGHT // 2 - 168, _auth_tab_w, _auth_tab_h)
    auth_tab_signup_rect = pygame.Rect(
        _auth_tab_x0 + _auth_tab_w + _auth_tab_gap, HEIGHT // 2 - 168, _auth_tab_w, _auth_tab_h
    )
    auth_submit_rect = pygame.Rect(WIDTH // 2 - 100, HEIGHT // 2 + 108, 200, 46)
    lobby_tab = "home"
    selected_chassis_id = 0
    unlocked_chassis = set(range(NUM_CAR_CHASSIS)) - {
        i for i in range(NUM_CAR_CHASSIS) if chassis_unlock_cost(i) > 0
    }
    _lobby_tab_w = 96
    _lobby_tab_h = 34
    _lobby_tab_gap = 8
    _lobby_tab_row = 3 * _lobby_tab_w + 2 * _lobby_tab_gap
    _lobby_tab_x0 = WIDTH // 2 - _lobby_tab_row // 2
    _lobby_tab_y = HEIGHT // 2 - 218
    lobby_tab_home_rect = pygame.Rect(_lobby_tab_x0, _lobby_tab_y, _lobby_tab_w, _lobby_tab_h)
    lobby_tab_cars_rect = pygame.Rect(
        _lobby_tab_x0 + _lobby_tab_w + _lobby_tab_gap, _lobby_tab_y, _lobby_tab_w, _lobby_tab_h
    )
    lobby_tab_multi_rect = pygame.Rect(
        _lobby_tab_x0 + 2 * (_lobby_tab_w + _lobby_tab_gap), _lobby_tab_y, _lobby_tab_w, _lobby_tab_h
    )
    mp_host_btn = pygame.Rect(WIDTH // 2 - 220, HEIGHT // 2 - 132, 200, 40)
    mp_seek_btn = pygame.Rect(WIDTH // 2 + 20, HEIGHT // 2 - 132, 200, 40)
    mp_stop_btn = pygame.Rect(WIDTH // 2 - 100, HEIGHT // 2 + 72, 200, 38)
    mp_start_btn = pygame.Rect(WIDTH // 2 - 100, HEIGHT // 2 + 118, 200, 44)
    mp_join_rows = []
    race_button = pygame.Rect(WIDTH // 2 - 90, HEIGHT // 2 - 42, 180, 48)
    tune_button = pygame.Rect(WIDTH // 2 - 90, HEIGHT // 2 + 14, 180, 44)
    customize_button = pygame.Rect(WIDTH // 2 - 90, HEIGHT // 2 + 68, 180, 44)
    leave_race_rect = pygame.Rect(WIDTH - 188, HEIGHT - 50, 176, 40)
    _diff_cols = 4
    _diff_btn_w = 244
    _diff_btn_h = 30
    _diff_gap_x = 8
    _diff_gap_y = 8
    _diff_total_w = _diff_cols * _diff_btn_w + (_diff_cols - 1) * _diff_gap_x
    _diff_x0 = WIDTH // 2 - _diff_total_w // 2
    _diff_y0 = HEIGHT // 2 - 228
    difficulty_choice_rects = []
    for i in range(DIFFICULTY_LEVEL_COUNT):
        r = i // _diff_cols
        c = i % _diff_cols
        difficulty_choice_rects.append(
            pygame.Rect(
                _diff_x0 + c * (_diff_btn_w + _diff_gap_x),
                _diff_y0 + r * (_diff_btn_h + _diff_gap_y),
                _diff_btn_w,
                _diff_btn_h,
            )
        )
    tune_bar_rect = pygame.Rect(WIDTH // 2 - 150, HEIGHT // 2 - 58, 300, 22)
    tune_minus_rect = pygame.Rect(tune_bar_rect.left - 52, tune_bar_rect.top - 4, 44, 30)
    tune_plus_rect = pygame.Rect(tune_bar_rect.right + 8, tune_bar_rect.top - 4, 44, 30)
    tune_back_rect = pygame.Rect(WIDTH // 2 - 72, HEIGHT // 2 + 132, 144, 44)

    cust_slider_w = 340
    cust_slider_left = WIDTH // 2 - cust_slider_w // 2
    cust_susp_slider = pygame.Rect(cust_slider_left, HEIGHT // 2 - 100, cust_slider_w, 26)
    cust_drift_slider = pygame.Rect(cust_slider_left, HEIGHT // 2 - 42, cust_slider_w, 26)
    cust_back_rect = pygame.Rect(WIDTH // 2 - 72, HEIGHT // 2 + 124, 144, 44)

    cust_suspension = 0.5
    cust_drift = 0.5
    cust_drag = None
    cust_tab = "setup"
    cust_decal_subtab = "design"
    _cty = HEIGHT // 2 - 242
    _tab_w = 104
    _tab_gap = 6
    _tab_row = 3 * _tab_w + 2 * _tab_gap
    _ctx0 = WIDTH // 2 - _tab_row // 2
    tab_setup_rect = pygame.Rect(_ctx0, _cty, _tab_w, 36)
    tab_paint_rect = pygame.Rect(_ctx0 + _tab_w + _tab_gap, _cty, _tab_w, 36)
    tab_decal_rect = pygame.Rect(_ctx0 + 2 * (_tab_w + _tab_gap), _cty, _tab_w, 36)
    cust_decal_sub_design_rect = pygame.Rect(WIDTH // 2 - 108, HEIGHT // 2 - 154, 104, 28)
    cust_decal_sub_color_rect = pygame.Rect(WIDTH // 2 + 4, HEIGHT // 2 - 154, 104, 28)

    speed_upgrade = 0
    difficulty_level = DIFFICULTY_LEVEL_DEFAULT
    money = 0

    def cust_slider01(rect, mx):
        return max(0.0, min(1.0, (mx - rect.left) / rect.width))

    def car_choice_card_rects():
        cols = 3
        card_w = 300
        card_h = 168
        gap_x = 14
        gap_y = 14
        total_w = cols * card_w + (cols - 1) * gap_x
        x0 = WIDTH // 2 - total_w // 2
        y0 = HEIGHT // 2 - 198
        rects = []
        for i in range(NUM_CAR_CHASSIS):
            r = i // cols
            c = i % cols
            rects.append(
                pygame.Rect(
                    x0 + c * (card_w + gap_x),
                    y0 + r * (card_h + gap_y),
                    card_w,
                    card_h,
                )
            )
        return rects

    def player_physics_from_customization():
        """Chassis grip/accel tradeoff + sliders: suspension, drift."""
        s = cust_suspension
        d = cust_drift
        ch_base_grip, ch_accel, _ch_cap = chassis_physics_modifiers(selected_chassis_id)
        base_grip = ch_base_grip + s * 1.35 - 1.65 * 0.5
        base_grip = max(4.85, base_grip)
        drift_grip = 2.55 + s * 0.38 - d * 1.15
        drift_grip = max(1.62, min(3.85, drift_grip))
        accel_scale = ch_accel + (1.05 - s * 0.24 - ch_accel) * 0.35
        accel_scale = max(0.76, min(1.12, accel_scale))
        speed_mult = 0.9 + d * 0.18
        return base_grip, drift_grip, accel_scale, speed_mult

    def auth_mask_secret(text):
        return "*" * len(text)

    def auth_append_char(field_key, ch):
        nonlocal auth_username, auth_passcode, auth_confirm
        if ch < " " or ch == "\x7f":
            return
        if field_key == "username" and len(auth_username) < AUTH_USERNAME_MAX:
            auth_username += ch
        elif field_key == "passcode" and len(auth_passcode) < AUTH_PASSCODE_MAX:
            auth_passcode += ch
        elif field_key == "confirm" and len(auth_confirm) < AUTH_PASSCODE_MAX:
            auth_confirm += ch

    def auth_backspace_field(field_key):
        nonlocal auth_username, auth_passcode, auth_confirm
        if field_key == "username":
            auth_username = auth_username[:-1]
        elif field_key == "passcode":
            auth_passcode = auth_passcode[:-1]
        elif field_key == "confirm":
            auth_confirm = auth_confirm[:-1]

    def auth_submit():
        nonlocal game_state, auth_message, auth_message_is_error, logged_in_user
        if auth_mode == "login":
            ok, msg = login_account(auth_username, auth_passcode)
        else:
            if auth_passcode != auth_confirm:
                ok, msg = False, "Passcodes do not match."
            else:
                ok, msg = register_account(auth_username, auth_passcode)
        if ok:
            logged_in_user = msg
            auth_message = f"Welcome, {logged_in_user}!"
            auth_message_is_error = False
            game_state = "lobby"
            sync_mp_profile()
            mp.start_browse()
        else:
            auth_message = msg
            auth_message_is_error = True

    def sync_mp_profile():
        mp.set_profile(
            logged_in_user,
            selected_chassis_id,
            player_car_color,
            player_decal_style,
            player_decal_color,
        )

    def apply_mp_client_state(st):
        nonlocal sync_host_car, forward_speed, lap
        if not st:
            return
        cars = st.get("cars", [])
        sync_host_car = None
        opps = []
        for c in cars:
            if c.get("is_player"):
                sync_host_car = c
            else:
                opps.append(c)
        my_slot = mp.client_slot()
        for i, bot in enumerate(ai_bots):
            if i < len(opps):
                c = opps[i]
                bot["x"] = c["x"]
                bot["y"] = c["y"]
                bot["angle"] = c["angle"]
                bot["vel_x"] = c["vx"]
                bot["vel_y"] = c["vy"]
                bot["lap"] = c.get("lap", 0)
                bot["color"] = tuple(c.get("color", bot["color"]))
                bot["chassis_id"] = c.get("chassis_id", 0)
                bot["decal_style"] = c.get("decal_style", 0)
                bot["decal_color"] = tuple(c.get("decal_color", (255, 255, 255)))
                if my_slot == i:
                    forward_speed = math.hypot(bot["vel_x"], bot["vel_y"])
                    lap = bot.get("lap", lap)

    def process_mp_events():
        nonlocal mp_notice, mp_notice_timer, game_state, multiplayer_race
        for ev in mp.poll():
            et = ev.get("type")
            if et == "invite":
                host = ev.get("host", "Someone")
                mp_notice = f"Race invite from {host}! Open Multiplayer tab to join."
                mp_notice_timer = 8.0
            elif et == "player_joined":
                mp_notice = f"{ev.get('user', 'Player')} joined your race lobby."
                mp_notice_timer = 6.0
            elif et == "player_left":
                mp_notice = "A player left your lobby."
                mp_notice_timer = 4.0
            elif et == "invites_sent":
                n = ev.get("count", 0)
                mp_notice = f"Sent invites to {n} online player(s) on your network."
                mp_notice_timer = 5.0
            elif et == "joined":
                mp_notice = f"Joined lobby — you are racer slot {ev.get('slot', '?')}."
                mp_notice_timer = 6.0
            elif et == "race_start":
                if mp.is_client():
                    multiplayer_race = True
                    reset_race_state()
                    game_state = "race"
            elif et == "error":
                mp_notice = ev.get("message", "Network error")
                mp_notice_timer = 6.0
            elif et == "host_started":
                mp_notice = f"Hosting lobby {ev.get('lobby_id', '')} — seek players or wait for joins."
                mp_notice_timer = 6.0
            elif et == "remote_input" and game_state == "race":
                slot = ev.get("slot")
                if slot is not None and 0 <= slot < len(ai_bots):
                    ai_bots[slot]["remote_input"] = {
                        "throttle": ev.get("throttle", 0.0),
                        "brake": ev.get("brake", 0.0),
                        "steer": ev.get("steer", 0.0),
                    }

    def start_multiplayer_host():
        sync_mp_profile()
        mp.start_host()
        mp_notice = "Hosting multiplayer race — click Seek to notify online players."
        mp_notice_timer = 6.0

    def start_multiplayer_race():
        nonlocal game_state, multiplayer_race
        if not mp.is_host():
            return
        multiplayer_race = True
        mp.notify_race_start()
        reset_race_state()
        game_state = "race"

    def try_pick_chassis(ci):
        nonlocal selected_chassis_id, money, unlocked_chassis
        cost = chassis_unlock_cost(ci)
        if chassis_is_unlocked(ci, unlocked_chassis):
            selected_chassis_id = ci
            return
        if money >= cost:
            money -= cost
            unlocked_chassis.add(ci)
            selected_chassis_id = ci

    def pick_player_color(new_col):
        nonlocal player_car_color, saved_bot_colors
        new_col = (int(new_col[0]), int(new_col[1]), int(new_col[2]))
        if new_col == player_car_color:
            return
        if new_col == WHITE or new_col == CAR_PAINT_BLACK:
            player_car_color = new_col
        else:
            for i in range(len(saved_bot_colors)):
                if saved_bot_colors[i] == new_col:
                    saved_bot_colors[i] = player_car_color
                    player_car_color = new_col
                    break
        apply_saved_colors_to_bots()

    def paint_swatch_rects():
        """Returns [(rect, rgb), ...] white/black first, then saved opponent colors."""
        out = []
        row_y = HEIGHT // 2 - 150
        pair_w = 2 * PAINT_SWATCH_PX + PAINT_SWATCH_GAP
        x0 = WIDTH // 2 - pair_w // 2
        for i, col in enumerate((WHITE, CAR_PAINT_BLACK)):
            out.append(
                (
                    pygame.Rect(x0 + i * (PAINT_SWATCH_PX + PAINT_SWATCH_GAP), row_y, PAINT_SWATCH_PX, PAINT_SWATCH_PX),
                    col,
                )
            )
        row2 = row_y + PAINT_SWATCH_PX + 18
        cols = 4
        for j, col in enumerate(saved_bot_colors):
            r = j // cols
            c = j % cols
            bx = WIDTH // 2 - (cols * PAINT_SWATCH_PX + (cols - 1) * PAINT_SWATCH_GAP) // 2
            out.append(
                (
                    pygame.Rect(
                        bx + c * (PAINT_SWATCH_PX + PAINT_SWATCH_GAP),
                        row2 + r * (PAINT_SWATCH_PX + PAINT_SWATCH_GAP),
                        PAINT_SWATCH_PX,
                        PAINT_SWATCH_PX,
                    ),
                    col,
                )
            )
        return out

    def decal_style_choice_rects():
        rects = []
        nw = DECAL_NUM_STYLES
        bw = 52
        gap = 5
        total = nw * bw + (nw - 1) * gap
        x0 = WIDTH // 2 - total // 2
        y0 = HEIGHT // 2 - 110
        for i in range(nw):
            rects.append((pygame.Rect(x0 + i * (bw + gap), y0, bw, 28), i))
        return rects

    def decal_palette_swatch_rects():
        out = []
        row_y = HEIGHT // 2 - 100
        cols = 5
        for i, col in enumerate(DECAL_PALETTE):
            r = i // cols
            c = i % cols
            bx = WIDTH // 2 - (cols * PAINT_SWATCH_PX + (cols - 1) * PAINT_SWATCH_GAP) // 2
            out.append(
                (
                    pygame.Rect(
                        bx + c * (PAINT_SWATCH_PX + PAINT_SWATCH_GAP),
                        row_y + r * (PAINT_SWATCH_PX + PAINT_SWATCH_GAP),
                        PAINT_SWATCH_PX,
                        PAINT_SWATCH_PX,
                    ),
                    col,
                )
            )
        return out

    def speed_buy_cost(level_before):
        return SPEED_UPGRADE_BASE_PRICE + level_before * SPEED_UPGRADE_PRICE_STEP

    def speed_refund_at_level(level_now):
        if level_now <= 0:
            return 0
        return SPEED_UPGRADE_BASE_PRICE + (level_now - 1) * SPEED_UPGRADE_PRICE_STEP

    def tune_buy_one():
        nonlocal money, speed_upgrade
        if speed_upgrade >= SPEED_UPGRADE_MAX:
            return
        c = speed_buy_cost(speed_upgrade)
        if money >= c:
            money -= c
            speed_upgrade += 1

    def tune_sell_one():
        nonlocal money, speed_upgrade
        if speed_upgrade <= 0:
            return
        money += speed_refund_at_level(speed_upgrade)
        speed_upgrade -= 1

    def tune_set_level(desired):
        nonlocal money, speed_upgrade
        desired = max(0, min(SPEED_UPGRADE_MAX, desired))
        while speed_upgrade < desired:
            c = speed_buy_cost(speed_upgrade)
            if money < c:
                break
            money -= c
            speed_upgrade += 1
        while speed_upgrade > desired:
            money += speed_refund_at_level(speed_upgrade)
            speed_upgrade -= 1

    def reset_race_state():
        nonlocal car_x, car_y, car_angle, vel_x, vel_y
        nonlocal lap, next_checkpoint_index, ready_to_finish_lap
        nonlocal crossed_line_last_frame
        nonlocal forward_speed, side_speed
        nonlocal forward_x, forward_y, right_x, right_y
        nonlocal ai_bots
        nonlocal saved_bot_decals
        nonlocal winner_text

        car_x, car_y, car_angle, vel_x, vel_y = PLAYER_SPAWN_X, PLAYER_SPAWN_Y, SPAWN_ANGLE, 0.0, 0.0
        saved_bot_decals = [
            (random.randint(0, DECAL_NUM_STYLES - 1), tuple(random.choice(DECAL_PALETTE)))
            for _ in range(8)
        ]
        ai_bots = build_ai_bots()
        for bot in ai_bots:
            bot["control"] = "ai"
        apply_saved_colors_to_bots()
        apply_saved_decals_to_bots()
        if multiplayer_race and mp.is_host():
            mp.apply_roster_to_bots(ai_bots)
        lap = 0
        next_checkpoint_index = 0
        ready_to_finish_lap = False
        crossed_line_last_frame = False
        forward_speed = 0.0
        side_speed = 0.0
        sf = math.sin(SPAWN_ANGLE)
        cf = math.cos(SPAWN_ANGLE)
        forward_x, forward_y, right_x, right_y = cf, sf, -sf, cf
        winner_text = ""
        particles.clear()

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if game_state == "tune":
                    game_state = "lobby"
                elif game_state == "customize":
                    game_state = "lobby"
                    cust_drag = None
                    cust_tab = "setup"
                elif game_state == "lobby" and lobby_tab in ("cars", "multiplayer"):
                    if lobby_tab == "multiplayer":
                        mp.stop()
                    lobby_tab = "home"
                else:
                    running = False
            if game_state == "auth":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if auth_tab_login_rect.collidepoint(event.pos):
                        auth_mode = "login"
                        auth_focus = "username"
                        auth_message = ""
                    elif auth_tab_signup_rect.collidepoint(event.pos):
                        auth_mode = "signup"
                        auth_focus = "username"
                        auth_message = ""
                    elif auth_user_field.collidepoint(event.pos):
                        auth_focus = "username"
                    elif auth_pass_field.collidepoint(event.pos):
                        auth_focus = "passcode"
                    elif auth_mode == "signup" and auth_confirm_field.collidepoint(event.pos):
                        auth_focus = "confirm"
                    elif auth_submit_rect.collidepoint(event.pos):
                        auth_submit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_TAB:
                        if auth_mode == "signup":
                            order = ("username", "passcode", "confirm")
                            i = order.index(auth_focus)
                            auth_focus = order[(i + 1) % 3]
                        else:
                            auth_focus = "passcode" if auth_focus == "username" else "username"
                    elif event.key == pygame.K_RETURN:
                        auth_submit()
                    elif event.key == pygame.K_BACKSPACE:
                        auth_backspace_field(auth_focus)
                    elif event.unicode:
                        auth_append_char(auth_focus, event.unicode)
            elif game_state == "lobby":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if lobby_tab_home_rect.collidepoint(event.pos):
                        lobby_tab = "home"
                    elif lobby_tab_cars_rect.collidepoint(event.pos):
                        lobby_tab = "cars"
                        sync_mp_profile()
                    elif lobby_tab_multi_rect.collidepoint(event.pos):
                        lobby_tab = "multiplayer"
                        sync_mp_profile()
                        if not mp.is_host():
                            mp.start_browse()
                    elif lobby_tab == "multiplayer" and mp_host_btn.collidepoint(event.pos):
                        start_multiplayer_host()
                    elif lobby_tab == "multiplayer" and mp_seek_btn.collidepoint(event.pos):
                        if mp.is_host():
                            mp.seek_and_invite()
                        else:
                            mp_notice = "Host a race first, then Seek sends invites."
                            mp_notice_timer = 4.0
                    elif lobby_tab == "multiplayer" and mp_stop_btn.collidepoint(event.pos):
                        mp.stop()
                        mp.start_browse()
                        mp_notice = "Stopped hosting."
                        mp_notice_timer = 4.0
                    elif lobby_tab == "multiplayer" and mp_start_btn.collidepoint(event.pos):
                        start_multiplayer_race()
                    elif lobby_tab == "multiplayer":
                        for jrect, jip in mp_join_rows:
                            if jrect.collidepoint(event.pos) and jip:
                                sync_mp_profile()
                                mp.join_lobby(jip)
                                break
                    elif lobby_tab == "home" and race_button.collidepoint(event.pos):
                        if chassis_is_unlocked(selected_chassis_id, unlocked_chassis):
                            reset_race_state()
                            game_state = "race"
                    elif lobby_tab == "home" and tune_button.collidepoint(event.pos):
                        game_state = "tune"
                    elif lobby_tab == "home" and customize_button.collidepoint(event.pos):
                        game_state = "customize"
                        cust_tab = "setup"
                        cust_drag = None
                    elif lobby_tab == "cars":
                        for ci, crect in enumerate(car_choice_card_rects()):
                            if crect.collidepoint(event.pos):
                                try_pick_chassis(ci)
                                break
                if (
                    lobby_tab == "home"
                    and event.type == pygame.KEYDOWN
                    and event.key in (pygame.K_RETURN, pygame.K_SPACE)
                    and chassis_is_unlocked(selected_chassis_id, unlocked_chassis)
                ):
                    reset_race_state()
                    game_state = "race"
            elif game_state == "tune":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    picked_diff = None
                    for di, drect in enumerate(difficulty_choice_rects):
                        if drect.collidepoint(event.pos):
                            picked_diff = di + 1
                            break
                    if picked_diff is not None:
                        difficulty_level = picked_diff
                    elif tune_back_rect.collidepoint(event.pos):
                        game_state = "lobby"
                    elif tune_minus_rect.collidepoint(event.pos):
                        tune_sell_one()
                    elif tune_plus_rect.collidepoint(event.pos):
                        tune_buy_one()
                    elif tune_bar_rect.collidepoint(event.pos):
                        rel = (event.pos[0] - tune_bar_rect.left) / tune_bar_rect.width
                        tune_set_level(int(round(max(0.0, min(1.0, rel)) * SPEED_UPGRADE_MAX)))
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_LEFT:
                        tune_sell_one()
                    elif event.key == pygame.K_RIGHT:
                        tune_buy_one()
            elif game_state == "customize":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if tab_setup_rect.collidepoint(event.pos):
                        cust_tab = "setup"
                        cust_drag = None
                    elif tab_paint_rect.collidepoint(event.pos):
                        cust_tab = "paint"
                        cust_drag = None
                    elif tab_decal_rect.collidepoint(event.pos):
                        cust_tab = "decals"
                        cust_drag = None
                    elif cust_back_rect.collidepoint(event.pos):
                        game_state = "lobby"
                        cust_drag = None
                        cust_tab = "setup"
                    elif cust_tab == "decals":
                        if cust_decal_sub_design_rect.collidepoint(event.pos):
                            cust_decal_subtab = "design"
                        elif cust_decal_sub_color_rect.collidepoint(event.pos):
                            cust_decal_subtab = "color"
                        elif cust_decal_subtab == "design":
                            for srect, sid in decal_style_choice_rects():
                                if srect.collidepoint(event.pos):
                                    player_decal_style = sid
                                    break
                        elif cust_decal_subtab == "color":
                            for srect, scol in decal_palette_swatch_rects():
                                if srect.collidepoint(event.pos):
                                    player_decal_color = (
                                        int(scol[0]),
                                        int(scol[1]),
                                        int(scol[2]),
                                    )
                                    break
                    elif cust_tab == "paint":
                        for srect, scol in paint_swatch_rects():
                            if srect.collidepoint(event.pos):
                                pick_player_color(scol)
                                break
                    elif cust_tab == "setup" and cust_susp_slider.collidepoint(event.pos):
                        cust_drag = "susp"
                        cust_suspension = cust_slider01(cust_susp_slider, event.pos[0])
                    elif cust_tab == "setup" and cust_drift_slider.collidepoint(event.pos):
                        cust_drag = "drift"
                        cust_drift = cust_slider01(cust_drift_slider, event.pos[0])
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    cust_drag = None
                if event.type == pygame.MOUSEMOTION and cust_drag and cust_tab == "setup":
                    if cust_drag == "susp":
                        cust_suspension = cust_slider01(cust_susp_slider, event.pos[0])
                    elif cust_drag == "drift":
                        cust_drift = cust_slider01(cust_drift_slider, event.pos[0])
            elif game_state == "race":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and leave_race_rect.collidepoint(
                    event.pos
                ):
                    game_state = "lobby"
                    if multiplayer_race:
                        multiplayer_race = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                    reset_race_state()
            elif game_state == "result":
                if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                    reset_race_state()
                    game_state = "race"
                if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                    game_state = "lobby"

        if game_state in ("lobby", "race", "result"):
            mp.tick()
            process_mp_events()
            if mp_notice_timer > 0:
                mp_notice_timer = max(0.0, mp_notice_timer - dt)

        if game_state == "race":
            pg_base, pg_drift, player_accel_scale, drift_speed_mult = player_physics_from_customization()
            keys = pygame.key.get_pressed()
            throttle = keys[pygame.K_w] or keys[pygame.K_UP]
            brake = keys[pygame.K_s] or keys[pygame.K_DOWN]
            left = keys[pygame.K_a] or keys[pygame.K_LEFT]
            right = keys[pygame.K_d] or keys[pygame.K_RIGHT]

            steer = 0
            if left:
                steer -= 1
            if right:
                steer += 1
            throttle_value = 1.0 if throttle else 0.0
            brake_value = 1.0 if brake else 0.0

            if multiplayer_race and mp.is_client():
                mp.send_input(throttle_value, brake_value, steer)
                apply_mp_client_state(mp.latest_state())
            else:
                _, _, ch_cap_bonus = chassis_physics_modifiers(selected_chassis_id)
                player_cap = (
                    PLAYER_FORWARD_CAP_BASE
                    + speed_upgrade * SPEED_UPGRADE_FORWARD_PER_TIER
                    + ch_cap_bonus
                )
                player_cap_eff = player_cap * drift_speed_mult

                player_state = update_vehicle(
                    car_x,
                    car_y,
                    car_angle,
                    vel_x,
                    vel_y,
                    throttle_value,
                    brake_value,
                    steer,
                    dt,
                    base_grip=pg_base,
                    drift_grip=pg_drift,
                    forward_cap_high=player_cap_eff,
                    forward_accel_bonus=0.0,
                    accel_scale=player_accel_scale,
                )
                car_x = player_state["x"]
                car_y = player_state["y"]
                car_angle = player_state["angle"]
                vel_x = player_state["vel_x"]
                vel_y = player_state["vel_y"]
                forward_x = player_state["forward_x"]
                forward_y = player_state["forward_y"]
                right_x = player_state["right_x"]
                right_y = player_state["right_y"]
                forward_speed = player_state["forward_speed"]
                side_speed = player_state["side_speed"]

                if car_off_track(
                    car_x,
                    car_y,
                    CAR_HITBOX_RADIUS,
                    TRACK_CX,
                    TRACK_CY,
                    OUTER_RX,
                    OUTER_RY,
                    INNER_RX,
                    INNER_RY,
                ):
                    _slow = slow_zone_velocity_mult(OFF_TRACK_SLOW_PLAYER)
                    vel_x *= _slow
                    vel_y *= _slow

            if not (multiplayer_race and mp.is_client()):
                hb = CAR_HITBOX_RADIUS
                edge_frac = min(0.42, (45 + hb) / min(OUTER_RX, OUTER_RY))
                band_lo = max(0.0, (1.0 - edge_frac)) ** 2
                band_hi = (1.0 + edge_frac) ** 2

                for bot in ai_bots:
                    if bot.get("control") == "remote":
                        ri = bot.get("remote_input", {"throttle": 0.0, "brake": 0.0, "steer": 0.0})
                        ai_forward_cap = difficulty_ai_forward_cap(difficulty_level)
                        ai_state = update_vehicle(
                            bot["x"],
                            bot["y"],
                            bot["angle"],
                            bot["vel_x"],
                            bot["vel_y"],
                            ri.get("throttle", 0.0),
                            ri.get("brake", 0.0),
                            ri.get("steer", 0.0),
                            dt,
                            base_grip=10.5,
                            drift_grip=4.8,
                            forward_cap_high=ai_forward_cap,
                        )
                        bot["x"] = ai_state["x"]
                        bot["y"] = ai_state["y"]
                        bot["angle"] = ai_state["angle"]
                        bot["vel_x"] = ai_state["vel_x"]
                        bot["vel_y"] = ai_state["vel_y"]
                        bot["forward_speed"] = ai_state["forward_speed"]
                        bot["side_speed"] = ai_state["side_speed"]
                        bot["forward_x_now"] = ai_state["forward_x"]
                        bot["forward_y_now"] = ai_state["forward_y"]
                        bot["right_x_now"] = ai_state["right_x"]
                        bot["right_y_now"] = ai_state["right_y"]
                        if car_off_track(
                            bot["x"],
                            bot["y"],
                            CAR_HITBOX_RADIUS,
                            TRACK_CX,
                            TRACK_CY,
                            OUTER_RX,
                            OUTER_RY,
                            INNER_RX,
                            INNER_RY,
                        ):
                            _slow_ai = slow_zone_velocity_mult(OFF_TRACK_SLOW_AI)
                            bot["vel_x"] *= _slow_ai
                            bot["vel_y"] *= _slow_ai
                        continue

                    wi = bot["waypoint_index"]
                    ai_target_x, ai_target_y = ai_waypoints[wi]
                    if math.dist((bot["x"], bot["y"]), (ai_target_x, ai_target_y)) < 55 * CAR_SPEED_SCALE:
                        wi = (wi + 1) % len(ai_waypoints)
                        bot["waypoint_index"] = wi
                        ai_target_x, ai_target_y = ai_waypoints[wi]

                    ai_off_track = car_off_track(
                        bot["x"], bot["y"], hb, TRACK_CX, TRACK_CY, OUTER_RX, OUTER_RY, INNER_RX, INNER_RY
                    )
                    dx_ai = bot["x"] - TRACK_CX
                    dy_ai = bot["y"] - TRACK_CY
                    eo_raw = ellipse_metric(dx_ai, dy_ai, OUTER_RX, OUTER_RY)
                    ei_raw = ellipse_metric(dx_ai, dy_ai, INNER_RX, INNER_RY)
                    near_outer_edge = eo_raw <= 1.0 and eo_raw > band_lo
                    near_inner_edge = ei_raw >= 1.0 and ei_raw < band_hi
                    ai_risky_zone = ai_off_track or near_outer_edge or near_inner_edge

                    ai_next_index = (bot["waypoint_index"] + 1) % len(ai_waypoints)
                    ai_next_x, ai_next_y = ai_waypoints[ai_next_index]
                    ai_speed_now = math.hypot(bot["vel_x"], bot["vel_y"])
                    lookahead_blend = min(0.6, ai_speed_now / (360.0 * CAR_SPEED_SCALE))
                    if ai_risky_zone:
                        lookahead_blend *= 0.25
                    target_x = ai_target_x * (1.0 - lookahead_blend) + ai_next_x * lookahead_blend
                    target_y = ai_target_y * (1.0 - lookahead_blend) + ai_next_y * lookahead_blend

                    tan_dx = ai_next_x - ai_target_x
                    tan_dy = ai_next_y - ai_target_y
                    tn = max(1e-6, math.hypot(tan_dx, tan_dy))
                    rx = -tan_dy / tn
                    ry = tan_dx / tn
                    lat = bot["line_lateral"]
                    if ai_risky_zone:
                        lat *= 0.35
                    target_x += lat * rx
                    target_y += lat * ry

                    if ai_risky_zone:
                        recover_x, recover_y = nearest_point_on_mid_oval(
                            bot["x"], bot["y"], TRACK_CX, TRACK_CY, OUTER_RX, OUTER_RY, INNER_RX, INNER_RY
                        )
                        target_x = target_x * 0.35 + recover_x * 0.65
                        target_y = target_y * 0.35 + recover_y * 0.65

                    ai_forward_x = math.cos(bot["angle"])
                    ai_forward_y = math.sin(bot["angle"])
                    to_target_x = target_x - bot["x"]
                    to_target_y = target_y - bot["y"]
                    target_len = max(1.0, math.hypot(to_target_x, to_target_y))
                    to_target_x /= target_len
                    to_target_y /= target_len
                    cross = ai_forward_x * to_target_y - ai_forward_y * to_target_x
                    dot = max(-1.0, min(1.0, ai_forward_x * to_target_x + ai_forward_y * to_target_y))
                    turn_error = math.acos(dot)
                    ai_steer_gain = 4.2 if ai_risky_zone else 3.4
                    ai_steer = max(-1.0, min(1.0, cross * ai_steer_gain))
                    ts = max(105.0, 210.0 - turn_error * 95.0)
                    if ai_risky_zone:
                        ts = min(ts, 130.0)
                    ai_forward_cap = difficulty_ai_forward_cap(difficulty_level)
                    target_speed = (
                        min(ts * AI_SPEED_MULT, ai_forward_cap) * CAR_SPEED_SCALE
                    )
                    ai_throttle = 1.0 if ai_speed_now < target_speed else 0.20
                    ai_brake = (
                        0.45 if ai_speed_now > target_speed + 22 * CAR_SPEED_SCALE else 0.0
                    )

                    ai_state = update_vehicle(
                        bot["x"],
                        bot["y"],
                        bot["angle"],
                        bot["vel_x"],
                        bot["vel_y"],
                        ai_throttle,
                        ai_brake,
                        ai_steer,
                        dt,
                        base_grip=10.5,
                        drift_grip=4.8,
                        forward_cap_high=ai_forward_cap,
                    )
                    bot["x"] = ai_state["x"]
                    bot["y"] = ai_state["y"]
                    bot["angle"] = ai_state["angle"]
                    bot["vel_x"] = ai_state["vel_x"]
                    bot["vel_y"] = ai_state["vel_y"]
                    bot["forward_speed"] = ai_state["forward_speed"]
                    bot["side_speed"] = ai_state["side_speed"]
                    bot["forward_x_now"] = ai_state["forward_x"]
                    bot["forward_y_now"] = ai_state["forward_y"]
                    bot["right_x_now"] = ai_state["right_x"]
                    bot["right_y_now"] = ai_state["right_y"]

                    if car_off_track(
                        bot["x"],
                        bot["y"],
                        CAR_HITBOX_RADIUS,
                        TRACK_CX,
                        TRACK_CY,
                        OUTER_RX,
                        OUTER_RY,
                        INNER_RX,
                        INNER_RY,
                    ):
                        _slow_ai = slow_zone_velocity_mult(OFF_TRACK_SLOW_AI)
                        bot["vel_x"] *= _slow_ai
                        bot["vel_y"] *= _slow_ai

            car_sep = 2 * CAR_HITBOX_RADIUS
            for ci in range(4):
                for bot in ai_bots:
                    car_x, car_y, vel_x, vel_y, car_angle, bot["x"], bot["y"], bot["vel_x"], bot["vel_y"], bot[
                        "angle"
                    ], hit_spark = resolve_two_car_circles(
                        car_x,
                        car_y,
                        vel_x,
                        vel_y,
                        car_angle,
                        bot["x"],
                        bot["y"],
                        bot["vel_x"],
                        bot["vel_y"],
                        bot["angle"],
                        car_sep,
                    )
                    if hit_spark is not None and ci <= 1:
                        mx, my, snx, sny, closing_h, ovh = hit_spark
                        spawn_collision_sparks(particles, mx, my, snx, sny, closing_h, ovh)
                        spawn_collision_dirt(particles, mx, my, snx, sny, closing_h, ovh)
                nb = len(ai_bots)
                for ii in range(nb):
                    for jj in range(ii + 1, nb):
                        bi = ai_bots[ii]
                        bj = ai_bots[jj]
                        bi["x"], bi["y"], bi["vel_x"], bi["vel_y"], bi["angle"], bj["x"], bj["y"], bj["vel_x"], bj[
                            "vel_y"
                        ], bj["angle"], pair_spark = resolve_two_car_circles(
                            bi["x"],
                            bi["y"],
                            bi["vel_x"],
                            bi["vel_y"],
                            bi["angle"],
                            bj["x"],
                            bj["y"],
                            bj["vel_x"],
                            bj["vel_y"],
                            bj["angle"],
                            car_sep,
                        )
                        if pair_spark is not None and ci <= 1:
                            mx, my, snx, sny, closing_h, ovh = pair_spark
                            spawn_collision_sparks(particles, mx, my, snx, sny, closing_h, ovh)
                            spawn_collision_dirt(particles, mx, my, snx, sny, closing_h, ovh)

            if not (multiplayer_race and mp.is_client()):
                pfx = math.cos(car_angle)
                pfy = math.sin(car_angle)
                prx, pry = -pfy, pfx
                forward_speed = vel_x * pfx + vel_y * pfy
                side_speed = vel_x * prx + vel_y * pry

            for bot in ai_bots:
                bfx = math.cos(bot["angle"])
                bfy = math.sin(bot["angle"])
                brx, bry = -bfy, bfx
                bot["forward_speed"] = bot["vel_x"] * bfx + bot["vel_y"] * bfy
                bot["side_speed"] = bot["vel_x"] * brx + bot["vel_y"] * bry
                spawn_drift_particles(
                    particles,
                    bot["x"],
                    bot["y"],
                    bot["forward_x_now"],
                    bot["forward_y_now"],
                    bot["right_x_now"],
                    bot["right_y_now"],
                    bot["vel_x"],
                    bot["vel_y"],
                    bot["side_speed"],
                    bot["forward_speed"],
                )

            if not (multiplayer_race and mp.is_client()):
                spawn_drift_particles(
                    particles,
                    car_x,
                    car_y,
                    forward_x,
                    forward_y,
                    right_x,
                    right_y,
                    vel_x,
                    vel_y,
                    side_speed,
                    forward_speed,
                )

            if multiplayer_race and mp.is_host():
                mp.broadcast_state(
                    {
                        "x": car_x,
                        "y": car_y,
                        "angle": car_angle,
                        "vx": vel_x,
                        "vy": vel_y,
                        "lap": lap,
                        "color": player_car_color,
                        "chassis_id": selected_chassis_id,
                        "decal_style": player_decal_style,
                        "decal_color": player_decal_color,
                    },
                    ai_bots,
                )

            # Player checkpoints/laps (host / solo only).
            if multiplayer_race and mp.is_client():
                crossed_line_last_frame = False
            else:
                on_start_line = circle_overlaps_rect(car_x, car_y, CAR_HITBOX_RADIUS, start_line)
                crossed_start_forward = (
                    on_start_line and not crossed_line_last_frame and forward_speed > 20 * CAR_SPEED_SCALE
                )
                if next_checkpoint_index == 0:
                    if crossed_start_forward:
                        if ready_to_finish_lap:
                            lap += 1
                            ready_to_finish_lap = False
                        next_checkpoint_index = 1
                else:
                    cp_x, cp_y = checkpoints[next_checkpoint_index]
                    if math.dist((car_x, car_y), (cp_x, cp_y)) < checkpoint_radius + CAR_HITBOX_RADIUS:
                        next_checkpoint_index += 1
                        if next_checkpoint_index >= len(checkpoints):
                            next_checkpoint_index = 0
                            ready_to_finish_lap = True
                crossed_line_last_frame = on_start_line

            # AI checkpoints/laps (each opponent tracks independently).
            if not (multiplayer_race and mp.is_client()):
                for bot in ai_bots:
                    ai_on_start_line = circle_overlaps_rect(bot["x"], bot["y"], CAR_HITBOX_RADIUS, start_line)
                    ai_crossed_start_forward = (
                        ai_on_start_line
                        and not bot["crossed_line_last_frame"]
                        and bot["forward_speed"] > 20 * CAR_SPEED_SCALE
                    )
                    nci = bot["next_checkpoint_index"]
                    if nci == 0:
                        if ai_crossed_start_forward:
                            if bot["ready_to_finish_lap"]:
                                bot["lap"] += 1
                                bot["ready_to_finish_lap"] = False
                            bot["next_checkpoint_index"] = 1
                    else:
                        ai_cp_x, ai_cp_y = checkpoints[nci]
                        if math.dist((bot["x"], bot["y"]), (ai_cp_x, ai_cp_y)) < checkpoint_radius + CAR_HITBOX_RADIUS:
                            nci += 1
                            if nci >= len(checkpoints):
                                bot["next_checkpoint_index"] = 0
                                bot["ready_to_finish_lap"] = True
                            else:
                                bot["next_checkpoint_index"] = nci
                    bot["crossed_line_last_frame"] = ai_on_start_line

            ai_best_lap = max(b["lap"] for b in ai_bots)
            if not (multiplayer_race and mp.is_client()) and lap >= LAPS_TO_WIN:
                winner_text = "Player wins!"
                game_state = "result"
                money += RACE_PRIZE_MONEY
            elif not (multiplayer_race and mp.is_client()) and ai_best_lap >= LAPS_TO_WIN:
                winner_text = "Opponents win!"
                game_state = "result"
                money += RACE_PRIZE_MONEY

        # Update particles in race/result states.
        if game_state in ("race", "result"):
            i = len(particles) - 1
            while i >= 0:
                p = particles[i]
                p["life"] -= dt
                if p["life"] <= 0:
                    particles.pop(i)
                else:
                    p["x"] += p["vx"] * dt
                    p["y"] += p["vy"] * dt
                    p["vx"] *= 0.94
                    p["vy"] *= 0.94
                i -= 1

        # Camera: follow player in race/result; center track in lobby/tune. Clamp to track margins.
        pad_cam = 72
        cam_wl = TRACK_CX - OUTER_RX - pad_cam
        cam_wr = TRACK_CX + OUTER_RX + pad_cam
        cam_wt = TRACK_CY - OUTER_RY - pad_cam
        cam_wb = TRACK_CY + OUTER_RY + pad_cam
        view_w = WIDTH / CAMERA_ZOOM
        view_h = HEIGHT / CAMERA_ZOOM
        if game_state in ("race", "result"):
            if multiplayer_race and mp.is_client() and mp.client_slot() is not None:
                slot = mp.client_slot()
                if 0 <= slot < len(ai_bots):
                    cam_origin_x = ai_bots[slot]["x"] - view_w * 0.5
                    cam_origin_y = ai_bots[slot]["y"] - view_h * 0.5
                else:
                    cam_origin_x = car_x - view_w * 0.5
                    cam_origin_y = car_y - view_h * 0.5
            else:
                cam_origin_x = car_x - view_w * 0.5
                cam_origin_y = car_y - view_h * 0.5
        else:
            cam_origin_x = TRACK_CX - view_w * 0.5
            cam_origin_y = TRACK_CY - view_h * 0.5
        cam_origin_x = max(cam_wl, min(cam_wr - view_w, cam_origin_x))
        cam_origin_y = max(cam_wt, min(cam_wb - view_h, cam_origin_y))

        # Draw background at reduced resolution, then scale up for pixel look.
        outer_bg = pygame.Rect(
            int(outer.x / BG_PIXEL_SCALE),
            int(outer.y / BG_PIXEL_SCALE),
            max(1, int(outer.width / BG_PIXEL_SCALE)),
            max(1, int(outer.height / BG_PIXEL_SCALE)),
        )
        inner_bg = pygame.Rect(
            int(inner.x / BG_PIXEL_SCALE),
            int(inner.y / BG_PIXEL_SCALE),
            max(1, int(inner.width / BG_PIXEL_SCALE)),
            max(1, int(inner.height / BG_PIXEL_SCALE)),
        )
        start_line_bg = pygame.Rect(
            int(start_line.x / BG_PIXEL_SCALE),
            int(start_line.y / BG_PIXEL_SCALE),
            max(1, int(start_line.width / BG_PIXEL_SCALE)),
            max(1, int(start_line.height / BG_PIXEL_SCALE)),
        )
        outer_bg_outline = outer_bg.inflate(6, 6)
        outer_bg_outline_dark = outer_bg.inflate(8, 8)

        bg_surface.fill(GRASS)
        for speck in bg_specks:
            bg_surface.set_at((speck["x"], speck["y"]), speck["color"])
        pygame.draw.ellipse(bg_surface, DIRT_TRACK, outer_bg)
        pygame.draw.ellipse(bg_surface, TRACK_RIM_DARK, outer_bg_outline_dark, width=1)
        pygame.draw.ellipse(bg_surface, TRACK_RIM_LIGHT, outer_bg_outline, width=1)
        pygame.draw.ellipse(bg_surface, DIRT_INFIELD, inner_bg)
        pygame.draw.rect(bg_surface, START_LINE_NIGHT, start_line_bg)
        screen.fill(GRASS)
        scaled_bg = pygame.transform.scale(bg_surface, (WIDTH, HEIGHT))
        zw = int(round(WIDTH * CAMERA_ZOOM))
        zh = int(round(HEIGHT * CAMERA_ZOOM))
        zoomed_bg = pygame.transform.scale(scaled_bg, (zw, zh))
        screen.blit(
            zoomed_bg,
            (-int(round(cam_origin_x * CAMERA_ZOOM)), -int(round(cam_origin_y * CAMERA_ZOOM))),
        )

        for p in particles:
            sx = (p["x"] - cam_origin_x) * CAMERA_ZOOM
            sy = (p["y"] - cam_origin_y) * CAMERA_ZOOM
            draw_size = max(
                1, int(round(p["size"] * PARTICLE_SIZE_SCALE * CAMERA_ZOOM))
            )
            pygame.draw.rect(screen, p["color"], (sx, sy, draw_size, draw_size))

        # Checkpoint markers.
        cp_lines = max(1, int(round(2 * CAMERA_ZOOM)))
        cp_rad = int(round(checkpoint_radius * CAMERA_ZOOM))
        for i, (cp_x, cp_y) in enumerate(checkpoints):
            if game_state in ("race", "result"):
                color = (
                    (215, 222, 245) if i == next_checkpoint_index else (95, 102, 118)
                )
            else:
                color = (72, 78, 90)
            pygame.draw.circle(
                screen,
                color,
                (
                    int((cp_x - cam_origin_x) * CAMERA_ZOOM),
                    int((cp_y - cam_origin_y) * CAMERA_ZOOM),
                ),
                cp_rad,
                cp_lines,
            )

        for bot in ai_bots:
            spd = math.hypot(bot["vel_x"], bot["vel_y"]) if game_state == "race" else 0.0
            sx, sy = track_speed_draw_jitter(spd, bot["x"], bot["y"])
            draw_car(
                screen,
                (bot["x"] + sx - cam_origin_x) * CAMERA_ZOOM,
                (bot["y"] + sy - cam_origin_y) * CAMERA_ZOOM,
                bot["angle"],
                bot["color"],
                CAMERA_ZOOM,
                bot.get("decal_style", 1),
                bot.get("decal_color"),
                bot.get("chassis_id", 0),
            )
        if multiplayer_race and mp.is_client():
            if sync_host_car:
                hc = sync_host_car
                hs = math.hypot(hc.get("vx", 0), hc.get("vy", 0))
                hx, hy = track_speed_draw_jitter(hs, hc["x"], hc["y"])
                draw_car(
                    screen,
                    (hc["x"] + hx - cam_origin_x) * CAMERA_ZOOM,
                    (hc["y"] + hy - cam_origin_y) * CAMERA_ZOOM,
                    hc["angle"],
                    tuple(hc.get("color", player_car_color)),
                    CAMERA_ZOOM,
                    hc.get("decal_style", 0),
                    tuple(hc.get("decal_color", player_decal_color)),
                    hc.get("chassis_id", 0),
                )
        else:
            ps = math.hypot(vel_x, vel_y) if game_state == "race" else 0.0
            px, py = track_speed_draw_jitter(ps, car_x, car_y)
            draw_car(
                screen,
                (car_x + px - cam_origin_x) * CAMERA_ZOOM,
                (car_y + py - cam_origin_y) * CAMERA_ZOOM,
                car_angle,
                player_car_color,
                CAMERA_ZOOM,
                player_decal_style,
                player_decal_color,
                selected_chassis_id,
            )

        if game_state != "auth":
            speed_text = font.render(f"Speed: {max(0, forward_speed):.1f}", True, WHITE)
            lap_text = font.render(f"Lap: {lap}/{LAPS_TO_WIN}", True, WHITE)
            checkpoint_text = font.render(f"Checkpoint: {next_checkpoint_index + 1}/4", True, WHITE)
            best_ai_lap = max(b["lap"] for b in ai_bots)
            leader_fwd = max(max(0.0, b["forward_speed"]) for b in ai_bots)
            opponent_text = font.render(
                f"Opponents: {len(ai_bots)}   Best lap: {best_ai_lap}/{LAPS_TO_WIN}", True, WHITE
            )
            opponent_speed_text = small_font.render(f"Fastest opponent speed: {leader_fwd:.1f}", True, WHITE)
            _, _, _ch_cap_hud = chassis_physics_modifiers(selected_chassis_id)
            _player_cap_hud = (
                PLAYER_FORWARD_CAP_BASE + speed_upgrade * SPEED_UPGRADE_FORWARD_PER_TIER + _ch_cap_hud
            )
            cap_note = (
                small_font.render(f"Your tune cap: {_player_cap_hud:.0f}", True, WHITE)
                if speed_upgrade > 0 or _ch_cap_hud > 0
                else None
            )
            help_text = font.render("WASD drive · R reset race · Esc quit", True, WHITE)
            screen.blit(speed_text, (15, 10))
            screen.blit(lap_text, (15, 40))
            screen.blit(checkpoint_text, (15, 70))
            screen.blit(help_text, (15, 100))
            if cap_note is not None:
                screen.blit(cap_note, (15, 128))
            screen.blit(opponent_text, (WIDTH - 340, 10))
            screen.blit(opponent_speed_text, (WIDTH - 340, 40))
        if game_state == "race":
            pygame.draw.rect(screen, (72, 48, 52), leave_race_rect, border_radius=8)
            pygame.draw.rect(screen, (255, 200, 200), leave_race_rect, width=2, border_radius=8)
            leave_race_txt = small_font.render("Leave Race", True, WHITE)
            screen.blit(
                leave_race_txt,
                (
                    leave_race_rect.centerx - leave_race_txt.get_width() // 2,
                    leave_race_rect.centery - 10,
                ),
            )

        if game_state == "auth":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 200))
            screen.blit(overlay, (0, 0))

            def draw_auth_tab(rect, label, active):
                bg = (62, 78, 98) if active else (44, 48, 56)
                pygame.draw.rect(screen, bg, rect, border_radius=6)
                pygame.draw.rect(screen, YELLOW if active else LIGHT_GRAY, rect, width=2, border_radius=6)
                t = small_font.render(label, True, WHITE)
                screen.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - 10))

            def draw_auth_field(rect, label, value, focused, secret=False):
                pygame.draw.rect(screen, (36, 40, 48), rect, border_radius=8)
                pygame.draw.rect(screen, YELLOW if focused else LIGHT_GRAY, rect, width=2, border_radius=8)
                lbl = small_font.render(label, True, LIGHT_GRAY)
                screen.blit(lbl, (rect.left, rect.top - 20))
                shown = auth_mask_secret(value) if secret else (value if value else "")
                placeholder = "(type here)" if not shown else ""
                val_color = (120, 125, 135) if not value else WHITE
                val_t = font.render(shown or placeholder, True, val_color)
                screen.blit(val_t, (rect.left + 12, rect.centery - val_t.get_height() // 2))

            auth_title = title_font.render("Retro Rally", True, WHITE)
            auth_head = font.render("Login or Sign up", True, WHITE)
            screen.blit(auth_title, (WIDTH // 2 - auth_title.get_width() // 2, HEIGHT // 2 - 248))
            screen.blit(auth_head, (WIDTH // 2 - auth_head.get_width() // 2, HEIGHT // 2 - 208))
            draw_auth_tab(auth_tab_login_rect, "Login", auth_mode == "login")
            draw_auth_tab(auth_tab_signup_rect, "Sign up", auth_mode == "signup")
            draw_auth_field(auth_user_field, "Username", auth_username, auth_focus == "username")
            draw_auth_field(auth_pass_field, "Passcode", auth_passcode, auth_focus == "passcode", secret=True)
            if auth_mode == "signup":
                draw_auth_field(
                    auth_confirm_field, "Confirm passcode", auth_confirm, auth_focus == "confirm", secret=True
                )
            submit_lbl = "Log in" if auth_mode == "login" else "Create account"
            pygame.draw.rect(screen, (50, 90, 58), auth_submit_rect, border_radius=8)
            pygame.draw.rect(screen, WHITE, auth_submit_rect, width=2, border_radius=8)
            submit_t = font.render(submit_lbl, True, WHITE)
            screen.blit(
                submit_t,
                (auth_submit_rect.centerx - submit_t.get_width() // 2, auth_submit_rect.centery - 12),
            )
            if auth_message and game_state == "auth":
                msg_col = AUTH_ERROR_COLOR if auth_message_is_error else AUTH_OK_COLOR
                msg_t = small_font.render(auth_message, True, msg_col)
                screen.blit(msg_t, (WIDTH // 2 - msg_t.get_width() // 2, auth_submit_rect.bottom + 14))
            auth_hint = small_font.render("Tab switch field · Enter submit · Esc quit", True, LIGHT_GRAY)
            screen.blit(auth_hint, (WIDTH // 2 - auth_hint.get_width() // 2, HEIGHT - 36))

        if game_state == "lobby":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 140))
            screen.blit(overlay, (0, 0))

            def draw_lobby_tab(rect, label, active):
                bg = (62, 78, 98) if active else (44, 48, 56)
                pygame.draw.rect(screen, bg, rect, border_radius=6)
                pygame.draw.rect(screen, YELLOW if active else LIGHT_GRAY, rect, width=2, border_radius=6)
                t = small_font.render(label, True, WHITE)
                screen.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - 10))

            draw_lobby_tab(lobby_tab_home_rect, "Home", lobby_tab == "home")
            draw_lobby_tab(lobby_tab_cars_rect, "Cars", lobby_tab == "cars")
            draw_lobby_tab(lobby_tab_multi_rect, "Multiplayer", lobby_tab == "multiplayer")

            if lobby_tab == "home":
                title_text = title_font.render("Retro Rally", True, WHITE)
                subtitle_text = small_font.render("First to 8 laps wins", True, WHITE)
                welcome_line = small_font.render(f"Player: {logged_in_user}", True, YELLOW)
                cash_line = small_font.render(f"Purse: ${money}", True, YELLOW)
                button_text = font.render("Race", True, WHITE)
                tune_btn_text = font.render("Tune", True, WHITE)
                cust_btn_text = font.render("Customize", True, WHITE)
                sel = CAR_CHASSIS[selected_chassis_id]
                car_pick = small_font.render(f"Car: {sel['name']}", True, LIGHT_GRAY)
                hint_text = small_font.render(
                    "Race: Enter / Space · Home / Cars / Multiplayer tabs", True, WHITE
                )
                screen.blit(title_text, (WIDTH // 2 - title_text.get_width() // 2, HEIGHT // 2 - 172))
                screen.blit(subtitle_text, (WIDTH // 2 - subtitle_text.get_width() // 2, HEIGHT // 2 - 118))
                screen.blit(welcome_line, (WIDTH // 2 - welcome_line.get_width() // 2, HEIGHT // 2 - 88))
                screen.blit(cash_line, (WIDTH // 2 - cash_line.get_width() // 2, HEIGHT // 2 - 62))
                screen.blit(car_pick, (WIDTH // 2 - car_pick.get_width() // 2, HEIGHT // 2 - 36))
                pygame.draw.rect(screen, (50, 50, 50), race_button, border_radius=8)
                pygame.draw.rect(screen, WHITE, race_button, width=2, border_radius=8)
                screen.blit(
                    button_text, (race_button.centerx - button_text.get_width() // 2, race_button.centery - 10)
                )
                pygame.draw.rect(screen, (42, 52, 72), tune_button, border_radius=8)
                pygame.draw.rect(screen, LIGHT_GRAY, tune_button, width=2, border_radius=8)
                screen.blit(
                    tune_btn_text, (tune_button.centerx - tune_btn_text.get_width() // 2, tune_button.centery - 10)
                )
                pygame.draw.rect(screen, (52, 62, 82), customize_button, border_radius=8)
                pygame.draw.rect(screen, LIGHT_GRAY, customize_button, width=2, border_radius=8)
                screen.blit(
                    cust_btn_text,
                    (customize_button.centerx - cust_btn_text.get_width() // 2, customize_button.centery - 10),
                )
                screen.blit(hint_text, (WIDTH // 2 - hint_text.get_width() // 2, HEIGHT // 2 + 132))
            elif lobby_tab == "cars":
                cars_title = title_font.render("Choose Your Car", True, WHITE)
                cars_intro = small_font.render(
                    "Click to select · Paid cars unlock with coins from race purse", True, LIGHT_GRAY
                )
                screen.blit(cars_title, (WIDTH // 2 - cars_title.get_width() // 2, HEIGHT // 2 - 178))
                screen.blit(cars_intro, (WIDTH // 2 - cars_intro.get_width() // 2, HEIGHT // 2 - 148))
                for ci, crect in enumerate(car_choice_card_rects()):
                    ch = CAR_CHASSIS[ci]
                    active = selected_chassis_id == ci
                    locked = not chassis_is_unlocked(ci, unlocked_chassis)
                    cost = chassis_unlock_cost(ci)
                    bg = (56, 68, 88) if active else (40, 44, 52)
                    if locked:
                        bg = (34, 36, 42)
                    pygame.draw.rect(screen, bg, crect, border_radius=10)
                    pygame.draw.rect(screen, YELLOW if active else LIGHT_GRAY, crect, width=2, border_radius=10)
                    preview_zoom = 2.15 if ci == NUM_CAR_CHASSIS - 1 else 2.35
                    draw_car(
                        screen,
                        crect.centerx,
                        crect.centery - 22,
                        -math.pi / 2,
                        ch["preview"],
                        preview_zoom,
                        0,
                        None,
                        ci,
                    )
                    name_t = font.render(ch["name"], True, WHITE)
                    sp = ch.get("speed", 70)
                    stat_t = small_font.render(
                        f"Grip {ch['grip']}   Accel {ch['accel']}   Speed {sp}",
                        True,
                        YELLOW if active else LIGHT_GRAY,
                    )
                    screen.blit(name_t, (crect.centerx - name_t.get_width() // 2, crect.bottom - 56))
                    screen.blit(stat_t, (crect.centerx - stat_t.get_width() // 2, crect.bottom - 36))
                    if locked:
                        afford = money >= cost
                        price_t = small_font.render(
                            f"${cost:,} — click to buy" if afford else f"${cost:,} — need ${cost - money:,} more",
                            True,
                            YELLOW if afford else (255, 140, 140),
                        )
                        screen.blit(price_t, (crect.centerx - price_t.get_width() // 2, crect.bottom - 16))
                    elif cost > 0:
                        own_t = small_font.render("Owned", True, (120, 220, 140))
                        screen.blit(own_t, (crect.centerx - own_t.get_width() // 2, crect.bottom - 16))
                cars_hint = small_font.render("Home tab to race · Esc back to Home", True, WHITE)
                screen.blit(cars_hint, (WIDTH // 2 - cars_hint.get_width() // 2, HEIGHT // 2 + 228))
            else:
                mp_join_rows.clear()
                mp_title = title_font.render("Multiplayer", True, WHITE)
                mp_sub = small_font.render(
                    "LAN / same Wi‑Fi: host a race, Seek notifies online players, they replace AI slots",
                    True,
                    LIGHT_GRAY,
                )
                screen.blit(mp_title, (WIDTH // 2 - mp_title.get_width() // 2, HEIGHT // 2 - 178))
                screen.blit(mp_sub, (WIDTH // 2 - mp_sub.get_width() // 2, HEIGHT // 2 - 148))
                pygame.draw.rect(screen, (48, 72, 52), mp_host_btn, border_radius=8)
                pygame.draw.rect(screen, WHITE, mp_host_btn, width=2, border_radius=8)
                screen.blit(
                    font.render("Host race", True, WHITE),
                    (mp_host_btn.centerx - 40, mp_host_btn.centery - 10),
                )
                pygame.draw.rect(screen, (52, 62, 88), mp_seek_btn, border_radius=8)
                pygame.draw.rect(screen, WHITE, mp_seek_btn, width=2, border_radius=8)
                screen.blit(
                    font.render("Seek players", True, WHITE),
                    (mp_seek_btn.centerx - 52, mp_seek_btn.centery - 10),
                )
                if mp.is_host():
                    pygame.draw.rect(screen, (72, 48, 52), mp_stop_btn, border_radius=8)
                    pygame.draw.rect(screen, WHITE, mp_stop_btn, width=2, border_radius=8)
                    screen.blit(
                        small_font.render("Stop hosting", True, WHITE),
                        (mp_stop_btn.centerx - 48, mp_stop_btn.centery - 10),
                    )
                    pygame.draw.rect(screen, (50, 90, 58), mp_start_btn, border_radius=8)
                    pygame.draw.rect(screen, WHITE, mp_start_btn, width=2, border_radius=8)
                    screen.blit(
                        font.render("Start race", True, WHITE),
                        (mp_start_btn.centerx - 44, mp_start_btn.centery - 10),
                    )
                    roster = mp.roster()
                    rh = small_font.render(
                        f"Lobby — {len(roster)} joined (max 8 replace AI):", True, YELLOW
                    )
                    screen.blit(rh, (WIDTH // 2 - rh.get_width() // 2, HEIGHT // 2 - 88))
                    for ri, ent in enumerate(roster[:8]):
                        line = small_font.render(
                            f"  {ent.get('user', 'Racer')} · {CAR_CHASSIS[ent.get('chassis_id', 0)]['name']}",
                            True,
                            WHITE,
                        )
                        screen.blit(line, (WIDTH // 2 - 200, HEIGHT // 2 - 64 + ri * 20))
                elif mp.is_client():
                    cs = mp.client_slot()
                    st = small_font.render(
                        f"Connected — waiting for host to start (your slot {cs})" if cs is not None else "Connecting…",
                        True,
                        YELLOW,
                    )
                    screen.blit(st, (WIDTH // 2 - st.get_width() // 2, HEIGHT // 2 + 88))
                online = mp.online_players()
                olab = small_font.render("Online players (same network):", True, YELLOW)
                screen.blit(olab, (80, HEIGHT // 2 - 20))
                for oi, pl in enumerate(online[:6]):
                    row = pygame.Rect(80, HEIGHT // 2 + 4 + oi * 24, WIDTH - 520, 22)
                    txt = small_font.render(
                        f"{pl.get('user', '?')} · {CAR_CHASSIS[pl.get('chassis_id', 0)]['name']}",
                        True,
                        WHITE,
                    )
                    screen.blit(txt, (row.left + 6, row.top + 2))
                ltitle = small_font.render("Open race lobbies (click to join):", True, YELLOW)
                screen.blit(ltitle, (WIDTH - 380, HEIGHT // 2 - 20))
                for li, lb in enumerate(mp.open_lobbies()[:5]):
                    row = pygame.Rect(WIDTH - 380, HEIGHT // 2 + 4 + li * 26, 300, 24)
                    pygame.draw.rect(screen, (40, 48, 58), row, border_radius=5)
                    pygame.draw.rect(screen, LIGHT_GRAY, row, width=1, border_radius=5)
                    lt = small_font.render(
                        f"{lb.get('host', '?')} · {lb.get('racers', 1)} racers · {lb.get('slots_open', 0)} slots",
                        True,
                        WHITE,
                    )
                    screen.blit(lt, (row.left + 6, row.top + 4))
                    mp_join_rows.append((row, lb.get("host_ip")))
                if mp_notice and mp_notice_timer > 0:
                    nt = small_font.render(mp_notice, True, AUTH_OK_COLOR)
                    screen.blit(nt, (WIDTH // 2 - nt.get_width() // 2, HEIGHT // 2 + 168))
                mp_hint = small_font.render("Esc → Home · Seek pings invites on your LAN", True, WHITE)
                screen.blit(mp_hint, (WIDTH // 2 - mp_hint.get_width() // 2, HEIGHT // 2 + 228))

        if game_state == "tune":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 175))
            screen.blit(overlay, (0, 0))
            tune_title = title_font.render("Tuning", True, WHITE)
            screen.blit(tune_title, (WIDTH // 2 - tune_title.get_width() // 2, HEIGHT // 2 - 268))
            lvl_intro = small_font.render(
                f"Difficulty sets opponent forward cap (shown); bar buys your upgrades · Your base matches Standard ({PLAYER_FORWARD_CAP_BASE:.0f})",
                True,
                LIGHT_GRAY,
            )
            screen.blit(lvl_intro, (WIDTH // 2 - lvl_intro.get_width() // 2, HEIGHT // 2 - 238))
            for di, drect in enumerate(difficulty_choice_rects):
                lvl = di + 1
                active = difficulty_level == lvl
                bg = (72, 88, 118) if active else (48, 52, 62)
                pygame.draw.rect(screen, bg, drect, border_radius=6)
                pygame.draw.rect(screen, YELLOW if active else LIGHT_GRAY, drect, width=2, border_radius=6)
                cap = difficulty_ai_forward_cap(lvl)
                lab = small_font.render(f"{DIFFICULTY_LABELS[di]} {cap:.0f}", True, WHITE)
                screen.blit(lab, (drect.centerx - lab.get_width() // 2, drect.centery - 10))
            purse_tune = font.render(f"Purse: ${money}", True, YELLOW)
            screen.blit(purse_tune, (WIDTH // 2 - purse_tune.get_width() // 2, HEIGHT // 2 - 148))
            next_cost_val = speed_buy_cost(speed_upgrade)
            can_buy_next = speed_upgrade < SPEED_UPGRADE_MAX and money >= next_cost_val
            next_cost_txt = (
                small_font.render(f"Next tier: ${next_cost_val}", True, WHITE)
                if speed_upgrade < SPEED_UPGRADE_MAX
                else small_font.render("Max speed tier owned", True, LIGHT_GRAY)
            )
            screen.blit(next_cost_txt, (WIDTH // 2 - next_cost_txt.get_width() // 2, HEIGHT // 2 - 118))
            pygame.draw.rect(screen, (48, 48, 48), tune_bar_rect, border_radius=8)
            fill_ratio = speed_upgrade / SPEED_UPGRADE_MAX if SPEED_UPGRADE_MAX else 0.0
            fill_w = max(0, int(round(tune_bar_rect.width * fill_ratio)))
            if fill_w > 0:
                pygame.draw.rect(
                    screen,
                    YELLOW,
                    pygame.Rect(tune_bar_rect.left, tune_bar_rect.top, fill_w, tune_bar_rect.height),
                    border_radius=8,
                )
            pygame.draw.rect(screen, WHITE, tune_bar_rect, width=2, border_radius=8)
            pygame.draw.rect(screen, (58, 58, 58), tune_minus_rect, border_radius=6)
            pygame.draw.rect(screen, WHITE, tune_minus_rect, width=1, border_radius=6)
            plus_bg = (72, 92, 58) if can_buy_next else (38, 38, 38)
            pygame.draw.rect(screen, plus_bg, tune_plus_rect, border_radius=6)
            pygame.draw.rect(
                screen, WHITE if can_buy_next else DARK_GRAY, tune_plus_rect, width=1, border_radius=6
            )
            minus_txt = font.render("−", True, WHITE)
            plus_txt = font.render("+", True, WHITE)
            screen.blit(minus_txt, (tune_minus_rect.centerx - minus_txt.get_width() // 2, tune_minus_rect.centery - 12))
            screen.blit(plus_txt, (tune_plus_rect.centerx - plus_txt.get_width() // 2, tune_plus_rect.centery - 12))
            _yours = PLAYER_FORWARD_CAP_BASE + speed_upgrade * SPEED_UPGRADE_FORWARD_PER_TIER
            _ai_cap = difficulty_ai_forward_cap(difficulty_level)
            stat_line = font.render(
                f"Your tiers +{speed_upgrade} / +{SPEED_UPGRADE_MAX} · Your max {_yours:.0f} · AI max {_ai_cap:.0f}",
                True,
                WHITE,
            )
            screen.blit(stat_line, (WIDTH // 2 - stat_line.get_width() // 2, HEIGHT // 2 - 88))
            hint_tune = small_font.render(
                "Click a difficulty · Bar / − / + cash upgrades (refund on sell) · ←/→ keys · Esc back",
                True,
                WHITE,
            )
            screen.blit(hint_tune, (WIDTH // 2 - hint_tune.get_width() // 2, HEIGHT // 2 + 62))
            pygame.draw.rect(screen, (55, 55, 65), tune_back_rect, border_radius=8)
            pygame.draw.rect(screen, WHITE, tune_back_rect, width=2, border_radius=8)
            back_txt = font.render("Back", True, WHITE)
            screen.blit(back_txt, (tune_back_rect.centerx - back_txt.get_width() // 2, tune_back_rect.centery - 12))

        if game_state == "customize":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 175))
            screen.blit(overlay, (0, 0))
            cust_title = title_font.render("Customization", True, WHITE)
            screen.blit(cust_title, (WIDTH // 2 - cust_title.get_width() // 2, HEIGHT // 2 - 208))

            def draw_cust_tab(rect, label, active):
                bg = (62, 78, 98) if active else (44, 48, 56)
                pygame.draw.rect(screen, bg, rect, border_radius=6)
                pygame.draw.rect(screen, WHITE if active else LIGHT_GRAY, rect, width=2, border_radius=6)
                t = small_font.render(label, True, WHITE)
                screen.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - 10))

            draw_cust_tab(tab_setup_rect, "Setup", cust_tab == "setup")
            draw_cust_tab(tab_paint_rect, "Paint", cust_tab == "paint")
            draw_cust_tab(tab_decal_rect, "Decals", cust_tab == "decals")

            def draw_cust_slider(rect, val, label_y, label_str):
                pygame.draw.rect(screen, (44, 44, 50), rect, border_radius=7)
                fw = max(0, int(round(rect.width * val)))
                if fw > 0:
                    pygame.draw.rect(
                        screen,
                        (110, 155, 215),
                        pygame.Rect(rect.left, rect.top, fw, rect.height),
                        border_radius=7,
                    )
                pygame.draw.rect(screen, WHITE, rect, width=2, border_radius=7)
                kx = rect.left + int(val * rect.width)
                kx = max(rect.left + 8, min(rect.right - 8, kx))
                pygame.draw.circle(screen, WHITE, (kx, rect.centery), 9)
                pygame.draw.circle(screen, (55, 55, 62), (kx, rect.centery), 9, 2)
                lbl = small_font.render(label_str, True, WHITE)
                screen.blit(lbl, (rect.left, label_y))

            if cust_tab == "setup":
                free_txt = small_font.render("All adjustments free — $0", True, YELLOW)
                screen.blit(free_txt, (WIDTH // 2 - free_txt.get_width() // 2, HEIGHT // 2 - 174))
                draw_cust_slider(
                    cust_susp_slider,
                    cust_suspension,
                    cust_susp_slider.top - 22,
                    "Suspension — high: more grip / slower accel · low: opposite",
                )
                draw_cust_slider(
                    cust_drift_slider,
                    cust_drift,
                    cust_drift_slider.top - 22,
                    "Drift — high: higher top speed · low: lower top speed",
                )
                hint_cust = small_font.render("Drag sliders · Esc or Back for lobby", True, LIGHT_GRAY)
            elif cust_tab == "paint":
                paint_l1 = small_font.render(
                    "White & black: yours anytime. Other colors: you swap with that opponent.", True, YELLOW
                )
                paint_l2 = small_font.render("Top row: free paints · Bottom: opponent body colors (click to take)", True, LIGHT_GRAY)
                screen.blit(paint_l1, (WIDTH // 2 - paint_l1.get_width() // 2, HEIGHT // 2 - 178))
                screen.blit(paint_l2, (WIDTH // 2 - paint_l2.get_width() // 2, HEIGHT // 2 - 154))
                for srect, scol in paint_swatch_rects():
                    pygame.draw.rect(screen, scol, srect, border_radius=5)
                    pygame.draw.rect(screen, WHITE, srect, width=2, border_radius=5)
                    if scol == player_car_color:
                        hi = srect.inflate(8, 8)
                        pygame.draw.rect(screen, YELLOW, hi, width=2, border_radius=7)
                hint_cust = small_font.render("Click a swatch · Esc or Back for lobby", True, LIGHT_GRAY)
            else:
                d1 = small_font.render("Opponents: random decal style & color on every race reset.", True, LIGHT_GRAY)
                d2 = small_font.render("Yours: pick below (kept until you change them).", True, LIGHT_GRAY)
                screen.blit(d1, (WIDTH // 2 - d1.get_width() // 2, HEIGHT // 2 - 200))
                screen.blit(d2, (WIDTH // 2 - d2.get_width() // 2, HEIGHT // 2 - 178))

                def draw_decal_subtab(rect, label, active):
                    bg = (58, 72, 88) if active else (40, 44, 52)
                    pygame.draw.rect(screen, bg, rect, border_radius=5)
                    pygame.draw.rect(screen, WHITE if active else DARK_GRAY, rect, width=2, border_radius=5)
                    t = small_font.render(label, True, WHITE)
                    screen.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - 10))

                draw_decal_subtab(cust_decal_sub_design_rect, "Design", cust_decal_subtab == "design")
                draw_decal_subtab(cust_decal_sub_color_rect, "Decal color", cust_decal_subtab == "color")

                if cust_decal_subtab == "design":
                    dlab = small_font.render("Layout tabs — click a style", True, YELLOW)
                    screen.blit(dlab, (WIDTH // 2 - dlab.get_width() // 2, HEIGHT // 2 - 124))
                    for srect, sid in decal_style_choice_rects():
                        on = sid == player_decal_style
                        pygame.draw.rect(screen, (48, 56, 68) if not on else (78, 98, 128), srect, border_radius=5)
                        pygame.draw.rect(screen, YELLOW if on else LIGHT_GRAY, srect, width=2, border_radius=5)
                        lab = small_font.render(DECAL_STYLE_LABELS[sid], True, WHITE)
                        screen.blit(lab, (srect.centerx - lab.get_width() // 2, srect.centery - 10))
                else:
                    clab = small_font.render("Decal tint — click a color", True, YELLOW)
                    screen.blit(clab, (WIDTH // 2 - clab.get_width() // 2, HEIGHT // 2 - 124))
                    for srect, scol in decal_palette_swatch_rects():
                        pygame.draw.rect(screen, scol, srect, border_radius=5)
                        pygame.draw.rect(screen, WHITE, srect, width=2, border_radius=5)
                        if scol == player_decal_color:
                            hi = srect.inflate(8, 8)
                            pygame.draw.rect(screen, YELLOW, hi, width=2, border_radius=7)
                cur = small_font.render(
                    f"Current: {DECAL_STYLE_LABELS[player_decal_style]} · RGB {player_decal_color[0]},{player_decal_color[1]},{player_decal_color[2]}",
                    True,
                    LIGHT_GRAY,
                )
                screen.blit(cur, (WIDTH // 2 - cur.get_width() // 2, HEIGHT // 2 + 48))
                hint_cust = small_font.render("Design / Decal color tabs · Esc or Back for lobby", True, LIGHT_GRAY)
            screen.blit(hint_cust, (WIDTH // 2 - hint_cust.get_width() // 2, HEIGHT // 2 + 82))
            pygame.draw.rect(screen, (55, 55, 65), cust_back_rect, border_radius=8)
            pygame.draw.rect(screen, WHITE, cust_back_rect, width=2, border_radius=8)
            back_cust = font.render("Back", True, WHITE)
            screen.blit(back_cust, (cust_back_rect.centerx - back_cust.get_width() // 2, cust_back_rect.centery - 12))

        if game_state == "result":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 120))
            screen.blit(overlay, (0, 0))
            result_text = title_font.render(winner_text, True, WHITE)
            info_text = small_font.render("Press R to rematch or Enter for lobby", True, WHITE)
            purse_gain = small_font.render(f"+${RACE_PRIZE_MONEY} purse — total ${money}", True, YELLOW)
            screen.blit(result_text, (WIDTH // 2 - result_text.get_width() // 2, HEIGHT // 2 - 40))
            screen.blit(info_text, (WIDTH // 2 - info_text.get_width() // 2, HEIGHT // 2 + 16))
            screen.blit(purse_gain, (WIDTH // 2 - purse_gain.get_width() // 2, HEIGHT // 2 + 46))

        pygame.display.flip()

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
