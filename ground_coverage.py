"""
GROUND PLANT COLONY GENERATOR — Blender 4.5
=============================================
Procedurally generates 15 colonies of ground-cover plants (meshes + baked
vertex-color shading) and arranges them across a terrain patch, ready to
export as FBX and import into Unity.

WHY VERTEX COLORS INSTEAD OF SHADER NODES:
FBX export does NOT carry Blender's shader node graph into Unity. So all the
"procedural color/shading" here is baked directly onto the mesh as a vertex
color attribute called "Col" (varied per-leaf and per-plant-instance for
natural variation). In Blender, a simple material reads that attribute so
you see the correct look in the viewport/renders. In Unity:
  - URP/HDRP Shader Graph: add a "Vertex Color" node -> multiply into Base
    Color. The default Lit shader ignores vertex colors, so you need a small
    custom shader (a "Nature/Vegetation" style shader) or Shader Graph node
    for the colors to show up as intended.
  - If you'd rather not set up a vertex-color shader in Unity, you can bake
    each colony to a texture in Blender (Bake > Diffuse, with an unwrapped
    UV) before export — not done here, but flagged as an easy follow-up.

HOW TO USE:
1. Open Blender 4.5 -> Scripting tab -> open this file (or paste it) -> Run.
2. It builds a collection called "GroundPlantColonies" containing 15 mesh
   objects (one per species/colony) + an optional ground plane.
3. File > Export > FBX (or flip EXPORT_FBX = True below and set FBX_PATH).
4. Import the FBX into Unity as usual.

Re-running the script clears and rebuilds the collection, so it's safe to
tweak parameters and re-run repeatedly.
"""

import bpy
import bmesh
import math
import os
import random
from mathutils import Vector, Matrix

# -----------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------
SEED = 7
random.seed(SEED)

TERRAIN_W = 26.0          # meters, X extent
TERRAIN_D = 18.0          # meters, Y extent
GRID_COLS = 5
GRID_ROWS = 3

CREATE_GROUND_PLANE = False
EXPORT_FBX = False
FBX_PATH = "//ground_plant_colonies.fbx"   # used only if EXPORT_FBX = True

COLLECTION_NAME = "GroundPlantColonies"

# -----------------------------------------------------------------------
# SHADER MODE
# -----------------------------------------------------------------------
# 'VERTEX_COLOR'   -> fast, simple. Colors live only as a vertex color
#                     attribute ("Col"). Looks correct in Blender via an
#                     Attribute node. In Unity you need a shader that
#                     reads vertex color (default Lit shader does NOT).
#
# 'NODES_ONLY'     -> builds a real Blender node graph (Noise texture
#                     variegation mixed with the baked-in vertex color,
#                     plus roughness variation). Great for Blender-side
#                     look-dev / renders, but the node graph itself does
#                     NOT survive FBX export -> not Unity-ready by itself.
#
# 'BAKED_TEXTURE'  -> builds the same node graph, then automatically
#                     UV-unwraps each colony (Smart UV Project) and bakes
#                     the result to a PNG per colony, rewiring the
#                     material down to a plain Image Texture -> Base
#                     Color. This is the one that "just works" with
#                     Unity's standard Lit/Standard shader after FBX
#                     export -- no custom shader required on the Unity
#                     side. This is the recommended mode for a clean
#                     export pipeline.
SHADER_MODE = 'BAKED_TEXTURE'   # 'VERTEX_COLOR' | 'NODES_ONLY' | 'BAKED_TEXTURE'

BAKE_IMAGE_SIZE = 1024           # px, per colony texture (try 2048 for hero shots)
# Where baked PNGs are saved. If the .blend has been saved, this resolves
# relative to it ("//textures/"). If not saved yet, falls back to a
# folder in your home directory so baking still works.
TEXTURE_OUTPUT_DIR = "//textures/"

# -----------------------------------------------------------------------
# COLOR PALETTE (linear-ish 0-1 RGB tuples)
# -----------------------------------------------------------------------
def C(r, g, b):
    return (r, g, b)

FERN_SWORD_DARK   = C(0.035, 0.10, 0.03)
FERN_SWORD_LIGHT  = C(0.09, 0.24, 0.07)
FERN_OSTRICH_DARK = C(0.05, 0.13, 0.045)
FERN_OSTRICH_LIGHT= C(0.14, 0.30, 0.09)
FERN_MAIDEN_STEM  = C(0.03, 0.02, 0.02)
FERN_MAIDEN_DARK  = C(0.10, 0.22, 0.09)
FERN_MAIDEN_LIGHT = C(0.24, 0.42, 0.16)

GRASS_FESCUE_DARK  = C(0.16, 0.28, 0.06)
GRASS_FESCUE_LIGHT = C(0.42, 0.55, 0.16)
GRASS_RYE_DARK      = C(0.10, 0.22, 0.06)
GRASS_RYE_LIGHT     = C(0.36, 0.40, 0.14)
SEDGE_DARK          = C(0.04, 0.18, 0.16)
SEDGE_LIGHT         = C(0.14, 0.32, 0.26)

