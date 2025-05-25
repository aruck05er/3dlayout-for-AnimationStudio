import bpy
import os
from bpy.props import StringProperty, EnumProperty, CollectionProperty, IntProperty
from bpy.types import PropertyGroup, Operator, Panel, UIList

def filter_top_level(imported):
    top = []
    for col in imported:
        if not any(col.name in [c.name for c in parent.children] for parent in imported):
            top.append(col)
    for col in imported:
        if col not in top:
            try:
                for parent in bpy.data.collections:
                    if col in parent.children:
                        parent.children.unlink(col)
                bpy.data.collections.remove(col)
            except Exception:
                pass
    return top

def find_layer_collection(layer_coll, target_name):
    if layer_coll.collection.name == target_name:
        return layer_coll
    for child in layer_coll.children:
        found = find_layer_collection(child, target_name)
        if found:
            return found
    return None

def get_camera_layer_collection(view_layer):
    cam = bpy.context.scene.camera
    if cam and cam.name in bpy.data.collections:
        def recurse(lc):
            if lc.collection.name == cam.name:
                return lc
            for child in lc.children:
                result = recurse(child)
                if result:
                    return result
            return None
        found = recurse(view_layer.layer_collection)
        if found:
            return found
    return view_layer.layer_collection

def collect_override_layer_collections(layer_coll, result_list):
    coll = layer_coll.collection
    
    if getattr(coll, 'override_library', False):
        result_list.append(coll.name)
    for child in layer_coll.children:
        collect_override_layer_collections(child, result_list)

class FigureItem(PropertyGroup):
    name: StringProperty(name="Blend File Name")

class OverrideItem(PropertyGroup):
    name: StringProperty(name="Collection Name")

class Figure_OT_setup(Operator):
    bl_idname = "figure.setup"
    bl_label = "Set up Figure List"
    bl_description = "Scan the custom folder and list .blend files"

    def execute(self, context):
        wm = context.window_manager
        blend_folder = bpy.path.abspath(wm.figure_path)
        wm.figure_items.clear()
        if os.path.isdir(blend_folder):
            for f in sorted(os.listdir(blend_folder)):
                if f.lower().endswith('.blend'):
                    item = wm.figure_items.add()
                    item.name = os.path.splitext(f)[0]
            if wm.figure_items:
                wm.figure_list = wm.figure_items[0].name
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Invalid folder path")
            return {'CANCELLED'}

class Figure_OT_refresh_override_list(Operator):
    bl_idname = "figure.refresh_override_list"
    bl_label = "Refresh Armature List"
    bl_description = "Refresh list of collections under the active camera that contain armatures"
    
    def execute(self, context):
        wm = context.window_manager
        wm.override_items.clear()

        cam = context.scene.camera
        cam_coll = bpy.data.collections.get(cam.name) if cam and cam.name in bpy.data.collections else context.scene.collection

        names = []
        for col in cam_coll.children:
            if any(o.type == 'ARMATURE' for o in col.objects):
                names.append(col.name)
        for name in sorted(names):
            item = wm.override_items.add()
            item.name = name

        wm.override_index = 0
        return {'FINISHED'}

def override_selection_update(self, context):
    wm = context.window_manager
    idx = wm.override_index
    if idx < 0 or idx >= len(wm.override_items):
        return
    sel_name = wm.override_items[idx].name
    col = bpy.data.collections.get(sel_name)
    if not col:
        return

    bpy.ops.object.select_all(action='DESELECT')
    armatures = [o for o in col.objects if o.type == 'ARMATURE']
    if armatures:
        for o in armatures:
            o.select_set(True)
            context.view_layer.objects.active = o
            active_arm = armatures[0]
            wm.armature_height_cm = round(active_arm.dimensions.z * 100)
    else:
        for o in col.objects:
            o.select_set(True)

