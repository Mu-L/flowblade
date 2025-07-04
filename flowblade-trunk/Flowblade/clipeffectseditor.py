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
Module handles clip effects editing logic and gui
"""
import cairo
import copy
from gi.repository import GLib
from gi.repository import Gtk
import pickle

import appconsts
import atomicfile
import dialogs
import dialogutils
import edit
import editorlayout
import editorpersistance
import editorstate
from editorstate import PROJECT
from editorstate import PLAYER
from editorstate import current_sequence
import extraeditors
import gtkbuilder
import gui
import guicomponents
import guipopover
import guiutils
import mltfilters
import propertyedit
import propertyeditorbuilder
import propertyparse
import respaths
import translations
import updater
import utils

_filter_stack = None

widgets = utils.EmptyClass()

_block_changed_update = False # Used to block unwanted callback update from "changed"
_block_stack_update = False # Used to block full stack update when adding new filter. 
                            # Otherwise we got 2 updates EditAction objects must always try to update
                            # on undo/redo.

# Property change polling.
# We didn't put a layer of indirection to look for and launch events on filter property edits
# so now we detect filter edits by polling. This has no performance impect, n is so small.
#_edit_polling_thread = None
# filter_changed_since_last_save = False

# This is updated when filter panel is displayed and cleared when removed.
# Used to update kfeditors with external tline frame position changes
keyframe_editor_widgets = []

# Filter stack DND requires some state info to be maintained to make sure that it's only done when certain events
# happen in a certain sequence.
TOP_HALF = 0
BOTTOM_HALF = 1

NOT_ON = 0
MOUSE_PRESS_DONE = 1
INSERT_DONE = 2
stack_dnd_state = NOT_ON
stack_dnd_event_time = 0.0
stack_dnd_event_info = None



# ---------------------------------------------------------- filter stack objects
class FilterFooterRow:
    
    def __init__(self, filter_object, filter_stack):
        self.filter_object = filter_object
        self.filter_stack = filter_stack

        w=22
        h=22
        surface = guiutils.get_cairo_image("filter_save")
        save_button = guicomponents.PressLaunch(self.save_pressed, surface, w, h)
        save_button.widget.set_tooltip_markup(_("Save effect values"))
        
        surface = guiutils.get_cairo_image("filter_load")
        load_button = guicomponents.PressLaunch(self.load_pressed, surface, w, h)
        load_button.widget.set_tooltip_markup(_("Load effect values"))

        surface = guiutils.get_cairo_image("filter_reset")
        reset_button = guicomponents.PressLaunch(self.reset_pressed, surface, w, h)
        reset_button.widget.set_tooltip_markup(_("Reset effect values"))
        
        surface = guiutils.get_cairo_image("filters_mask_add")
        mask_button = guicomponents.PressLaunch(self.add_mask_pressed, surface, w, h)
        mask_button.widget.set_tooltip_markup(_("Add Filter Mask"))
        self.mask_button = mask_button
        
        surface = guiutils.get_cairo_image("filters_move_up")
        move_up_button = guicomponents.PressLaunch(self.move_up_pressed, surface, w, h)
        move_up_button.widget.set_tooltip_markup(_("Move Filter Up"))

        surface = guiutils.get_cairo_image("filters_move_down")
        move_down_button = guicomponents.PressLaunch(self.move_down_pressed, surface, w, h)
        move_down_button.widget.set_tooltip_markup(_("Move Filter Down"))

        surface = guiutils.get_cairo_image("filters_move_top")
        move_top_button = guicomponents.PressLaunch(self.move_top_pressed, surface, w, h)
        move_top_button.widget.set_tooltip_markup(_("Move Filter To Top"))

        surface = guiutils.get_cairo_image("filters_move_bottom")
        move_bottom_button = guicomponents.PressLaunch(self.move_bottom_pressed, surface, w, h)
        move_bottom_button.widget.set_tooltip_markup(_("Move Filter To Bottom"))
        
        self.widget = Gtk.HBox(False, 0)
        self.widget.pack_start(guiutils.pad_label(4,5), False, False, 0)
        self.widget.pack_start(mask_button.widget, False, False, 0)
        self.widget.pack_start(guiutils.pad_label(2,5), False, False, 0)
        self.widget.pack_start(reset_button.widget, False, False, 0)
        self.widget.pack_start(guiutils.pad_label(12,5), False, False, 0)
        self.widget.pack_start(move_up_button.widget, False, False, 0)
        self.widget.pack_start(move_down_button.widget, False, False, 0)
        self.widget.pack_start(move_top_button.widget, False, False, 0)
        self.widget.pack_start(move_bottom_button.widget, False, False, 0)
        self.widget.pack_start(guiutils.pad_label(12,5), False, False, 0)
        self.widget.pack_start(save_button.widget, False, False, 0)
        self.widget.pack_start(load_button.widget, False, False, 0)

        self.widget.pack_start(Gtk.Label(), True, True, 0)
        self.widget.set_name("lighter-bg-widget")
            
    def save_pressed(self, w, e):
        default_name = self.filter_object.info.name + _("_effect_values") + ".data"
        dialogs.save_effects_compositors_values(_save_effect_values_dialog_callback, default_name, True, self.filter_object)

    def load_pressed(self, w, e):
        dialogs.load_effects_compositors_values_dialog(_load_effect_values_dialog_callback, True, self.filter_object)

    def reset_pressed(self, w, e):
        _reset_filter_values(self.filter_object)

    def add_mask_pressed(self, w, e):
        filter_index = self.filter_stack.get_filter_index(self.filter_object)
        _filter_mask_launch_pressed(self.mask_button, w, filter_index)

    def move_up_pressed(self, w, e):
        from_index = self.filter_stack.get_filter_index(self.filter_object)
        if len(self.filter_stack.filter_stack) == 1:
            return
        if from_index == 0:
            return
        to_index = from_index - 1
        do_stack_move(self.filter_stack.clip, to_index, from_index)
        
    def move_down_pressed(self, w, e):
        from_index = self.filter_stack.get_filter_index(self.filter_object)
        if len(self.filter_stack.filter_stack) == 1:
            return
        if from_index == len(self.filter_stack.filter_stack) - 1:
            return
        to_index = from_index + 1
        do_stack_move(self.filter_stack.clip, to_index, from_index)
        
    def move_top_pressed(self, w, e):
        from_index = self.filter_stack.get_filter_index(self.filter_object)
        if len(self.filter_stack.filter_stack) == 1:
            return
        if from_index == 0:
            return
        to_index = 0
        do_stack_move(self.filter_stack.clip, to_index, from_index)
                
    def move_bottom_pressed(self, w, e):
        from_index = self.filter_stack.get_filter_index(self.filter_object)
        if len(self.filter_stack.filter_stack) == 1:
            return
        if from_index == len(self.filter_stack.filter_stack) - 1:
            return
        to_index = len(self.filter_stack.filter_stack) - 1
        do_stack_move(self.filter_stack.clip, to_index, from_index)


class FilterHeaderRow:
    
    def __init__(self, filter_object, stack_item):
        name = translations.get_filter_name(filter_object.info.name)
        self.filter_name_label = Gtk.Label(label= "<b>" + name + "</b>")
        self.filter_name_label.set_use_markup(True)
        self.icon = Gtk.Image.new_from_pixbuf(filter_object.info.get_icon())

        surface = cairo.ImageSurface.create_from_png(respaths.IMAGE_PATH + "trash.png")
        trash_button = guicomponents.PressLaunch(stack_item.trash_pressed, surface, w=22, h=22)
        
        surface = cairo.ImageSurface.create_from_png(respaths.IMAGE_PATH + "filters_up_arrow.png")
        up_button = guicomponents.PressLaunch(stack_item.up_pressed, surface, w=10, h=22)
        up_button.surface_x = 0
        up_button.widget.set_margin_right(2)

        surface = cairo.ImageSurface.create_from_png(respaths.IMAGE_PATH + "filters_down_arrow.png")
        down_button = guicomponents.PressLaunch(stack_item.down_pressed, surface, w=10, h=22)
        down_button.surface_x = 0
        down_button.surface_y = 10
        
        
        hbox = Gtk.HBox(False, 0)
        hbox.pack_start(stack_item.active_check, False, False, 0)
        hbox.pack_start(guiutils.pad_label(4,5), False, False, 0)
        hbox.pack_start(self.icon, False, False, 0)
        hbox.pack_start(self.filter_name_label, False, False, 0)
        hbox.pack_start(Gtk.Label(), True, True, 0)
        hbox.pack_start(up_button.widget, False, False, 0)
        hbox.pack_start(down_button.widget, False, False, 0)
        hbox.pack_start(trash_button.widget, False, False, 0)
        self.widget = hbox


class FilterStackItem:

    def __init__(self, filter_object, edit_panel, filter_stack):
        self.filter_object = filter_object

        self.active_check = Gtk.CheckButton()
        self.active_check.set_active(self.filter_object.active)
        self.active_check.connect("toggled", self.toggle_filter_active)

        self.active_check.set_margin_left(2)
        self.filter_header_row = FilterHeaderRow(filter_object, self)

        self.edit_panel = edit_panel
        self.edit_panel_frame = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.edit_panel_frame.add(edit_panel)
        
        self.filter_stack = filter_stack
        self.expander = Expander()
        self.expander.set_label_widget(self.filter_header_row.widget)
        self.expander.add(self.edit_panel_frame)

        self.expander_frame = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.expander_frame.add(self.expander.widget)
        guiutils.set_margins(self.expander_frame, 2, 0, 0, 0)
        
        self.widget = Gtk.HBox(False, 0)
        self.widget.pack_start(self.expander_frame, True, True, 0)
        self.widget.pack_start(guiutils.pad_label(10,2), False, False, 0)

        self.widget.show_all()

    def trash_pressed(self, w, e):
        self.filter_stack.delete_filter_for_stack_item(self)

    def up_pressed(self, w, e):
        from_index = self.filter_stack.get_filter_index(self.filter_object)
        if len(self.filter_stack.filter_stack) == 1:
            return
        if from_index == 0:
            return
        to_index = from_index - 1

        do_stack_move(self.filter_stack.clip, to_index, from_index, False)

    def down_pressed(self, w, e):
        from_index = self.filter_stack.get_filter_index(self.filter_object)
        if len(self.filter_stack.filter_stack) == 1:
            return
        if from_index == len(self.filter_stack.filter_stack) - 1:
            return
        to_index = from_index + 1

        do_stack_move(self.filter_stack.clip, to_index, from_index, False)

    def toggle_filter_active(self, widget):
        self.filter_object.active = (self.filter_object.active == False)
        self.filter_object.update_mlt_disabled_value()


class ClipFilterStack:

    def __init__(self, clip, track, clip_index):
        self.clip = clip
        self.track = track
        self.clip_index = clip_index
        
        # Create filter stack and GUI
        self.filter_stack = []
        self.filter_kf_editors = {} # filter_object -> [kf_editors]
        self.widget = Gtk.VBox(False, 0)
        for filter_index in range(0, len(clip.filters)):
            filter_object = clip.filters[filter_index]
            edit_panel, kf_editors = _get_filter_panel(clip, filter_object, filter_index, track, clip_index)
            self.filter_kf_editors[filter_object] = kf_editors
            footer_row = FilterFooterRow(filter_object, self)
            edit_panel.pack_start(footer_row.widget, False, False, 0)
            edit_panel.pack_start(guiutils.pad_label(12,12), False, False, 0)
            stack_item = FilterStackItem(filter_object, edit_panel, self)
            self.filter_stack.append(stack_item)
            self.widget.pack_start(stack_item.widget, False, False, 0)

        self.widget.show_all()

    def get_filters(self):
        filters = []
        for stack_item in self.filter_stack:
            filters.append(stack_item.filter_object)
        return filters

    def reinit_stack_item(self, filter_object):
        stack_index = -1
        for i in range(0, len(self.filter_stack)):
            stack_item = self.filter_stack[i]
            if stack_item.filter_object is filter_object:
                stack_index = i 
        
        if stack_index != -1:
            # Remove panels from box
            children = self.widget.get_children()
            for child in children:
                self.widget.remove(child)
                
            # Remove old stack item for reset filter.
            self.filter_stack.pop(stack_index)
            self.clear_kf_editors_from_update_list(filter_object)

            # Create new stack item
            edit_panel, kf_editors = _get_filter_panel(self.clip, filter_object, stack_index, self.track, self.clip_index)
            self.filter_kf_editors[filter_object] = kf_editors
            footer_row = FilterFooterRow(filter_object, self)
            edit_panel.pack_start(footer_row.widget, False, False, 0)
            edit_panel.pack_start(guiutils.pad_label(12,12), False, False, 0)
            stack_item = FilterStackItem(filter_object, edit_panel, self)
            
            # Put everything back
            self.filter_stack.insert(stack_index, stack_item)
            for stack_item in self.filter_stack:
                self.widget.pack_start(stack_item.widget,False, False, 0)
                
            self.set_filter_item_expanded(stack_index)
            
    def get_clip_data(self):
        return (self.clip, self.track, self.clip_index)
    
    def get_filter_index(self, filter_object):
        return self.clip.filters.index(filter_object)

    def delete_filter_for_stack_item(self, stack_item):
        filter_index = self.filter_stack.index(stack_item)
        delete_effect_pressed(self.clip, filter_index)

    def stack_changed(self, clip):
        if len(clip.filters) != len(self.filter_stack):
            return True

        for i in range(0, len(clip.filters)):
            clip_filter_info = clip.filters[i].info
            stack_filter_info = self.filter_stack[i].filter_object.info
            
            if stack_filter_info.mlt_service_id != clip_filter_info.mlt_service_id:
                return True

        return False

    def clear_kf_editors_from_update_list(self, filter_object):
        kf_editors = self.filter_kf_editors[filter_object]
        global keyframe_editor_widgets
        for editor in kf_editors:
            try:
                keyframe_editor_widgets.remove(editor)
            except:
                pass
                print("Trying to remove non-existing editor from keyframe_editor_widgets")
                
        self.filter_kf_editors.pop(filter_object)

    def set_filter_item_expanded(self, filter_index):
        filter_stack_item = self.filter_stack[filter_index]
        filter_stack_item.expander.set_expanded(True)

    def set_filter_item_minified(self, filter_index):
        filter_stack_item = self.filter_stack[filter_index]
        filter_stack_item.expander.set_expanded(False)
        
    def set_all_filters_expanded_state(self, expanded):
        for i in range(0, len(self.filter_stack)):
            stack_item = self.filter_stack[i]
            stack_item.expander.set_expanded(expanded)
            
    def get_expanded(self):
        state_list = []
        for stack_item in self.filter_stack:
            state_list.append(stack_item.expander.get_expanded())
        return state_list

    def set_expanded(self, state_list):
        for i in range(0, len(self.filter_stack)):
            stack_item = self.filter_stack[i]
            stack_item.expander.set_expanded(state_list[i])

    def set_single_expanded(self, expanded_index):
        for i in range(0, len(self.filter_stack)):
            stack_item = self.filter_stack[i]
            stack_item.expander.set_expanded(False)
        
        stack_item = self.filter_stack[expanded_index]
        stack_item.expander.set_expanded(True)

class Expander:
    
    def __init__(self):
        self.widget = Gtk.VBox(False, 0) 
        self.label = None
        self.child = None
        self.expanded = True
        
        self.label_box = Gtk.HBox(False, 0) 
        self.child_box = Gtk.VBox(False, 0) 
        
        self.img_unexpanded = Gtk.Image.new_from_icon_name("pan-end-symbolic", Gtk.IconSize.BUTTON)
        self.img_expanded = Gtk.Image.new_from_icon_name("pan-down-symbolic", Gtk.IconSize.BUTTON)

        self.arrow_box = gtkbuilder.EventBox(self.img_expanded, 'button-release-event', self._toggle_expand)
        
        self.widget.pack_start(self.label_box, False, False, 0)
        self.widget.pack_start(self.child_box, True, True, 0)
        
    def set_label_widget(self, label_widget):
        self.label = label_widget
        self._update_label_row()
        self.widget.queue_draw()

    def _update_label_row(self):
        # Remove panels from box
        children = self.label_box.get_children()
        for child in children:
            self.label_box.remove(child)
        self.arrow_box.remove(self.arrow_box.get_child())
        if self.expanded == True:
            self.arrow_box.add(self.img_expanded)
        else:
            self.arrow_box.add(self.img_unexpanded)
        self.arrow_box.show_all()

        self.label_box.pack_start(self.arrow_box, False, False, 0)
        self.label_box.pack_start(self.label, True, True, 0)

    def add(self, child_widget):
        self.child = child_widget
        self._update_child_row()
        self.widget.queue_draw()

    def _update_child_row(self):
        children = self.child_box.get_children()
        for child in children:
            self.child_box.remove(child)
        
        if self.expanded == True:
            self.child_box.pack_start(self.child, False, False, 0)

    def set_expanded(self, expanded):
        self.expanded = expanded
        self._update_label_row()
        self._update_child_row()

    def get_expanded(self):
        return self.expanded

    def _toggle_expand(self, widget, event):
        self.expanded = not self.expanded
        self._update_label_row()
        self._update_child_row()
        

# -------------------------------------------------------------- GUI INIT
def get_clip_effects_editor_info_row():
    _create_widgets()

    info_row = Gtk.HBox(False, 2)
    info_row.pack_start(widgets.hamburger_launcher.widget, False, False, 0)
    info_row.pack_start(widgets.filter_add_launch.widget, True, True, 0)
    info_row.pack_start(Gtk.Label(), True, True, 0)
    info_row.pack_start(widgets.clip_info, False, False, 0)
    info_row.pack_start(Gtk.Label(), True, True, 0)

    return info_row

def _create_widgets():
    """
    Widgets for editing clip effects properties.
    """
    widgets.clip_info = guicomponents.ClipInfoPanel()
    
    widgets.value_edit_box = Gtk.VBox()
    widgets.value_edit_frame = Gtk.Frame()
    widgets.value_edit_frame.add(widgets.value_edit_box)
    
    widgets.hamburger_launcher = guicomponents.HamburgerPressLaunch(_hamburger_launch_pressed)
    widgets.hamburger_launcher.do_popover_callback = True
    guiutils.set_margins(widgets.hamburger_launcher.widget, 6, 8, 1, 0)

    surface_active = guiutils.get_cairo_image("filter_add")
    surface_not_active = guiutils.get_cairo_image("filter_add_not_active")
    surfaces = [surface_active, surface_not_active]
    widgets.filter_add_launch = guicomponents.HamburgerPressLaunch(lambda w,e:_filter_add_menu_launch_pressed(w, e), surfaces)
    guiutils.set_margins(widgets.filter_add_launch.widget, 6, 8, 1, 0)
    
# ------------------------------------------------------------------- interface
def set_clip(clip, track, clip_index, show_tab=True):
    """
    Sets clip being edited and inits gui.
    """
    if _filter_stack != None:
        if clip == _filter_stack.clip and track == _filter_stack.track and clip_index == _filter_stack.clip_index and show_tab == False:
            return

    global keyframe_editor_widgets
    keyframe_editor_widgets = []

    if _filter_stack != None and clip != _filter_stack.clip:
        clip_start_frame = track.clip_start(clip_index)
        PLAYER().seek_frame(clip_start_frame)
    
    widgets.clip_info.display_clip_info(clip, track, clip_index)
    set_enabled(True)
    update_stack(clip, track, clip_index)
    if len(clip.filters) > 0:
        set_filter_item_expanded(len(clip.filters) - 1)

    if len(clip.filters) > 0:
        pass # remove if nothing needed here.
    else:
        show_text_in_edit_area(_("Clip Has No Filters"))

    if show_tab:
        editorlayout.show_panel(appconsts.PANEL_MULTI_EDIT)

    gui.editor_window.edit_multi.set_visible_child_name(appconsts.EDIT_MULTI_FILTERS)


def set_clip_and_filter(clip, track, clip_index, filter_index):
    set_clip(clip, track, clip_index, True)
    _filter_stack.set_single_expanded(filter_index)

def refresh_clip():
    if _filter_stack == None:
        return 
    
    expanded_panels = _filter_stack.get_expanded()
    
    clip, track, clip_index = _filter_stack.get_clip_data()
    set_clip(clip, track, clip_index)

    _filter_stack.set_expanded(expanded_panels)

def get_clip_editor_clip_data():
    if _filter_stack == None:
        return None
    else:
        return _filter_stack.get_clip_data()

def clip_is_being_edited(clip):
    if _filter_stack == None:
        return False

    if _filter_stack.clip == clip:
        return True

    return False

def get_edited_clip():
    if _filter_stack == None:
        return None
    else:
        return  _filter_stack.clip

def set_filter_item_expanded(filter_index):
    if _filter_stack == None:
        return 
    
    _filter_stack.set_filter_item_expanded(filter_index)

def effect_select_row_double_clicked(treeview, tree_path, col, effect_select_combo_box):
    if _filter_stack == None:
        return

    row_index = int(tree_path.get_indices()[0])
    group_index = effect_select_combo_box.get_active()

    _add_filter_from_effect_select_panel(row_index, group_index)

def add_currently_selected_effect():
    # Currently selected in effect select panel, not here.
    treeselection = gui.effect_select_list_view.treeview.get_selection()
    (model, rows) = treeselection.get_selected_rows()    
    row = rows[0]
    row_index = max(row)
    group_index = gui.effect_select_combo_box.get_active()

    _add_filter_from_effect_select_panel(row_index, group_index)

def get_currently_selected_filter_info():
    # Currently selected in effect select panel, not here.
    treeselection = gui.effect_select_list_view.treeview.get_selection()
    (model, rows) = treeselection.get_selected_rows()    
    row = rows[0]
    row_index = max(row)
    group_index = gui.effect_select_combo_box.get_active()
    group_name, filters_array = mltfilters.groups[group_index]
    filter_info = filters_array[row_index]
    return filter_info
    
def _add_filter_from_effect_select_panel(row_index, group_index):
    # Add filter
    group_name, filters_array = mltfilters.groups[group_index]
    filter_info = filters_array[row_index]

    data = {"clip":_filter_stack.clip, 
            "filter_info":filter_info,
            "filter_edit_done_func":filter_edit_done_stack_update}
    action = edit.add_filter_action(data)

    set_stack_update_blocked()
    action.do_edit()
    set_stack_update_unblocked()

    clip, track, clip_index = _filter_stack.get_clip_data()
    set_clip(clip, track, clip_index)

    updater.repaint_tline()

def clear_clip():
    """
    Removes clip from effects editing gui.
    """
    global _filter_stack
    _filter_stack = None
    _set_no_clip_info()
    show_text_in_edit_area(_("No Clip"))

    set_enabled(False)

    global keyframe_editor_widgets
    keyframe_editor_widgets = []

def _set_no_clip_info():
    widgets.clip_info.set_no_clip_info()

def set_enabled(value):
    widgets.clip_info.set_enabled(value)
    widgets.hamburger_launcher.set_sensitive(value)
    widgets.hamburger_launcher.widget.queue_draw()
    widgets.filter_add_launch.set_sensitive(value)
    widgets.filter_add_launch.widget.queue_draw()

def set_stack_update_blocked():
    global _block_stack_update
    _block_stack_update = True

def set_stack_update_unblocked():
    global _block_stack_update
    _block_stack_update = False

def update_stack(clip, track, clip_index):
    new_stack = ClipFilterStack(clip, track, clip_index)
    global _filter_stack
    _filter_stack = new_stack

    scroll_window = Gtk.ScrolledWindow()
    scroll_window.add(_filter_stack.widget)
    scroll_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroll_window.show_all()

    global widgets
    widgets.value_edit_frame.remove(widgets.value_edit_box)
    widgets.value_edit_frame.add(scroll_window)

    widgets.value_edit_box = scroll_window

def _alpha_filter_add_maybe_info(filter_info):
    if editorpersistance.prefs.show_alpha_info_message == True and \
       editorstate. current_sequence().compositing_mode != appconsts.COMPOSITING_MODE_STANDARD_FULL_TRACK:
        dialogs.alpha_info_msg(_alpha_info_dialog_cb, translations.get_filter_name(filter_info.name))

def _alpha_info_dialog_cb(dialog, response_id, dont_show_check):
    if dont_show_check.get_active() == True:
        editorpersistance.prefs.show_alpha_info_message = False
        editorpersistance.save()

    dialog.destroy()

def get_filter_add_action(filter_info, target_clip):
    # Maybe show info on using alpha filters
    if filter_info.group == "Alpha":
        GLib.idle_add(_alpha_filter_add_maybe_info, filter_info)
    data = {"clip":target_clip, 
            "filter_info":filter_info,
            "filter_edit_done_func":filter_edit_done_stack_update}
    action = edit.add_filter_action(data)
    return action

def delete_effect_pressed(clip, filter_index):
    set_stack_update_blocked()

    current_filter = clip.filters[filter_index]
    
    if current_filter.info.filter_mask_filter == "":
        # Clear keyframe editors from update list
        _filter_stack.clear_kf_editors_from_update_list(current_filter)

        # Regular filters
        data = {"clip":clip,
                "index":filter_index,
                "filter_edit_done_func":filter_edit_done_stack_update}
        action = edit.remove_filter_action(data)
        action.do_edit()

    else:
        # Filter mask filters.
        index_1 = -1
        index_2 = -1
        for i in range(0, len(clip.filters)):
            f = clip.filters[i]
            if f.info.filter_mask_filter != "":
                if index_1 == -1:
                    index_1 = i
                else:
                    index_2 = i

        # Clear keyframe editors from update list
        filt_1 = clip.filters[index_1]
        filt_2 = clip.filters[index_2]
        _filter_stack.clear_kf_editors_from_update_list(filt_1)
        _filter_stack.clear_kf_editors_from_update_list(filt_2)
        
        # Do edit
        data = {"clip":clip,
                "index_1":index_1,
                "index_2":index_2,
                "filter_edit_done_func":filter_edit_done_stack_update}
        action = edit.remove_two_filters_action(data)
        action.do_edit()
        
    set_stack_update_unblocked()

    clip, track, clip_index = _filter_stack.get_clip_data()
    set_clip(clip, track, clip_index)

    updater.repaint_tline()

def _save_stack_pressed():
    default_name = _("unnamed_stack_values") + ".data"
    dialogs.save_effects_compositors_values(_save_effect_stack_values_dialog_callback, default_name, True, None, True)

def _load_stack_pressed():
    dialogs.load_effects_compositors_values_dialog(_load_effect_stack_values_dialog_callback, True, None, True)
        
def _toggle_all_pressed():
    if _filter_stack == None:
        return False
        
    for i in range(0, len(_filter_stack.clip.filters)):
        filter_object = _filter_stack.clip.filters[i]
        filter_object.active = (filter_object.active == False)
        filter_object.update_mlt_disabled_value()

    clip, track, clip_index = _filter_stack.get_clip_data()
    expanded_panels = _filter_stack.get_expanded()
    update_stack(clip, track, clip_index)
    _filter_stack.set_expanded(expanded_panels)

def do_stack_move(clip, insert_row, delete_row, expand=True):
    data = {"clip":clip,
            "insert_index":insert_row,
            "delete_index":delete_row,
            "filter_edit_done_func":filter_edit_done_stack_update}
    action = edit.move_filter_action(data)
    set_stack_update_blocked()
    action.do_edit()
    if expand:
        _filter_stack.set_single_expanded(insert_row)
    else:
        _filter_stack.set_all_filters_expanded_state(False)
    set_stack_update_unblocked()

def reinit_stack_if_needed(force_update):
    clip, track, clip_index = _filter_stack.get_clip_data()
    if _filter_stack.stack_changed(clip) == True or force_update == True:
        # expanded state here 
        set_clip(clip, track, clip_index, show_tab=True)

def _get_filter_panel(clip, filter_object, filter_index, track, clip_index):
    # Create EditableProperty wrappers for properties
    editable_properties = propertyedit.get_filter_editable_properties(
                                                               clip, 
                                                               filter_object,
                                                               filter_index,
                                                               track,
                                                               clip_index)

    # Get editors and set them displayed
    vbox = Gtk.VBox(False, 0)

    filter_keyframe_editor_widgets = []

    vbox.pack_start(guicomponents.EditorSeparator().widget, False, False, 0)

    if len(editable_properties) > 0:
        # Create editor row for each editable property
        for ep in editable_properties:
            editor_row = propertyeditorbuilder.get_editor_row(ep)
            if editor_row == None:
                continue
            editor_row.set_name("editor-row-widget")
            # Set keyframe editor widget to be updated for frame changes if such is created 
            try:
                editor_type = ep.args[propertyeditorbuilder.EDITOR]
            except KeyError:
                editor_type = propertyeditorbuilder.SLIDER # this is the default value
            
            if ((editor_type == propertyeditorbuilder.KEYFRAME_EDITOR)
                or (editor_type == propertyeditorbuilder.KEYFRAME_EDITOR_RELEASE)
                or (editor_type == propertyeditorbuilder.KEYFRAME_EDITOR_CLIP)
                or (editor_type == propertyeditorbuilder.FILTER_RECT_GEOM_EDITOR)
                or (editor_type == propertyeditorbuilder.NO_KF_RECT)
                or (editor_type == propertyeditorbuilder.KEYFRAME_EDITOR_CLIP_FADE_FILTER)):
                    keyframe_editor_widgets.append(editor_row)
                    filter_keyframe_editor_widgets.append(editor_row)

            # if slider property is being edited as keyrame property
            if hasattr(editor_row, "is_kf_editor"):
                keyframe_editor_widgets.append(editor_row)
                filter_keyframe_editor_widgets.append(editor_row)

            vbox.pack_start(editor_row, False, False, 0)
            if not hasattr(editor_row, "no_separator"):
                vbox.pack_start(guicomponents.EditorSeparator().widget, False, False, 0)
            
            # Some editors need to be accessed by extraeditors for controlling their state.
            try:
                name = ep.args[propertyedit.ACCESSABLE_EDITOR]
                filter_index = ep.filter_index
                extraeditors.accessable_editors[name + ":" + str(filter_index)] = editor_row
            except Exception as e:
                pass

        # Create NonMltEditableProperty wrappers for properties
        non_mlteditable_properties = propertyedit.get_non_mlt_editable_properties( clip, 
                                                                                   filter_object,
                                                                                   filter_index,
                                                                                   track,
                                                                                   clip_index)

        # Extra editors. Editable properties may have already been created 
        # with "editor=no_editor" and now extra editors may be created to edit those
        # Non mlt properties are added as these are only needed with extraeditors
        editable_properties.extend(non_mlteditable_properties)
        editor_rows = propertyeditorbuilder.get_filter_extra_editor_rows(filter_object, editable_properties, track, clip_index)
        for editor_row in editor_rows:
            vbox.pack_start(editor_row, False, False, 0)
            if not hasattr(editor_row, "no_separator"):
                vbox.pack_start(guicomponents.EditorSeparator().widget, False, False, 0)
            if hasattr(editor_row, "kf_edit_geom_editor"):
                # kf_edit_geom_editor is keyframeeditor.FilterRotatingGeometryEditor,
                # the widget that actually needs to be updated.
                # editor_row is just Gtk.VBox.
                keyframe_editor_widgets.append(editor_row.kf_edit_geom_editor)
                filter_keyframe_editor_widgets.append(editor_row.kf_edit_geom_editor)
    else:
        vbox.pack_start(Gtk.Label(label=_("No editable parameters")), True, True, 0)
    vbox.show_all()

    return (vbox, filter_keyframe_editor_widgets)

def show_text_in_edit_area(text):
    vbox = Gtk.VBox(False, 0)

    filler = Gtk.Stack()  
    filler.add_named(Gtk.Label(), "filler")
    vbox.pack_start(filler, True, True, 0)
    
    info = Gtk.Label(label=text)
    info.set_sensitive(False)
    filler = Gtk.Stack()  
    filler.add_named(info, "filler")
    vbox.pack_start(filler, False, False, 0)
    
    filler = Gtk.Stack()  
    filler.add_named(Gtk.Label(), "filler")
    vbox.pack_start(filler, True, True, 0)

    vbox.show_all()

    scroll_window = Gtk.ScrolledWindow()
    scroll_window.add(vbox)
    scroll_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroll_window.show_all()

    widgets.value_edit_frame.remove(widgets.value_edit_box)
    widgets.value_edit_frame.add(scroll_window)

    widgets.value_edit_box = scroll_window

def clear_effects_edit_panel():
    show_text_in_edit_area(_("Clip Has No Filters"))

def filter_edit_done_stack_update(edited_clip, index=-1):
    """
    EditAction object calls this after edits and undos and redos.
    Methods updates filter stack to new state. 
    """
    if _block_stack_update == True:
        return
        
    if edited_clip != get_edited_clip(): # This gets called by all undos/redos, we only want to update if clip being edited here is affected
        return

    track = _filter_stack.track
    clip_index = _filter_stack.clip_index
        
    global _block_changed_update
    _block_changed_update = True
    update_stack(edited_clip, track, clip_index)
    _block_changed_update = False

    if len(_filter_stack.clip.filters) == 0:
        clear_effects_edit_panel()
    
def filter_edit_multi_done_stack_update(clips):
    for clip in clips:
        if clip == get_edited_clip():
             clear_clip()

def display_kfeditors_tline_frame(frame):
    for kf_widget in keyframe_editor_widgets:
        kf_widget.display_tline_frame(frame)

def update_kfeditors_sliders(frame):
    for kf_widget in keyframe_editor_widgets:
        kf_widget.update_slider_value_display(frame)
        
def update_kfeditors_positions():
    if _filter_stack == None:
        return 

    for kf_widget in keyframe_editor_widgets:
        kf_widget.update_clip_pos()


# ------------------------------------------------ FILTER MASK 
def _filter_mask_launch_pressed(launcher, widget, filter_index):
    filter_names, filter_msgs = mltfilters.get_filter_mask_start_filters_data()
    guipopover.filter_mask_popover_show(launcher, widget, _filter_mask_item_activated, filter_names, filter_msgs, filter_index)

def _filter_mask_item_activated(action, variant, data):
    if _filter_stack == None:
        return False
    
    clip, track, clip_index = _filter_stack.get_clip_data()
    full_stack_mask, msg, current_filter_index = data
    
    filter_info_1 = mltfilters.get_filter_mask_filter(msg)
    filter_info_2 = mltfilters.get_filter_mask_filter("Mask - End")

    if full_stack_mask == True:
        index_1 = 0
        index_2 = len(clip.filters) + 1
    else:
        if current_filter_index != -1:
            index_1 = current_filter_index
            index_2 = current_filter_index + 2
        else:
            index_1 = 0
            index_2 = len(clip.filters) + 1

    data = {"clip":clip, 
            "filter_info_1":filter_info_1,
            "filter_info_2":filter_info_2,
            "index_1":index_1,
            "index_2":index_2,
            "filter_edit_done_func":filter_edit_done_stack_update}
    action = edit.add_two_filters_action(data)

    set_stack_update_blocked()
    action.do_edit()
    set_stack_update_unblocked()

    set_clip(clip, track, clip_index)
    _filter_stack.set_single_expanded(index_1)


# ------------------------------------------------ SAVE, LOAD etc. from hamburger menu
def _hamburger_launch_pressed(launcher, widget, event, data):
    guipopover.effects_editor_hamburger_popover_show(launcher, widget, _clip_hamburger_item_activated)
    
    #guicomponents.get_clip_effects_editor_hamburger_menu(event, _clip_hamburger_item_activated)

def _clip_hamburger_item_activated(action, event, msg):
    if msg == "fade_length":
        dialogs.set_fade_length_default_dialog(_set_fade_length_dialog_callback, PROJECT().get_project_property(appconsts.P_PROP_DEFAULT_FADE_LENGTH))

    if _filter_stack == None:
        return False
    
    if msg == "close":
        clear_clip()
        gui.editor_window.edit_multi.set_visible_child_name(appconsts.EDIT_MULTI_EMPTY)
    elif  msg == "expanded":
        _filter_stack.set_all_filters_expanded_state(True)
    elif  msg == "unexpanded":
        _filter_stack.set_all_filters_expanded_state(False)
    elif  msg == "toggle":
        _toggle_all_pressed()
    elif  msg == "save_stack":
        _save_stack_pressed()
    elif  msg == "load_stack":
        _load_stack_pressed()

def _filter_add_menu_launch_pressed(w, event):
    if _filter_stack != None:
        clip = _filter_stack.clip
        track = _filter_stack.track 
        guipopover.filter_add_popover_show(widgets.filter_add_launch, w, clip, track, event.x, mltfilters.groups, _filter_popover_callback)

def _filter_popover_callback(action, variant, data):
    _filter_menu_callback(None, data)

def _filter_menu_callback(w, data):
    clip, track, item_id, item_data = data
    x, filter_info = item_data

    action = get_filter_add_action(filter_info, clip)
    set_stack_update_blocked() # We update stack on set_clip below
    action.do_edit()
    set_stack_update_unblocked()

    # (re)open clip in editor.
    index = track.clips.index(clip)
    set_clip(clip, track, index)
    set_filter_item_expanded(len(clip.filters) - 1)
    
def _save_effect_values_dialog_callback(dialog, response_id, filter_object):
    if response_id == Gtk.ResponseType.ACCEPT:
        save_path = dialog.get_filenames()[0]
        effect_data = EffectValuesSaveData(filter_object)
        effect_data.save(save_path)
    
    dialog.destroy()

def _load_effect_values_dialog_callback(dialog, response_id, filter_object):
    if response_id == Gtk.ResponseType.ACCEPT:
        load_path = dialog.get_filenames()[0]
        effect_data = utils.unpickle(load_path)
        
        if effect_data.data_applicable(filter_object.info):
            effect_data.set_effect_values(filter_object)
            _filter_stack.reinit_stack_item(filter_object)
        else:
            # Info window
            saved_effect_name = effect_data.info.name
            current_effect_name = filter_object.info.name
            primary_txt = _("Saved Filter data not applicable for this Filter!")
            secondary_txt = _("Saved data is for ") + saved_effect_name + " Filter,\n" + _("current edited Filter is ") + current_effect_name + "."
            dialogutils.warning_message(primary_txt, secondary_txt, gui.editor_window.window)
    
    dialog.destroy()

def _save_effect_stack_values_dialog_callback(dialog, response_id):
    if response_id == Gtk.ResponseType.ACCEPT:
        save_path = dialog.get_filenames()[0]
        stack_data = EffectStackSaveData()
        stack_data.save(save_path)
    dialog.destroy()

def _load_effect_stack_values_dialog_callback(dialog, response_id):
    if response_id == Gtk.ResponseType.ACCEPT:
        load_path = dialog.get_filenames()[0]
        stack_data = utils.unpickle(load_path)

        for effect_data in stack_data.effects_data:
            filter_info, properties, non_mlt_properties = effect_data
      
            data = {"clip":_filter_stack.clip, 
                    "filter_info":filter_info,
                    "filter_edit_done_func":filter_edit_done_stack_update}
            action = edit.add_filter_action(data)

            set_stack_update_blocked()
            action.do_edit()
            set_stack_update_unblocked()
    
            filters = _filter_stack.get_filters()
            filter_object = filters[len(filters) - 1]
    
            filter_object.properties = copy.deepcopy(properties)
            filter_object.non_mlt_properties = copy.deepcopy(non_mlt_properties)
            filter_object.update_mlt_filter_properties_all()

            _filter_stack.reinit_stack_item(filter_object)
                    
    dialog.destroy()

def _reset_filter_values(filter_object):
        filter_object.properties = copy.deepcopy(filter_object.info.properties)
        propertyparse.replace_value_keywords(filter_object.properties, current_sequence().profile)
        
        filter_object.non_mlt_properties = copy.deepcopy(filter_object.info.non_mlt_properties)
        filter_object.update_mlt_filter_properties_all()
                
        _filter_stack.reinit_stack_item(filter_object)

def _set_fade_length_dialog_callback(dialog, response_id, spin):
    if response_id == Gtk.ResponseType.ACCEPT:
        default_length = int(spin.get_value())
        PROJECT().set_project_property(appconsts.P_PROP_DEFAULT_FADE_LENGTH, default_length)
        
    dialog.destroy()


class EffectValuesSaveData:
    
    def __init__(self, filter_object):
        self.info = filter_object.info
        self.multipart_filter = self.info.multipart_filter # DEPRECATED

        # Values of these are edited by the user.
        self.properties = copy.deepcopy(filter_object.properties)
        try:
            self.non_mlt_properties = copy.deepcopy(filter_object.non_mlt_properties)
        except:
            self.non_mlt_properties = [] # Versions prior 0.14 do not have non_mlt_properties and fail here on load

        if self.multipart_filter == True: # DEPRECATED
            self.value = filter_object.value
        else:
            self.value = None
        
    def save(self, save_path):
        with atomicfile.AtomicFileWriter(save_path, "wb") as afw:
            write_file = afw.get_file()
            pickle.dump(self, write_file)
        
    def data_applicable(self, filter_info):
        if isinstance(self.info, filter_info.__class__):
            return self.info.__dict__ == filter_info.__dict__
        return False

    def set_effect_values(self, filter_object):
        if self.multipart_filter == True: # DEPRECATED
            filter_object.value = self.value
         
        filter_object.properties = copy.deepcopy(self.properties)
        filter_object.non_mlt_properties = copy.deepcopy(self.non_mlt_properties)
        filter_object.update_mlt_filter_properties_all()

class EffectStackSaveData:
    def __init__(self):
        self.effects_data = []
        self.empty = True
        filters = _filter_stack.get_filters()
        if len(filters) > 0:
            self.empty = False
            for f in filters:
                self.effects_data.append((f.info,
                                          copy.deepcopy(f.properties),
                                          copy.deepcopy(f.non_mlt_properties)))
                                      
    def save(self, save_path):
        with atomicfile.AtomicFileWriter(save_path, "wb") as afw:
            write_file = afw.get_file()
            pickle.dump(self, write_file)