CLOVER_DARK   = C(0.06, 0.22, 0.07)
CLOVER_LIGHT  = C(0.18, 0.38, 0.14)
DAISY_LEAF_DARK  = C(0.05, 0.16, 0.05)
DAISY_LEAF_LIGHT = C(0.16, 0.30, 0.11)
DANDY_LEAF_DARK  = C(0.06, 0.20, 0.05)
DANDY_LEAF_LIGHT = C(0.17, 0.33, 0.09)
SORREL_GREEN_DARK   = C(0.05, 0.18, 0.07)
SORREL_GREEN_LIGHT  = C(0.16, 0.32, 0.14)
SORREL_PURPLE_DARK  = C(0.10, 0.03, 0.10)
SORREL_PURPLE_LIGHT = C(0.24, 0.09, 0.22)
PLANTAIN_DARK  = C(0.045, 0.14, 0.04)
PLANTAIN_LIGHT = C(0.12, 0.24, 0.08)
VIOLET_LEAF_DARK  = C(0.05, 0.17, 0.06)
VIOLET_LEAF_LIGHT = C(0.15, 0.30, 0.12)
BT_DARK  = C(0.08, 0.24, 0.08)
BT_LIGHT = C(0.22, 0.42, 0.18)
THYME_DARK  = C(0.10, 0.20, 0.10)
THYME_LIGHT = C(0.24, 0.34, 0.16)
BUNCHBERRY_DARK  = C(0.04, 0.15, 0.06)
BUNCHBERRY_LIGHT = C(0.13, 0.28, 0.11)

WHITE       = C(0.92, 0.92, 0.88)
CREAM       = C(0.95, 0.90, 0.70)
YELLOW      = C(0.85, 0.65, 0.05)
PINK        = C(0.75, 0.35, 0.45)
PURPLE      = C(0.42, 0.16, 0.55)
STEM_GREEN  = C(0.08, 0.20, 0.06)

# -----------------------------------------------------------------------
# LOW-LEVEL MESH HELPERS
# -----------------------------------------------------------------------
def lerp_color(c0, c1, t):
    t = max(0.0, min(1.0, t))
    return (c0[0] + (c1[0] - c0[0]) * t,
            c0[1] + (c1[1] - c0[1]) * t,
            c0[2] + (c1[2] - c0[2]) * t)


def jitter_color(c, amt=0.05):
    return tuple(max(0.0, min(1.0, ch + random.uniform(-amt, amt))) for ch in c)


def leaf_profile(shape, t):
    """Half-width multiplier along leaf length, t in [0,1] (0=base,1=tip)."""
    if shape == 'lanceolate':
        return math.sin(t * math.pi) ** 0.9
    if shape == 'oval':
        return math.sin(min(t, 1.0) * math.pi) ** 0.6
    if shape == 'heart':
        base = math.sin(min(t * 1.1, 1.0) * math.pi)
        notch = 1.0 if t > 0.12 else (t / 0.12) * 0.6 + 0.4
        return base * notch
    if shape == 'jagged':
        base = math.sin(t * math.pi)
        zig = 1.0 + 0.22 * math.sin(t * 46.0)
        return max(0.0, base * zig)
    if shape == 'round':
        v = 1.0 - (2.0 * t - 1.0) ** 2
        return math.sqrt(max(0.0, v))
    return math.sin(t * math.pi)


def add_shaped_leaf(bm, col_layer, matrix, length, width, shape, c0, c1, segments=7):
    """A single flat leaf/petal/leaflet blade, shaped by `shape`."""
    c0 = jitter_color(c0)
    c1 = jitter_color(c1)
    left, right = [], []
    for i in range(segments + 1):
        t = i / segments
        w = width * leaf_profile(shape, t)
        y = t * length
        bend = math.sin(t * math.pi / 2.0) * length * 0.08
        left.append(bm.verts.new(matrix @ Vector((-w / 2.0 + bend, y, 0.0))))
        right.append(bm.verts.new(matrix @ Vector((w / 2.0 + bend, y, 0.0))))
    for i in range(segments):
        tm = (i + 0.5) / segments
        col = lerp_color(c0, c1, tm)
        try:
            f = bm.faces.new((left[i], right[i], right[i + 1], left[i + 1]))
            for loop in f.loops:
                loop[col_layer] = (col[0], col[1], col[2], 1.0)
        except Exception:
            pass


def add_tapered_blade(bm, col_layer, matrix, length, base_w, tip_w, curve, segments, c0, c1):
    """Thin tapered blade — used for grass blades, fern rachis/stems."""
    c0 = jitter_color(c0, 0.04)
    c1 = jitter_color(c1, 0.04)
    left, right = [], []
    for i in range(segments + 1):
        t = i / segments
        w = base_w * (1 - t) + tip_w * t
        y = t * length
        bend = math.sin(t * math.pi / 2.0) * curve
        left.append(bm.verts.new(matrix @ Vector((-w / 2.0 + bend, y, 0.0))))
        right.append(bm.verts.new(matrix @ Vector((w / 2.0 + bend, y, 0.0))))
    for i in range(segments):
        tm = (i + 0.5) / segments
        col = lerp_color(c0, c1, tm)
        try:
            f = bm.faces.new((left[i], right[i], right[i + 1], left[i + 1]))
            for loop in f.loops:
                loop[col_layer] = (col[0], col[1], col[2], 1.0)
        except Exception:
            pass


