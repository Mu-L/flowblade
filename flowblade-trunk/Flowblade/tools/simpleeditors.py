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
    along with Flowblade Movie Editor. If not, see <http://www.gnu.org/licenses/>.
"""

"""
Module for creating simple editors for e.g. container clips program data.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
from gi.repository import GObject
from gi.repository import PangoCairo
import cairo
import copy

import cairoarea
import dialogutils
import editorstate
import gtkbuilder
import guiutils
import respaths
import translations
import webbrowser
import utils

# NOTE: These need to correspond exactly with fluxity.FluxityContext.<editor> enum values because we do not want to import anything into fluxity.py.    
SIMPLE_EDITOR_STRING = 0
SIMPLE_EDITOR_VALUE = 1
SIMPLE_EDITOR_FLOAT = 2
SIMPLE_EDITOR_INT = 3
SIMPLE_EDITOR_COLOR = 4
SIMPLE_EDITOR_FILE_PATH = 5
SIMPLE_EDITOR_OPTIONS = 6
SIMPLE_EDITOR_CHECK_BOX = 7
SIMPLE_EDITOR_FLOAT_RANGE = 8
SIMPLE_EDITOR_INT_RANGE = 9
SIMPLE_EDITOR_PANGO_FONT = 10
SIMPLE_EDITOR_TEXT_AREA = 11
SIMPLE_EDITOR_HTML_LINK = 12

LOCAL_ROOT = "##LOCAL##" # magic value shared with fluxity.py to indicate that we are accessing local file that is part of installation. 

FACE_REGULAR = "Regular"
FACE_BOLD = "Bold"
FACE_ITALIC = "Italic"
FACE_BOLD_ITALIC = "Bold Italic"
DEFAULT_FONT_SIZE = 40

ALIGN_LEFT = 0
ALIGN_CENTER = 1
ALIGN_RIGHT = 2

VERTICAL = 0
HORIZONTAL = 1

NO_PREVIEW_FILE = "fallback_thumb.png"

# Gtk.Adjustments require some bounds.
MIN_VAL = -pow(2, 63) 
MAX_VAL = pow(2, 63)

SIMPLE_EDITOR_LEFT_WIDTH = 150
SIMPLE_EDITOR_RIGHT_WIDTH = 200
MONITOR_WIDTH = 600
MONITOR_HEIGHT = 360


# -------------------------------------------------------------------- Media Plugin timeline clip editor
def show_fluxity_container_clip_program_editor(clip, action_object, script_data_object, name_box):
    editor_panel = FluxityScriptEditorPanel(clip, action_object, script_data_object, name_box)
    return editor_panel

class FluxityScriptEditorPanel:
    def __init__(self, clip, action_object, script_data_object, name_box):
        
        self.clip = clip
        self.action_object = action_object
        self.script_data_object = copy.deepcopy(script_data_object)
         
        self.preview_frame = -1 # -1 used as flag that no preview renders ongoing and new one can be started
         
        # Create panels for objects
        self.editor_widgets = []
        editors_list = self.script_data_object["editors_list"]
        try:
            groups = self.script_data_object["groups_list"]
        except:
            groups = {}

        for editor_data in editors_list:
            name, etype, value = editor_data
            editor_type = int(etype)
            self.editor_widgets.append(_get_editor(editor_type, name, name, value, ""))

        editors_v_panel = Gtk.VBox(False, 2)
        count = 0
        if len(groups.keys()) > 0:
            notebook = Gtk.Notebook()
        else:
            notebook = None
        for w in self.editor_widgets:
            try:
                group_name = groups[count]
                group_label = guiutils.bold_label(translations.plugin_editor_groups[group_name])
                editors_v_panel = Gtk.VBox(False, 2)
                notebook.append_page(editors_v_panel, group_label)
            except:
                pass # no group in this index
                
            editors_v_panel.pack_start(w, False, False, 0)
            count += 1

        pane = Gtk.VBox(False, 2)
        pane.pack_start(name_box, False, False, 0)
        if len(self.editor_widgets) != 0:
            if notebook != None:
                editors_panel = notebook
            else:
                editors_panel = editors_v_panel
            editors_panel.set_margin_top(4)
            pane.pack_start(editors_panel, False, False, 0)
        else:
            pane.pack_start(Gtk.Label(label=_("No Editors for this script")), False, False, 0)
            
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.add(pane)
        self.scrolled_window = sw


    
# -------------------------------------------------------------------- Media Plugin add editors
def create_add_media_plugin_editors(script_data_object):
    global SIMPLE_EDITOR_LEFT_WIDTH
    SIMPLE_EDITOR_LEFT_WIDTH = 200
    
    editors_object = AddMediaPluginEditors(script_data_object)
    return editors_object


