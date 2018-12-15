# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import bpy
import sys
import os
import shlex
import subprocess
import tempfile
import time
from collections import OrderedDict

bl_info = {
    "name": "External Text Edit",
    "author": "IRIE Shinsuke",
    "version": (1, 0, 1),
    "blender": (2, 80, 0),  # or (2, 79, 0)
    "location": "Text Editor > Properties > External Text Edit",
    "description": "Edit text with external text editor and reload automatically",
    "tracker_url": "https://github.com/iRi-E/blender_external_text_edit/issues",
    "category": "Text Editor"}

# presets data
BPYVERSION = "{}.{}".format(sys.version_info.major, sys.version_info.minor)

PRESETS_DICT = OrderedDict((
    # label            command  args       wait   server
    ("IDLE",          ["idle"]),
    ("IDLE (Debian)", ["idle-python" + BPYVERSION]),
    ("Emacs",         ["emacs"]),
    ("EmacsClient",   ["emacsclient", "",  True,  "emacs"]),
    ("VS Code",       ["code", "--wait"]),
    ("gedit",         ["gedit", "--wait"]),
    ("Kate",          ["kate", "--block",  True,  True]),
    ("Eclipse",       ["eclipse", "",      False]),
    ("Ninja IDE",     ["ninja-ide", "",    False]),
    ("Geany",         ["geany", "",        False]),
    ("Notepad++",     ["notepad++", "",    False]),
    ("GVim",          ["gvim", "--remote", False, True]),
    ("Atom",          ["atom", "",         False, True]),
    ("MonoDevelop",   ["monodevelop", "",  False, True]),
    ("PyCharm",       ["charm", "",        False, True]),
    # ("NetBeans",      ["netbeans", "",     False, True]), # untested
))


class ExternalTextEditPrefs(bpy.types.AddonPreferences):
    # this must match the addon name, use '__package__'
    # when defining this in a submodule of a python package.
    bl_idname = __name__

    interval = bpy.props.FloatProperty(
        name="Interval",
        description="Time interval to watch if the file has been changed on disk",
        min=0.1,
        max=10.0,
        default=1.0)

    launch = bpy.props.BoolProperty(
        name="Launch External Editor",
        description="Automatically launch external editor when starting auto-reload",
        default=True)

    command = bpy.props.StringProperty(
        subtype="FILE_PATH",
        name="Command",
        description="File path to text editor program",
        default="emacs")

    arguments = bpy.props.StringProperty(
        name="Arguments",
        description="Command line options to give to the external text editor",
        default="")

    wait = bpy.props.BoolProperty(
        name="Wait for Return",
        description="Automatically stop the auto-reload when the command terminates",
        default=True)

    server = bpy.props.StringProperty(options={'SKIP_SAVE'})  # used only for presets

    def draw(self, context):
        layout = self.layout
        col = layout.column()

        col.prop(self, "interval")
        col.prop(self, "launch")

        if self.launch:
            col = layout.column(align=True)
            col.label(text="External Editor Settings:")
            col.menu("external_text_edit.presets", text=TEXT_MT_external_edit_presets.bl_label)
            col.prop(self, "command")
            col.prop(self, "arguments")
            col.prop(self, "wait")

            if self.server:
                col.label(text="You need to manually launch '{0}' as a server before opening temp file"
                          .format(self.server), icon='INFO')
            if not self.wait:
                col.label(text="You need to manually stop the automatic reload after closing temp file",
                          icon='INFO')


# define UI
class TEXT_OT_external_edit_execute_preset(bpy.types.Operator):
    """Execute a preset"""
    bl_idname = "text.external_edit_execute_preset"
    bl_label = "Execute a Preset of Edit Text External"

    preset = bpy.props.StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        def defaults(command, arguments="", wait=True, server=""):
            return command, arguments, wait, command if server is True else server

        preset_class = getattr(bpy.types, "external_text_edit.presets")
        preset_class.bl_label = self.preset

        prefs = context.user_preferences.addons[__name__].preferences
        prefs.command, prefs.arguments, prefs.wait, prefs.server = defaults(*PRESETS_DICT[self.preset])

        return {'FINISHED'}


class TEXT_MT_external_edit_presets(bpy.types.Menu):
    bl_idname = "external_text_edit.presets"
    bl_label = "Presets"

    def draw(self, context):
        layout = self.layout

        for preset in PRESETS_DICT.keys():
            props = layout.operator("text.external_edit_execute_preset", text=preset)
            props.preset = preset