def add_flower(bm, col_layer, matrix, petal_count, petal_len, petal_width,
                petal_color, center_color, center_radius=0.006):
    """Builds a flower assuming `matrix`'s local Y axis is the stem's
    up/growth direction (this matches how stems are built below). The
    disc + petals are laid out in the local X-Z plane (perpendicular to
    Y) so the flower faces upward/outward atop the stem instead of lying
    flat against the ground."""
    segs = 8
    verts = []
    for i in range(segs):
        ang = 2 * math.pi * i / segs
        v = Vector((math.cos(ang) * center_radius, 0.003, math.sin(ang) * center_radius))
        verts.append(bm.verts.new(matrix @ v))
    try:
        f = bm.faces.new(verts)
        cc = jitter_color(center_color, 0.03)
        for loop in f.loops:
            loop[col_layer] = (cc[0], cc[1], cc[2], 1.0)
    except Exception:
        pass
    for i in range(petal_count):
        ang = 360.0 * i / petal_count
        # RotY spins the petal around the stem's up axis to its compass
        # position; RotZ(~90) tips a normally-vertical leaf blade down
        # into the horizontal plane, with a few degrees of upward flare
        # so the bloom looks gently open rather than perfectly flat.
        flare = 78 + random.uniform(-6, 6)
        rot = Matrix.Rotation(math.radians(ang), 4, 'Y') @ Matrix.Rotation(math.radians(flare), 4, 'Z')
        pm = matrix @ Matrix.Translation((0, 0.004, 0)) @ rot
        add_shaped_leaf(bm, col_layer, pm, petal_len, petal_width, 'oval', petal_color, petal_color)


def add_rosette(bm, col_layer, matrix, count, leaf_len, leaf_width, shape, c0, c1, spread_deg=360):
    for i in range(count):
        ang = spread_deg / count * i + random.uniform(-15, 15)
        length_j = leaf_len * random.uniform(0.8, 1.15)
        width_j = leaf_width * random.uniform(0.85, 1.15)
        tilt = random.uniform(5, 28)
        rot = Matrix.Rotation(math.radians(ang), 4, 'Z') @ Matrix.Rotation(math.radians(tilt), 4, 'X')
        add_shaped_leaf(bm, col_layer, matrix @ rot, length_j, width_j, shape, c0, c1)


def add_trifoliate(bm, col_layer, matrix, leaflet_len, leaflet_width, shape, c0, c1):
    for ang in (-125, 0, 125):
        rot = Matrix.Rotation(math.radians(ang + random.uniform(-8, 8)), 4, 'Z') \
              @ Matrix.Rotation(math.radians(random.uniform(5, 20)), 4, 'X')
        add_shaped_leaf(bm, col_layer, matrix @ rot, leaflet_len, leaflet_width, shape, c0, c1)


def add_whorl(bm, col_layer, matrix, count, leaf_len, leaf_width, shape, c0, c1):
    """Radiates `count` leaves outward around matrix's local Y axis
    (the stem's up/growth direction), roughly horizontal with a slight
    droop -- used for whorled leaves atop an upright stem (e.g. bunchberry)."""
    for i in range(count):
        ang = 360.0 / count * i + random.uniform(-8, 8)
        droop = random.uniform(8, 22)
        rot = Matrix.Rotation(math.radians(ang), 4, 'Y') @ Matrix.Rotation(math.radians(90 + droop), 4, 'Z')
        add_shaped_leaf(bm, col_layer, matrix @ rot, leaf_len, leaf_width, shape, c0, c1)


def add_grass_tuft(bm, col_layer, matrix, blade_count, min_len, max_len, width,
                    c0, c1, curve_amt, spread_deg=360, min_tilt=5, max_tilt=20):
    for i in range(blade_count):
        ang = random.uniform(0, spread_deg)
        length = random.uniform(min_len, max_len)
        tilt = random.uniform(min_tilt, max_tilt)
        rot = Matrix.Rotation(math.radians(ang), 4, 'Z') @ Matrix.Rotation(math.radians(90 - tilt), 4, 'X')
        add_tapered_blade(bm, col_layer, matrix @ rot, length, width, width * 0.15, curve_amt, 6, c0, c1)