class AddMediaPluginEditors:
    def __init__(self, script_data_object):
        self.script_data_object = copy.deepcopy(script_data_object)
        #print(self.script_data_object)
        
        self.preview_frame = -1 # -1 used as flag that no preview renders ongoing and new one can be started
         
        # Create panels for objects
        self.editor_widgets = []
        editors_list = self.script_data_object["editors_list"]
        try:
            groups = self.script_data_object["groups_list"]
        except:
            groups = {}
        
        for editor_data in editors_list:
            name, type, value = editor_data
            editor_type = int(type)
            self.editor_widgets.append(_get_editor(editor_type, name, name, value, ""))

        editors_v_panel = Gtk.VBox(False, 2)
        count = 0
        if len(groups.keys()) > 0:
            notebook = Gtk.Notebook()
        else:
            notebook = None
        for w in self.editor_widgets:
            try:
                group_name = groups[str(count)]
                group_label = guiutils.bold_label(translations.plugin_editor_groups[group_name])
                editors_v_panel = Gtk.VBox(False, 2)
                notebook.append_page(editors_v_panel, group_label)
            except:
                pass # no group in this index
                
            editors_v_panel.pack_start(w, False, False, 0)

            count += 1

        pane = Gtk.VBox(False, 2)
        if len(self.editor_widgets) != 0:
            if notebook != None:
                editors_panel = notebook
            else:
                editors_panel = editors_v_panel
            editors_panel.set_margin_top(4)
            pane.pack_start(editors_panel, False, False, 0)
        else:
            pane.pack_start(Gtk.Label(label=_("No Editors for this script")), False, False, 0)
            
        # Put in scrollpane if too many editors for screensize.
        n_editors = len(self.editor_widgets )
        add_scroll = False
        if editorstate.screen_size_small_height() == True and n_editors > 4:
            add_scroll = True
        elif editorstate.screen_size_small_height() == True and editorstate.screen_size_large_height() == False and n_editors > 5:
            add_scroll = True
        elif editorstate.screen_size_large_height() == True and n_editors > 6:
            add_scroll = True

        if add_scroll == True:
            sw = Gtk.ScrolledWindow()
            sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            sw.add(pane)

        if add_scroll == True:
            editors_panel = sw
        else:
            editors_panel = pane

        self.editors_panel = editors_panel
        
def get_editors_data_as_editors_list(editor_widgets):
    new_editors_list = [] # This is the editors list in format created in
                          # fluxity.FluxityContext.get_script_data()
    for editor in editor_widgets:
        value = editor.get_value()
        # Special casing required for editors that have different internal representation of data
        # compared to what they give to out scripts.
        # BE VERY CAREFUL IF ADDING ANY NEW SUCH EDITORS.
        if editor.editor_type == SIMPLE_EDITOR_COLOR:
            value = editor.get_value_as_color_tuple()
        elif editor.editor_type == SIMPLE_EDITOR_FLOAT_RANGE or editor.editor_type == SIMPLE_EDITOR_INT_RANGE:
            value = editor.get_value_as_range_tuple()
        elif editor.editor_type == SIMPLE_EDITOR_OPTIONS:
            value = editor.get_value_as_tuple()
        new_editor = [editor.id_data, editor.editor_type, value]
        new_editors_list.append(new_editor)

    return new_editors_list
        


# ----------------------------------------------------------------------- editors
def _get_editor(editor_type, id_data, label_text, value, tooltip):
    if editor_type == SIMPLE_EDITOR_STRING:
        editor = TextEditor(id_data, label_text, value, tooltip)
        editor.return_quoted_string = True
        editor.editor_type = SIMPLE_EDITOR_STRING
        return editor
    elif editor_type == SIMPLE_EDITOR_VALUE:
        editor = TextEditor(id_data, label_text, value, tooltip)
        editor.editor_type = SIMPLE_EDITOR_VALUE
        return editor
    elif editor_type == SIMPLE_EDITOR_FLOAT:
        return FloatEditor(id_data, label_text, value, tooltip)
    elif editor_type == SIMPLE_EDITOR_INT:
        return IntEditor(id_data, label_text, value, tooltip)
    elif editor_type == SIMPLE_EDITOR_COLOR:
        return ColorEditor(id_data, label_text, value, tooltip)
    elif editor_type == SIMPLE_EDITOR_FILE_PATH:
        return FilePathEditor(id_data, label_text, value, tooltip)
    elif editor_type == SIMPLE_EDITOR_OPTIONS:
        return OptionsEditor(id_data, label_text, value, tooltip)
    elif editor_type == SIMPLE_EDITOR_CHECK_BOX:
        return CheckboxEditor(id_data, label_text, value, tooltip)
    elif editor_type == SIMPLE_EDITOR_FLOAT_RANGE:
        return FloatEditorRange(id_data, label_text, value, tooltip)
    elif editor_type == SIMPLE_EDITOR_INT_RANGE:
        return IntEditorRange(id_data, label_text, value, tooltip)
    elif editor_type == SIMPLE_EDITOR_PANGO_FONT:
        return PangoFontEditor(id_data, label_text, value, tooltip)
    elif editor_type == SIMPLE_EDITOR_TEXT_AREA:
        return TextAreaEditor(id_data, label_text, value, tooltip)
    elif editor_type == SIMPLE_EDITOR_HTML_LINK:
        return HTMlLinkEditor(id_data, label_text, value, tooltip)
    elif editor_type == EDITOR_GROUP_LABEL:
        return GroupLabel(text)
        