class Figure_OT_add(Operator):
    bl_idname = "figure.add"
    bl_label = "Add Figure"
    bl_description = "Link all collections from the selected .blend file and store them in the active camera's collection"

    def execute(self, context):
        wm = context.window_manager

        if wm.figure_mode == 'DEFAULT':
            script_dir = os.path.dirname(__file__)
            blend_path = os.path.join(script_dir, "model", "Default_Figure.blend")
        else:
            name = wm.figure_list
            if not name:
                self.report({'ERROR'}, "No file selected in custom mode")
                return {'CANCELLED'}
            blend_path = os.path.join(bpy.path.abspath(wm.figure_path), name + ".blend")
            
        with bpy.data.libraries.load(blend_path, link=True) as (data_from, data_to):
            col_names = data_from.collections[:]
            
        if not os.path.isfile(blend_path):
            self.report({'ERROR'}, f"Blend file not found: {blend_path}")
            return {'CANCELLED'}

        with bpy.data.libraries.load(blend_path, link=True) as (data_from, data_to):
            col_names = data_from.collections[:]

        imported = []
        coll_dir = blend_path + "/Collection/"
        for cname in col_names:
            if not cname:
                continue
            try:
                bpy.ops.wm.link(
                    directory=coll_dir,
                    filename=cname,
                    relative_path=True,
                    autoselect=False,
                    active_collection=False,
                    instance_collections=False,
                    instance_object_data=True
                )
                col = bpy.data.collections.get(cname)
                if col:
                    imported.append(col)
            except Exception as e:
                self.report({'WARNING'}, f"Failed to link {cname}: {e}")

        cam = context.scene.camera
        if cam and cam.name in bpy.data.collections:
            cam_coll = bpy.data.collections[cam.name]
        else:
            cam_coll = context.scene.collection

        for col in imported:
            if col.name not in [c.name for c in cam_coll.children]:
                cam_coll.children.link(col)

        target_coll = bpy.data.collections.get(cam.name) if cam and cam.name in bpy.data.collections else context.scene.collection
        linked_data = bpy.data.collections.get('Linked Data')
        if linked_data:

            for obj in list(linked_data.objects):
                linked_data.objects.unlink(obj)
                target_coll.objects.link(obj)

            for parent in bpy.data.collections:
                if linked_data.name in parent.children:
                    parent.children.unlink(linked_data)
            bpy.data.collections.remove(linked_data)
        
        for coll in imported:
            lc = find_layer_collection(context.view_layer.layer_collection, coll.name)
            if lc:
                context.view_layer.active_layer_collection = lc
                break  
            
        override_and_remove_collection()
    
        return {'FINISHED'}

def update_armature_height(context):
    obj = context.active_object
    if obj and obj.type == 'ARMATURE':
        target_cm = context.window_manager.armature_height_cm
        if target_cm <= 0:
            return
        current_z = obj.dimensions.z
        if current_z <= 0:
            return
        scale_factor = (target_cm / 100.0) / current_z
        obj.scale *= scale_factor
        bpy.context.view_layer.update()
        bpy.ops.object.transforms_to_deltas(mode='ALL')
        