def add_pinnate_frond(bm, col_layer, matrix, frond_length, pairs, leaflet_len, leaflet_width,
                       droop, c_stem0, c_stem1, c_leaf0, c_leaf1):
    add_tapered_blade(bm, col_layer, matrix, frond_length, 0.012, 0.002, frond_length * 0.1, 10, c_stem0, c_stem1)
    for i in range(pairs):
        t = (i + 1) / (pairs + 1)
        y = t * frond_length
        size_mult = math.sin(t * math.pi) ** 0.6
        for side in (-1, 1):
            ang = side * random.uniform(55, 75)
            droop_ang = droop * t * 0.6
            rot = Matrix.Rotation(math.radians(ang), 4, 'Z') @ Matrix.Rotation(math.radians(droop_ang), 4, 'X')
            lm = matrix @ Matrix.Translation((0, y, 0)) @ rot
            add_shaped_leaf(bm, col_layer, lm, leaflet_len * size_mult, leaflet_width * size_mult,
                             'lanceolate', c_leaf0, c_leaf1)


def add_fan_frond(bm, col_layer, matrix, frond_length, nodes, leaflet_len, leaflet_width,
                   c_stem0, c_stem1, c_leaf0, c_leaf1):
    add_tapered_blade(bm, col_layer, matrix, frond_length, 0.006, 0.001, frond_length * 0.25, 10, c_stem0, c_stem1)
    for i in range(nodes):
        t = (i + 1) / (nodes + 1)
        y = t * frond_length
        for ang in (-55, -18, 18, 55):
            rot = Matrix.Rotation(math.radians(ang + random.uniform(-6, 6)), 4, 'Z') \
                  @ Matrix.Rotation(math.radians(25), 4, 'X')
            lm = matrix @ Matrix.Translation((0, y, 0)) @ rot
            add_shaped_leaf(bm, col_layer, lm, leaflet_len, leaflet_width, 'round', c_leaf0, c_leaf1)


# -----------------------------------------------------------------------
# SPECIES BUILDERS — each builds ONE plant instance at the given matrix
# -----------------------------------------------------------------------
def build_sword_fern(bm, col_layer, matrix):
    frond_count = random.randint(4, 7)
    for _ in range(frond_count):
        ang = random.uniform(0, 360)
        tilt = random.uniform(15, 35)
        length = random.uniform(0.35, 0.55)
        rot = Matrix.Rotation(math.radians(ang), 4, 'Z') @ Matrix.Rotation(math.radians(90 - tilt), 4, 'X')
        fm = matrix @ rot
        add_pinnate_frond(bm, col_layer, fm, length, random.randint(10, 14),
                           length * 0.14, length * 0.05, 25,
                           FERN_SWORD_DARK, FERN_SWORD_DARK, FERN_SWORD_DARK, FERN_SWORD_LIGHT)


def build_ostrich_fern(bm, col_layer, matrix):
    frond_count = random.randint(6, 9)
    for _ in range(frond_count):
        ang = random.uniform(0, 360)
        tilt = random.uniform(3, 14)  # upright shuttlecock shape
        length = random.uniform(0.55, 0.85)
        rot = Matrix.Rotation(math.radians(ang), 4, 'Z') @ Matrix.Rotation(math.radians(90 - tilt), 4, 'X')
        fm = matrix @ rot
        add_pinnate_frond(bm, col_layer, fm, length, random.randint(14, 20),
                           length * 0.12, length * 0.045, 15,
                           FERN_OSTRICH_DARK, FERN_OSTRICH_DARK, FERN_OSTRICH_DARK, FERN_OSTRICH_LIGHT)


def build_maidenhair_fern(bm, col_layer, matrix):
    frond_count = random.randint(5, 8)
    for _ in range(frond_count):
        ang = random.uniform(0, 360)
        tilt = random.uniform(20, 45)
        length = random.uniform(0.18, 0.28)
        rot = Matrix.Rotation(math.radians(ang), 4, 'Z') @ Matrix.Rotation(math.radians(90 - tilt), 4, 'X')
        fm = matrix @ rot
        add_fan_frond(bm, col_layer, fm, length, random.randint(5, 7),
                       length * 0.22, length * 0.10,
                       FERN_MAIDEN_STEM, FERN_MAIDEN_STEM, FERN_MAIDEN_DARK, FERN_MAIDEN_LIGHT)


def build_fescue(bm, col_layer, matrix):
    add_grass_tuft(bm, col_layer, matrix, random.randint(22, 32), 0.15, 0.28, 0.004,
                   GRASS_FESCUE_DARK, GRASS_FESCUE_LIGHT, 0.05, min_tilt=5, max_tilt=18)


def build_wild_rye(bm, col_layer, matrix):
    add_grass_tuft(bm, col_layer, matrix, random.randint(12, 18), 0.30, 0.50, 0.006,
                   GRASS_RYE_DARK, GRASS_RYE_LIGHT, 0.13, min_tilt=10, max_tilt=30)


def build_sedge(bm, col_layer, matrix):
    add_grass_tuft(bm, col_layer, matrix, random.randint(28, 42), 0.18, 0.30, 0.0035,
                   SEDGE_DARK, SEDGE_LIGHT, 0.02, min_tilt=3, max_tilt=12)