class AbstractSimpleEditor(Gtk.HBox):
    
    def __init__(self, id_data, tooltip):
        GObject.GObject.__init__(self)
        self.id_data = id_data # the data needed to target edited values on correct object.
        self.tooltip = tooltip
        self.editor_type = -1 # dis not through constructor, because _get_editor () elif, is wrong.
        
    def build_editor(self, label_text, widget):
        widget.set_tooltip_text (self.tooltip)
        left_box = guiutils.get_left_justified_box([Gtk.Label(label=translations.get_param_name(label_text))])
        left_box.set_size_request(SIMPLE_EDITOR_LEFT_WIDTH, guiutils.TWO_COLUMN_BOX_HEIGHT)
        widget.set_size_request(SIMPLE_EDITOR_RIGHT_WIDTH, guiutils.TWO_COLUMN_BOX_HEIGHT)

        internal_box = Gtk.HBox(0, False)
        internal_box.pack_start(left_box, False, False, 0)
        internal_box.pack_start(Gtk.Label(), True, True, 0)
        internal_box.pack_start(widget, False, False, 0)

        self.set_margins(internal_box)

        self.pack_start(internal_box, True, True, 0)

    def set_margins(self, editor_panel):
        editor_panel.set_margin_top(2)
        editor_panel.set_margin_start(4)
        editor_panel.set_margin_end(4)
        
class TextEditor(AbstractSimpleEditor):

    def __init__(self, id_data, label_text, value, tooltip):
        AbstractSimpleEditor.__init__(self, id_data, tooltip)
        
        self.return_quoted_string = False # This is set elsewhere if needed
        
        # If input value has quotes we need to strip them before editing
        # and put back when value is asked for.
        if value[0:1] == '"':
            value = value[1:len(value) - 1]

        self.entry = Gtk.Entry()
        self.entry.set_text(value)
        
        self.build_editor(label_text, self.entry)
        # editor type set at _get_editor()
        
    def get_value(self):
        value = self.entry.get_text()
        if self.return_quoted_string == True:
            return '"' + value  + '"'
        else:
            return value


class FloatEditor(AbstractSimpleEditor):

    def __init__(self, id_data, label_text, value, tooltip):
        AbstractSimpleEditor.__init__(self, id_data, tooltip)

        self.spinbutton = Gtk.SpinButton.new_with_range(MIN_VAL, MAX_VAL, 0.1)
        self.spinbutton.set_snap_to_ticks(False)
        self.spinbutton.set_digits(2)
        self.spinbutton.set_value(float(value))
        
        self.build_editor(label_text, self.spinbutton)
        self.editor_type = SIMPLE_EDITOR_FLOAT

    def get_value(self):
        return self.spinbutton.get_value()
            

class IntEditor(AbstractSimpleEditor):

    def __init__(self, id_data, label_text, value, tooltip):
        AbstractSimpleEditor.__init__(self, id_data, tooltip)

        self.spinbutton = Gtk.SpinButton.new_with_range(MIN_VAL, MAX_VAL, 1.0)
        self.spinbutton.set_snap_to_ticks(False)
        self.spinbutton.set_digits(0)
        self.spinbutton.set_value(int(value))
        
        self.build_editor(label_text, self.spinbutton)
        self.editor_type = SIMPLE_EDITOR_INT
        
    def get_value(self):
        return self.spinbutton.get_value_as_int()

class ColorEditor(AbstractSimpleEditor):

    def __init__(self, id_data, label_text, value, tooltip):
        AbstractSimpleEditor.__init__(self, id_data, tooltip)

        try:
            # This works for blender program input data.
            # Values may have parenthesis around 
            if value[0:1] == '(':
                value = value[1:len(value) - 1]

            if value[len(value) - 1:len(value)] == ')':
                value = value[0:len(value) - 1]
            
            value = value.replace(", ", ",") # input value can easily have some extra spaces, even better if we had some generic solution here
            four_float_tuple = tuple(map(float, value.split(',')))
        except:
            # This works for Media Plugins script input data.
            four_float_tuple = value

        rgba = Gdk.RGBA(*four_float_tuple)

        self.colorbutton = Gtk.ColorButton.new_with_rgba(rgba)
        
        self.build_editor(label_text, self.colorbutton)
        self.editor_type = SIMPLE_EDITOR_COLOR
        
    def get_value(self):
        # Blender projects use this output
        value = self.colorbutton.get_rgba().to_string()
        value = value[4:len(value)]
        value = value[0:len(value) - 1]

        color_list = list(map(float, value.split(',')))
        out_value = ""
        for color_val in color_list:
            color_val_str = str(float(color_val) / 255.0)
            out_value += color_val_str
            out_value += ","
            
        out_value += "1.0"

        return out_value
    
    def get_value_as_color_tuple(self):
        color = self.colorbutton.get_rgba()
        return (color.red, color.green, color.blue, 1.0)


class CheckboxEditor(AbstractSimpleEditor):

    def __init__(self, id_data, label_text, value, tooltip):
        AbstractSimpleEditor.__init__(self, id_data, tooltip)
        self.checkbox = Gtk.CheckButton.new()
        self.checkbox.set_active(bool(value))
        
        self.build_editor(label_text, self.checkbox)
        self.editor_type = SIMPLE_EDITOR_CHECK_BOX
        
    def get_value(self):
        return self.checkbox.get_active()