class Figure_UL_override_list(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(text=item.name)

class Figure_PT_panel(Panel):
    bl_label = "Figure"
    bl_idname = "Figure_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Model"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return hasattr(context.window_manager, "figure_mode")

    def draw(self, context):
        wm = context.window_manager
        layout = self.layout
        layout.prop(wm, "figure_mode", expand=True)
        if wm.figure_mode == 'CUSTOM':
            layout.prop(wm, "figure_path")
            layout.operator("figure.setup", text="Set up")
            if wm.figure_items:
                layout.prop(wm, "figure_list", text="Select .blend")
        layout.operator("figure.add", text="マネキンを追加")
        layout.separator()
        layout.label(text='List')
        layout.operator('figure.refresh_override_list', text='リスト更新')
        layout.template_list(
            'Figure_UL_override_list', '',
            wm, 'override_items',
            wm, 'override_index',
            rows=5
        )
        layout.operator('figure.delete_override', text='削除')

        obj = context.active_object
        if obj and obj.type == 'ARMATURE':
            layout.label(text="Figure Controll")
            row = layout.row(align=True)
            row.label(text=f"Mode: {obj.mode}")
            row = layout.row(align=True)
            row.operator("object.mode_set", text="ポーズモード").mode = 'POSE'
            row.operator("object.mode_set", text="オブジェクトモード").mode = 'OBJECT'
            layout.separator()
        
            layout.label(text="身長")
            layout.prop(context.window_manager, "armature_height_cm", text="身長 (cm)")

def init_props():
    wm = bpy.types.WindowManager
    wm.figure_mode = EnumProperty(
        name="Mode",
        items=[
            ('DEFAULT', "Default", "Use default figure.blend from addon folder"),
            ('CUSTOM',  "Custom",  "Use custom folder path"),
        ],
        default='DEFAULT'
    )
    wm.figure_path = StringProperty(
        name="Figure Path",
        description="Folder containing .blend files",
        subtype='DIR_PATH',
        default=""
    )
    wm.figure_items = CollectionProperty(type=FigureItem)
    wm.figure_list = EnumProperty(
        name="Blend Files",
        description="Choose a .blend file",
        items=lambda self, context: [
            (item.name, item.name, "") for item in context.window_manager.figure_items
        ] or [("", "None", "")],
    )
    wm.override_items = CollectionProperty(type=OverrideItem)
    wm.override_index = IntProperty(name="Index", default=0, min=0, update=override_selection_update)
    wm.armature_height_cm = IntProperty(
        name="身長",
        description="アーマチュアの身長（cm）",
        default=170,
        min=1,
        max=300,
        update=lambda self, ctx: update_armature_height(ctx)
    )


def clear_props():
    wm = bpy.types.WindowManager
    for p in ['figure_mode','figure_path','figure_items','figure_list','override_items','override_index']:
        if hasattr(wm,p): delattr(wm,p)

def override_and_remove_collection(
    lc=None,
    scene=None,
    view_layer=None,
    do_fully_editable: bool = True
):

    if scene is None:
        scene = bpy.context.scene
    if view_layer is None:
        view_layer = bpy.context.view_layer
    if lc is None:
        lc = view_layer.active_layer_collection.collection
    if not lc.library:
        print(f"'{lc.name}' is not linked, skipping.")
        return False

    original_name = lc.name
    new_override = lc.override_hierarchy_create(
        scene,
        view_layer,
        do_fully_editable=do_fully_editable
    )
    if not new_override:
        new_override = scene.collection.children.get(original_name) \
            or bpy.data.collections.get(original_name)
    print(f"Created override: {original_name} → {new_override.name}")

    parent = None
    
    if new_override.name in [c.name for c in scene.collection.children]:
        parent = scene.collection
    else:
        for col in bpy.data.collections:
            if new_override.name in [c.name for c in col.children]:
                parent = col
                break
    if parent is None:
        parent = scene.collection

    siblings = [c.name for c in parent.children if c is not new_override]

    n = 1
    while True:
        cand = f"{original_name}_{n}"
        if cand not in siblings:
            break
        n += 1

    new_override.rename(cand, mode='NEVER')
    print(f"Renamed override to '{new_override.name}'")

    if original_name in [c.name for c in scene.collection.children]:
        scene.collection.children.unlink(lc)
        print(f"Unlinked original from scene.collection")
    for col in bpy.data.collections:
        if original_name in [c.name for c in col.children]:
            col.children.unlink(lc)
            print(f"Unlinked original from '{col.name}'")

    bpy.data.collections.remove(lc)
    print(f"Removed original linked collection '{original_name}'")

    return True

class Figure_OT_delete_override(Operator):
    bl_idname = "figure.delete_override"
    bl_label = "Delete"
    bl_description = "Unlink and remove selected library-override collection"

    def execute(self, context):
        wm = context.window_manager
        idx = wm.override_index
        if idx < 0 or idx >= len(wm.override_items):
            self.report({'ERROR'}, "No collection selected")
            return {'CANCELLED'}
        name = wm.override_items[idx].name
        coll = bpy.data.collections.get(name)
        if not coll:
            self.report({'ERROR'}, f"Collection not found: {name}")
            return {'CANCELLED'}
        
        cam = context.scene.camera
        cam_coll = (bpy.data.collections.get(cam.name)
                    if cam and cam.name in bpy.data.collections
                    else context.scene.collection)
        if cam_coll.children.get(name):
            cam_coll.children.unlink(coll)
        bpy.data.collections.remove(coll)
        bpy.ops.figure.refresh_override_list()
        return {'FINISHED'}

class Figure_OT_external_import(Operator):
    bl_idname = "figure.external_import"
    bl_label = "外部参照読込"
    bl_description = (
        "Load external reference with Link, Relative Path, and Instance Object Data set to True."
        "Execute override_and_remove_collection on top-level collections only."
    )

    filepath: StringProperty(name="Blend File", subtype='FILE_PATH')

    def execute(self, context):
        blend_path = self.filepath
        if not os.path.isfile(blend_path):
            self.report({'ERROR'}, f"File not found: {blend_path}")
            return {'CANCELLED'}

        with bpy.data.libraries.load(blend_path, link=True) as (data_from, data_to):
            col_names = data_from.collections[:]

        imported = []
        coll_dir = os.path.join(blend_path, "Collection") + os.sep
        for name in col_names:
            try:
                bpy.ops.wm.link(
                    directory=coll_dir,
                    filename=name,
                    relative_path=True,
                    instance_collections=False,
                    instance_object_data=True
                )
                col = bpy.data.collections.get(name)
                if col:
                    imported.append(col)
            except Exception as e:
                self.report({'WARNING'}, f"Failed to link {name}: {e}")

        imported = filter_top_level(imported)
        cam = context.scene.camera
        parent_coll = (
            bpy.data.collections.get(cam.name)
            if cam and cam.name in bpy.data.collections
            else context.scene.collection
        )
        for col in imported:
            if col.name not in [c.name for c in parent_coll.children]:
                parent_coll.children.link(col)

        if imported:
            lc_layer = find_layer_collection(
                context.view_layer.layer_collection,
                imported[0].name
            )
            if lc_layer:
                context.view_layer.active_layer_collection = lc_layer
                override_and_remove_collection(
                    lc=lc_layer.collection,
                    scene=context.scene,
                    view_layer=context.view_layer
                )
        def localize_hierarchy(coll):
            try:
                coll.make_local()
            except Exception:
                pass
            for child in coll.children:
                localize_hierarchy(child)

        root_coll = context.view_layer.active_layer_collection.collection
        localize_hierarchy(root_coll)

        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class Figure_OT_append_import(Operator):
    bl_idname = "figure.append_import"
    bl_label = "通常読込"
    bl_description = "Append loading (Localize All: True, skip existing collections)."
    filepath: StringProperty(name="Blend File", subtype='FILE_PATH')

    def execute(self, context):
        blend_path = self.filepath
        if not os.path.isfile(blend_path):
            self.report({'ERROR'}, f"File not found: {blend_path}")
            return {'CANCELLED'}

        with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
            all_names = data_from.collections[:]

        imported = []
        coll_dir = os.path.join(blend_path, "Collection") + os.sep

        for name in all_names:
            if bpy.data.collections.get(name):
                self.report({'INFO'}, f"Collection '{name}' already exists, skipping import")
                continue
            try:
                bpy.ops.wm.append(
                    directory=coll_dir,
                    filename=name
                )
                col = bpy.data.collections.get(name)
                if col:
                    imported.append(col)
            except Exception as e:
                self.report({'WARNING'}, f"Failed to append {name}: {e}")

        top_imported = filter_top_level(imported)

        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class Figure_OT_external_localize(Operator):
    bl_idname = "figure.external_localize"
    bl_label = "Localize"
    bl_description = "Disconnect the external reference of the selected object."
    bl_options = {'REGISTER', 'UNDO'}
    
    def draw(self, context):
        self.layout.label(text="選択したオブジェクトの外部参照を切断しますがよろしいですか？")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=350)

    def execute(self, context):
        selected_objs = list(bpy.context.selected_objects)

        for obj in selected_objs:
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.make_local(type='SELECT_OBDATA')

        return {'FINISHED'}