def build_clover(bm, col_layer, matrix):
    clusters = random.randint(4, 7)
    for _ in range(clusters):
        offset = Vector((random.uniform(-0.06, 0.06), random.uniform(-0.06, 0.06), 0))
        m = matrix @ Matrix.Translation(offset) @ Matrix.Rotation(math.radians(random.uniform(0, 360)), 4, 'Z')
        add_trifoliate(bm, col_layer, m, 0.025, 0.018, 'heart', CLOVER_DARK, CLOVER_LIGHT)
        if random.random() < 0.25:
            ang = random.uniform(0, 360)
            h = random.uniform(0.03, 0.05)
            rot = Matrix.Rotation(math.radians(ang), 4, 'Z') @ Matrix.Rotation(math.radians(90 - random.uniform(0, 8)), 4, 'X')
            sm = m @ rot
            add_tapered_blade(bm, col_layer, sm, h, 0.002, 0.001, 0.004, 3, STEM_GREEN, STEM_GREEN)
            fm = sm @ Matrix.Translation((0, h, 0))
            add_flower(bm, col_layer, fm, 8, 0.012, 0.004, WHITE, YELLOW, 0.004)


def build_daisy(bm, col_layer, matrix):
    add_rosette(bm, col_layer, matrix, random.randint(6, 9), 0.045, 0.013, 'oval', DAISY_LEAF_DARK, DAISY_LEAF_LIGHT)
    for _ in range(random.randint(2, 4)):
        ang = random.uniform(0, 360)
        tilt = random.uniform(0, 10)
        h = random.uniform(0.06, 0.11)
        rot = Matrix.Rotation(math.radians(ang), 4, 'Z') @ Matrix.Rotation(math.radians(90 - tilt), 4, 'X')
        sm = matrix @ rot
        add_tapered_blade(bm, col_layer, sm, h, 0.003, 0.001, 0.01, 4, STEM_GREEN, STEM_GREEN)
        fm = sm @ Matrix.Translation((0, h, 0))
        add_flower(bm, col_layer, fm, 13, 0.018, 0.005, WHITE, YELLOW, 0.006)


def build_dandelion(bm, col_layer, matrix):
    add_rosette(bm, col_layer, matrix, random.randint(6, 10), 0.07, 0.022, 'jagged', DANDY_LEAF_DARK, DANDY_LEAF_LIGHT)
    ang = random.uniform(0, 360)
    h = random.uniform(0.10, 0.16)
    rot = Matrix.Rotation(math.radians(ang), 4, 'Z') @ Matrix.Rotation(math.radians(90 - random.uniform(0, 6)), 4, 'X')
    sm = matrix @ rot
    add_tapered_blade(bm, col_layer, sm, h, 0.004, 0.0015, 0.015, 5, STEM_GREEN, STEM_GREEN)
    fm = sm @ Matrix.Translation((0, h, 0))
    add_flower(bm, col_layer, fm, 22, 0.02, 0.004, YELLOW, YELLOW, 0.007)


def build_wood_sorrel(bm, col_layer, matrix):
    purple_variant = random.random() < 0.3
    c0, c1 = (SORREL_PURPLE_DARK, SORREL_PURPLE_LIGHT) if purple_variant else (SORREL_GREEN_DARK, SORREL_GREEN_LIGHT)
    clusters = random.randint(5, 8)
    for _ in range(clusters):
        offset = Vector((random.uniform(-0.05, 0.05), random.uniform(-0.05, 0.05), 0))
        m = matrix @ Matrix.Translation(offset) @ Matrix.Rotation(math.radians(random.uniform(0, 360)), 4, 'Z')
        add_trifoliate(bm, col_layer, m, 0.03, 0.026, 'heart', c0, c1)


def build_plantain(bm, col_layer, matrix):
    add_rosette(bm, col_layer, matrix, random.randint(5, 7), 0.09, 0.045, 'oval', PLANTAIN_DARK, PLANTAIN_LIGHT)
    for _ in range(random.randint(1, 2)):
        ang = random.uniform(0, 360)
        h = random.uniform(0.12, 0.18)
        rot = Matrix.Rotation(math.radians(ang), 4, 'Z') @ Matrix.Rotation(math.radians(90 - random.uniform(0, 5)), 4, 'X')
        sm = matrix @ rot
        add_tapered_blade(bm, col_layer, sm, h, 0.005, 0.0015, 0.005, 5, STEM_GREEN, PLANTAIN_DARK)


def build_violet(bm, col_layer, matrix):
    add_rosette(bm, col_layer, matrix, random.randint(5, 7), 0.04, 0.035, 'heart', VIOLET_LEAF_DARK, VIOLET_LEAF_LIGHT)
    for _ in range(random.randint(1, 3)):
        ang = random.uniform(0, 360)
        h = random.uniform(0.05, 0.08)
        rot = Matrix.Rotation(math.radians(ang), 4, 'Z') @ Matrix.Rotation(math.radians(90 - random.uniform(0, 10)), 4, 'X')
        sm = matrix @ rot
        add_tapered_blade(bm, col_layer, sm, h, 0.003, 0.001, 0.006, 3, STEM_GREEN, STEM_GREEN)
        fm = sm @ Matrix.Translation((0, h, 0))
        add_flower(bm, col_layer, fm, 5, 0.014, 0.008, PURPLE, YELLOW, 0.003)