class OptionsEditor(AbstractSimpleEditor):

    def __init__(self, id_data, label_text, value, tooltip):
        AbstractSimpleEditor.__init__(self, id_data, tooltip)
        
        active_index, self.options = value
        self.combo = Gtk.ComboBoxText.new()
        for opt in self.options:
            self.combo.append_text(translations.get_combo_option(opt))
        self.combo.set_active(active_index)
        
        self.build_editor(label_text, self.combo)
        self.editor_type = SIMPLE_EDITOR_OPTIONS

    def get_value_as_tuple(self):
        # e.g. data ["Animation Type", 6, [0, ["Letters", "Words", "Lines"]]]
        # we need to do [0, ["Letters", "Words", "Lines"]] here.
        return (self.get_value(), self.options)
            
    def get_value(self):
        return self.combo.get_active()

class FilePathEditor(AbstractSimpleEditor):

    def __init__(self, id_data, label_text, value, tooltip):
        AbstractSimpleEditor.__init__(self, id_data, tooltip)

        self.file_choose = gtkbuilder.get_file_chooser_button("", Gtk.FileChooserAction.OPEN)
        
        self.build_editor(label_text, self.file_choose)
        self.editor_type = SIMPLE_EDITOR_FILE_PATH
        
    def get_value(self):
        return self.file_choose.get_filename()

class FloatEditorRange(AbstractSimpleEditor):

    def __init__(self, id_data, label_text, value, tooltip):
        AbstractSimpleEditor.__init__(self, id_data, tooltip)
        default_val, min_val, max_val = value
        self.spinbutton = Gtk.SpinButton.new_with_range(float(min_val), float(max_val), 0.1)
        self.spinbutton.set_snap_to_ticks(False)
        self.spinbutton.set_digits(2)
        self.spinbutton.set_value(float(default_val))
        
        self.build_editor(label_text, self.spinbutton)
        self.editor_type = SIMPLE_EDITOR_FLOAT_RANGE

    def get_value_as_range_tuple(self):
        # We need this because externally we are giving value but internally we are 
        # saving value inside tuple with range.
        min, max = self.spinbutton.get_range()
        return (self.spinbutton.get_value(), min, max)
        
    def get_value(self):
        return self.spinbutton.get_value()

class IntEditorRange(AbstractSimpleEditor):

    def __init__(self, id_data, label_text, value, tooltip):
        AbstractSimpleEditor.__init__(self, id_data, tooltip)
        default_val, min_val, max_val = value
        self.spinbutton = Gtk.SpinButton.new_with_range(min_val, max_val, 1.0)
        self.spinbutton.set_snap_to_ticks(False)
        self.spinbutton.set_digits(0)
        self.spinbutton.set_value(int(default_val))
        
        self.build_editor(label_text, self.spinbutton)
        self.editor_type = SIMPLE_EDITOR_INT_RANGE

    def get_value_as_range_tuple(self):
        # We need this because externally we are giving value but internally we are 
        # saving value inside tuple with range.
        min, max = self.spinbutton.get_range()
        return (self.spinbutton.get_value_as_int(), int(min), int(max))
        
    def get_value(self):
        return self.spinbutton.get_value_as_int()

