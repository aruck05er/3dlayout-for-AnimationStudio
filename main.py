import bpy
import os
import math
import mathutils
import uuid
from bpy.app.handlers import persistent
from collections import defaultdict
from bpy.props import (
    CollectionProperty,
    IntProperty,
    StringProperty,
    IntVectorProperty,
    FloatProperty,
    BoolProperty,
    PointerProperty,
    EnumProperty,
    FloatVectorProperty
)
from bpy.types import PropertyGroup, UIList, Panel, Operator
from mathutils import Vector

# ---------------------------------------------------
# Update Camera
# ---------------------------------------------------

def update_camera_list(scene):
    cams = sorted(
        (o for o in scene.objects if o.type == 'CAMERA'),
        key=lambda c: c.name
    )
    col = scene.camera_list
    col.clear()
    for cam in cams:
        item = col.add()
        item.name = cam.name
    if scene.camera_index >= len(col):
        scene.camera_index = max(0, len(col) - 1)

def update_new_res_x(self, context):
    context.scene.render.resolution_x = self.new_setting_res_x

def update_new_res_y(self, context):
    context.scene.render.resolution_y = self.new_setting_res_y

def clean_unpaired_switch_collections():
    from collections import defaultdict

    scene = bpy.context.scene
    prop_to_colls = defaultdict(list)

    # 1. Switch Collectionプロパティを持つコレクションを集める
    for coll in bpy.data.collections:
        for key, val in coll.items():
            if key.startswith("Switch Collection"):
                prop_to_colls[(key, val)].append(coll)

    # 2. ペアができていないコレクションを抽出
    unpaired = []
    for (key, val), colls in prop_to_colls.items():
        if len(colls) < 2:
            unpaired.extend(colls)

    # 3. 安全に削除
    for coll in unpaired:
        parent = next((p for p in bpy.data.collections if coll.name in p.children), None)
        target_parent = parent or bpy.context.scene.collection

        # 子を移動
        for child in list(coll.children):
            target_parent.children.link(child)
            coll.children.unlink(child)

        # オブジェクトを移動
        for obj in list(coll.objects):
            if obj.name not in target_parent.objects:
                target_parent.objects.link(obj)
            coll.objects.unlink(obj)

        # 他の親からも unlink
        for p in bpy.data.collections:
            if coll.name in p.children:
                p.children.unlink(coll)
        if coll.name in bpy.context.scene.collection.children:
            bpy.context.scene.collection.children.unlink(coll)

        # remove 実行
        bpy.data.collections.remove(coll)

    # 孤立データの整理
    bpy.ops.outliner.orphans_purge(do_recursive=True)
    print(f"Unpaired Switch Collection 削除完了: {len(unpaired)} 件")
    
@persistent
def update_camera(self, context):
    
    scene = context.scene
    for coll in bpy.data.collections:
        keys = {
            key
            for o in coll.objects
            for key in o.keys()
            if key.startswith("Switch Collection")
        }
    key_to_cols = defaultdict(set)
    key_to_objs = defaultdict(list)
    for o in scene.objects:
        for key in list(o.keys()):
            if not key.startswith("Switch Collection"):
                continue
            for coll in o.users_collection:
                key_to_cols[key].add(coll.name)
            key_to_objs[key].append(o)
            
    for key, cols in key_to_cols.items():
        if len(cols) < 2:
            for o in key_to_objs[key]:
                del o[key]
    
    idx = scene.camera_index
    cams = sorted(
        (o for o in scene.objects if o.type == 'CAMERA'),
        key=lambda c: c.name
    )
    if not (0 <= idx < len(cams)):
        return
    cam = cams[idx]
    scene.camera = cam
    # 1
    for o in scene.objects:
        if o.name == "EyeLevelCircle":
            continue
        o.hide_set(True)
        o.hide_viewport = True
        o.hide_render = True
    # 2
    cam.hide_set(False)
    cam.hide_viewport = False
    cam.hide_render = False
    # 3
    active_coll = bpy.data.collections.get(cam.name)
    if active_coll:
        for o in active_coll.objects:
            o.hide_set(False)
            o.hide_viewport = False
            o.hide_render = False
    # 4
    for coll in bpy.data.collections:
        has_cam = any(o.type == 'CAMERA' for o in coll.objects)
        if cam.name in coll.objects:
            coll.hide_viewport = False
            coll.hide_render = False
        elif has_cam:
            coll.hide_viewport = True
            coll.hide_render = True
    # 5
    for coll in bpy.data.collections:
        for key, val in coll.items():
            if key.startswith("Switch Collection") and val == cam.name:
                coll.hide_viewport = True
                coll.hide_render = True
                break
            else:
                coll.hide_viewport = False
                coll.hide_render = False
    # 6
    for coll in bpy.data.collections:
        has_prop_for_cam = any(
            key.startswith("Switch Collection") and val == cam.name
            for key, val in coll.items()
        )
        if not has_prop_for_cam:
            for o in coll.objects:
                o.hide_set(False)
                o.hide_viewport = False
                o.hide_render = False
    # 7
    book_prefix = f"{cam.name} Book"
    for coll in bpy.data.collections:
        if coll.name.startswith(book_prefix):
            coll.hide_viewport = False
            coll.hide_render   = False
            for o in coll.objects:
                o.hide_set(False)
                o.hide_viewport = False
                o.hide_render   = False
    # 8
    res = getattr(cam, 'resolution_xy', None)
    if res and len(res) == 2:
        context.scene.render.resolution_x = res[0]
        context.scene.render.resolution_y = res[1]
        context.scene.new_setting_res_x = res[0]
        context.scene.new_setting_res_y = res[1]
    # 9
    if cam.get("EyeLevel"):
        circle = bpy.data.objects.get("EyeLevelCircle")
        if circle:
            for con in circle.constraints:
                if con.type == 'COPY_LOCATION':
                    con.target = cam
                    break
        else:
            create_eye_level_circle(cam)
    else:
        remove_eye_level_circle()
    # 10
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()
    
    for coll in list(bpy.data.collections):
        if not coll.objects and not coll.children:
            bpy.data.collections.remove(coll)
    
    scene.switch_coll_list.clear()
    root = bpy.data.collections.get(cam.name)
    if root:
        def scan(coll):
            if any(key.startswith("Switch Collection") for o in coll.objects for key in o.keys()):
                item = scene.switch_coll_list.add()
                item.name = coll.name
            for child in coll.children:
                scan(child)
        scan(root)
    bpy.ops.scene.refresh_switch_list()
    clean_unpaired_switch_collections()