def build_babys_tears(bm, col_layer, matrix):
    n = random.randint(10, 18)
    for _ in range(n):
        offset = Vector((random.uniform(-0.05, 0.05), random.uniform(-0.05, 0.05), 0))
        ang = random.uniform(0, 360)
        m = matrix @ Matrix.Translation(offset) @ Matrix.Rotation(math.radians(ang), 4, 'Z')
        add_shaped_leaf(bm, col_layer, m, 0.008, 0.007, 'round', BT_DARK, BT_LIGHT, segments=4)


def build_thyme(bm, col_layer, matrix):
    n = random.randint(12, 20)
    for _ in range(n):
        offset = Vector((random.uniform(-0.06, 0.06), random.uniform(-0.06, 0.06), 0))
        ang = random.uniform(0, 360)
        m = matrix @ Matrix.Translation(offset) @ Matrix.Rotation(math.radians(ang), 4, 'Z')
        add_shaped_leaf(bm, col_layer, m, 0.01, 0.006, 'oval', THYME_DARK, THYME_LIGHT, segments=4)
        if random.random() < 0.18:
            sang = random.uniform(0, 360)
            h = random.uniform(0.015, 0.03)
            rot = Matrix.Rotation(math.radians(sang), 4, 'Z') @ Matrix.Rotation(math.radians(90 - random.uniform(0, 10)), 4, 'X')
            sm = m @ rot
            add_tapered_blade(bm, col_layer, sm, h, 0.0015, 0.001, 0.002, 2, STEM_GREEN, STEM_GREEN)
            fm = sm @ Matrix.Translation((0, h, 0))
            add_flower(bm, col_layer, fm, 5, 0.007, 0.004, PINK, PINK, 0.002)


def build_bunchberry(bm, col_layer, matrix):
    ang = random.uniform(0, 360)
    h = random.uniform(0.05, 0.08)
    rot = Matrix.Rotation(math.radians(ang), 4, 'Z') @ Matrix.Rotation(math.radians(90 - random.uniform(0, 8)), 4, 'X')
    sm = matrix @ rot
    add_tapered_blade(bm, col_layer, sm, h, 0.006, 0.003, 0.006, 4, STEM_GREEN, STEM_GREEN)
    top = sm @ Matrix.Translation((0, h, 0))
    add_whorl(bm, col_layer, top, random.choice((4, 5, 6)), 0.05, 0.028, 'oval', BUNCHBERRY_DARK, BUNCHBERRY_LIGHT)
    if random.random() < 0.4:
        add_flower(bm, col_layer, top @ Matrix.Translation((0, 0.01, 0)), 4, 0.02, 0.014, CREAM, YELLOW, 0.004)


# -----------------------------------------------------------------------
# SPECIES TABLE — 15 colonies: 3 ferns, 3 grasses, 9 other ground plants
# -----------------------------------------------------------------------
SPECIES = [
    dict(name="Sword Fern",          category="Fern",              build=build_sword_fern,     count=(14, 20), radius=1.6, scale=(0.85, 1.15)),
    dict(name="Ostrich Fern",        category="Fern",              build=build_ostrich_fern,   count=(8, 12),  radius=1.9, scale=(0.9, 1.2)),
    dict(name="Maidenhair Fern",     category="Fern",              build=build_maidenhair_fern,count=(16, 22), radius=1.3, scale=(0.8, 1.1)),
    dict(name="Tufted Fescue Grass", category="Grass",             build=build_fescue,         count=(60, 90), radius=1.7, scale=(0.85, 1.2)),
    dict(name="Wild Rye Grass",      category="Grass",             build=build_wild_rye,       count=(45, 70), radius=1.9, scale=(0.85, 1.2)),
    dict(name="Sedge",               category="Grass",             build=build_sedge,          count=(55, 85), radius=1.6, scale=(0.85, 1.15)),
    dict(name="White Clover",        category="Ground Cover",      build=build_clover,         count=(70, 110),radius=1.5, scale=(0.8, 1.2)),
    dict(name="Common Daisy",        category="Flowering",         build=build_daisy,          count=(30, 50), radius=1.6, scale=(0.85, 1.15)),
    dict(name="Dandelion",           category="Flowering",         build=build_dandelion,      count=(20, 35), radius=1.7, scale=(0.85, 1.2)),
    dict(name="Wood Sorrel",         category="Ground Cover",      build=build_wood_sorrel,    count=(50, 80), radius=1.4, scale=(0.8, 1.15)),
    dict(name="Broadleaf Plantain",  category="Ground Cover",      build=build_plantain,       count=(15, 25), radius=1.6, scale=(0.85, 1.2)),
    dict(name="Wild Violet",         category="Flowering",         build=build_violet,         count=(35, 55), radius=1.4, scale=(0.8, 1.15)),
    dict(name="Baby's Tears",        category="Moss/Ground Cover", build=build_babys_tears,    count=(80, 130),radius=1.3, scale=(0.8, 1.2)),
    dict(name="Creeping Thyme",      category="Flowering Ground Cover", build=build_thyme,     count=(70, 110),radius=1.4, scale=(0.8, 1.15)),
    dict(name="Bunchberry",          category="Ground Cover",      build=build_bunchberry,     count=(20, 35), radius=1.5, scale=(0.85, 1.15)),
]