class PangoFontEditor(AbstractSimpleEditor):
    def __init__(self, id_data, label_text, value, tooltip):
        AbstractSimpleEditor.__init__(self, id_data, tooltip)
        notebook = self._get_widget()
        self.set_editor_values(value)

        self.build_editor(label_text, notebook)
        self.editor_type = SIMPLE_EDITOR_PANGO_FONT
    
    def _get_widget(self):
        font_map = PangoCairo.font_map_get_default()
        unsorted_families = font_map.list_families()
        
        self.widgets = utils.EmptyClass()
        
        self.widgets.font_families = sorted(unsorted_families, key=lambda family: family.get_name())
        self.widgets.font_family_indexes_for_name = {}
        combo = Gtk.ComboBoxText()
        indx = 0
        for family in self.widgets.font_families:
            combo.append_text(family.get_name())
            self.widgets.font_family_indexes_for_name[family.get_name()] = indx
            indx += 1
        combo.set_active(0)
        self.widgets.font_select = combo
        #self.font_select.connect("changed", self._edit_value_changed)
        adj = Gtk.Adjustment(value=float(DEFAULT_FONT_SIZE), lower=float(1), upper=float(300), step_increment=float(1))
        self.widgets.size_spin = Gtk.SpinButton()
        self.widgets.size_spin.set_adjustment(adj)

        font_main_row = Gtk.HBox()
        font_main_row.pack_start(self.widgets.font_select, True, True, 0)
        font_main_row.pack_start(guiutils.pad_label(5, 5), False, False, 0)
        font_main_row.pack_start(self.widgets.size_spin, False, False, 0)
        guiutils.set_margins(font_main_row, 0,4,0,0)
        
        self.widgets.bold_font = Gtk.ToggleButton()
        self.widgets.italic_font = Gtk.ToggleButton()
        gtkbuilder.button_set_image_icon_name(self.widgets.bold_font, "format-text-bold")
        gtkbuilder.button_set_image_icon_name(self.widgets.italic_font, "format-text-italic")
        
        self.widgets.left_align = Gtk.RadioButton(None)
        self.widgets.center_align = Gtk.RadioButton.new_from_widget(self.widgets.left_align)
        self.widgets.right_align = Gtk.RadioButton.new_from_widget(self.widgets.left_align)
        gtkbuilder.button_set_image_icon_name(self.widgets.left_align, "format-justify-left")
        gtkbuilder.button_set_image_icon_name(self.widgets.center_align, "format-justify-center")
        gtkbuilder.button_set_image_icon_name(self.widgets.right_align, "format-justify-right")
        
        self.widgets.left_align.set_mode(False)
        self.widgets.center_align.set_mode(False)
        self.widgets.right_align.set_mode(False)
        
        self.widgets.color_button = Gtk.ColorButton.new_with_rgba(Gdk.RGBA(red=1.0, green=1.0, blue=1.0, alpha=1.0))
        self.widgets.fill_on = Gtk.CheckButton()
        self.widgets.fill_on.set_active(True)

        buttons_box = Gtk.HBox()
        buttons_box.pack_start(Gtk.Label(), True, True, 0)
        buttons_box.pack_start(self.widgets.bold_font, False, False, 0)
        buttons_box.pack_start(self.widgets.italic_font, False, False, 0)
        buttons_box.pack_start(guiutils.pad_label(5, 5), False, False, 0)
        buttons_box.pack_start(self.widgets.left_align, False, False, 0)
        buttons_box.pack_start(self.widgets.center_align, False, False, 0)
        buttons_box.pack_start(self.widgets.right_align, False, False, 0)
        buttons_box.pack_start(guiutils.pad_label(15, 5), False, False, 0)
        buttons_box.pack_start(self.widgets.color_button, False, False, 0)
        buttons_box.pack_start(guiutils.pad_label(2, 1), False, False, 0)
        buttons_box.pack_start(self.widgets.fill_on, False, False, 0)
        buttons_box.pack_start(Gtk.Label(), True, True, 0)

        # ------------------------------------------- Outline Panel
        outline_size = Gtk.Label(label=_("Size:"))
        
        self.widgets.out_line_color_button = Gtk.ColorButton.new_with_rgba(Gdk.RGBA(red=0.3, green=0.3, blue=0.3, alpha=1.0))

        adj2 = Gtk.Adjustment(value=float(3), lower=float(1), upper=float(50), step_increment=float(1))
        self.widgets.out_line_size_spin = Gtk.SpinButton()
        self.widgets.out_line_size_spin.set_adjustment(adj2)

        self.widgets.outline_on = Gtk.CheckButton()
        self.widgets.outline_on.set_active(False)
        
        outline_box = Gtk.HBox()
        outline_box.pack_start(outline_size, False, False, 0)
        outline_box.pack_start(guiutils.pad_label(2, 1), False, False, 0)
        outline_box.pack_start(self.widgets.out_line_size_spin, False, False, 0)
        outline_box.pack_start(guiutils.pad_label(15, 1), False, False, 0)
        outline_box.pack_start(self.widgets.out_line_color_button, False, False, 0)
        outline_box.pack_start(guiutils.pad_label(2, 1), False, False, 0)
        outline_box.pack_start(self.widgets.outline_on, False, False, 0)
        outline_box.pack_start(Gtk.Label(), True, True, 0)

        # -------------------------------------------- Shadow panel 
        shadow_opacity_label = Gtk.Label(label=_("Opacity:"))
        shadow_xoff = Gtk.Label(label=_("X Off:"))
        shadow_yoff = Gtk.Label(label=_("Y Off:"))
        shadow_blur_label = Gtk.Label(label=_("Blur:"))
        
        self.widgets.shadow_opa_spin = Gtk.SpinButton()

        adj3 = Gtk.Adjustment(value=float(100), lower=float(1), upper=float(100), step_increment=float(1))
        self.widgets.shadow_opa_spin.set_adjustment(adj3)

        self.widgets.shadow_xoff_spin = Gtk.SpinButton()

        adj4 = Gtk.Adjustment(value=float(3), lower=float(1), upper=float(100), step_increment=float(1))
        self.widgets.shadow_xoff_spin.set_adjustment(adj4)

        self.widgets.shadow_yoff_spin = Gtk.SpinButton()

        adj5 = Gtk.Adjustment(value=float(3), lower=float(1), upper=float(100), step_increment=float(1))
        self.widgets.shadow_yoff_spin.set_adjustment(adj5)

        self.widgets.shadow_on = Gtk.CheckButton()
        self.widgets.shadow_on.set_active(False)
        
        self.widgets.shadow_color_button = Gtk.ColorButton.new_with_rgba(Gdk.RGBA(red=0.3, green=0.3, blue=0.3, alpha=1.0))

        self.widgets.shadow_blur_spin = Gtk.SpinButton()
        adj6 = Gtk.Adjustment(value=float(0), lower=float(0), upper=float(20), step_increment=float(1))
        self.widgets.shadow_blur_spin.set_adjustment(adj6)

        shadow_box_1 = Gtk.HBox()
        shadow_box_1.pack_start(shadow_opacity_label, False, False, 0)
        shadow_box_1.pack_start(self.widgets.shadow_opa_spin, False, False, 0)
        shadow_box_1.pack_start(guiutils.pad_label(15, 1), False, False, 0)
        shadow_box_1.pack_start(self.widgets.shadow_color_button, False, False, 0)
        shadow_box_1.pack_start(guiutils.pad_label(2, 1), False, False, 0)
        shadow_box_1.pack_start(self.widgets.shadow_on, False, False, 0)
        shadow_box_1.pack_start(Gtk.Label(), True, True, 0)
        guiutils.set_margins(shadow_box_1, 0,4,0,0)

        shadow_box_2 = Gtk.HBox()
        shadow_box_2.pack_start(shadow_xoff, False, False, 0)
        shadow_box_2.pack_start(self.widgets.shadow_xoff_spin, False, False, 0)
        shadow_box_2.pack_start(guiutils.pad_label(15, 1), False, False, 0)
        shadow_box_2.pack_start(shadow_yoff, False, False, 0)
        shadow_box_2.pack_start(self.widgets.shadow_yoff_spin, False, False, 0)
        shadow_box_2.pack_start(Gtk.Label(), True, True, 0)

        shadow_box_3 = Gtk.HBox()
        shadow_box_3.pack_start(shadow_blur_label, False, False, 0)
        shadow_box_3.pack_start(self.widgets.shadow_blur_spin, False, False, 0)
        shadow_box_3.pack_start(Gtk.Label(), True, True, 0)

        # ------------------------------------ Gradient panel
        self.widgets.gradient_color_button = Gtk.ColorButton.new_with_rgba(Gdk.RGBA(red=0.0, green=0.0, blue=0.8, alpha=1.0))
        self.widgets.gradient_on = Gtk.CheckButton()
        self.widgets.gradient_on.set_active(True)

        direction_label = Gtk.Label(label=_("Gradient Direction:"))
        self.widgets.direction_combo = Gtk.ComboBoxText()
        self.widgets.direction_combo.append_text(_("Vertical"))
        self.widgets.direction_combo.append_text(_("Horizontal"))
        self.widgets.direction_combo.set_active(0)
         
        gradient_box_row1 = Gtk.HBox()
        gradient_box_row1.pack_start(self.widgets.gradient_on, False, False, 0)
        gradient_box_row1.pack_start(self.widgets.gradient_color_button, False, False, 0)
        gradient_box_row1.pack_start(Gtk.Label(), True, True, 0)

        gradient_box_row2 = Gtk.HBox()
        gradient_box_row2.pack_start(direction_label, False, False, 0)
        gradient_box_row2.pack_start(self.widgets.direction_combo, False, False, 0)
        gradient_box_row2.pack_start(Gtk.Label(), True, True, 0)
        
        gradient_box = Gtk.VBox()
        gradient_box.pack_start(gradient_box_row1, False, False, 0)
        gradient_box.pack_start(gradient_box_row2, False, False, 0)
        gradient_box.pack_start(Gtk.Label(), True, True, 0)

        controls_panel_2 = Gtk.VBox()
        controls_panel_2.pack_start(font_main_row, False, False, 0)
        controls_panel_2.pack_start(buttons_box, False, False, 0)

        controls_panel_3 = Gtk.VBox()
        controls_panel_3.pack_start(outline_box, False, False, 0)

        controls_panel_4 = Gtk.VBox()
        controls_panel_4.pack_start(shadow_box_1, False, False, 0)
        controls_panel_4.pack_start(shadow_box_2, False, False, 0)
        controls_panel_4.pack_start(shadow_box_3, False, False, 0)

        controls_panel_5 = Gtk.VBox()
        controls_panel_5.pack_start(gradient_box, False, False, 0)

        notebook = Gtk.Notebook()
        notebook.append_page(guiutils.set_margins(controls_panel_2,8,8,8,8), Gtk.Label(label=_("Font")))
        notebook.append_page(guiutils.set_margins(controls_panel_3,8,8,8,8), Gtk.Label(label=_("Outline")))
        notebook.append_page(guiutils.set_margins(controls_panel_4,8,8,8,8), Gtk.Label(label=_("Shadow")))
        notebook.append_page(guiutils.set_margins(controls_panel_5,8,8,8,8), Gtk.Label(label=_("Gradient")))
        
        return notebook

    def set_editor_values(self, font_data):
        font_family, font_face, font_size, alignment, color_rgba, fill_on, outline_color_rgba, outline_on, \
        outline_width, shadow_on, shadow_color_rgb, shadow_opacity, shadow_xoff, \
        shadow_yoff, shadow_blur, gradient_color_rgba, \
        gradient_direction = font_data

        r, g, b, a = color_rgba
        button_color = Gdk.RGBA(r, g, b, 1.0)
        self.widgets.color_button.set_rgba(button_color)

        if FACE_REGULAR == font_face:
            self.widgets.bold_font.set_active(False)
            self.widgets.italic_font.set_active(False)
        elif FACE_BOLD == font_face:
            self.widgets.bold_font.set_active(True)
            self.widgets.italic_font.set_active(False)
        elif FACE_ITALIC == font_face:
            self.widgets.bold_font.set_active(False)
            self.widgets.italic_font.set_active(True) 
        else:#FACE_BOLD_ITALIC
            self.widgets.bold_font.set_active(True)
            self.widgets.italic_font.set_active(True)

        if alignment == ALIGN_LEFT:
            self.widgets.left_align.set_active(True)
        elif alignment == ALIGN_CENTER:
            self.widgets.center_align.set_active(True)
        else:#ALIGN_RIGHT
            self.widgets.right_align.set_active(True)

        self.widgets.size_spin.set_value(font_size)
        
        try:
            combo_index = self.widgets.font_family_indexes_for_name[font_family]
            self.widgets.font_select.set_active(combo_index)
        except:# if font family not found we'll use first. This happens e.g at start-up if "Times New Roman" not in system.
            family = self.widgets.font_families[0]
            font_family = family.get_name()
            self.widgets.font_select.set_active(0)
        
        self.widgets.fill_on.set_active(fill_on)
                
        # OUTLINE
        r, g, b, a = outline_color_rgba
        button_color = Gdk.RGBA(r, g, b, 1.0)
        self.widgets.out_line_color_button.set_rgba(button_color)
        self.widgets.out_line_size_spin.set_value(outline_width)
        self.widgets.outline_on.set_active(outline_on)
        
        # SHADOW
        r, g, b = shadow_color_rgb
        button_color = Gdk.RGBA(r, g, b, 1.0)
        self.widgets.shadow_color_button.set_rgba(button_color)
        self.widgets.shadow_opa_spin.set_value(shadow_opacity)
        self.widgets.shadow_xoff_spin.set_value(shadow_xoff)
        self.widgets.shadow_yoff_spin.set_value(shadow_yoff)
        self.widgets.shadow_on.set_active(shadow_on)
        self.widgets.shadow_blur_spin.set_value(shadow_blur)
        
        # GRADIENT
        if gradient_color_rgba != None:
            r, g, b, a = gradient_color_rgba
            button_color = Gdk.RGBA(r, g, b, 1.0)
            self.widgets.gradient_color_button.set_rgba(button_color)
            self.widgets.gradient_on.set_active(True)
        else:
            button_color = Gdk.RGBA(0.0, 0.0, 0.6, 1.0)
            self.widgets.gradient_color_button.set_rgba(button_color)
            self.widgets.gradient_on.set_active(False)
        self.widgets.direction_combo.set_active(gradient_direction)

    def get_editor_values(self):

        family = self.widgets.font_families[self.widgets.font_select.get_active()]
        font_family = family.get_name()

        font_size = self.widgets.size_spin.get_value_as_int()
        
        face = FACE_REGULAR
        if self.widgets.bold_font.get_active() and self.widgets.italic_font.get_active():
            face = FACE_BOLD_ITALIC
        elif self.widgets.italic_font.get_active():
            face = FACE_ITALIC
        elif self.widgets.bold_font.get_active():
            face = FACE_BOLD
        font_face = face
        
        align = ALIGN_LEFT
        if self.widgets.center_align.get_active():
            align = ALIGN_CENTER
        elif  self.widgets.right_align.get_active():
             align = ALIGN_RIGHT
        alignment = align

        color = self.widgets.color_button.get_color()
        r, g, b = utils.hex_to_rgb(color.to_string())
        new_color = (r/65535.0, g/65535.0, b/65535.0, 1.0)        
        color_rgba = new_color
        fill_on = self.widgets.fill_on.get_active()
        
        # OUTLINE
        color = self.widgets.out_line_color_button.get_color()
        r, g, b = utils.hex_to_rgb(color.to_string())
        new_color2 = (r/65535.0, g/65535.0, b/65535.0, 1.0)    
        outline_color_rgba = new_color2
        outline_on = self.widgets.outline_on.get_active()
        outline_width = self.widgets.out_line_size_spin.get_value()

        # SHADOW
        color = self.widgets.shadow_color_button.get_color()
        r, g, b = utils.hex_to_rgb(color.to_string())
        new_color3 = (r/65535.0, g/65535.0, b/65535.0)  
        shadow_color_rgb = new_color3
        shadow_on = self.widgets.shadow_on.get_active()
        shadow_opacity = self.widgets.shadow_opa_spin.get_value()
        shadow_xoff = self.widgets.shadow_xoff_spin.get_value()
        shadow_yoff = self.widgets.shadow_yoff_spin.get_value()
        shadow_blur = self.widgets.shadow_blur_spin.get_value()
        
        # GRADIENT
        if self.widgets.gradient_on.get_active() == True:
            color = self.widgets.gradient_color_button.get_color()
            r, g, b = utils.hex_to_rgb(color.to_string())
            new_color = (r/65535.0, g/65535.0, b/65535.0, 1.0)  
            gradient_color_rgba = new_color
        else:
            gradient_color_rgba = None
        gradient_direction = self.widgets.direction_combo.get_active() # Combo indexes correspond with values of VERTICAL and HORIZONTAL

        return (font_family, font_face, font_size, alignment, color_rgba, \
        fill_on, outline_color_rgba, outline_on, \
        outline_width, shadow_on, shadow_color_rgb, shadow_opacity, shadow_xoff, \
        shadow_yoff, shadow_blur, gradient_color_rgba, \
        gradient_direction)

    def get_value(self):
        return self.get_editor_values()