class TEXT_PT_external_edit(bpy.types.Panel):
    bl_space_type = 'TEXT_EDITOR'
    bl_region_type = 'UI'
    bl_label = "External Text Edit"
    # bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        col = layout.column()

        text = context.edit_text
        if text:
            row = col.row(align=True)
            row.operator("text.external_edit_start", text="Start")
            row.operator("text.external_edit_stop", text="Stop")

        row = col.row(align=True)
        row.operator("text.external_edit_start_all", text="Start All")
        row.operator("text.external_edit_stop_all", text="Stop All")


class TEXT_MT_external_edit(bpy.types.Menu):
    bl_label = "Edit with External Editor"

    def draw(self, context):
        layout = self.layout
        layout.operator("text.external_edit_start", text="Start")
        layout.operator("text.external_edit_stop", text="Stop")


def external_text_edit_menu(self, context):
    layout = self.layout
    if context.edit_text:
        layout.menu("TEXT_MT_external_edit", icon='PLUGIN')


# main part
class ExternalEditorManager():

    def __init__(self, text, launch, command, options):
        self.text = text
        self.internal = not text.filepath

        if self.internal:
            self.filename = tempfile.mkstemp(prefix="", suffix="-"+text.name, text=True)[1]
            print("copy internal text to temporary file '{}'".format(self.filename))
            with open(self.filename, mode="w", encoding="UTF-8") as f:
                f.write(text.as_string())
        else:
            self.filename = text.filepath

        self.mtime = os.path.getmtime(self.filename)
        self.proc = None

        if launch:
            args = [command]
            args.extend(shlex.split(options))
            args.append(self.filename)

            print("starting external text editor...")
            self.proc = subprocess.Popen(args)

    def __del__(self):
        self.terminate()
        self.delete_temp()

    def is_alive(self):
        try:
            return self.proc.poll() is None
        except AttributeError:
            return False

    def is_unlinked(self):
        return self.text not in tuple(bpy.data.texts)

    def is_modified(self):
        return os.path.getmtime(self.filename) > self.mtime

    def terminate(self):
        if self.is_alive():
            print("terminate external text editor")
            self.proc.terminate()

    def delete_temp(self):
        if self.internal and self.filename:
            print("delete temporary file '{}'".format(self.filename))
            os.remove(self.filename)
            self.filename = ""

    def update(self):
        line = self.text.current_line_index

        with open(self.filename, encoding="UTF-8") as f:
            self.text.clear()
            self.text.write(f.read())

        self.text.current_line_index = line
        self.mtime = os.path.getmtime(self.filename)


def sync_text(context, text):
    if text.filepath and text.is_dirty:
        # unset 'is_dirty' flag
        bpy.ops.text.save({"edit_text": text, "window": context.window,
                           "area": context.area, "region": context.region})


def ignore_conflict(context, text):
    if text.filepath:
        # unset 'is_modified' flag
        bpy.ops.text.resolve_conflict({"edit_text": text, "window": context.window}, resolution='IGNORE')


def tag_redraw(context):
    for a in context.screen.areas:
        if a.type == 'TEXT_EDITOR':
            for r in a.regions:
                if r.type == 'UI':
                    r.tag_redraw()


class TEXT_OT_external_edit_start(bpy.types.Operator):
    """Save current text to disk and start automatic reload"""
    bl_idname = "text.external_edit_start"
    bl_label = "Start External Text Edit"

    @classmethod
    def poll(cls, context):
        return not context.edit_text.external_editing

    def invoke(self, context, event):
        self.text = context.edit_text
        self.subproc_running = False
        prefs = context.user_preferences.addons[__name__].preferences

        if not (self.text.filepath or prefs.launch):
            self.report({'ERROR'}, "Turn on \"Launch External Editor\" if you want to edit internal texts")
            return {'CANCELLED'}

        sync_text(context, self.text)

        try:
            self.editor = ExternalEditorManager(self.text, prefs.launch, prefs.command, prefs.arguments)
        except FileNotFoundError as err:
            self.report({'ERROR'}, "{}".format(err))
            return {'CANCELLED'}
        self.subproc_running = self.editor.is_alive()

        self.timer = context.window_manager.event_timer_add(prefs.interval, window=context.window)
        context.window_manager.modal_handler_add(self)
        self.text.external_editing = True
        tag_redraw(context)

        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        def stop_editing():
            if self.timer:
                context.window_manager.event_timer_remove(self.timer)
                self.timer = None
                self.editor.delete_temp()

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        if self.editor.is_unlinked():
            print("'{}' was unlinked".format(self.editor.filename))
            self.editor.terminate()
            stop_editing()
            return {'CANCELLED'}

        prefs = context.user_preferences.addons[__name__].preferences

        if self.subproc_running and not self.editor.is_alive():
            print("external text editor was terminated")
            self.subproc_running = False

            if prefs.wait:
                self.text.external_editing = False
                tag_redraw(context)
                sync_text(context, self.text)

        if self.text.external_editing:
            if self.editor.is_modified():
                print("'{}' was changed on disk".format(self.editor.filename))
                self.editor.update()
                ignore_conflict(context, self.text)
        else:
            if prefs.wait and self.subproc_running:
                print("external edit was stopped")
                self.editor.terminate()
                self.subproc_running = False
            stop_editing()
            if not self.subproc_running:
                return {'FINISHED'}

        return {'RUNNING_MODAL'}


