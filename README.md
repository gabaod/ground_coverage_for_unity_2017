
HOW TO USE:
1. Open Blender 4.5 -> Scripting tab -> open this file (or paste it) -> Run.
2. It builds a collection called "GroundPlantColonies" containing 15 mesh
   objects (one per species/colony) + an optional ground plane.
3. File > Export > FBX (or flip EXPORT_FBX = True below and set FBX_PATH).
4. Import the FBX into Unity as usual.
5. Update settings to your liking:  CREATE_GROUND_PLANE = False
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