class Figure_PTO_panel(Panel):
    bl_label = "Import"
    bl_idname = "Figure_PTO_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Model'

    def draw(self, context):
        layout = self.layout
        layout.label(text="model")
        layout.operator('figure.external_import', text="外部参照読込")
        layout.operator('figure.append_import', text="通常読込")
        layout.separator()
        layout.label(text="Localize")
        layout.label(text="選択したオブジェクトを編集可能にする")
        layout.operator('figure.external_localize', text="Localize")
######
######

class Figure_Panel(bpy.types.Panel):
    bl_label = "Figure_Controll"
    bl_idname = "OBJECT_PT_Figure_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Model'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.label(text="ギズモ操作切り替え")
        row = layout.row()
        row.operator("object.gizmo_toggle_operator", text= ("移動" if context.space_data.show_gizmo_object_translate else "回転"))
        
        layout.label(text="軸の切り替え")
        col = layout.column(align=True)
        col.operator_menu_enum("view3d.switch_axis", "axis_type", text= context.scene.transform_orientation_slots[1].type, icon='WORLD')
        
        layout.label(text="ポーズオプション")
        layout.operator("wm.all_clear")
        layout.operator("wm.select_clear")
        layout.operator("wm.copy_pose")
        layout.operator("wm.paste_pose")
        layout.operator("wm.mirror_pose")
    