assert len(SPECIES) == 15

# -----------------------------------------------------------------------
# MATERIAL
# -----------------------------------------------------------------------
def create_vertex_color_material(name, roughness=0.65):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial')
    out.location = (300, 0)
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (0, 0)
    attr = nodes.new('ShaderNodeAttribute')
    attr.attribute_name = "Col"
    attr.location = (-300, 0)
    links.new(attr.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = roughness
    links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    mat.use_backface_culling = False
    return mat


def build_procedural_material(name, roughness=0.65, variegation_scale=18.0, variegation_strength=0.18):
    """Real node-graph material: Attribute('Col') as the base, with a Noise
    Texture multiplied in for extra per-leaf-cluster variegation, and a
    second noise driving roughness variation. Looks great in Blender.
    For export, feed this into bake_material_to_texture()."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links
    nodes.clear()

    out = nodes.new('ShaderNodeOutputMaterial'); out.location = (700, 0)
    bsdf = nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location = (400, 0)
    attr = nodes.new('ShaderNodeAttribute'); attr.location = (-700, 200)
    attr.attribute_name = "Col"

    tex_coord = nodes.new('ShaderNodeTexCoord'); tex_coord.location = (-1000, -250)

    noise = nodes.new('ShaderNodeTexNoise'); noise.location = (-750, -100)
    noise.inputs['Scale'].default_value = variegation_scale
    noise.inputs['Detail'].default_value = 3.0
    ramp = nodes.new('ShaderNodeValToRGB'); ramp.location = (-500, -100)
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.82, 0.82, 0.82, 1.0)
    ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[1].color = (1.18, 1.18, 1.18, 1.0)
    mix = nodes.new('ShaderNodeMixRGB'); mix.location = (-150, 100)
    mix.blend_type = 'MULTIPLY'
    mix.inputs['Fac'].default_value = variegation_strength

    links.new(tex_coord.outputs['Object'], noise.inputs['Vector'])
    links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
    links.new(attr.outputs['Color'], mix.inputs['Color1'])
    links.new(ramp.outputs['Color'], mix.inputs['Color2'])
    links.new(mix.outputs['Color'], bsdf.inputs['Base Color'])

    rnoise = nodes.new('ShaderNodeTexNoise'); rnoise.location = (-750, -400)
    rnoise.inputs['Scale'].default_value = variegation_scale * 2.0
    rmap = nodes.new('ShaderNodeMapRange'); rmap.location = (-450, -400)
    rmap.inputs['To Min'].default_value = max(0.0, roughness - 0.15)
    rmap.inputs['To Max'].default_value = min(1.0, roughness + 0.15)
    links.new(tex_coord.outputs['Object'], rnoise.inputs['Vector'])
    links.new(rnoise.outputs['Fac'], rmap.inputs['Value'])
    links.new(rmap.outputs['Result'], bsdf.inputs['Roughness'])

    links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    mat.use_backface_culling = False
    return mat


def resolve_texture_dir():
    if bpy.data.filepath:
        d = bpy.path.abspath(TEXTURE_OUTPUT_DIR)
    else:
        d = os.path.join(os.path.expanduser("~"), "ground_plant_colony_textures")
    os.makedirs(d, exist_ok=True)
    return d


def uv_unwrap_object(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.03)
    bpy.ops.object.mode_set(mode='OBJECT')


def bake_material_to_texture(obj, mat, image_size, out_dir):
    """UV-unwraps `obj` (assumed already done by caller) and bakes `mat`'s
    node graph down to a single PNG, then rewires the material to a plain
    Image Texture -> Base Color so it's fully FBX/Unity friendly."""
    img_name = mat.name + "_Bake"
    img = bpy.data.images.new(img_name, image_size, image_size, alpha=False)

    nt = mat.node_tree
    nodes = nt.nodes
    bake_node = nodes.new('ShaderNodeTexImage')
    bake_node.image = img
    for n in nodes:
        n.select = False
    bake_node.select = True
    nodes.active = bake_node

    scene = bpy.context.scene
    prev_engine = scene.render.engine
    scene.render.engine = 'CYCLES'
    prev_samples = getattr(scene.cycles, 'samples', 32)
    scene.cycles.samples = 24

    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    # Diffuse/Color-only pass: lighting-independent, bakes just the
    # material's base color output (what the node graph computes).
    bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, save_mode='INTERNAL')

    scene.render.engine = prev_engine
    scene.cycles.samples = prev_samples

    filepath = os.path.join(out_dir, img_name + ".png")
    img.filepath_raw = filepath
    img.file_format = 'PNG'
    img.save()

    # Rewire down to a simple, Unity-friendly material.
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial'); out.location = (300, 0)
    bsdf = nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location = (0, 0)
    tex = nodes.new('ShaderNodeTexImage'); tex.location = (-350, 0)
    tex.image = img
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    bsdf.inputs['Roughness'].default_value = 0.75
    return img