class TextAreaEditor(AbstractSimpleEditor):

    def __init__(self, id_data, label_text, value, tooltip):
        AbstractSimpleEditor.__init__(self, id_data, tooltip)

        editor_label = Gtk.Label(label=translations.get_param_name(label_text))
        editor_label.set_margin_end(12)
        
        self.text_view = Gtk.TextView()
        self.text_view.set_pixels_above_lines(2)
        self.text_view.set_left_margin(2)
        self.text_view.get_buffer().set_text(value)

        self.sw = Gtk.ScrolledWindow()
        self.sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.ALWAYS)
        self.sw.add(self.text_view)
        self.sw.set_size_request(300, 200)

        self.scroll_frame = Gtk.Frame()
        self.scroll_frame.add(self.sw)

        widget = self.scroll_frame
        widget.set_tooltip_text (self.tooltip)
        widget.set_size_request(SIMPLE_EDITOR_RIGHT_WIDTH, guiutils.TWO_COLUMN_BOX_HEIGHT)

        internal_box = Gtk.HBox(0, False)
        internal_box.pack_start(editor_label, False, False, 0)
        internal_box.pack_start(widget, True, True, 0)

        self.set_margins(internal_box)

        self.pack_start(internal_box, True, True, 0)
        
        self.editor_type = SIMPLE_EDITOR_TEXT_AREA

    def get_value(self):
        buf = self.text_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), include_hidden_chars=True)
        return text