# ---------------------------------------------------
# Panels
# ---------------------------------------------------
class CameraItem(PropertyGroup):
    name: StringProperty(name="Camera Name")

class SCENE_UL_camera_list(UIList):
    def draw_item(
        self, context, layout, data, item,
        icon, active_data, active_propname, index
    ):
        cam = bpy.data.objects.get(item.name)
        if not cam or cam.type != 'CAMERA':
            return
        scene = context.scene
        icon_id = (
            'RADIOBUT_ON' if scene.camera == cam else 'RADIOBUT_OFF'
        )
        res = getattr(cam, 'resolution_xy', None)
        if res and len(res) == 2:
            name = f"{cam.name} ({res[0]}×{res[1]})"
        else:
            name = cam.name
        layout.label(text=name, icon=icon_id)
        
class SwitchCollItem(PropertyGroup):
    name: StringProperty(name="Collection Name")

class SCENE_UL_switch_coll_list(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(text=item.name, icon='OUTLINER_COLLECTION')

class VIEW3D_PT_camera_switcher(Panel):
    bl_label = "Camera Switcher"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Camera"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.template_list(
            "SCENE_UL_camera_list", "",
            scene, "camera_list",
            scene, "camera_index",
            rows=8
        )
        layout.separator()
        layout.operator("object.separate_objects", text="Book 作成")
        layout.operator("object.copy_layer", text="Layer 複製")
        
        if len(scene.switch_coll_list) == 0:
            return
        
        layout.template_list(
            "SCENE_UL_switch_coll_list", "",
            scene, "switch_coll_list",
            scene, "switch_coll_index",
            rows=4
        )
        layout.operator("scene.delete_switch_collection", text="Delete")

class OBJECT_OT_refresh_switch_list(Operator):
    bl_idname = "scene.refresh_switch_list"
    bl_label = "Refresh Switch-Collections"
    bl_description = "List the collections within the active camera’s collection that have the “Switch Collection” property."

    def execute(self, context):
        scene = context.scene
        scene.switch_coll_list.clear()
        cam = scene.camera
        
        if not cam:
            self.report({'WARNING'}, "There is no active camera.")
            return {'CANCELLED'}
        root = bpy.data.collections.get(cam.name)
        if not root:
            self.report({'WARNING'}, f"Not found {cam.name} camera collection")
            return {'CANCELLED'}

        def scan(coll):
            for key, val in coll.items():
                if key.startswith("Switch Collection") and val == cam.name:
                    item = scene.switch_coll_list.add()
                    item.name = coll.name
                    break
            for child in coll.children:
                scan(child)

        scan(root)
        return {'FINISHED'}

class OBJECT_OT_delete_switch_collection(Operator):
    bl_idname = "scene.delete_switch_collection"
    bl_label = "Delete"
    bl_description = "Unlink the selected collection from the scene."

    def execute(self, context):
        scene = context.scene
        idx = scene.switch_coll_index
        if idx < 0 or idx >= len(scene.switch_coll_list):
            return {'CANCELLED'}
        coll_name = scene.switch_coll_list[idx].name
        coll = bpy.data.collections.get(coll_name)
        if not coll:
            self.report({'ERROR'}, f"{coll_name} is not found")
            return {'CANCELLED'}
        if coll.name in scene.collection.children:
            scene.collection.children.unlink(coll)
        else:
            for parent in bpy.data.collections:
                if coll.name in parent.children:
                    parent.children.unlink(coll)
                    break
        bpy.ops.scene.refresh_switch_list()
        return {'FINISHED'}

