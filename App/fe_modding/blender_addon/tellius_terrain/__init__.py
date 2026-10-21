"""Tellius Terrain: sculpt and paint Fire Emblem: Path of Radiance map
terrain with its texture atlas, for the Tellius modding app.

Open a terrain kit made by the app (Assets > 3D Models, a zmap/ set,
"Sculpt & paint kit..."), sculpt FE9 Sculpt, paint the layers from the
sidebar's Tellius tab, save, and import the .blend back in the app.
"""

bl_info = {
    "name": "Tellius Terrain",
    "author": "Tellius modding app",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar > Tellius",
    "description": "Sculpt and paint FE9 map terrain with its texture atlas",
    "category": "Paint",
}

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty

from . import kit

_swatch_items_cache = []


def _swatch_items(self, context):
    global _swatch_items_cache
    layout = kit.layout_of(context.scene) if context and context.scene else None
    if layout is None:
        _swatch_items_cache = [("0", "No atlas swatches", "")]
    else:
        _swatch_items_cache = [
            (str(i), s.name, f"{s.w}x{s.h} texels at ({s.x}, {s.y})") for i, s in enumerate(layout.swatches)
        ]
    return _swatch_items_cache


def _refresh(self, context):
    if kit.kit_data(context.scene) is not None:
        kit.build_paint_material(context.scene)


class FE9Layer(bpy.types.PropertyGroup):
    name: StringProperty(name="Name", update=_refresh)
    swatch: IntProperty(name="Swatch", min=0, update=_refresh)
    image: PointerProperty(name="Weights", type=bpy.types.Image)
    slopes: BoolProperty(name="Cliffs", description="Cover steep faces with this layer", default=False)
    visible: BoolProperty(name="Visible", default=True, update=_refresh)


