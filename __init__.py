bl_info = {
    "name": "3dlayout for AnimationStudio",
    "author": "Areku",
    "version": (1, 0, 0),
    "blender": (4, 4, 0),
    "location": "View3D > Sidebar",
    "description": "3D Layout for AnimeStudio is a Blender addon designed specifically to support animation studios in the early stages of anime production. This tool provides essential features for 3D layout creation, including scene management functions tailored for camera blocking, staging, and composition.",
    "category": "3D View"
}

import bpy
from . import main
from . import model

def delayed_register():
    main.register()
    model.register()

def register():
    bpy.app.timers.register(delayed_register, first_interval=0.1)

def unregister():
    model.unregister()
    main.unregister()

if __name__ == "__main__":
    register()
