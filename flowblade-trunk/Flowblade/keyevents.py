"""
    Flowblade Movie Editor is a nonlinear video editor.
    Copyright 2012 Janne Liljeblad.

    This file is part of Flowblade Movie Editor <https://github.com/jliljebl/flowblade/>.

    Flowblade Movie Editor is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    Flowblade Movie Editor is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with Flowblade Movie Editor.  If not, see <http://www.gnu.org/licenses/>.
"""

"""
Module handles keyevents.
"""

from gi.repository import Gdk, Gtk

import re

import appconsts
import clipeffectseditor
import compositeeditor
import compositormodes
import glassbuttons
import gui
import editorpersistance
import editorstate
from editorstate import current_sequence
from editorstate import PLAYER
from editorstate import timeline_visible
import keyframeeditor
import kftoolmode
import medialog
import menuactions
import modesetting
import monitorevent
import movemodes
import multitrimmode
import shortcuts
import shortcutsquickeffects
import syncsplitevent
import render
import targetactions
import tlineaction
import tlinewidgets
import tlineypage
import trackaction
import trimmodes
import updater
import projectaction
import workflow

# TODO: We should consider integrating some parts of this with targetactions.py
# TODO:
# TODO: As of this writing, targetactions.py has a superset of targetable
# TODO: actions, as compared to keyevents.py, totally separate from any keyboard
# TODO: event handling. There are a few new named target actions in there that
# TODO: aren't available in here. There is also currently a lot code duplication
# TODO: between the two modules. See targetactions.py for more details.
# TODO:
# TODO: At a minimum, if you add or modify any of the key actions in here,
# TODO: please consider updating targetactions.py as well. Right now there
# TODO: is a lot of duplication between these modules, and often a change
# TODO: in one would warrant a change in the other.
# TODO:
# TODO: keyevents.py is all about handling key presses from the keyboard, and
# TODO: routing those events to trigger actions in various parts of the program.
# TODO:
# TODO: targetactions.py is basically a bunch of zero-argument functions with
# TODO: names based on the shortcut key names found here. It was created as part
# TODO: of the USB HID work, so that USB jog/shuttle devices could have their
# TODO: buttons target various actions within the program, without requiring
# TODO: each USB driver to directly make connections to a dozen different parts
# TODO: of the program to control it.
# TODO:
# TODO: So now we have two collections of shortcut key names which map to
# TODO: basically the same actions, but in a different way. I originally wanted
# TODO: to just use keyevents.py as the target for the USB driver actions, but
# TODO: couldn't use it directly since this module is intertwined with the
# TODO: main computer keyboard and its events.
# TODO:
# TODO: For now, I have integrated the new command targets from
# TODO: targetactions.py into keyevents.py, both for completeness, and also as
# TODO: a proof of concept as to how we might migrate some of the other code
# TODO: in here over to call targetactions.py
# TODO:
# TODO:   -- Nathan Rosenquist (@ratherlargerobot)
# TODO:      Feb 2022