class FE9_UL_layers(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        atlas = kit.layout_of(context.scene)
        swatch = atlas.swatches[item.swatch].name if atlas and item.swatch < len(atlas.swatches) else "?"
        split = layout.split(factor=0.5)
        split.prop(item, "name", text="", emboss=False, icon="TEXTURE" if index else "WORLD")
        row = split.row(align=True)
        row.label(text=swatch)
        if index:
            row.prop(item, "slopes", text="", icon="IPO_EXPO" if item.slopes else "IPO_LINEAR", emboss=False)
            row.prop(item, "visible", text="", icon="HIDE_OFF" if item.visible else "HIDE_ON", emboss=False)


def _kit_or_cancel(operator, context) -> bool:
    if kit.kit_data(context.scene) is None:
        operator.report({"ERROR"}, "This file is not a terrain kit. Make one in the Tellius app.")
        return False
    return True


class FE9_OT_paint_layer(bpy.types.Operator):
    bl_idname = "tellius.paint_layer"
    bl_label = "Paint Layer"
    bl_description = "Texture-paint the selected layer's weights on FE9 Sculpt (white shows the layer)"
    bl_options = {"REGISTER"}

    def execute(self, context):
        if not _kit_or_cancel(self, context):
            return {"CANCELLED"}
        scene = context.scene
        index = scene.fe9_layer_index
        if index == 0 or index >= len(scene.fe9_layers):
            self.report({"ERROR"}, "The base layer shows wherever the others leave room; pick a layer above it.")
            return {"CANCELLED"}
        image = scene.fe9_layers[index].image
        sculpt = kit.sculpt_object(scene)
        if sculpt is None or image is None:
            self.report({"ERROR"}, "The kit has no FE9 Sculpt object or layer image.")
            return {"CANCELLED"}
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        kit.remove_preview(scene)
        scene.fe9_preview_report = ""
        for obj in context.view_layer.objects:
            obj.select_set(False)
        sculpt.hide_set(False)
        sculpt.select_set(True)
        context.view_layer.objects.active = sculpt
        kit.set_paint_uv(sculpt)
        bpy.ops.object.mode_set(mode="TEXTURE_PAINT")
        settings = scene.tool_settings.image_paint
        settings.mode = "IMAGE"
        settings.canvas = image
        _set_brush_colour(context, (1.0, 1.0, 1.0))
        return {"FINISHED"}


def _set_brush_colour(context, colour) -> None:
    settings = context.scene.tool_settings
    for owner in (getattr(settings.image_paint, "unified_paint_settings", None),
                  getattr(settings, "unified_paint_settings", None),
                  getattr(settings.image_paint, "brush", None)):
        if owner is not None and hasattr(owner, "color"):
            try:
                owner.color = colour
            except (AttributeError, TypeError):
                pass


class FE9_OT_brush(bpy.types.Operator):
    bl_idname = "tellius.brush"
    bl_label = "Brush Colour"
    bl_description = "White paints the layer in, black takes it out"
    erase: BoolProperty(default=False)

    def execute(self, context):
        _set_brush_colour(context, (0.0, 0.0, 0.0) if self.erase else (1.0, 1.0, 1.0))
        return {"FINISHED"}


class FE9_OT_add_layer(bpy.types.Operator):
    bl_idname = "tellius.add_layer"
    bl_label = "Add Layer"
    bl_description = "Add a layer showing one atlas swatch"
    bl_options = {"REGISTER", "UNDO"}
    swatch: EnumProperty(name="Swatch", items=_swatch_items)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if not _kit_or_cancel(self, context):
            return {"CANCELLED"}
        layout = kit.layout_of(context.scene)
        index = int(self.swatch)
        kit.add_layer(context.scene, layout.swatches[index].name, index)
        context.scene.fe9_layer_index = len(context.scene.fe9_layers) - 1
        kit.build_paint_material(context.scene)
        return {"FINISHED"}


class FE9_OT_remove_layer(bpy.types.Operator):
    bl_idname = "tellius.remove_layer"
    bl_label = "Remove Layer"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        if scene.fe9_layer_index == 0:
            self.report({"ERROR"}, "The base layer cannot be removed.")
            return {"CANCELLED"}
        kit.remove_layer(scene, scene.fe9_layer_index)
        scene.fe9_layer_index = min(scene.fe9_layer_index, len(scene.fe9_layers) - 1)
        kit.build_paint_material(scene)
        return {"FINISHED"}


class FE9_OT_move_layer(bpy.types.Operator):
    bl_idname = "tellius.move_layer"
    bl_label = "Move Layer"
    bl_description = "Layers lower in the list are painted over the ones above them"
    bl_options = {"REGISTER", "UNDO"}
    up: BoolProperty(default=True)

    def execute(self, context):
        scene = context.scene
        index = scene.fe9_layer_index
        target = index - 1 if self.up else index + 1
        if index == 0 or target < 1 or target >= len(scene.fe9_layers):
            return {"CANCELLED"}
        scene.fe9_layers.move(index, target)
        scene.fe9_layer_index = target
        kit.build_paint_material(scene)
        return {"FINISHED"}


class FE9_OT_set_swatch(bpy.types.Operator):
    bl_idname = "tellius.set_swatch"
    bl_label = "Change Swatch"
    bl_description = "Show another atlas swatch on the selected layer"
    bl_options = {"REGISTER", "UNDO"}
    swatch: EnumProperty(name="Swatch", items=_swatch_items)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        item = context.scene.fe9_layers[context.scene.fe9_layer_index]
        item.swatch = int(self.swatch)
        return {"FINISHED"}


class FE9_OT_refresh(bpy.types.Operator):
    bl_idname = "tellius.refresh_material"
    bl_label = "Refresh Material"
    bl_description = "Rebuild the painted preview material from the layers"

    def execute(self, context):
        if not _kit_or_cancel(self, context):
            return {"CANCELLED"}
        kit.build_paint_material(context.scene)
        if bpy.data.objects.get(kit.PREVIEW_NAME) is not None:
            bpy.data.objects[kit.PREVIEW_NAME].data.materials[0] = kit.build_preview_material(context.scene)
        return {"FINISHED"}


class FE9_OT_game_preview(bpy.types.Operator):
    bl_idname = "tellius.game_preview"
    bl_label = "Game Preview"
    bl_description = ("Compile the layers as the game draws them (two swatches per triangle, one mask) "
                      "onto a separate preview object, conflicts in red")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if not _kit_or_cancel(self, context):
            return {"CANCELLED"}
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        try:
            result, source = kit.game_preview(context.scene)
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        layout = kit.layout_of(context.scene)
        context.scene.fe9_preview_report = "\n".join([f"From {source}."] + result.report(layout))
        sculpt = kit.sculpt_object(context.scene)
        if sculpt is not None:
            sculpt.hide_set(True)
        self.report({"INFO"}, result.report(layout)[0])
        return {"FINISHED"}


class FE9_OT_end_preview(bpy.types.Operator):
    bl_idname = "tellius.end_preview"
    bl_label = "Back to Painting"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        kit.remove_preview(context.scene)
        sculpt = kit.sculpt_object(context.scene)
        if sculpt is not None:
            sculpt.hide_set(False)
        context.scene.fe9_preview_report = ""
        return {"FINISHED"}


class FE9_OT_make_game_mesh(bpy.types.Operator):
    bl_idname = "tellius.make_game_mesh"
    bl_label = "Make Game Mesh"
    bl_description = ("Reduce a copy of the sculpt to the triangle budget; the app imports it "
                      "(saving without it makes one at import)")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if not _kit_or_cancel(self, context):
            return {"CANCELLED"}
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        obj, count = kit.make_game_mesh(context.scene, context.scene.fe9_budget)
        self.report({"INFO"}, f"{obj.name}: about {count:,} triangles once cut on the swatch repeats "
                              "(hidden; the import uses it).")
        return {"FINISHED"}


class FE9_OT_tile_panels(bpy.types.Operator):
    bl_idname = "tellius.tile_panels"
    bl_label = "Show Tile Panels"
    bl_description = ("Show the flat panels units will stand on: the import flattens the playable area "
                      "onto them and moves the tile heights")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            kit.tile_panels(context.scene)
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class FE9_OT_bake_light(bpy.types.Operator):
    bl_idname = "tellius.bake_light"
    bl_label = "Bake Light Overlay"
    bl_description = "Replace the light overlay with sun shading and shadows of the current terrain"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        try:
            kit.bake_light(scene, scene.fe9_light_strength, scene.fe9_sun_angle, scene.fe9_sun_height)
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        kit.build_paint_material(scene)
        return {"FINISHED"}


class FE9_OT_auto_paint(bpy.types.Operator):
    bl_idname = "tellius.auto_paint"
    bl_label = "Auto Paint"
    bl_description = "Fill the selected layer from the terrain's slope or height"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        try:
            kit.auto_paint(scene, scene.fe9_layer_index, scene.fe9_auto_mode, scene.fe9_auto_low,
                           scene.fe9_auto_high, scene.fe9_auto_combine)
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class FE9_OT_apply_swatch(bpy.types.Operator):
    bl_idname = "tellius.apply_swatch"
    bl_label = "Apply Swatch to Faces"
    bl_description = ("Lay one atlas swatch on the selected faces through both game UV sets "
                      "(indoor floors and walls of a plain map export)")
    bl_options = {"REGISTER", "UNDO"}
    swatch: EnumProperty(name="Swatch", items=_swatch_items)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        layout = kit.layout_of(context.scene)
        if layout is None:
            self.report({"ERROR"}, "No atlas swatches in this file: export the map from the app again.")
            return {"CANCELLED"}
        try:
            faces, too_big = kit.apply_swatch_to_faces(context.object, int(self.swatch), layout,
                                                       context.scene.fe9_piece_slope)
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        message = f"{faces} faces textured."
        if too_big:
            message += f" {too_big} are larger than one repeat of the swatch and were squeezed; cut them smaller."
        self.report({"WARNING"} if too_big else {"INFO"}, message)
        return {"FINISHED"}


class FE9_OT_save(bpy.types.Operator):
    bl_idname = "tellius.save"
    bl_label = "Save Kit"
    bl_description = "Pack the painted images into the file and save it"

    def execute(self, context):
        if context.object and context.object.mode == "TEXTURE_PAINT":
            bpy.ops.object.mode_set(mode="OBJECT")
        kit.pack_dirty_images()
        bpy.ops.wm.save_mainfile()
        return {"FINISHED"}


class FE9_PT_base:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Tellius"


class FE9_PT_kit(FE9_PT_base, bpy.types.Panel):
    bl_label = "FE9 Terrain"

    def draw(self, context):
        layout = self.layout
        data = kit.kit_data(context.scene)
        if data is None:
            layout.label(text="Not a terrain kit.", icon="INFO")
            layout.label(text="Make one in the Tellius app.")
            return
        layout.label(text=f"Map {data.get('map', '?')} - {data.get('terrain', '?')}")
        layout.operator("tellius.save", icon="FILE_TICK")


class FE9_PT_layers(FE9_PT_base, bpy.types.Panel):
    bl_label = "Paint Layers"
    bl_parent_id = "FE9_PT_kit"

    @classmethod
    def poll(cls, context):
        return kit.kit_data(context.scene) is not None

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        row = layout.row()
        row.template_list("FE9_UL_layers", "", scene, "fe9_layers", scene, "fe9_layer_index", rows=5)
        column = row.column(align=True)
        column.operator("tellius.add_layer", text="", icon="ADD")
        column.operator("tellius.remove_layer", text="", icon="REMOVE")
        column.separator()
        column.operator("tellius.move_layer", text="", icon="TRIA_UP").up = True
        column.operator("tellius.move_layer", text="", icon="TRIA_DOWN").up = False
        row = layout.row(align=True)
        row.operator("tellius.paint_layer", icon="BRUSH_DATA")
        row.operator("tellius.set_swatch", text="", icon="TEXTURE")
        row = layout.row(align=True)
        row.operator("tellius.brush", text="Paint in").erase = False
        row.operator("tellius.brush", text="Erase").erase = True
        layout.prop(scene, "fe9_show_light")
        layout.operator("tellius.refresh_material", icon="FILE_REFRESH")


class FE9_PT_auto(FE9_PT_base, bpy.types.Panel):
    bl_label = "Auto Paint"
    bl_parent_id = "FE9_PT_kit"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return kit.kit_data(context.scene) is not None

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        layout.prop(scene, "fe9_auto_mode", expand=True)
        row = layout.row(align=True)
        row.prop(scene, "fe9_auto_low")
        row.prop(scene, "fe9_auto_high")
        layout.prop(scene, "fe9_auto_combine", text="")
        layout.operator("tellius.auto_paint", icon="MOD_SMOOTH")


class FE9_PT_preview(FE9_PT_base, bpy.types.Panel):
    bl_label = "Game Check"
    bl_parent_id = "FE9_PT_kit"

    @classmethod
    def poll(cls, context):
        return kit.kit_data(context.scene) is not None

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        row = layout.row(align=True)
        row.operator("tellius.game_preview", icon="HIDE_OFF")
        row.operator("tellius.end_preview", text="", icon="X")
        layout.prop(scene, "fe9_show_conflicts")
        for line in scene.fe9_preview_report.splitlines():
            layout.label(text=line)
        layout.separator()
        layout.prop(scene, "fe9_budget")
        layout.operator("tellius.make_game_mesh", icon="MOD_DECIM")
        layout.operator("tellius.tile_panels", icon="MESH_GRID")


class FE9_PT_light(FE9_PT_base, bpy.types.Panel):
    bl_label = "Light Overlay"
    bl_parent_id = "FE9_PT_kit"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return kit.kit_data(context.scene) is not None

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        layout.prop(scene, "fe9_sun_angle")
        layout.prop(scene, "fe9_sun_height")
        layout.prop(scene, "fe9_light_strength")
        layout.operator("tellius.bake_light", icon="LIGHT_SUN")


class FE9_PT_pieces(FE9_PT_base, bpy.types.Panel):
    bl_label = "Atlas Pieces"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return kit.layout_of(context.scene) is not None

    def draw(self, context):
        layout = self.layout
        layout.label(text="Edit Mode: select faces, then")
        layout.prop(context.scene, "fe9_piece_slope")
        layout.operator("tellius.apply_swatch", icon="UV")


@persistent
def _pack_before_save(_dummy):
    kit.pack_dirty_images()


classes = (
    FE9Layer, FE9_UL_layers,
    FE9_OT_paint_layer, FE9_OT_brush, FE9_OT_add_layer, FE9_OT_remove_layer, FE9_OT_move_layer,
    FE9_OT_set_swatch, FE9_OT_refresh, FE9_OT_game_preview, FE9_OT_end_preview, FE9_OT_make_game_mesh,
    FE9_OT_tile_panels, FE9_OT_bake_light, FE9_OT_auto_paint, FE9_OT_apply_swatch, FE9_OT_save,
    FE9_PT_kit, FE9_PT_layers, FE9_PT_auto, FE9_PT_preview, FE9_PT_light, FE9_PT_pieces,
)

_registered = False


def register():
    global _registered
    if _registered:
        return
    for cls in classes:
        bpy.utils.register_class(cls)
    scene = bpy.types.Scene
    scene.fe9_layers = CollectionProperty(type=FE9Layer)
    scene.fe9_layer_index = IntProperty(default=0)
    scene.fe9_show_light = BoolProperty(name="Show light overlay", default=True, update=_refresh)
    scene.fe9_show_conflicts = BoolProperty(name="Show conflicts in red", default=True)
    scene.fe9_preview_report = StringProperty(default="")
    scene.fe9_budget = IntProperty(name="Triangle budget", default=8000, min=500, max=30000,
                                   description="Triangles after the swatch cuts; vanilla terrains have 6,000 to 21,000")
    scene.fe9_auto_mode = EnumProperty(name="From", items=(("SLOPE", "Slope", "Degrees of slope"),
                                                           ("HEIGHT", "Height", "Height in game units")))
    scene.fe9_auto_low = FloatProperty(name="From", default=30.0)
    scene.fe9_auto_high = FloatProperty(name="To", default=45.0)
    scene.fe9_auto_combine = EnumProperty(name="Combine", items=(
        ("ADD", "Add to the layer", ""), ("REPLACE", "Replace the layer", ""), ("SUBTRACT", "Take out", "")))
    scene.fe9_sun_angle = FloatProperty(name="Sun direction", default=225.0, min=0.0, max=360.0)
    scene.fe9_sun_height = FloatProperty(name="Sun height", default=40.0, min=5.0, max=90.0)
    scene.fe9_light_strength = FloatProperty(name="Shadow darkness", default=0.35, min=0.0, max=1.0)
    scene.fe9_piece_slope = FloatProperty(name="Side projection above (degrees)", default=50.0, min=1.0, max=90.0)
    if _pack_before_save not in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.append(_pack_before_save)
    _registered = True


def unregister():
    global _registered
    if _pack_before_save in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(_pack_before_save)
    for name in ("fe9_layers", "fe9_layer_index", "fe9_show_light", "fe9_show_conflicts", "fe9_preview_report",
                 "fe9_budget", "fe9_auto_mode", "fe9_auto_low", "fe9_auto_high", "fe9_auto_combine",
                 "fe9_sun_angle", "fe9_sun_height", "fe9_light_strength", "fe9_piece_slope"):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _registered = False