class HTMlLinkEditor(AbstractSimpleEditor):

    def __init__(self, id_data, label_text, value, tooltip):
        AbstractSimpleEditor.__init__(self, id_data, tooltip)

        self.value = value

        self.button = Gtk.Button(label=label_text)
        self.button.connect("clicked", lambda w: self._button_pressed())
        
        widget = self.button
        widget.set_tooltip_text (self.tooltip)

        internal_box = Gtk.HBox(0, False)
        internal_box.pack_start(Gtk.Label(), True, True, 0)
        internal_box.pack_start(widget, False, False, 0)
        internal_box.pack_start(Gtk.Label(), True, True, 0)

        internal_box.set_margin_top(12)
        internal_box.set_margin_top(12)
        internal_box.set_margin_start(4)
        internal_box.set_margin_end(4)

        self.pack_start(internal_box, True, True, 0)

        self.editor_type = SIMPLE_EDITOR_HTML_LINK

    def _button_pressed(self):
        try:
            if self.value.startswith(LOCAL_ROOT):
                print("jj")
                self.value = self.value[len(LOCAL_ROOT):]
            url = "file://" + respaths.ROOT_PATH + self.value # "/res/help/en/advanced.html#9._Credits_Scroll_Generator"
            print(url)
            webbrowser.open(url)
        except:
            dialogutils.info_message(_("Help page not found!"), _("Unfortunately the webresource containing help information\nfor this application was not found."), None)
        
    def get_value(self):
        return self.value