def button1_callback(self):
    bpy.ops.pose.select_all(action='DESELECT')
    bpy.ops.pose.select_all(action='SELECT')
    bpy.ops.pose.transforms_clear()
    bpy.ops.pose.select_all(action='SELECT')
    bpy.ops.pose.transforms_clear()
    bpy.ops.pose.select_all(action='DESELECT')

def button2_callback(self):
    bpy.ops.pose.transforms_clear()
    bpy.ops.pose.select_all(action='DESELECT')

def button3_callback(self):
    bpy.ops.pose.copy()
    bpy.ops.pose.select_all(action='DESELECT')

def button4_callback(self):
    bpy.ops.pose.paste(flipped=False)
    bpy.ops.pose.select_all(action='DESELECT')
    
def button5_callback(self):
    bpy.ops.pose.copy()
    bpy.ops.pose.paste(flipped=True)
    bpy.ops.pose.select_all(action='DESELECT') 

class GizmoToggleOperator(bpy.types.Operator):
    bl_idname = "object.gizmo_toggle_operator"
    bl_label = "Toggle Gizmo"

    def execute(self, context):
        space = context.space_data
        if space.show_gizmo_object_translate:
            space.show_gizmo_object_translate = False
            space.show_gizmo_object_rotate = True
        else:
            space.show_gizmo_object_translate = True
            space.show_gizmo_object_rotate = False
        return {'FINISHED'}

class VIEW3D_OT_SwitchAxis(bpy.types.Operator):
    bl_idname = "view3d.switch_axis"
    bl_label = "Switch Axis"
    
    axis_type: bpy.props.EnumProperty(
        items=[('GLOBAL', "Global", "Switch to Global Axis"),
               ('LOCAL', "Local", "Switch to Local Axis")],
        default='GLOBAL')

    def execute(self, context):
        if self.axis_type == 'GLOBAL':
            bpy.context.scene.transform_orientation_slots[1].type = 'GLOBAL'
        elif self.axis_type == 'LOCAL':
            bpy.context.scene.transform_orientation_slots[1].type = 'LOCAL'
        return {'FINISHED'}

class All_Clear(bpy.types.Operator):
    bl_idname = "wm.all_clear"
    bl_label = "All_Clear"

    def execute(self, context):
        button1_callback(None)
        return {'FINISHED'}  

class Select_Clear(bpy.types.Operator):
    bl_idname = "wm.select_clear"
    bl_label = "Select_Clear"

    def execute(self, context):
        button2_callback(None)
        return {'FINISHED'}  
    
class Copy_Pose(bpy.types.Operator):
    bl_idname = "wm.copy_pose"
    bl_label = "Copy_Pose"

    def execute(self, context):
        button3_callback(None)
        return {'FINISHED'}    

class Paste_Pose(bpy.types.Operator):
    bl_idname = "wm.paste_pose"
    bl_label = "Paste_Pose"

    def execute(self, context):
        button4_callback(None)
        return {'FINISHED'}

class Mirror_Pose(bpy.types.Operator):
    bl_idname = "wm.mirror_pose"
    bl_label = "Mirror_Pose"

    def execute(self, context):
        button5_callback(None)
        return {'FINISHED'}
######
######
classes = (
    FigureItem,
    OverrideItem,
    Figure_OT_setup,
    Figure_OT_refresh_override_list,
    Figure_OT_add,
    Figure_OT_delete_override,
    Figure_UL_override_list,
    Figure_PT_panel,
    Figure_OT_external_import,
    Figure_OT_append_import,
    Figure_OT_external_localize,
    Figure_Panel,
    Figure_PTO_panel,
    All_Clear,
    Select_Clear,
    Copy_Pose,
    Paste_Pose,
    Mirror_Pose,
    VIEW3D_OT_SwitchAxis,
    GizmoToggleOperator
    )

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    init_props()
    try:
        bpy.ops.figure.refresh_override_list()
    except RuntimeError as e:
        pass
    
def unregister():
    clear_props()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