def create_material_for_species(obj_name):
    if SHADER_MODE == 'VERTEX_COLOR':
        return create_vertex_color_material(obj_name + "_Mat")
    else:
        return build_procedural_material(obj_name + "_Mat")


# -----------------------------------------------------------------------
# COLONY GENERATION
# -----------------------------------------------------------------------
def random_point_in_disc(radius, bias=1.6):
    r = radius * (random.random() ** (1.0 / bias))
    theta = random.uniform(0, 2 * math.pi)
    return Vector((r * math.cos(theta), r * math.sin(theta), 0.0))


def generate_colony(species, center, collection, texture_dir=None):
    bm = bmesh.new()
    col_layer = bm.loops.layers.color.new("Col")
    n = random.randint(*species['count'])
    for _ in range(n):
        p = center + random_point_in_disc(species['radius'])
        yaw = random.uniform(0, 360)
        s = random.uniform(*species['scale'])
        m = Matrix.Translation(p) @ Matrix.Rotation(math.radians(yaw), 4, 'Z') @ Matrix.Scale(s, 4)
        species['build'](bm, col_layer, m)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh_name = species['name'].replace(" ", "_").replace("'", "") + "_Mesh"
    mesh = bpy.data.meshes.new(mesh_name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    for poly in mesh.polygons:
        poly.use_smooth = False

    obj_name = species['name'].replace(" ", "_").replace("'", "")
    obj = bpy.data.objects.new(obj_name, mesh)
    mat = create_material_for_species(obj_name)
    obj.data.materials.append(mat)

    # Object needs to be in the scene/view layer before UV/bake ops can run.
    collection.objects.link(obj)

    if SHADER_MODE == 'BAKED_TEXTURE':
        uv_unwrap_object(obj)
        bake_material_to_texture(obj, mat, BAKE_IMAGE_SIZE, texture_dir)

    return obj, n


def build_colony_centers():
    cell_w = TERRAIN_W / GRID_COLS
    cell_d = TERRAIN_D / GRID_ROWS
    cells = []
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            cx = -TERRAIN_W / 2 + cell_w * (col + 0.5)
            cy = -TERRAIN_D / 2 + cell_d * (row + 0.5)
            jitter_x = random.uniform(-cell_w * 0.18, cell_w * 0.18)
            jitter_y = random.uniform(-cell_d * 0.18, cell_d * 0.18)
            cells.append(Vector((cx + jitter_x, cy + jitter_y, 0.0)))
    random.shuffle(cells)
    return cells


def create_ground_plane(collection):
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0, 0, -0.005))
    plane = bpy.context.active_object
    plane.scale = (TERRAIN_W * 0.6, TERRAIN_D * 0.6, 1.0)
    plane.name = "Ground_Soil"
    mat = bpy.data.materials.new("Ground_Soil_Mat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs['Base Color'].default_value = (0.09, 0.06, 0.045, 1.0)
        bsdf.inputs['Roughness'].default_value = 0.95
    plane.data.materials.append(mat)
    for c in list(plane.users_collection):
        c.objects.unlink(plane)
    collection.objects.link(plane)
    return plane


def clear_collection(name):
    if name in bpy.data.collections:
        col = bpy.data.collections[name]
        for obj in list(col.objects):
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        bpy.data.collections.remove(col)


def main():
    clear_collection(COLLECTION_NAME)
    collection = bpy.data.collections.new(COLLECTION_NAME)
    bpy.context.scene.collection.children.link(collection)

    if CREATE_GROUND_PLANE:
        create_ground_plane(collection)

    centers = build_colony_centers()
    texture_dir = resolve_texture_dir() if SHADER_MODE == 'BAKED_TEXTURE' else None

    print("=" * 60)
    print(f"GROUND PLANT COLONIES  (shader mode: {SHADER_MODE})")
    if texture_dir:
        print(f"Baked textures will be saved to: {texture_dir}")
    print("=" * 60)
    for species, center in zip(SPECIES, centers):
        obj, n = generate_colony(species, center, collection, texture_dir)
        print(f"  {species['name']:<22} ({species['category']:<24}) "
              f"x{n:<4} instances @ ({center.x:6.2f}, {center.y:6.2f})")
    print("=" * 60)

    if EXPORT_FBX:
        bpy.ops.object.select_all(action='DESELECT')
        for obj in collection.objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = collection.objects[0]
        bpy.ops.export_scene.fbx(
            filepath=FBX_PATH,
            use_selection=True,
            global_scale=1.0,
            apply_unit_scale=True,
            bake_space_transform=True,
            object_types={'MESH'},
            mesh_smooth_type='FACE',
            colors_type='LINEAR',
            path_mode='COPY',
            embed_textures=True,
        )
        print(f"Exported FBX to: {FBX_PATH}")


if __name__ == "__main__":
    main()