# ------------------------------------- keyboard events
def key_down(widget, event):
    
    #print (_get_shortcut_action(event))
    
    """
    Global key press listener.
    """
    # Handle ESCAPE.
    if event.keyval == Gdk.KEY_Escape:
        if editorstate.current_is_move_mode() == False:
            modesetting.set_default_edit_mode()
            return True
        elif gui.big_tc.get_visible_child_name() == "BigTCEntry":
            gui.big_tc.set_visible_child_name("BigTCDisplay")
            return True
    
    # Make Home and End work on name entry widget.
    # TODO: See which other components could benefit from this check.
    if render.widgets.file_panel.movie_name.has_focus():
        return False

    # If timeline widgets are in focus timeline keyevents are available.
    if _timeline_has_focus():
        was_handled = _handle_tline_key_event(event)
        if was_handled:
            # Stop widget focus from travelling if arrow key pressed for next frame
            # by stopping signal.
            gui.editor_window.window.emit_stop_by_name("key_press_event")
        return was_handled
    
    # Insert shortcut keys need more focus then timeline shortcuts.
    # these may already have been handled in timeline focus events.
    was_handled = _handle_extended_monitor_focus_events(event)
    if was_handled:
        # Stop event handling here
        return True

    was_handled = _handle_configurable_global_events(event)
    if was_handled:
        return True

    # Pressing timeline button obviously leaves user expecting
    # to have focus in timeline.
    if gui.monitor_switch.widget.has_focus() and timeline_visible():
        was_handled = _handle_tline_key_event(event)
        return was_handled

    #  Handle non-timeline delete.
    if event.keyval == Gdk.KEY_Delete:
        return _handle_delete()

    # Select all with CTRL + A in media panel.
    if event.keyval == Gdk.KEY_a:
        if (event.get_state() & Gdk.ModifierType.CONTROL_MASK):
            if gui.media_list_view.widget.has_focus() or gui.media_list_view.widget.get_focus_child() != None: 
                gui.media_list_view.select_all()
                return True

    if event.keyval == Gdk.KEY_F11:
        menuactions.toggle_fullscreen()
        return True

    # Key event was not handled here.
    #print(_get_shortcut_action(event), " not handled")
    return False
    
def _timeline_has_focus():
    if gui.editor_window.tool_selector != None and gui.editor_window.tool_selector.widget.has_focus():
        return True
    
    if(gui.tline_canvas.widget.has_focus()
       or gui.tline_column.widget.has_focus()
       or (gui.pos_bar.widget.has_focus() and timeline_visible())
       or gui.tline_scale.widget.has_focus()
       or glassbuttons.focus_group_has_focus(glassbuttons.DEFAULT_FOCUS_GROUP)):
        return True

    return False
    
def _handle_tline_key_event(event):
    """
    This is called when timeline widgets have focus and key is pressed.
    Returns True for handled key presses to stop those
    keyevents from going forward.
    """
    tool_was_selected = workflow.tline_tool_keyboard_selected(event)
    if tool_was_selected == True:
        return True

    was_handled = shortcutsquickeffects.maybe_do_quick_shortcut_filter_add(event)
    if was_handled == True:
        return True

    return False

def _handle_extended_monitor_focus_events(event):
    tool_was_selected = workflow.tline_tool_keyboard_selected(event)
    if tool_was_selected == True:
        return True

    return False
        
# Apr-2017 - SvdB
def _get_shortcut_action(event):
    return shortcuts.get_shortcut_action(event)

def _handle_configurable_global_events(event):
    action = _get_shortcut_action(event)
    if action == 'tline_page_up':
        tlineypage.page_up_key()
        return True
    if action == 'tline_page_down':
        tlineypage.page_down_key()
        return True
    if action == 'open_next':
        projectaction.open_next_media_item_in_monitor()
        return True
    if action == 'open_prev':
        projectaction.open_prev_media_item_in_monitor()
        return True
    if action == "append_from_bin":
        if gui.media_list_view.widget.has_focus() or gui.media_list_view.widget.get_focus_child() != None: 
            projectaction.append_selected_media_clips_into_timeline()
            return True
    if action == "move_media":
        gui.media_list_view.init_move()
    if action == 'monitor_show_video':
        tlineaction.set_monitor_display_mode(appconsts.PROGRAM_OUT_MODE)
        return True
    if action == 'monitor_show_scope':
        tlineaction.set_monitor_display_mode(appconsts.VECTORSCOPE_MODE)
        return True
    if action == 'monitor_show_rgb':
        tlineaction.set_monitor_display_mode(appconsts.RGB_PARADE_MODE)
        return True

    return False

def _handle_delete():
    # Delete media file
    if gui.media_list_view.widget.get_focus_child() != None:
        projectaction.delete_media_files()
        return True
    
    focus_editor = _get_focus_keyframe_editor(compositeeditor.keyframe_editor_widgets)
    if focus_editor != None:
        focus_editor.delete_pressed()
        return True

    focus_editor = _get_focus_keyframe_editor(clipeffectseditor.keyframe_editor_widgets)
    if focus_editor != None:
        focus_editor.delete_pressed()
        return True

    return False