# ------------------------------------------------------------------- preview
class PreviewPanel(Gtk.VBox):

    def __init__(self, parent, clip, length=-1):
        GObject.GObject.__init__(self)

        self.frame = 0
        self.parent = parent
        self.preview_surface = None # gets set by parent on preview completion
        
        self.preview_info = Gtk.Label()
        self.preview_info.set_markup("<small>" + _("no preview") + "</small>" )
        preview_info_row = Gtk.HBox()
        preview_info_row.pack_start(self.preview_info, False, False, 0)
        preview_info_row.pack_start(Gtk.Label(), True, True, 0)
        preview_info_row.set_margin_top(6)
        preview_info_row.set_margin_bottom(8)

        self.preview_monitor = cairoarea.CairoDrawableArea2(MONITOR_WIDTH, MONITOR_HEIGHT, self._draw_preview)

        self.no_preview_icon = cairo.ImageSurface.create_from_png(respaths.IMAGE_PATH + NO_PREVIEW_FILE)

        # Control row
        self.frame_display = Gtk.Label(label=_("Clip Frame"))
        self.frame_display.set_margin_end(2)
        
        if length == -1:
            length = clip.clip_out - clip.clip_in
        
        self.frame_select = Gtk.SpinButton.new_with_range (0, length, 1)
        self.frame_select.set_value(0)
        
        self.preview_button = Gtk.Button(label=_("Preview"))
        self.preview_button.connect("clicked", lambda w: parent.render_preview_frame())
                            
        control_panel = Gtk.HBox(False, 2)
        control_panel.pack_start(self.frame_display, False, False, 0)
        control_panel.pack_start(self.frame_select, False, False, 0)
        control_panel.pack_start(Gtk.Label(), True, True, 0)
        control_panel.pack_start(self.preview_button, False, False, 0)

        self.pack_start(preview_info_row, False, False, 0)
        self.pack_start(self.preview_monitor, False, False, 0)
        self.pack_start(guiutils.pad_label(4,4), False, False, 0)
        self.pack_start(control_panel, False, False, 0)
        self.pack_start(Gtk.Label(), True, True, 0)

    def _draw_preview(self, event, cr, allocation):
        x, y, w, h = allocation

        if self.preview_surface != None:
            sw = self.preview_surface.get_width()
            scale = float(w) / float(sw)
            cr.scale(scale, scale) # pixel aspect ratio not used in computation, correct image only for square pixel formats.
            cr.set_source_surface(self.preview_surface, 0, 0)
            cr.paint()
        else:
            cr.set_source_rgb(0.0, 0.0, 0.0)
            cr.rectangle(0, 0, w, h)
            cr.fill()