class OBJECT_OT_copy_layer(Operator):
    bl_idname = "object.copy_layer"
    bl_label = "Copy Layer"
    bl_description = "Duplicate the active camera’s collection and all its child collections/objects"
    
    new_name: StringProperty(
        name="New Collection Name",
        default="C000_Camera"
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def execute(self, context):
        cam = context.scene.camera
        src_coll = bpy.data.collections.get(cam.name)
        new_root = bpy.data.collections.new(self.new_name)
        context.scene.collection.children.link(new_root)
        
        duplicate_collection(src_coll, new_root)

        for obj in new_root.objects:
            if obj.type == 'CAMERA':
                obj.name = self.new_name
                obj.data.name = self.new_name
                break

        context.view_layer.update()
        return {'FINISHED'}
    
def duplicate_collection(src, dest):
    obj_map = {}

    # 1. オブジェクト複製
    for obj in src.objects:
        dup = obj.copy()
        if obj.data:
            dup.data = obj.data.copy()
        dest.objects.link(dup)
        dup.matrix_local = obj.matrix_local.copy()
        obj_map[obj] = dup

    # 2. 子コレクションを複製（Switch Collection プロパティがあるものはスキップ）
    for child in src.children:
        has_switch_prop = any(
            key.startswith("Switch Collection") for key, val in child.items()
        )
        if has_switch_prop:
            print(f"[SKIP] '{child.name}' は Switch Collection を持つため複製をスキップ")
            continue

        dup_child = bpy.data.collections.new(child.name)
        dest.children.link(dup_child)
        child_map = duplicate_collection(child, dup_child)
        obj_map.update(child_map)

    # 3. 親子関係を再接続
    for src_obj, dup_obj in obj_map.items():
        if src_obj.parent in obj_map:
            dup_obj.parent = obj_map[src_obj.parent]
            dup_obj.parent_type = src_obj.parent_type
            if hasattr(src_obj, "parent_bone"):
                dup_obj.parent_bone = src_obj.parent_bone
            dup_obj.matrix_parent_inverse = src_obj.matrix_parent_inverse.copy()

    return obj_map


    
class VIEW3D_PT_cam_control(Panel):
    bl_label = "Cam Control"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Camera"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        box = layout.box()
        row = box.row()
        row.scale_y = 3.0
        row.operator('camera.add', text="カメラを作成")

        if obj and obj.type == 'CAMERA':
            layout.prop(obj.data, "lens", text="画角")
            layout.operator("object.camera_viewfollow", text="ビューに固定")

            props = context.scene.cam_control_props
            layout.label(text="基点軸:")
            layout.prop(props, "axis_mode", expand=True)
            if props.control_mode == 'MOVE':
                layout.prop(props, "move_distance")
            else:
                layout.prop(props, "rotate_angle")
            layout.prop(props, "control_mode", expand=True)

            box = layout.box()
            box.label(text=props.control_mode)

            col = box.column(align=True)

                
            if props.control_mode == 'MOVE':
                if props.axis_mode == 'LOCAL':
                    col.operator("camera.move_direction", text="上").direction = 'FORWARD'

                    row = col.row(align=True)
                    row.operator("camera.move_direction", text="左").direction = 'RIGHT'
                    row.operator("camera.move_direction", text="右").direction = 'LEFT'

                    col.operator("camera.move_direction", text="下").direction = 'BACKWARD'
                    col.operator("camera.move_direction", text="前").direction = 'DOWN'
                    col.operator("camera.move_direction", text="後").direction = 'UP'
                else:
                    col.operator("camera.move_direction", text="上").direction = 'UP'
                    col.operator("camera.move_direction", text="△").direction = 'YPLUS'
                    row = col.row(align=True)
                    row.operator("camera.move_direction", text="◁").direction = 'LEFT'
                    row.operator("camera.move_direction", text="▷").direction = 'RIGHT'
                    col.operator("camera.move_direction", text="▽").direction = 'YMINUS'
                    col.operator("camera.move_direction", text="下").direction = 'DOWN'
            else:
                col.label(text="上下回転 (X軸):")
                row = col.row(align=True)
                op = row.operator("camera.rotate_axis", text="▽")
                op.axis = 'X'
                op.direction = -1.0
                op = row.operator("camera.rotate_axis", text="△")
                op.axis = 'X'
                op.direction = 1.0

                col.label(text="Z軸回転:")
                row = col.row(align=True)
                op = row.operator("camera.rotate_axis", text="◁")
                op.axis = 'Z'
                op.direction = 1.0
                op = row.operator("camera.rotate_axis", text="▷")
                op.axis = 'Z'
                op.direction = -1.0

                col.label(text="ロール (Y軸):")
                row = col.row(align=True)
                op = row.operator("camera.rotate_axis", text="◁")
                op.axis = 'Y'
                op.direction = -1.0
                op = row.operator("camera.rotate_axis", text="▷")
                op.axis = 'Y'
                op.direction = 1.0
                    
class Camera_ViewFollow(bpy.types.Operator):
    bl_idname = "object.camera_viewfollow"
    bl_label = "Lock the camera to the view."
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        area = next((a for a in context.screen.areas if a.type == 'VIEW_3D'), None)
        if not area:
            self.report({'WARNING'}, "The 3D Viewport could not be found.")
            return {'CANCELLED'}
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                space.lock_camera = not space.lock_camera
                return {'FINISHED'}
        self.report({'ERROR'}, "failed")
        return {'CANCELLED'}

    bl_label = "Over Scan"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Camera"

    def draw(self, context):
        layout = self.layout
        cam = context.scene.camera
        if not cam or cam.type != 'CAMERA':
            layout.label(text="No camera selected.")
            return
        props = cam.data.overscan_props
        layout.prop(props, "scale_x")
        if not props.lock_ratio:
            layout.prop(props, "scale_y")
        layout.prop(props, "lock_ratio")
        layout.operator(
            "camera.apply_overscan",
            text="Apply Overscan"
        )
        layout.operator(
            "camera.reset_overscan",
            text="Reset Overscan"
        )

class VIEW3D_PT_viewport_camera_lens(Panel):
    bl_label = "Viewport Camera Lens"
    bl_idname = "VIEW3D_PT_viewport_camera_lens"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Camera"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        space = context.space_data
        layout.prop(space, "lens", text="画角")

class VIEW3D_PT_resolution_settings(Panel):
    bl_label = "Resolution Settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Camera"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.prop(
            scene, "new_setting_res_x",
            text="解像度 X"
        )
        layout.prop(
            scene, "new_setting_res_y",
            text="解像度 Y"
        )

class Camera_viewpoint_btn(Operator):
    bl_idname = 'camera.add'
    bl_label = 'カメラを作成'
    bl_options = {'REGISTER'}

    camera_name: StringProperty(name="Camera Name", default="C000_Camera")
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
        scene = context.scene
        if scene.scene_settings:
            max_id = max(item.id for item in scene.scene_settings)
            self.scene_setting_id = scene.scene_settings_index + 1
            self.__class__.scene_setting_id.min = 1
            self.__class__.scene_setting_id.max = max_id
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        camera_data = bpy.data.cameras.new(name=self.camera_name)
        cam_obj = bpy.data.objects.new(self.camera_name, camera_data)
        col = bpy.data.collections.get(self.camera_name)
        if not col:
            col = bpy.data.collections.new(self.camera_name)
            context.scene.collection.children.link(col)
            
        col.objects.link(cam_obj)
        context.scene.camera = cam_obj

        bpy.ops.view3d.camera_to_view()
        
        sx = context.scene.new_setting_res_x
        sy = context.scene.new_setting_res_y
        cam_obj.resolution_xy = (sx, sy)

        return {'FINISHED'}

# ---------------------------------------------------
# overscan
# ---------------------------------------------------
class OverScanCamera(Operator):
    bl_idname = "scene.over_scan_camera"
    bl_label = "Bake to New Camera"

    @classmethod
    def poll(cls, context):
        active_cam = getattr(context.scene, "camera", None)
        return active_cam is not None

    def execute(self, context):
        active_cam = getattr(context.scene, "camera", None)
        try:
            if active_cam and active_cam.type == 'CAMERA':
                cam_obj = active_cam.copy()
                cam_obj.data = active_cam.data.copy()
                cam_obj.name = "Camera_Overscan"
                context.collection.objects.link(cam_obj)
        except:
            self.report({'WARNING'})
            return {'CANCELLED'}

        return {'FINISHED'}


def ResolutionUpdate(self, context):
    scene = context.scene
    overscan = scene.camera_overscan
    render_settings = scene.render
    active_camera = getattr(scene, "camera", None)
    active_cam = getattr(active_camera, "data", None)

    if not active_cam or active_camera.type not in {'CAMERA'}:
        return None

    if overscan.RO_Activate:
        
        if overscan.RO_Safe_SensorSize == -1:
            overscan.RO_Safe_Res_X = render_settings.resolution_x
            overscan.RO_Safe_Res_Y = render_settings.resolution_y
            overscan.RO_Safe_SensorSize = active_cam.sensor_width
            overscan.RO_Safe_SensorFit = active_cam.sensor_fit

        if overscan.RO_Custom_Res_X == 0 or overscan.RO_Custom_Res_Y == 0:
            if overscan.RO_Custom_Res_X != render_settings.resolution_x:
                overscan.RO_Custom_Res_X = render_settings.resolution_x
            if overscan.RO_Custom_Res_Y != render_settings.resolution_y:
                overscan.RO_Custom_Res_Y = render_settings.resolution_y

        active_cam.sensor_width = scene.camera_overscan.RO_Safe_SensorSize
        sensor_size_factor = overscan.RO_Custom_Res_X / overscan.RO_Safe_Res_X
        Old_SensorSize = active_cam.sensor_width
        New_SensorSize = Old_SensorSize * sensor_size_factor

        active_cam.sensor_width = New_SensorSize
        render_settings.resolution_x = overscan.RO_Custom_Res_X
        render_settings.resolution_y = overscan.RO_Custom_Res_Y

    else:
        if overscan.RO_Safe_SensorSize != -1:
            render_settings.resolution_x = overscan.RO_Safe_Res_X
            render_settings.resolution_y = overscan.RO_Safe_Res_Y
            active_cam.sensor_width = overscan.RO_Safe_SensorSize
            active_cam.sensor_fit = overscan.RO_Safe_SensorFit
            overscan.RO_Safe_SensorSize = -1


def RO_Menu(self, context):
    scene = context.scene
    overscan = scene.camera_overscan
    active_cam = getattr(scene, "camera", None)
    layout = self.layout

    if active_cam and active_cam.type == 'CAMERA':
        col = layout.column(align=True)
        col.prop(overscan, "RO_Custom_Res_X", text="OS X")
        col.prop(overscan, "RO_Custom_Res_Y", text="OS Y")
    else:
        col = layout.column()
        col.label(text="No active Camera type in the Scene", icon='INFO')

class camera_overscan_props(PropertyGroup):
    RO_Activate: BoolProperty(
                        default=False,
                        update=ResolutionUpdate
                        )
    RO_Custom_Res_X: IntProperty(
                        default=0,
                        min=4,
                        max=65536,
                        subtype='PIXEL',
                        update=ResolutionUpdate
                        )
    RO_Custom_Res_Y: IntProperty(
                        default=0,
                        min=4,
                        max=65536,
                        subtype='PIXEL',
                        update=ResolutionUpdate
                        )
    RO_Safe_Res_X: FloatProperty()
    RO_Safe_Res_Y: FloatProperty()

    RO_Safe_SensorSize: FloatProperty(
                        default=-1,
                        min=-1,
                        max=65536
                        )
    RO_Safe_SensorFit: StringProperty()

class VIEW3D_PT_OSpanel(Panel):
    bl_label = "OverScan"
    bl_idname = "VIEW3D_PT_OSpanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Camera'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        overscan = scene.camera_overscan
        active_cam = getattr(scene, "camera", None)

        if active_cam and active_cam.type == 'CAMERA':
            col = layout.column(align=True)
            col.prop(overscan, "RO_Activate", text="Overscanを有効化")

            if overscan.RO_Activate:
                col.prop(overscan, "RO_Custom_Res_X", text="解像度 X")
                col.prop(overscan, "RO_Custom_Res_Y", text="解像度 Y")
        else:
            layout.label(text="No active Camera in the Scene", icon='INFO')

# ---------------------------------------------------
# eye_level_circle
# ---------------------------------------------------
def create_eye_level_circle(cam):
    name = "EyeLevelCircle"
    if bpy.data.objects.get(name):
        return
    bpy.ops.curve.primitive_bezier_circle_add(
        enter_editmode=False,
        radius=0.23,
        align='WORLD'
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.data.dimensions = '2D'
    obj.data.resolution_u = 3
    obj.data.extrude = 0.00005

    mat = bpy.data.materials.get("EyeLevelCircleMat")
    if mat is None:
        mat = bpy.data.materials.new("EyeLevelCircleMat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    for n in list(nodes):
        nodes.remove(n)
    rgb = nodes.new(type="ShaderNodeRGB")
    rgb.outputs['Color'].default_value = (1.0, 0.0, 0.0, 1.0)
    out = nodes.new(type="ShaderNodeOutputMaterial")
    links.new(rgb.outputs['Color'], out.inputs['Surface'])
    obj.data.materials.clear()
    obj.data.materials.append(mat)

    c = obj.constraints.new(type='COPY_LOCATION')
    c.target = cam

    obj.show_in_front = True
    obj.hide_select = True

    bpy.context.view_layer.objects.active = cam
    cam.select_set(True)
 
def remove_eye_level_circle():
    circle = bpy.data.objects.get("EyeLevelCircle")
    if circle:
        bpy.data.objects.remove(circle, do_unlink=True)

class CAMERA_OT_toggle_eyelevel(bpy.types.Operator):
    bl_idname = "camera.toggle_eyelevel"
    bl_label = "Toggle EyeLevel Box"
    bl_description = "Add or remove the EyeLevelBox to/from the active camera, and set or clear a Boolean property on the camera."

    def execute(self, context):
        cam = context.scene.camera
        if not cam:
            self.report({'ERROR'}, "There is no active camera.")
            return {'CANCELLED'}

        if cam.get("EyeLevel"):
            del cam["EyeLevel"]
            remove_eye_level_circle()
        else:
            cam["EyeLevel"] = True
            create_eye_level_circle(cam)
        return {'FINISHED'}

# ---------------------------------------------------
# resolution
# ---------------------------------------------------
class SCENE_OT_camera_resolution_add(Operator):
    bl_idname = "camera_resolution.add"
    bl_label = "Save Resolution to Camera"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        cam = context.scene.camera
        if not cam or cam.type != 'CAMERA':
            self.report({'ERROR'}, "No active camera.")
            return {'CANCELLED'}
        cam.resolution_xy = (
            context.scene.new_setting_res_x,
            context.scene.new_setting_res_y
        )
        self.report(
            {'INFO'},
            f"Saved {cam.resolution_xy[0]}×{cam.resolution_xy[1]} to {cam.name}"
        )
        return {'FINISHED'}

class SCENE_OT_camera_resolution_remove(Operator):
    bl_idname = "camera_resolution.remove"
    bl_label = "Reset Camera Resolution"

    def execute(self, context):
        cam = context.scene.camera
        if not cam or cam.type != 'CAMERA':
            self.report({'ERROR'}, "No active camera.")
            return {'CANCELLED'}
        cam.resolution_xy = (1632, 918)
        self.report(
            {'INFO'},
            f"Reset resolution of {cam.name} to default"
        )
        return {'FINISHED'}
    
# -------------------------------------------------------------------
# rocal/world switch
# -------------------------------------------------------------------
class CamControlProperties(PropertyGroup):
    axis_mode: EnumProperty(
        name="Axis Mode",
        description="Choose World or Local axis",
        items=[
            ('WORLD', "ワールド軸", "Use World Axis"),
            ('LOCAL', "ローカル軸", "Use Local Axis"),
        ],
        default='WORLD'
    )
    move_distance: FloatProperty(
        name="移動距離",
        description="Distance to move the camera",
        default=0.01,
        min=0.001,
        max=0.1,
        subtype='PERCENTAGE'
    )
    rotate_angle: FloatProperty(
        name="回転強度",
        description="Degrees to rotate the camera",
        default=1.0,
        min=0.1,
        max=5.0
    )
    control_mode: EnumProperty(
        name="操作モード",
        description="移動か回転を選択",
        items=[
            ('MOVE', "移動", "Move the camera"),
            ('ROTATE', "回転", "Rotate the camera"),
        ],
        default='MOVE'
    )
 
# -------------------------------------------------------------------
# move Cam operator
# -------------------------------------------------------------------
class CAMERA_OT_move_direction(Operator):
    bl_idname = "camera.move_direction"
    bl_label = "Move Camera"

    direction: EnumProperty(
        items=[
            ('UP', "Up", "Move Up"),
            ('DOWN', "Down", "Move Down"),
            ('LEFT', "Left", "Move Left"),
            ('RIGHT', "Right", "Move Right"),
            ('FORWARD', "Forward", "Move Forward (Local Y+)"),
            ('BACKWARD', "Backward", "Move Backward (Local Y-)"),
            ('YPLUS', "Y+", "Move along Y+ (World)"),
            ('YMINUS', "Y-", "Move along Y- (World)")
        ]
    )

    def execute(self, context):
        obj = context.active_object
        props = getattr(context.scene, "cam_control_props", None)
        if not props:
            self.report({'ERROR'}, "cam_control_props が初期化されていません。")
            return {'CANCELLED'}
        if not obj or obj.type != 'CAMERA':
            self.report({'WARNING'}, "No camera selected")
            return {'CANCELLED'}
        
        d = props.move_distance
        vec_map = {
            'UP': (0, 0, d),
            'DOWN': (0, 0, -d),
            'LEFT': (d, 0, 0),
            'RIGHT': (-d, 0, 0),
            'FORWARD': (0, d, 0),
            'BACKWARD': (0, -d, 0),
            'YPLUS': (0, -d, 0),
            'YMINUS': (0, +d, 0),
        }
        move_vec = mathutils.Vector(vec_map[self.direction])
        if props.axis_mode == 'LOCAL' and self.direction not in ['YPLUS', 'YMINUS']:
            move_vec = obj.matrix_world.to_3x3() @ move_vec
        obj.location += move_vec
        return {'FINISHED'}

# -------------------------------------------------------------------
# move Cam operator
# -------------------------------------------------------------------
class CAMERA_OT_apply_rotation(Operator):
    bl_idname = "camera.apply_rotation"
    bl_label = "Apply Rotation Increment"

    def execute(self, context):
        obj = context.active_object
        props = context.scene.cam_control_props

        if not obj or obj.type != 'CAMERA':
            self.report({'WARNING'}, "No camera selected")
            return {'CANCELLED'}

        obj.rotation_mode = 'XYZ'
        obj.rotation_euler[0] += props.rot_pitch
        obj.rotation_euler[2] += props.rot_pitch

        props.rot_pitch = 0.0
        props.rot_yaw = 0.0
        props.rot_roll = 0.0

        obj.update_tag()
        context.view_layer.update()
        
        return {'FINISHED'}
    
class CAMERA_OT_rotate_axis(Operator):
    bl_idname = "camera.rotate_axis"
    bl_label = "Rotate Camera Axis"

    axis: EnumProperty(
        name="Axis",
        items=[
            ('X', "X", "Rotate around X Axis"),
            ('Y', "Y", "Rotate around Y Axis (Roll)"),
            ('Z', "Z", "Rotate around Z Axis")
        ]
    )

    direction: FloatProperty(default=1.0)  # +1 or -1

    def execute(self, context):
        obj = context.active_object
        props = context.scene.cam_control_props
        if not obj or obj.type != 'CAMERA':
            self.report({'WARNING'}, "No camera selected")
            return {'CANCELLED'}

        obj.rotation_mode = 'XYZ'
        angle_rad = math.radians(props.rotate_angle) * self.direction

        if self.axis == 'X':
            obj.rotation_euler.x += angle_rad
        elif self.axis == 'Y':
            obj.rotation_euler.y += angle_rad
        elif self.axis == 'Z':
            obj.rotation_euler.z += angle_rad
        obj.update_tag()
        context.view_layer.update()
        
        return {'FINISHED'}

# ---------------------------------------------------
# Contoll Collection
# ---------------------------------------------------

class OBJECT_OT_separate_objects(bpy.types.Operator):
    bl_idname = "object.separate_objects"
    bl_label = "Separate Objects"
    bl_description = (
        "Duplicate the selected object and assign a Switch CollectionX property for the active camera."
    )
    bl_options = {'REGISTER', 'UNDO'}

    change_color: BoolProperty(
        name="色を変更しますか？",
        default=False
    )
    color: FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        size=3,
        min=0.0,
        max=1.0,
        default=(1.0, 0.8, 0.2)
    )
    book_n: IntProperty(
        name="Bookの設定",
        description="Book番号を指定",
        default=1,
        min=0
    )


    def draw(self, context):
        layout = self.layout
        layout.prop(self, "change_color")
        if self.change_color:
            layout.prop(self, "color", text="Color")
        layout.prop(self, "book_n", text="Bookの設定")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        bpy.ops.outliner.orphans_purge(do_recursive=True)

        scene = context.scene
        cam = scene.camera
        if not cam:
            self.report({'ERROR'}, "There is no active camera.")
            return {'CANCELLED'}

        # カメラ名のコレクション（親）を取得または作成
        cam_col = bpy.data.collections.get(cam.name)
        if not cam_col:
            cam_col = bpy.data.collections.new(cam.name)
            scene.collection.children.link(cam_col)

        # Bookコレクションの取得または作成
        book_col_name = f"{cam_col.name} Book {self.book_n}"
        book_col = bpy.data.collections.get(book_col_name)
        if not book_col:
            book_col = bpy.data.collections.new(book_col_name)
            cam_col.children.link(book_col)

        count = 0
        for obj in context.selected_objects:
            # ▼ 元の親コレクションを取得
            parent_col = obj.users_collection[0] if obj.users_collection else None
            if not parent_col:
                parent_col = scene.collection  # シーンルートに退避

            # ▼ 元オブジェクト名のサブコレクションを作成（すでに存在していない場合）
            src_coll_name = obj.name
            src_coll = bpy.data.collections.get(src_coll_name)
            if not src_coll:
                src_coll = bpy.data.collections.new(src_coll_name)
                parent_col.children.link(src_coll)

            # ▼ オブジェクトを他のコレクションからアンリンク（※重複リンク防止）
            for c in obj.users_collection:
                try:
                    c.objects.unlink(obj)
                except:
                    pass
            if obj.name not in src_coll.objects:
                src_coll.objects.link(obj)

            # ▼ カスタムプロパティをコレクションに付与
            existing_idxs = sorted(
                int(k.replace("Switch Collection", "").split('_')[0])
                for k in src_coll.keys() if k.startswith("Switch Collection")
            )
            next_idx = existing_idxs[-1] + 1 if existing_idxs else 1
            uid = uuid.uuid4().hex[:8]
            prop_key = f"Switch Collection{next_idx}_{uid}"
            src_coll[prop_key] = cam.name

            # ▼ 複製処理
            dup = obj.copy()
            if obj.data:
                dup.data = obj.data.copy()

            # ▼ Bookコレクションにリンク
            book_col.objects.link(dup)

            # ▼ Bookコレクションにもプロパティを付与（識別用）
            if prop_key not in book_col.keys():
                book_col[prop_key] = cam.name

            # ▼ カラー変更オプション
            if self.change_color:
                mat = (dup.active_material.copy() if dup.active_material else bpy.data.materials.new(f"Mat_{dup.name}"))
                mat.diffuse_color = (*self.color, 1.0)
                dup.data.materials.clear()
                dup.data.materials.append(mat)

            count += 1

        # ▼ Book内すべてに統一マテリアル適用（必要であれば）
        if self.change_color:
            mat_name = f"Mat_{book_col.name}"
            mat = bpy.data.materials.new(mat_name)
            mat.diffuse_color = (*self.color, 1.0)
            for o in book_col.objects:
                if hasattr(o.data, "materials"):
                    o.data.materials.clear()
                    o.data.materials.append(mat)

        self.report({'INFO'}, f"{count} object(s) processed and structured with collections.")
        return {'FINISHED'}


# ---------------------------------------------------
# Walk_Navigation_Panel
# ---------------------------------------------------
class WalkNavigation_Panel(bpy.types.Panel):
    bl_label = "Walk_Navigation"
    bl_idname = "VIEW3D_PT_walk_navigation"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Camera'
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="TABキーでFREEモード")        
        layout.operator("view3d.activate_walk_navigation", text="ウォークスルーモード")

def activate_walk_navigation(self, context):
    saved_area_type = bpy.context.area.type
    bpy.ops.view3d.walk('INVOKE_DEFAULT')
    
class OBJECT_OT_ActivateWalkNavigation(bpy.types.Operator):
    bl_label = "activate_walk_navigation"
    bl_idname = "view3d.activate_walk_navigation"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        activate_walk_navigation(self, context)
        return {'FINISHED'}

# ---------------------------------------------------
# frame_image
# ---------------------------------------------------
def get_bg_image(cam_data):
    if cam_data.background_images:
        return cam_data.background_images[0]
    return None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

class VIEW3D_PT_add_frame(Panel):
    bl_label = "Add Frame"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Camera"

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'CAMERA'

    def draw(self, context):
        layout = self.layout
        obj = context.object
        cam = context.scene.camera
        cam_data = obj.data

        layout.operator("camera.add_frame_image", text="フレームを追加")
        label = "アイレベルを削除" if cam and cam.get("EyeLevel") else "アイレベルを追加"
        layout.operator("camera.toggle_eyelevel", text=label)
        
        if cam.get("EyeLevel"):
            box = layout.box()
            box.label(text="👁️ アイレベル追加済")

        if not cam_data.show_background_images or not cam_data.background_images:
            layout.label(text="No background images")
            return

        layout.separator()

        for idx, bg in enumerate(cam_data.background_images):
            box = layout.box()
            box.label(text=f"フレーム {idx + 1}", icon='IMAGE_DATA')
            row = box.row()
            row.prop(bg, 'show_background_image', text="有効")
            row.label(text=bg.image.name if bg.image else "No Image")

            col = box.column(align=True)
            col.prop(bg, 'offset', index=0, text='オフセット X')
            col.prop(bg, 'offset', index=1, text='オフセット Y')
            col.prop(bg, 'scale', text='スケール')
            col.prop(bg, 'alpha', text='アルファ')

            op = col.operator("camera.remove_frame_image", text="このフレームを削除")
            op.index = idx

class CAMERA_OT_add_frame_image(Operator):
    bl_idname = "camera.add_frame_image"
    bl_label = "Add Frame Image"

    def execute(self, context):

        cam = context.scene.camera
        if not cam or cam.type != 'CAMERA':
            self.report({'ERROR'}, "There is no active camera.")
            return {'CANCELLED'}
        cam_data = cam.data
        cam_data.show_background_images = True

        image_path = os.path.join(SCRIPT_DIR, "Frame.png")
        image = bpy.data.images.get("Frame.png")
        if not image:
            try:
                image = bpy.data.images.load(image_path)
                image.name = "Frame.png"
            except Exception as e:
                self.report({'ERROR'}, f"Frame.png Failed to load: {e}")
                return {'CANCELLED'}

        bg = cam_data.background_images.new()
        bg.image = image
        bg.alpha = 0.9
        bg.display_depth = 'FRONT'
        bg.frame_method = 'CROP'
        bg.show_background_image = True
        bg.offset = (0.0, 0.0)
        bg.scale = 1.0

        return {'FINISHED'}

class CAMERA_OT_remove_frame_image(Operator):
    bl_idname = "camera.remove_frame_image"
    bl_label = "Remove Frame Image"

    index: IntProperty()

    def execute(self, context):
        obj = context.object
        cam_data = obj.data
        bg_list = cam_data.background_images

        if 0 <= self.index < len(bg_list):
            target = bg_list[self.index]
            bg_list.remove(target)
            if len(bg_list) > 0:
                bg_list[0].show_background_image = False
                bg_list[0].show_background_image = True
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Invalid background image index")
            return {'CANCELLED'}

# ---------------------------------------------------
# Rendering properties
# ---------------------------------------------------
class VIEW3D_PT_render_adjust(Panel):
    bl_label = "Rendering"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Camera"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.scene.camera and context.scene.camera.type == 'CAMERA'

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        row = box.row()
        row.scale_y = 3.0
        row.operator(
            "camera.apply_transform_from_bg",
            text="レンダリング",
        )

class CAMERA_OT_apply_transform_from_bg(Operator):
    bl_idname = "camera.apply_transform_from_bg"
    bl_label = "Apply Transform From BG"
    
    def calculate_s(x, y):
        aspect = x / y
        threshold = 1632 / 918

        if x > 1632 and aspect > threshold:
            return 1.0 + (x - 1632) / (2100 - 1632) * (1.2865 - 1.0)
        if y <= 918:
            return 1.0
        elif y <= 1632:
            return 1.0 + (y - 918) / (1632 - 918) * (1.7778 - 1.0)
        else:
            return 1.78 + (y - 1632) / (1900 - 1632) * (2.069 - 1.78)

    def execute(self, context):
        scene = context.scene
        camera = scene.camera
        cam_data = camera.data

        res_x = scene.render.resolution_x
        res_y = scene.render.resolution_y

        scene.use_nodes = True
        tree  = scene.node_tree
        nodes = tree.nodes
        links = tree.links

        if not tree.get("composite_setup_done", False):
            for n in list(nodes):
                nodes.remove(n)
            rl = nodes.new(type='CompositorNodeRLayers')
            rl.label    = 'Render Layers'
            rl.location = (0, 0)

            alpha_nodes = []
            for i in range(1, 6):
                x = 300 * i

                img = nodes.new(type='CompositorNodeImage')
                img.label    = f"{i}_Frame.png"
                img.image    = bpy.data.images.get("Frame.png")
                img.location = (x, 200)

                tr = nodes.new(type='CompositorNodeTransform')
                tr.label    = f"{i}_Frame Transform"
                tr.location = (x, 0)
                tr.filter_type  = "BICUBIC"
                links.new(img.outputs['Image'], tr.inputs['Image'])

                ao = nodes.new(type='CompositorNodeAlphaOver')
                ao.label          = f"{i}_Alpha Over"
                ao.use_premultiply = False
                ao.premul = 1
                ao.location = (x, -200)
                ao.inputs[0].default_value = 1.0

                links.new(tr.outputs['Image'],    ao.inputs[2])
                links.new(rl.outputs['Image'],    ao.inputs[1])

                alpha_nodes.append(ao)

            mix_nodes = []
            for m in range(1, 5):
                mx = nodes.new(type='CompositorNodeMixRGB')
                mx.label        = f"cmp{m}"
                mx.blend_type   = 'DARKEN'
                mx.inputs['Fac'].default_value = 1.0
                mx.location     = (300 * m, -400)

                src1 = alpha_nodes[m-1].outputs['Image'] if m == 1 else mix_nodes[-1].outputs['Image']
                links.new(src1,mx.inputs[1])
                links.new(alpha_nodes[m].outputs['Image'], mx.inputs[2])
                mix_nodes.append(mx)

            final = mix_nodes[-1].outputs['Image']
            comp = nodes.new(type='CompositorNodeComposite')
            comp.location = (1000, -400)
            links.new(final, comp.inputs['Image'])

            for idx, vx in enumerate((1200, 1400), start=1):
                vw = nodes.new(type='CompositorNodeViewer')
                vw.location = (vx, -400)
                links.new(final, vw.inputs['Image'])
        tree["composite_setup_done"] = True

        max_frame_number = 6

        for idx in range(max_frame_number):
            prefix = str(idx + 1)

            transform_node = next(
                (n for n in nodes if n.type == 'TRANSFORM' and n.label == f"{prefix}_Frame Transform"), None)
            alpha_node = next(
                (n for n in nodes if n.type == 'ALPHAOVER' and n.label == f"{prefix}_Alpha Over"), None)

            if not alpha_node:
                continue

            if idx < len(cam_data.background_images):
                bg_image = cam_data.background_images[idx]
                if bg_image.show_background_image:
                    if not transform_node:
                        self.report({'WARNING'}, f"Transform node number{prefix}could not be found.")
                        continue

                    offset_x = bg_image.offset[0]
                    offset_y = bg_image.offset[1]
                    scale = bg_image.scale
                    alpha = bg_image.alpha

                    px_offset_x = offset_x * res_x
                    px_offset_y = (offset_y * res_x / 0.889) / 2

                    base_scale = self.__class__.calculate_s(res_x, res_y)
                    final_scale = base_scale * scale

                    transform_node.inputs[1].default_value = px_offset_x
                    transform_node.inputs[2].default_value = px_offset_y
                    transform_node.inputs[4].default_value = final_scale
                    alpha_node.inputs[0].default_value = alpha
                else:
                    alpha_node.inputs[0].default_value = 0.0
            else:
                alpha_node.inputs[0].default_value = 0.0

        bpy.ops.render.render(use_viewport=True)
        bpy.ops.render.view_show('INVOKE_DEFAULT')
        self.report({'INFO'}, "レンダリング完了")
        return {'FINISHED'}

# ---------------------------------------------------
# Registration of custom properties
# ---------------------------------------------------

def register_props():
    bpy.types.Scene.camera_list = CollectionProperty(type=CameraItem)
    bpy.types.Scene.camera_index = IntProperty(
        name="Camera Index",
        default=0,
        min=0,
        update=update_camera
    )
    bpy.types.Scene.new_setting_res_x = IntProperty(
        name="X",
        default=1632,
        min=1,
        update=update_new_res_x
    )
    bpy.types.Scene.new_setting_res_y = IntProperty(
        name="Y",
        default=918,
        min=1,
        update=update_new_res_y
    )
    bpy.types.Object.resolution_xy = IntVectorProperty(
        name="Camera Resolution",
        size=2,
        default=(1632, 918),
        min=1
    )
    bpy.types.Scene.cam_control_props = PointerProperty(type=CamControlProperties)
    bpy.types.Scene.camera_overscan = PointerProperty(type=camera_overscan_props)
    bpy.types.Scene.switch_coll_list = CollectionProperty(type=SwitchCollItem)
    bpy.types.Scene.switch_coll_index = IntProperty(default=0, min=0)

def unregister_props():
    del bpy.types.Scene.camera_list
    del bpy.types.Scene.camera_index
    del bpy.types.Scene.new_setting_res_x
    del bpy.types.Scene.new_setting_res_y
    del bpy.types.Object.resolution_xy
    del bpy.types.Scene.cam_control_props
    del bpy.types.Scene.camera_overscan
    del bpy.types.Scene.switch_coll_list
    del bpy.types.Scene.switch_coll_index

# ---------------------------------------------------
# Class registration
# ---------------------------------------------------
classes = (
    CameraItem,
    SCENE_UL_camera_list,
    VIEW3D_PT_camera_switcher,
    SwitchCollItem, 
    SCENE_UL_switch_coll_list,
    OBJECT_OT_refresh_switch_list, 
    OBJECT_OT_delete_switch_collection,
    OBJECT_OT_copy_layer,
    VIEW3D_PT_cam_control,
    Camera_viewpoint_btn,
    VIEW3D_PT_viewport_camera_lens,
    VIEW3D_PT_resolution_settings,
    SCENE_OT_camera_resolution_add,
    SCENE_OT_camera_resolution_remove,
    Camera_ViewFollow,
    OverScanCamera,
    camera_overscan_props,
    VIEW3D_PT_OSpanel,
    WalkNavigation_Panel,
    OBJECT_OT_ActivateWalkNavigation,
    VIEW3D_PT_add_frame,
    CAMERA_OT_add_frame_image,
    CAMERA_OT_remove_frame_image,
    CAMERA_OT_toggle_eyelevel,
    VIEW3D_PT_render_adjust,
    CAMERA_OT_apply_transform_from_bg,
    CamControlProperties,
    CAMERA_OT_move_direction,
    CAMERA_OT_rotate_axis,
    OBJECT_OT_separate_objects,
)

@persistent
def _depsgraph_handler(depsgraph):
    for scene in bpy.data.scenes:
        update_camera_list(scene)
        scene.new_setting_res_x = scene.render.resolution_x
        scene.new_setting_res_y = scene.render.resolution_y
        cam = scene.camera
        if cam and hasattr(cam, "resolution_xy"):
            cam.resolution_xy = (
                scene.render.resolution_x,
                scene.render.resolution_y
            )
        ov = getattr(scene, "camera_overscan", None)
        if ov and ov.RO_Activate:
            ov.RO_Custom_Res_X = scene.render.resolution_x
            ov.RO_Custom_Res_Y = scene.render.resolution_y
        
def _deferred_init():
    for scene in bpy.data.scenes:
        update_camera_list(scene)
    return None
        
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    register_props()
    bpy.app.handlers.depsgraph_update_post.append(_depsgraph_handler)
    bpy.app.timers.register(_deferred_init, first_interval=0.1)

def unregister():
    if _depsgraph_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_handler)
    unregister_props()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()