class TEXT_OT_external_edit_stop(bpy.types.Operator):
    """Stop automatic reload and delete temporary file created for internal text \
(it would be better to terminate the auto-launched external editor before doing this)"""
    bl_idname = "text.external_edit_stop"
    bl_label = "Stop External Text Edit"

    @classmethod
    def poll(cls, context):
        return context.edit_text.external_editing

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        text = context.edit_text
        if text.external_editing:
            text.external_editing = False
            tag_redraw(context)
            sync_text(context, text)

        return {'FINISHED'}


class TEXT_OT_external_edit(bpy.types.Operator):
    """Start/stop external text edit"""
    bl_idname = "text.external_edit"
    bl_label = "Edit Text with External Editor"

    action = bpy.props.EnumProperty(
        items=[('START', "Start", "Start external edit"),
               ('STOP',  "Stop",  "Stop external edit"),
               ('TOGGLE', "Toggle", "Toggle external edit")],
        name="Action",
        description="Specify 'Start' or 'Stop' if necessary to force",
        default='TOGGLE')

    def execute(self, context):
        if self.action == 'START' or \
           self.action == 'TOGGLE' and not context.edit_text.external_editing:
            bpy.ops.text.external_edit_start('INVOKE_DEFAULT')
        else:
            bpy.ops.text.external_edit_stop('INVOKE_DEFAULT')

        return {'FINISHED'}


class TEXT_OT_external_edit_start_all(bpy.types.Operator):
    """Start external edits for all texts"""
    bl_idname = "text.external_edit_start_all"
    bl_label = "Start External Text Edit All"

    @classmethod
    def poll(cls, context):
        for text in bpy.data.texts:
            if not text.external_editing:
                return True
        return False

    def execute(self, context):
        prefs = context.user_preferences.addons[__name__].preferences

        c = context.copy()
        for text in bpy.data.texts:
            if not text.external_editing:
                if not (text.filepath or prefs.launch):
                    self.report({'ERROR'}, "Turn on \"Launch External Editor\" if you want to edit internal texts")
                else:
                    c["edit_text"] = text
                    bpy.ops.text.external_edit_start(c, 'INVOKE_DEFAULT')
                    time.sleep(0.1)  # workaround for gvim failing to open files
        return {'FINISHED'}


class TEXT_OT_external_edit_stop_all(bpy.types.Operator):
    """Stop all of external text edits in progress (it would be better \
to terminate the auto-launched external editor before doing this)"""
    bl_idname = "text.external_edit_stop_all"
    bl_label = "Stop External Text Edit All"

    @classmethod
    def poll(cls, context):
        for text in bpy.data.texts:
            if text.external_editing:
                return True
        return False

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        c = context.copy()
        for text in bpy.data.texts:
            if text.external_editing:
                c["edit_text"] = text
                bpy.ops.text.external_edit_stop(c, 'EXEC_DEFAULT')
        return {'FINISHED'}


# register this addon
classes = (
    ExternalTextEditPrefs,
    TEXT_OT_external_edit_execute_preset,
    TEXT_MT_external_edit_presets,
    TEXT_PT_external_edit,
    TEXT_MT_external_edit,
    TEXT_OT_external_edit_start,
    TEXT_OT_external_edit_stop,
    TEXT_OT_external_edit,
    TEXT_OT_external_edit_start_all,
    TEXT_OT_external_edit_stop_all,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Text.external_editing = bpy.props.BoolProperty(
        name="Switch for External Editing",
        description="Setting the value to 'False' will stop external editing",
        default=False,
        options={'SKIP_SAVE'})
    bpy.types.TEXT_MT_text.append(external_text_edit_menu)


def unregister():
    del bpy.types.Text.external_editing
    bpy.types.TEXT_MT_text.remove(external_text_edit_menu)

    for cls in classes:
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
