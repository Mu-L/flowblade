"""
    Flowblade Movie Editor is a nonlinear video editor.
    Copyright 2014 Janne Liljeblad.

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
This module contains complex property editors.
"""

from PIL import Image

from datetime import datetime
import math
import os
import webbrowser

from gi.repository import Gtk

import appconsts
import cairo
import cairoarea
import dialogutils
from editorstate import PROJECT
import guiutils
import guicomponents
import glassbuttons
import jobs
import lutfilter
import motiontracking
import respaths
import translations
import utils

SHADOW = 0
MID = 1
HI = 2

NO_HIT = 99

SELECT_CIRCLE = 0
SELECT_LINE = 1

ACTIVE_RING_COLOR = (0.0, 0.0, 0.0)
DEACTIVE_RING_COLOR = (0.6, 0.6, 0.6)

ACTIVE_SHADOW_COLOR = (0.15, 0.15, 0.15)
ACTIVE_MID_COLOR = (0.5, 0.5, 0.5)
ACTIVE_HI_COLOR = (1.0, 1.0, 1.0)

DEACTIVE_SHADOW_COLOR = (0.6, 0.6, 0.6)
DEACTIVE_MID_COLOR = (0.7, 0.7, 0.7)
DEACTIVE_HI_COLOR = (0.85, 0.85, 0.85)

BOX_BG_COLOR = (0.8, 0.8, 0.8)
BOX_LINE_COLOR = (0.4, 0.4, 0.4)

CURVE_COLOR = (0, 0, 0)
R_CURVE_COLOR = (0.78, 0, 0)
G_CURVE_COLOR = (0, 0.75, 0)
B_CURVE_COLOR = (0, 0, 0.8)

RED_STOP = (0, 1, 0, 0, 1)
YELLOW_STOP = (1.0/6.0, 1, 1, 0, 1)
GREEN_STOP = (2.0/6.0, 0, 1, 0, 1)
CYAN_STOP = (3.0/6.0, 0, 1, 1, 1)
BLUE_STOP = (4.0/6.0, 0, 0, 1, 1)
MAGENTA_STOP = (5.0/6.0, 1, 0, 1, 1)
RED_STOP_END = (1, 1, 0, 0, 1)

GREY_GRAD_1 = (1, 0.4, 0.4, 0.4, 1)
GREY_GRAD_2 = (0, 0.4, 0.4, 0.4, 0)

MID_GREY_GRAD_1 = (1, 0.3, 0.3, 0.3, 0)
MID_GREY_GRAD_2 = (0.5, 0.3, 0.3, 0.3, 1)
MID_GREY_GRAD_3 = (0, 0.3, 0.3, 0.3, 0)

CIRCLE_GRAD_1 = (1, 0.3, 0.3, 0.3, 1)
CIRCLE_GRAD_2 = (0, 0.8, 0.8, 0.8, 1)

FX_GRAD_1 = (0, 1.0, 1.0, 1.0, 0.4)
FX_GRAD_2 = (1, 0.3, 0.3, 0.3, 0.4)


accessable_editors = {}

def _p(name):
    try:
        return translations.param_names[name]
    except KeyError:
        return name

def _draw_select_circle(cr, x, y, main_color, radius, small_radius, pad, x_off=0, y_off=0):
    degrees = math.pi / 180.0

    grad = cairo.LinearGradient (x, y, x, y + 2 * radius)
    grad.add_color_stop_rgba(*CIRCLE_GRAD_1)
    grad.add_color_stop_rgba(*CIRCLE_GRAD_2)
    cr.set_source(grad)
    cr.move_to(x + pad, y + pad)
    cr.arc (x + pad, y + pad, radius, 0.0 * degrees, 360.0 * degrees)
    cr.fill()

    cr.set_source_rgb(*main_color)
    cr.move_to(x + pad, y + pad)
    cr.arc (x + pad, y + pad, small_radius, 0.0 * degrees, 360.0 * degrees)
    cr.fill()

    grad = cairo.LinearGradient (x, y, x, y + 2 * radius)
    grad.add_color_stop_rgba(*FX_GRAD_1)
    grad.add_color_stop_rgba(*FX_GRAD_2)
    cr.set_source(grad)
    cr.move_to(x + pad, y + pad)
    cr.arc (x + pad, y + pad, small_radius, 0.0 * degrees, 360.0 * degrees)
    cr.fill()

    x = x + x_off
    y = y + y_off

    cr.set_source_rgb(0.4,0.4,0.4)
    cr.set_line_width(1.0)
    cr.move_to(x + radius - 0.5, y)
    cr.line_to(x + radius - 0.5, y + 2 * radius)
    cr.stroke()

    cr.set_source_rgb(0.4,0.4,0.4)
    cr.set_line_width(1.0)
    cr.move_to(x, y + radius - 0.5)
    cr.line_to(x + 2 * radius, y + radius - 0.5)
    cr.stroke()

    cr.set_source_rgb(0.6,0.6,0.6)
    cr.move_to(x, y + radius + 0.5)
    cr.line_to(x + radius * 2.0, y + radius + 0.5)
    cr.stroke()

    cr.set_source_rgb(0.6,0.6,0.6)
    cr.move_to(x + radius + 0.5, y)
    cr.line_to(x + radius + 0.5, y + 2 * radius)
    cr.stroke()

def _draw_select_line(cr, x, y):
    height = 22
    y = y - 19

    cr.set_source_rgb(0.7,0.7,0.7)
    cr.rectangle(x - 2.0, y, 4, height)
    cr.fill()

    cr.set_source_rgb(0.3,0.3,0.3)
    cr.set_line_width(1.0)
    cr.move_to(x - 0.5, y)
    cr.line_to(x - 0.5, y + height)
    cr.stroke()

    cr.set_source_rgb(0.95,0.95,0.95)
    cr.move_to(x + 0.5, y)
    cr.line_to(x + 0.5, y + height)
    cr.stroke()

def _draw_cursor_indicator(cr, x, y, radius):
    degrees = math.pi / 180.0

    pad = radius
    cr.set_source_rgba(0.9, 0.9, 0.9, 0.6)
    cr.set_line_width(3.0)
    cr.arc (x + pad, y + pad, radius, 0.0 * degrees, 360.0 * degrees)
    cr.stroke()


class ColorBox:

    def __init__(self, edit_listener, width=260, height=260):
        self.W = width
        self.H = height
        self.widget = cairoarea.CairoDrawableArea2( self.W,
                                                    self.H,
                                                    self._draw)
        self.widget.press_func = self._press_event
        self.widget.motion_notify_func = self._motion_notify_event
        self.widget.release_func = self._release_event
        self.X_PAD = 12
        self.Y_PAD = 12
        self.CIRCLE_HALF = 8
        self.cursor_x = self.X_PAD
        self.cursor_y = self.H - self.Y_PAD
        self.edit_listener = edit_listener
        self.hue = 0.0
        self.saturation = 0.0
        self.draw_saturation_gradient = True
        self.selection_cursor = SELECT_CIRCLE
        self.motion_on = False

    def get_hue_saturation(self):
        return (self.hue, self.saturation)

    def _save_values(self):
        self.hue = float((self.cursor_x - self.X_PAD)) / float((self.W - 2 * self.X_PAD))
        self.saturation = float(abs(self.cursor_y - self.H + self.Y_PAD)) / float((self.H - 2 * self.Y_PAD))

    def set_cursor(self, hue, saturation):
        self.cursor_x = self._x_for_hue(hue)
        self.cursor_y = self._y_for_saturation(saturation)
        self._save_values()

    def _x_for_hue(self, hue):
        return self.X_PAD + hue * (self.W - self.X_PAD * 2)

    def _y_for_saturation(self, saturation):
        return self.Y_PAD + (1.0 - saturation) * (self.H - self.Y_PAD *2)

    def _press_event(self, event):
        self.cursor_x, self.cursor_y = self._get_legal_point(event.x, event.y)
        self._save_values()
        self.edit_listener()
        self.widget.queue_draw()
        self.motion_on = True

    def _motion_notify_event(self, x, y, state):
        if self.motion_on == False:
            return
        self.cursor_x, self.cursor_y = self._get_legal_point(x, y)
        self._save_values()
        self.edit_listener()
        self.widget.queue_draw()

    def _release_event(self, event):
        self.cursor_x, self.cursor_y = self._get_legal_point(event.x, event.y)
        self._save_values()
        self.edit_listener()
        self.widget.queue_draw()
        self.motion_on = False
        
    def _get_legal_point(self, x, y):
        if x < self.X_PAD:
            x = self.X_PAD
        elif x > self.W - self.X_PAD:
            x = self.W - self.X_PAD

        if y < self.Y_PAD:
            y = self.Y_PAD
        elif y > self.H - self.Y_PAD:
            y = self.H - self.Y_PAD

        return (x, y)

    def _draw(self, event, cr, allocation):
        """
        Callback for repaint from CairoDrawableArea.
        We get cairo context and allocation.
        """
        x, y, w, h = allocation

        # Draw bg
        #cr.set_source_rgb(*guiutils.get_theme_bg_color())
        #cr.rectangle(0, 0, w, h)
        #cr.fill()

        x_in = self.X_PAD
        x_out = self.W - self.X_PAD
        y_in = self.Y_PAD
        y_out = self.H - self.Y_PAD

        grad = cairo.LinearGradient (x_in, 0, x_out, 0)
        grad.add_color_stop_rgba(*RED_STOP)
        grad.add_color_stop_rgba(*YELLOW_STOP)
        grad.add_color_stop_rgba(*GREEN_STOP)
        grad.add_color_stop_rgba(*CYAN_STOP)
        grad.add_color_stop_rgba(*MAGENTA_STOP)
        grad.add_color_stop_rgba(*RED_STOP_END)

        cr.set_source(grad)
        cr.rectangle(self.X_PAD, self.Y_PAD, x_out - x_in, y_out - y_in)
        cr.fill()

        if self.draw_saturation_gradient == True:
            grey_grad = cairo.LinearGradient (0, y_in, 0, y_out)
            grey_grad.add_color_stop_rgba(*GREY_GRAD_1)
            grey_grad.add_color_stop_rgba(*GREY_GRAD_2)

            cr.set_source(grey_grad)
            cr.rectangle(self.X_PAD, self.Y_PAD, x_out - x_in, y_out - y_in)
            cr.fill()

        if self.selection_cursor == SELECT_CIRCLE:
            _draw_select_circle(cr, self.cursor_x - self.CIRCLE_HALF, self.cursor_y - self.CIRCLE_HALF, (1, 1, 1), 8, 6, 8)
        else:
            _draw_select_line(cr, self.cursor_x, y_out)

class ThreeBandColorBox(ColorBox):

    def __init__(self, edit_listener, band_change_listerner, width=260, height=260):
        ColorBox.__init__(self, edit_listener, width, height)
        self.band = SHADOW
        self.shadow_x = self.cursor_x
        self.shadow_y = self.cursor_y
        self.mid_x = self.cursor_x
        self.mid_y = self.cursor_y
        self.hi_x = self.cursor_x
        self.hi_y = self.cursor_y
        self.band_change_listerner = band_change_listerner
        self.motion_on = False

    def set_cursors(self, s_h, s_s, m_h, m_s, h_h, h_s):
        self.shadow_x = self._x_for_hue(s_h)
        self.shadow_y = self._y_for_saturation(s_s)
        self.mid_x = self._x_for_hue(m_h)
        self.mid_y = self._y_for_saturation(m_s)
        self.hi_x = self._x_for_hue(h_h)
        self.hi_y = self._y_for_saturation(h_s)

    def _press_event(self, event):
        self.cursor_x, self.cursor_y = self._get_legal_point(event.x, event.y)
        hit_value = self._check_band_hit(self.cursor_x, self.cursor_y)
        if hit_value != self.band and hit_value != NO_HIT:
            self.band = hit_value
            self.band_change_listerner(self.band)
        self._save_values()
        self.edit_listener()
        self.widget.queue_draw()
        self.motion_on = True
        
    def _motion_notify_event(self, x, y, state):
        if self.motion_on == False:
            return
        self.cursor_x, self.cursor_y = self._get_legal_point(x, y)
        self._save_values()
        self.edit_listener()
        self.widget.queue_draw()

    def _release_event(self, event):
        if self.motion_on == False:
            return
        self.cursor_x, self.cursor_y = self._get_legal_point(event.x, event.y)
        self._save_values()
        self.edit_listener()
        self.widget.queue_draw()
        self.motion_on = False
        
    def _check_band_hit(self, x, y):
        if self._control_point_hit(x, y, self.shadow_x, self.shadow_y):
            return SHADOW
        elif self._control_point_hit(x, y, self.mid_x, self.mid_y):
            return MID
        elif self._control_point_hit(x, y, self.hi_x, self.hi_y):
            return HI
        else:
            return NO_HIT

    def _control_point_hit(self, x, y, cx, cy):
        if x >= cx - self.CIRCLE_HALF and x <= cx + self.CIRCLE_HALF:
            if y >= cy - self.CIRCLE_HALF and y <= cy + self.CIRCLE_HALF:
                return True
        return False

    def _save_values(self):
        self.hue = float((self.cursor_x - self.X_PAD)) / float((self.W - 2 * self.X_PAD))
        self.saturation = float(abs(self.cursor_y - self.H + self.Y_PAD)) / float((self.H - 2 * self.Y_PAD))
        if self.band == SHADOW:
            self.shadow_x = self.cursor_x
            self.shadow_y = self.cursor_y
        elif self.band == MID:
            self.mid_x = self.cursor_x
            self.mid_y = self.cursor_y
        else:
            self.hi_x = self.cursor_x
            self.hi_y = self.cursor_y

    def _draw(self, event, cr, allocation):
        """
        Callback for repaint from CairoDrawableArea.
        We get cairo context and allocation.
        """
        x, y, w, h = allocation

        # Draw bg
        #cr.set_source_rgb(*guiutils.get_theme_bg_color())
        #cr.rectangle(0, 0, w, h)
        #cr.fill()

        x_in = self.X_PAD
        x_out = self.W - self.X_PAD
        y_in = self.Y_PAD
        y_out = self.H - self.Y_PAD

        grad = cairo.LinearGradient (x_in, 0, x_out, 0)
        grad.add_color_stop_rgba(*RED_STOP)
        grad.add_color_stop_rgba(*YELLOW_STOP)
        grad.add_color_stop_rgba(*GREEN_STOP)
        grad.add_color_stop_rgba(*CYAN_STOP)
        grad.add_color_stop_rgba(*MAGENTA_STOP)
        grad.add_color_stop_rgba(*RED_STOP_END)

        cr.set_source(grad)
        cr.rectangle(self.X_PAD, self.Y_PAD, x_out - x_in, y_out - y_in)
        cr.fill()

        grey_grad = cairo.LinearGradient (0, y_in, 0, y_out)
        grey_grad.add_color_stop_rgba(*MID_GREY_GRAD_1)
        grey_grad.add_color_stop_rgba(*MID_GREY_GRAD_2)
        grey_grad.add_color_stop_rgba(*MID_GREY_GRAD_3)

        cr.set_source(grey_grad)
        cr.rectangle(self.X_PAD, self.Y_PAD, x_out - x_in, y_out - y_in)
        cr.fill()

        y_mid =  self.Y_PAD + math.floor((y_out - y_in)/2.0) + 0.2
        cr.set_line_width(0.6)
        cr.set_source_rgb(0.7,0.7,0.7)
        cr.move_to(x_in, y_mid)
        cr.line_to(x_out, y_mid)
        cr.stroke()

        _draw_select_circle(cr, self.shadow_x - self.CIRCLE_HALF, self.shadow_y - self.CIRCLE_HALF, ACTIVE_SHADOW_COLOR, 8, 7, 8)
        _draw_select_circle(cr, self.mid_x - self.CIRCLE_HALF, self.mid_y - self.CIRCLE_HALF, ACTIVE_MID_COLOR, 8, 7, 8)
        _draw_select_circle(cr, self.hi_x - self.CIRCLE_HALF, self.hi_y - self.CIRCLE_HALF, ACTIVE_HI_COLOR, 8, 7, 8)

        _draw_cursor_indicator(cr, self.cursor_x - 11, self.cursor_y - 11, 11)


class ColorBoxFilterEditor:

    def __init__(self, editable_properties):
        self.SAT_MAX = 0.5
        self.widget = Gtk.VBox()

        self.hue = [ep for ep in editable_properties if ep.name == "hue"][0]
        self.saturation = [ep for ep in editable_properties if ep.name == "saturation"][0]

        self.R = [ep for ep in editable_properties if ep.name == "R"][0]
        self.G = [ep for ep in editable_properties if ep.name == "G"][0]
        self.B = [ep for ep in editable_properties if ep.name == "B"][0]

        self.color_box = ColorBox(self.color_box_values_changed)
        self.color_box.set_cursor(self.hue.get_float_value(), self.saturation.get_float_value())

        box_row = Gtk.HBox()
        box_row.pack_start(Gtk.Label(), True, True, 0)
        box_row.pack_start(self.color_box.widget, False, False, 0)
        box_row.pack_start(Gtk.Label(), True, True, 0)

        self.h_label = Gtk.Label()
        self.s_label = Gtk.Label()

        info_box = Gtk.HBox(True)
        info_box.pack_start(self.h_label, False, False, 0)
        info_box.pack_start(self.s_label, False, False, 0)
        info_box.set_size_request(65, 20)

        info_row = Gtk.HBox()
        info_row.pack_start(Gtk.Label(), True, True, 0)
        info_row.pack_start(info_box, False, False, 0)
        info_row.pack_start(Gtk.Label(), True, True, 0)

        self.widget.pack_start(box_row, False, False, 0)
        self.widget.pack_start(info_row, False, False, 0)
        self.widget.pack_start(Gtk.Label(), True, True, 0)

        self._display_values(self.hue.get_float_value(), self.saturation.get_float_value())

    def color_box_values_changed(self):
        hue_val, sat_val = self.color_box.get_hue_saturation()
        self.hue.write_property_value(str(hue_val))
        self.saturation.write_property_value(str(sat_val))
        self._display_values(hue_val, sat_val)
        r, g, b = lutfilter.get_RGB_for_angle_saturation_and_value(hue_val * 360, sat_val * self.SAT_MAX, 0.5)

        self.R.write_value("0=" + str(r))
        self.G.write_value("0=" + str(g))
        self.B.write_value("0=" + str(b))

    def _display_values(self, hue, saturation):
        sat_str = str(int(saturation * 100)) + "%"
        hue_str = str(int(360 * hue)) + ColorGrader.DEGREE_CHAR + ' '
        self.h_label.set_text(hue_str)
        self.s_label.set_text(sat_str)



class ColorLGGFilterEditor:

    def __init__(self, editable_properties):
        self.widget = Gtk.VBox()

        # Get MLT properties
        self.lift_r = [ep for ep in editable_properties if ep.name == "lift_r"][0]
        self.lift_g = [ep for ep in editable_properties if ep.name == "lift_g"][0]
        self.lift_b = [ep for ep in editable_properties if ep.name == "lift_b"][0]
        self.gamma_r = [ep for ep in editable_properties if ep.name == "gamma_r"][0]
        self.gamma_g = [ep for ep in editable_properties if ep.name == "gamma_g"][0]
        self.gamma_b = [ep for ep in editable_properties if ep.name == "gamma_b"][0]
        self.gain_r = [ep for ep in editable_properties if ep.name == "gain_r"][0]
        self.gain_g = [ep for ep in editable_properties if ep.name == "gain_g"][0]
        self.gain_b = [ep for ep in editable_properties if ep.name == "gain_b"][0]

        # Get Non-MLT properties
        self.lift_hue = [ep for ep in editable_properties if ep.name == "lift_hue"][0]
        self.lift_value = [ep for ep in editable_properties if ep.name == "lift_value"][0]
        self.gamma_hue = [ep for ep in editable_properties if ep.name == "gamma_hue"][0]
        self.gamma_value = [ep for ep in editable_properties if ep.name == "gamma_value"][0]
        self.gain_hue = [ep for ep in editable_properties if ep.name == "gain_hue"][0]
        self.gain_value = [ep for ep in editable_properties if ep.name == "gain_value"][0]

        # Lift editor
        self.lift_hue_selector = self.get_hue_selector(self.lift_hue_edited)
        self.lift_hue_value_label = Gtk.Label()
        self.lift_hue_row = self.get_hue_row(self.lift_hue_selector.widget, self.lift_hue_value_label)

        self.lift_adjustment = self.lift_value.get_input_range_adjustment()
        self.lift_adjustment.connect("value-changed", self.lift_value_changed)
        self.lift_slider_row = self.get_slider_row(self.lift_adjustment)
        self.update_lift_display(self.lift_hue.get_float_value(), self.lift_value.get_current_in_value())

        # Gamma editor
        self.gamma_hue_selector = self.get_hue_selector(self.gamma_hue_edited)
        self.gamma_hue_value_label = Gtk.Label()
        self.gamma_hue_row = self.get_hue_row(self.gamma_hue_selector.widget, self.gamma_hue_value_label)

        self.gamma_adjustment = self.gamma_value.get_input_range_adjustment()
        self.gamma_adjustment.connect("value-changed", self.gamma_value_changed)
        self.gamma_slider_row = self.get_slider_row(self.gamma_adjustment)
        self.update_gamma_display(self.gamma_hue.get_float_value(), self.gamma_value.get_current_in_value())

        # Gain editor
        self.gain_hue_selector = self.get_hue_selector(self.gain_hue_edited)
        self.gain_hue_value_label = Gtk.Label()
        self.gain_hue_row = self.get_hue_row(self.gain_hue_selector.widget, self.gain_hue_value_label)

        self.gain_adjustment = self.gain_value.get_input_range_adjustment()
        self.gain_adjustment.connect("value-changed", self.gain_value_changed)
        self.gain_slider_row = self.get_slider_row(self.gain_adjustment)
        self.update_gain_display(self.gain_hue.get_float_value(), self.gain_value.get_current_in_value())

        # Pack
        self.widget.pack_start(self.get_name_row("Lift"), True, True, 0)
        self.widget.pack_start(self.lift_hue_row, True, True, 0)
        self.widget.pack_start(self.lift_slider_row, True, True, 0)
        self.widget.pack_start(guicomponents.EditorSeparator().widget, True, True, 0)
        self.widget.pack_start(self.get_name_row("Gamma"), True, True, 0)
        self.widget.pack_start(self.gamma_hue_row , True, True, 0)
        self.widget.pack_start(self.gamma_slider_row , True, True, 0)
        self.widget.pack_start(guicomponents.EditorSeparator().widget, True, True, 0)
        self.widget.pack_start(self.get_name_row("Gain"), True, True, 0)
        self.widget.pack_start(self.gain_hue_row , True, True, 0)
        self.widget.pack_start(self.gain_slider_row , True, True, 0)
        self.widget.pack_start(Gtk.Label(), True, True, 0)

    # ---------------------------------------------- gui building
    def get_hue_selector(self, callback):
        color_box = ColorBox(callback, width=290, height=40)
        color_box.draw_saturation_gradient = False
        color_box.selection_cursor = SELECT_LINE
        return color_box

    def get_name_row(self, name):
        name = _p(name)
        name_label = Gtk.Label(label=name + ":")

        hbox = Gtk.HBox(False, 4)
        hbox.pack_start(name_label, False, False, 4)
        hbox.pack_start(Gtk.Label(), True, True, 0)

        return hbox

    def get_hue_row(self, color_box, value_label):
        hbox = Gtk.HBox(False, 4)
        hbox.pack_start(color_box, False, False, 0)
        hbox.pack_start(value_label, False, False, 4)
        hbox.pack_start(Gtk.Label(), False, False, 0)

        return hbox

    def get_slider_row(self, adjustment):#, name):
        hslider = Gtk.HScale()
        hslider.set_adjustment(adjustment)
        hslider.set_draw_value(False)

        spin = Gtk.SpinButton()
        spin.set_numeric(True)
        spin.set_adjustment(adjustment)

        hslider.set_digits(0)
        spin.set_digits(0)

        hbox = Gtk.HBox(False, 4)
        #hbox.pack_start(name_label, False, False, 4)
        hbox.pack_start(hslider, True, True, 0)
        hbox.pack_start(spin, False, False, 4)

        return hbox

    # --------------------------------------- gui updating
    def update_lift_display(self, hue, val):
        self.lift_hue_selector.set_cursor(hue, 0.0)
        self.set_hue_label_value(hue, self.lift_hue_value_label)

        self.lift_adjustment.set_value(val)

    def update_gamma_display(self, hue, val):
        self.gamma_hue_selector.set_cursor(hue, 0.0)
        self.set_hue_label_value(hue, self.gamma_hue_value_label)

        self.gamma_adjustment.set_value(val)

    def update_gain_display(self, hue, val):
        self.gain_hue_selector.set_cursor(hue, 0.0)
        self.set_hue_label_value(hue, self.gain_hue_value_label)

        self.gain_adjustment.set_value(val)

    def set_hue_label_value(self, hue, label):
        hue_str = str(int(360 * hue)) + ColorGrader.DEGREE_CHAR + ' '
        label.set_text(hue_str)

    # ------------------------------ color box listeners
    def lift_hue_edited(self):
        hue, sat = self.lift_hue_selector.get_hue_saturation()
        self.set_hue_label_value(hue, self.lift_hue_value_label)

        self.update_lift_property_values()

    def gamma_hue_edited(self):
        hue, sat = self.gamma_hue_selector.get_hue_saturation()
        self.set_hue_label_value(hue, self.gamma_hue_value_label)

        self.update_gamma_property_values()

    def gain_hue_edited(self):
        hue, sat = self.gain_hue_selector.get_hue_saturation()
        self.set_hue_label_value(hue, self.gain_hue_value_label)

        self.update_gain_property_values()

    # ----------------------------------- slider listeners
    def lift_value_changed(self, adjustment):
        self.update_lift_property_values()

    def gamma_value_changed(self, adjustment):
        self.update_gamma_property_values()

    def gain_value_changed(self, adjustment):
        self.update_gain_property_values()

    # -------------------------------------- value writers
    def update_lift_property_values(self):
        hue, sat = self.lift_hue_selector.get_hue_saturation()
        r, g, b = lutfilter.get_RGB_for_angle(hue * 360)

        value = self.lift_adjustment.get_value() / 100.0

        r = r * value
        g = g * value
        b = b * value

        self.lift_hue.write_number_value(hue)
        self.lift_value.write_number_value(value)
        self.lift_r.write_value(r)
        self.lift_g.write_value(g)
        self.lift_b.write_value(b)

    def update_gamma_property_values(self):
        hue, sat = self.gamma_hue_selector.get_hue_saturation()
        r, g, b = lutfilter.get_RGB_for_angle(hue * 360)

        value = self.gamma_value.get_out_value(self.gamma_adjustment.get_value())

        r = 1.0 + r * (value - 1.0)
        g = 1.0 + g * (value - 1.0)
        b = 1.0 + b * (value - 1.0)

        self.gamma_hue.write_number_value(hue)
        self.gamma_value.write_number_value(value)
        self.gamma_r.write_value(r)
        self.gamma_g.write_value(g)
        self.gamma_b.write_value(b)

    def update_gain_property_values(self):
        hue, sat = self.gain_hue_selector.get_hue_saturation()
        r, g, b = lutfilter.get_RGB_for_angle(hue * 360)

        value = self.gain_value.get_out_value(self.gain_adjustment.get_value())

        r = 1.0 + r * (value - 1.0)
        g = 1.0 + g * (value - 1.0)
        b = 1.0 + b * (value - 1.0)

        self.gain_hue.write_number_value(hue)
        self.gain_value.write_number_value(value)
        self.gain_r.write_value(r)
        self.gain_g.write_value(g)
        self.gain_b.write_value(b)


class BoxEditor:

    def __init__(self, pix_size):
        self.value_size = 1.0 # Box editor works in 0-1 normalized space

        self.pix_size = pix_size
        self.pix_per_val = self.value_size / pix_size
        self.off_x = 0.5
        self.off_y = 0.5

    def get_box_val_point(self, x, y):
        # calculate value
        px = (x - self.off_x) * self.pix_per_val
        py = (self.pix_size - (y - self.off_y)) * self.pix_per_val

        # force range
        if px < 0:
            px = 0.0
        if py < 0:
            py = 0.0
        if px >= self.value_size:
            px = self.value_size
        if py >= self.value_size:
            py = self.value_size

        return px, py

    def get_box_panel_point(self, x, y, max_value):
        px = x/max_value * self.pix_size + self.off_x
        py = self.off_y + self.pix_size - (y/max_value * self.pix_size) # higher values are up
        return (px, py)

    def draw_box(self, cr, allocation):
        x, y, w, h = allocation

        # value lines
        cr.set_source_rgb(*BOX_LINE_COLOR)
        step = self.pix_size / 8
        cr.set_line_width(1.0)
        for i in range(0, 9):
            cr.move_to(0.5 + step * i, 0.5)
            cr.line_to(step * i, self.pix_size + 0.5)
            cr.stroke()

        for i in range(0, 9):
            cr.move_to(0.5, step * i + 0.5)
            cr.line_to(self.pix_size + 0.5, step * i + 0.5)
            cr.stroke()


class CatmullRomFilterEditor:
    RGB = 0
    R = 1
    G = 2
    B = 3

    def __init__(self, editable_properties):
        self.widget = Gtk.VBox()

        # These properties hold the values that are writtenout to MLT to do the filtering
        self.cr_filter = lutfilter.CatmullRomFilter(editable_properties)
        default_curve = self.cr_filter.value_cr_curve
        self.current_edit_curve = CatmullRomFilterEditor.RGB

        # This is used to edit points of currently active curve
        self.curve_editor = CurvesBoxEditor(256.0, default_curve, self)

        # This is used to change currently active curve
        self.channel_buttons = glassbuttons.GlassButtonsToggleGroup(32, 19, 2, 2, 5)
        self.channel_buttons.add_button(cairo.ImageSurface.create_from_png(respaths.IMAGE_PATH + "rgb_channel.png"), self.channel_changed)
        self.channel_buttons.add_button(cairo.ImageSurface.create_from_png(respaths.IMAGE_PATH + "red_channel.png"), self.channel_changed)
        self.channel_buttons.add_button(cairo.ImageSurface.create_from_png(respaths.IMAGE_PATH + "green_channel.png"), self.channel_changed)
        self.channel_buttons.add_button(cairo.ImageSurface.create_from_png(respaths.IMAGE_PATH + "blue_channel.png"), self.channel_changed)
        self.channel_buttons.widget.set_pref_size(132, 28)
        self.channel_buttons.set_pressed_button(0)

        self.curve_buttons = glassbuttons.GlassButtonsGroup(32, 19, 2, 2, 5)
        self.curve_buttons.add_button(cairo.ImageSurface.create_from_png(respaths.IMAGE_PATH + "linear_curve.png"), self.do_curve_reset_pressed)
        self.curve_buttons.add_button(cairo.ImageSurface.create_from_png(respaths.IMAGE_PATH + "curve_s.png"), self.do_curve_reset_pressed)
        self.curve_buttons.add_button(cairo.ImageSurface.create_from_png(respaths.IMAGE_PATH + "curve_flipped_s.png"), self.do_curve_reset_pressed)
        self.curve_buttons.widget.set_pref_size(97, 28)

        button_hbox = Gtk.HBox()
        button_hbox.pack_start(self.channel_buttons.widget, False, False, 0)
        button_hbox.pack_start(guiutils.get_pad_label(4, 4), False, False, 0)
        button_hbox.pack_start(self.curve_buttons.widget, False, False, 0)

        buttons_row = guiutils.get_in_centering_alignment(button_hbox)

        box_row = Gtk.HBox()
        box_row.pack_start(Gtk.Label(), True, True, 0)
        box_row.pack_start(self.curve_editor.widget, False, False, 0)
        box_row.pack_start(Gtk.Label(), True, True, 0)

        self.widget.pack_start(Gtk.Label(), True, True, 0)
        self.widget.pack_start(box_row, False, False, 0)
        self.widget.pack_start(guiutils.get_pad_label(12, 8), False, False, 0)
        self.widget.pack_start(buttons_row, False, False, 0)
        self.widget.pack_start(Gtk.Label(), True, True, 0)

    def channel_changed(self):
        channel = self.channel_buttons.pressed_button # indexes match
        self.update_editors_to_channel(channel)

    def update_editors_to_channel(self, channel):
        # Channel values and button indexes match
        if channel == CatmullRomFilterEditor.RGB:
            self.current_edit_curve = CatmullRomFilterEditor.RGB
            self.curve_editor.set_curve(self.cr_filter.value_cr_curve, CURVE_COLOR)

        elif channel == CatmullRomFilterEditor.R:
            self.current_edit_curve = CatmullRomFilterEditor.R
            self.curve_editor.set_curve(self.cr_filter.r_cr_curve, R_CURVE_COLOR)

        elif channel == CatmullRomFilterEditor.G:
            self.current_edit_curve = CatmullRomFilterEditor.G
            self.curve_editor.set_curve(self.cr_filter.g_cr_curve, G_CURVE_COLOR)

        else:
            self.current_edit_curve = CatmullRomFilterEditor.B
            self.curve_editor.set_curve(self.cr_filter.b_cr_curve, B_CURVE_COLOR)

    def do_curve_reset_pressed(self):
        button_index = self.curve_buttons.pressed_button
        channel = self.current_edit_curve

        if button_index == 0: # Linear
            new_points_str = "0/0;255/255"
        elif button_index == 1: # Default add gamma
            new_points_str = "0/0;64/48;192/208;255/255"
        elif button_index == 2: # Default remove gamma
            new_points_str = "0/0;64/80;192/176;255/255"

        if channel == CatmullRomFilterEditor.RGB:
            self.cr_filter.value_cr_curve.set_points_from_str(new_points_str)
        elif channel == CatmullRomFilterEditor.R:
            self.cr_filter.r_cr_curve.set_points_from_str(new_points_str)
        elif channel== CatmullRomFilterEditor.G:
            self.cr_filter.g_cr_curve.set_points_from_str(new_points_str)
        else:
            self.cr_filter.b_cr_curve.set_points_from_str(new_points_str)

        self.write_points_to_current_curve(new_points_str)
        self.update_editors_to_channel(channel)

    def curve_edit_done(self):
        points_str = self.curve_editor.curve.get_points_string()
        self.write_points_to_current_curve(points_str)

    def write_points_to_current_curve(self, points_str):
        if self.current_edit_curve == CatmullRomFilterEditor.RGB:
            self.cr_filter.value_points_prop.write_property_value(points_str)

        elif self.current_edit_curve == CatmullRomFilterEditor.R:
            self.cr_filter.r_points_prop.write_property_value(points_str)

        elif self.current_edit_curve == CatmullRomFilterEditor.G:
            self.cr_filter.g_points_prop.write_property_value(points_str)

        else: # CatmullRomFilterEditor.B
            self.cr_filter.b_points_prop.write_property_value(points_str)

        self.cr_filter.update_table_property_values()


class CurvesBoxEditor(BoxEditor):

    def __init__(self, pix_size, curve, edit_listener):
        BoxEditor.__init__(self, pix_size)
        self.curve = curve # lutfilter.CRCurve
        global BOX_LINE_COLOR, CURVE_COLOR
        self.curve_color = CURVE_COLOR
        self.edit_listener = edit_listener # Needs to implement "curve_edit_done()"

        self.widget = cairoarea.CairoDrawableArea2( self.pix_size + 2,
                                                    self.pix_size + 2,
                                                    self._draw)
        self.widget.press_func = self._press_event
        self.widget.motion_notify_func = self._motion_notify_event
        self.widget.release_func = self._release_event

        self.last_point = None
        self.edit_on = False

        BOX_LINE_COLOR = (0.8, 0.8, 0.8)
        CURVE_COLOR = (0.8, 0.8, 0.8)
        self.curve_color = CURVE_COLOR

    def set_curve(self, curve, curve_color):
        self.curve = curve
        self.curve_color = curve_color

        self.widget.queue_draw()

    def _press_event(self, event):
        vx, vy = BoxEditor.get_box_val_point(self, event.x, event.y)
        p = lutfilter.CurvePoint(int(round(vx * 255)), int(round(vy * 255)))
        self.last_point = p
        self.edit_on = True
        self.curve.remove_range(self.last_point.x - 3, self.last_point.x + 3 )
        self.curve.set_curve_point(p)

        self.widget.queue_draw()

    def _motion_notify_event(self, x, y, state):
        if self.edit_on == False:
            return
        vx, vy = BoxEditor.get_box_val_point(self, x, y)
        p = lutfilter.CurvePoint(int(round(vx * 255)), int(round(vy * 255)))
        self.curve.remove_range(self.last_point.x, p.x)
        self.curve.set_curve_point(p)
        self.last_point = p

        self.widget.queue_draw()

    def _release_event(self, event):
        if self.edit_on == False:
            return
        vx, vy = BoxEditor.get_box_val_point(self, event.x, event.y)
        p = lutfilter.CurvePoint(int(round(vx * 255)), int(round(vy * 255)))
        self.curve.remove_range(self.last_point.x, p.x)
        self.curve.set_curve_point(p)

        self.edit_on = False
        self.edit_listener.curve_edit_done()
        self.widget.queue_draw()

    def _draw(self, event, cr, allocation):
        # bg box
        BoxEditor.draw_box(self, cr, allocation)

        x, y, w, h = allocation

        # curve
        cr.set_source_rgb(*self.curve_color)#  seg.setColor( CURVE_COLOR );
        cr.set_line_width(1.5)
        cp = self.curve.get_curve(True) #we get 256 values
        px, py = BoxEditor.get_box_panel_point(self, 0, cp[0], 255)
        cr.move_to(px, py)

        for i in range(1, len(cp)): #int i = 0; i < cp.length - 1; i++ )
            px, py = BoxEditor.get_box_panel_point(self, i, cp[i], 255.0)
            cr.line_to(px, py)
        cr.stroke()

        cr.rectangle(1, 1, w - 3, h - 3)
        cr.clip()

        # edit points
        for p in self.curve.points:
            px, py = BoxEditor.get_box_panel_point(self, p.x, p.y, 255.0)
            _draw_select_circle(cr, px, py, (1,1,1), 4, 2, 0, -4, -4)


class ColorGrader:

    DEGREE_CHAR = '\u00B0'

    def __init__(self, editable_properties):
        # Initial active band
        self.band = SHADOW

        # HUE and SAT are both saved in range (0,1)
        # HUE and SAT are both handled in editor using range (0,1)
        # Saved and editor ranges are the same.
        # ColorGradeBandCorrection objects handle ranges differently
        # - saturation values 0-1 converted to range (-1, 1)
        # - saturation value 0.5 is converted to 0 and means no correction applied
        # - converted range(-1, 0) means negative correction applied
        # - negative correction is interpreted as positive correction of complimentary color

        # Editable properties
        self.shadow_hue = [ep for ep in editable_properties if ep.name == "shadow_hue"][0]
        self.shadow_saturation = [ep for ep in editable_properties if ep.name == "shadow_saturation"][0]
        self.mid_hue = [ep for ep in editable_properties if ep.name == "mid_hue"][0]
        self.mid_saturation = [ep for ep in editable_properties if ep.name == "mid_saturation"][0]
        self.hi_hue = [ep for ep in editable_properties if ep.name == "hi_hue"][0]
        self.hi_saturation = [ep for ep in editable_properties if ep.name == "hi_saturation"][0]

        # Create filter and init values
        self.filt = lutfilter.ColorGradeFilter(editable_properties)
        self.filt.shadow_band.set_hue_and_saturation(self.shadow_hue.get_float_value(),
                                                     self.shadow_saturation.get_float_value())
        self.filt.mid_band.set_hue_and_saturation(self.mid_hue.get_float_value(),
                                                     self.mid_saturation.get_float_value())
        self.filt.hi_band.set_hue_and_saturation(self.hi_hue.get_float_value(),
                                                     self.hi_saturation.get_float_value())
        self.filt.update_all_corrections()
        self.filt.update_rgb_lookups()
        self.filt.write_out_tables()

        # Create GUI
        self.color_box = ThreeBandColorBox(self.color_box_values_changed, self.band_changed, 340, 200)
        self.color_box.set_cursor(self.shadow_hue.get_float_value(), self.shadow_saturation.get_float_value())
        self.color_box.set_cursors(self.shadow_hue.get_float_value(), self.shadow_saturation.get_float_value(),
                                   self.mid_hue.get_float_value(), self.mid_saturation.get_float_value(),
                                   self.hi_hue.get_float_value(), self.hi_saturation.get_float_value())

        box_row = Gtk.HBox()
        box_row.pack_start(Gtk.Label(), True, True, 0)
        box_row.pack_start(self.color_box.widget, False, False, 0)
        box_row.pack_start(Gtk.Label(), True, True, 0)


        shadow_icon = Gtk.Image.new_from_file(respaths.IMAGE_PATH + "shadow.png")
        self.sh_label = Gtk.Label()
        self.ss_label = Gtk.Label()
        shadow_box = Gtk.HBox()
        shadow_box.pack_start(shadow_icon, False, False, 0)
        shadow_box.pack_start(guiutils.pad_label(3,5), False, False, 0)
        shadow_box.pack_start(self.sh_label, False, False, 0)
        shadow_box.pack_start(self.ss_label, False, False, 0)
        shadow_box.set_size_request(95, 20)

        midtone_icon = Gtk.Image.new_from_file(respaths.IMAGE_PATH + "midtones.png")
        self.mh_label = Gtk.Label()
        self.ms_label = Gtk.Label()
        midtone_box = Gtk.HBox()
        midtone_box.pack_start(midtone_icon, False, False, 0)
        midtone_box.pack_start(guiutils.pad_label(3,5), False, False, 0)
        midtone_box.pack_start(self.mh_label, False, False, 0)
        midtone_box.pack_start(self.ms_label, False, False, 0)
        midtone_box.set_size_request(95, 20)

        highligh_icon = Gtk.Image.new_from_file(respaths.IMAGE_PATH + "highlights.png")
        self.hh_label = Gtk.Label()
        self.hs_label = Gtk.Label()
        highlight_box = Gtk.HBox()
        highlight_box.pack_start(highligh_icon, False, False, 0)
        highlight_box.pack_start(guiutils.pad_label(3,5), False, False, 0)
        highlight_box.pack_start(self.hh_label, False, False, 0)
        highlight_box.pack_start(self.hs_label, False, False, 0)
        highlight_box.set_size_request(95, 20)

        self._display_values(SHADOW, self.shadow_hue.get_float_value(), self.shadow_saturation.get_float_value())
        self._display_values(MID, self.mid_hue.get_float_value(), self.mid_saturation.get_float_value())
        self._display_values(HI, self.hi_hue.get_float_value(), self.hi_saturation.get_float_value())

        info_row = Gtk.HBox()
        info_row.pack_start(Gtk.Label(), True, True, 0)
        info_row.pack_start(shadow_box, False, False, 0)
        info_row.pack_start(midtone_box, False, False, 0)
        info_row.pack_start(highlight_box, False, False, 0)
        info_row.pack_start(Gtk.Label(), True, True, 0)

        self.widget = Gtk.VBox()
        self.widget.pack_start(box_row, False, False, 0)
        self.widget.pack_start(info_row, False, False, 0)
        self.widget.pack_start(Gtk.Label(), True, True, 0)

    def band_changed(self, band):
        self.band = band

    def color_box_values_changed(self):
        hue, sat = self.color_box.get_hue_saturation()

        if self.band == SHADOW:
            self.shadow_hue.write_number_value(hue)
            self.shadow_saturation.write_number_value(sat)

            self.filt.shadow_band.set_hue_and_saturation(hue, sat)
            self.filt.shadow_band.update_correction()
        elif self.band == MID:
            self.mid_hue.write_number_value(hue)
            self.mid_saturation.write_number_value(sat)

            self.filt.mid_band.set_hue_and_saturation(hue, sat)
            self.filt.mid_band.update_correction()
        else:
            self.hi_hue.write_number_value(hue)
            self.hi_saturation.write_number_value(sat)

            self.filt.hi_band.set_hue_and_saturation(hue, sat)
            self.filt.hi_band.update_correction()

        self._display_values(self.band, hue, sat)

        self.filt.update_rgb_lookups()
        self.filt.write_out_tables()

    def _display_values(self, band, hue, saturation):
        sat_str = str(int(((saturation - 0.5) * 2.0) * 100)) + "%"
        hue_str = str(int(360 * hue)) + ColorGrader.DEGREE_CHAR + ' '
        if band == SHADOW:
            self.sh_label.set_text(hue_str)
            self.ss_label.set_text(sat_str)
        elif band == MID:
            self.mh_label.set_text(hue_str)
            self.ms_label.set_text(sat_str)
        else:
            self.hh_label.set_text(hue_str)
            self.hs_label.set_text(sat_str)


class ColorBandSelector:
    def __init__(self):
        self.band = SHADOW

        self.widget = cairoarea.CairoDrawableArea2( 42,
                                                    18,
                                                    self._draw)

        self.widget.press_func = self._press_event
        self.SHADOW_X = 0
        self.MID_X = 15
        self.HI_X = 30

        self.band_change_listener = None # monkey patched in at creation site

    def _press_event(self, event):
        x = event.x
        y = event.y

        if self._circle_hit(self.SHADOW_X, x, y):
            self.band_change_listener(SHADOW)
        elif self._circle_hit(self.MID_X, x, y):
            self.band_change_listener(MID)
        elif self._circle_hit(self.HI_X, x, y):
             self.band_change_listener(HI)

    def _circle_hit(self, band_x, x, y):
        if x >= band_x and x < band_x + 12:
            if y > 0 and y < 12:
                return True

        return False

    def _draw(self, event, cr, allocation):
        """
        Callback for repaint from CairoDrawableArea.
        We get cairo context and allocation.
        """
        x, y, w, h = allocation

        ring_color = (0.0, 0.0, 0.0)
        _draw_select_circle(cr, self.SHADOW_X, 0, (0.1, 0.1, 0.1), ring_color)
        _draw_select_circle(cr, self.MID_X, 0, (0.5, 0.5, 0.5), ring_color)
        _draw_select_circle(cr, self.HI_X, 0, (1.0, 1.0, 1.0), ring_color)

        self._draw_active_indicator(cr)

    def _draw_active_indicator(self, cr):
        y = 14.5
        HALF = 4.5
        HEIGHT = 2

        if self.band == SHADOW:
            x = self.SHADOW_X + 1.5
        elif self.band == MID:
            x = self.MID_X + 1.5
        else:
            x = self.HI_X + 1.5

        cr.set_source_rgb(0, 0, 0)
        cr.move_to(x, y)
        cr.line_to(x + 2 * HALF, y)
        cr.line_to(x + 2 * HALF, y + HEIGHT)
        cr.line_to(x, y + HEIGHT)
        cr.close_path()
        cr.fill()


class InfoAndTipsEditor:
    
    def __init__(self, uri, link_text):
        self.uri = uri
        self.widget = Gtk.LinkButton.new_with_label(uri, link_text)
        self.widget.connect("activate-link", self._open_info)
        self.widget.set_margin_top(24)
        self.widget.set_margin_bottom(4)

    def _open_info(self, widget):
        webbrowser.open(self.uri)
        return True


class AnalyzeStabilizeFilterEditor:
    def __init__(self, filter, editable_properties):
        self.filter = filter
        self.editable_properties = editable_properties
        self.widget = Gtk.HBox()
        self.button = Gtk.Button(label=_("Analyze video"))
        self.button.connect("clicked", self.analyze_button_clicked)
        self.no_data_text = "<small>" + _("No stabilizing data") + "</small>"
        self.loaded_data_text = "<small>" + _("Stabilizing data loaded") + "</small>"
        prop_name, prop_value, prop_type = filter.non_mlt_properties[0]
        if prop_value == appconsts.FILE_PATH_NOT_SET:
            text = self.no_data_text 
        else:
            text = self.loaded_data_text 
        self.info_label = Gtk.Label(label=text)
        self.info_label.set_use_markup(True)
        self.info_label.set_margin_right(4)
        self.widget.pack_start(self.info_label, False, False, 0) 
        self.widget.pack_start(self.button, False, False, 0) 

        self.widget.set_margin_top(24)
        self.widget.set_margin_bottom(24)

    def analyze_button_clicked(self, button):
        session_id = utils.create_render_session_uid()
        profile_desc = PROJECT().profile_desc.replace(" ", "_")
        clip_path = self.editable_properties[0].clip.path
        accuracy_prop = [ep for ep in self.editable_properties if ep.name == "accuracy"][0]
        shakiness_prop = [ep for ep in self.editable_properties if ep.name == "shakiness"][0]
        smoothing_prop = [ep for ep in self.editable_properties if ep.name == "smoothing"][0]
        zoom_prop = [ep for ep in self.editable_properties if ep.name == "zoom"][0]
        
        args = ("session_id:" + str(session_id),
                "profile_desc:" + str(profile_desc),
                "clip_path:" + str(clip_path),
                "shakiness:" + str(shakiness_prop.value),
                "accuracy:" + str(accuracy_prop.value),
                "smoothing:" + str(smoothing_prop.value),
                "zoom:" + str(zoom_prop.value))

        job = jobs.StablizeDataRenderJobQueueObject(session_id, self.filter, self.editable_properties, self, args)
        job.add_to_queue()
    
    def analysis_complete(self):
        self.info_label.set_text(self.loaded_data_text)
        self.info_label.set_use_markup(True)
        self.info_label.queue_draw()



class AnalyzeMotionTrackingFilterEditor:
    def __init__(self, filter, editable_properties):
        self.filter = filter
        # We need to turn this because otherwise filter keeps attempting to 
        # analyze tracking continuously. We want analyzing to happen in the 
        # dedicated process and only results be displayed.
        # ...aaand this only has effect if we have some results?
        self.filter.mlt_filter.set("analyze", "0")

        self.editable_properties = editable_properties

        # We need access to GUI box editor to control its state.
        box_editor_key ="trackerrect" + ":" + str(editable_properties[0].filter_index)
        self.box_gui_editor = accessable_editors[box_editor_key]
        
        label_info_label = Gtk.Label(label=_("Tracking Data Label:"))
        label_info_label.set_margin_right(4)

        def_label = self.get_default_data_label()
        
        self.label_entry = Gtk.Entry()
        self.label_entry.set_width_chars(28)
        self.label_entry.set_text(def_label)
        self.label_entry.set_activates_default(True)

        hbox1 = Gtk.HBox()
        hbox1.pack_start(label_info_label, False, False, 0) 
        hbox1.pack_start(self.label_entry, True, True, 0)
        
        self.button = Gtk.Button(label=_("Create Motion Tracking Data"))
        self.button.connect("clicked", self.analyze_button_clicked)

        self.clear_button = Gtk.Button(label=_("Clear Data"))
        self.clear_button.connect("clicked", self.clear_button_clicked)
        
        self.info_label = Gtk.Label("")
        self.info_label.set_use_markup(True)
        self.info_label.set_margin_right(4)

        hbox2 = Gtk.HBox()
        hbox2.pack_start(Gtk.Label(), True, True, 0) 
        hbox2.pack_start(self.info_label, False, False, 0) 
        hbox2.set_margin_top(4)
        
        hbox3 = Gtk.HBox()
        hbox3.pack_start(self.clear_button, False, False, 0)
        hbox3.pack_start(Gtk.Label(), True, True, 0) 
        hbox3.pack_start(self.button, False, False, 0)
        hbox3.set_margin_top(4)

        vbox = Gtk.VBox()
        
        vbox.pack_start(hbox1, False, False, 0) 
        vbox.pack_start(hbox2, False, False, 0)
        vbox.pack_start(hbox3, False, False, 0)

        self.widget = Gtk.HBox()
        self.widget.pack_start(vbox, True, True, 0)

        self.widget.set_margin_top(24)
        self.widget.set_margin_bottom(24)
        
        self.set_buttons_state()
            
    def get_default_data_label(self):
        clip_path = self.editable_properties[0].clip.path
        file_name = os.path.splitext(os.path.basename(clip_path))[0]
        if len(file_name) < 8:
            def_file_part = file_name
        else:
            def_file_part = file_name[:8]
        
        return def_file_part + "-" + _("tracking")
        
    def analyze_button_clicked(self, button):
        session_id = utils.create_render_session_uid()
        profile_desc = PROJECT().profile_desc.replace(" ", "_")
        clip_path = self.editable_properties[0].clip.path
        clip_in = str(self.editable_properties[0].clip.clip_in)
        clip_out = str(self.editable_properties[0].clip.clip_out)
        step_prop = [ep for ep in self.editable_properties if ep.name == "steps"][0]
        algo_prop = [ep for ep in self.editable_properties if ep.name == "algo"][0]
        rect_prop = [ep for ep in self.editable_properties if ep.name == "rect"][0]
        rect_value = rect_prop.value.replace(" ", "_")

        args = ("session_id:" + str(session_id),
                "profile_desc:" + str(profile_desc),
                "clip_path:" + clip_path,
                "clip_in:" + clip_in,
                "clip_out:" + clip_out,
                "rect:" + str(rect_value),
                "algo:" + str(algo_prop.value),
                "step:" + str(step_prop.value))

        data_label = self.label_entry.get_text()
        if len(data_label) == 0:
            data_label = self.get_default_data_label()
        
        job = jobs.TrackingDataRenderJobQueueObject(session_id, self.filter, self.editable_properties, self, args, data_label)
        job.add_to_queue()

    def analysis_complete(self, final_label, data_file_path):
        f = open(data_file_path, 'r')
        results = f.read()
        f.close()

        self.filter.mlt_filter.set("results", results)
        self.filter.mlt_filter.set("reload", "1")
        self.filter.mlt_filter.set("shape_color", "#00ff00")

        try:
            create_info_text = "<small>" + _("Motion Tracking Data created: ") + final_label + "</small>"
            self.info_label.set_text(create_info_text)
            self.info_label.set_use_markup(True)
            self.info_label.queue_draw()
            self.box_gui_editor.geom_kf_edit.active = False
            self.box_gui_editor.geom_kf_edit.widget.queue_draw()
            self.set_buttons_state()
        except Exception as e :
            # GUI might havenn destroyed during rendering.
            print(e)

    def clear_button_clicked(self, button):
        self.filter.mlt_filter.set("analyze", "0")
        self.filter.mlt_filter.set("results", "")
        self.filter.mlt_filter.set("reload", "1")
        self.filter.mlt_filter.set("shape_color", "#aa2222")
        self.box_gui_editor.geom_kf_edit.active = True
        self.box_gui_editor.geom_kf_edit.widget.queue_draw()
        self.set_buttons_state()

    def set_buttons_state(self):
        results = self.filter.mlt_filter.get("results") 
        if results == None or len(results) == 0:
            self.button.set_sensitive(True)
            self.clear_button.set_sensitive(False)
        else:
            self.button.set_sensitive(False)
            self.clear_button.set_sensitive(True)
        

class ApplyMotionTrackingFilterEditor:
    def __init__(self, filter, editable_properties, non_mlt_editors, non_mlt_properties):
        self.filter = filter
        self.editable_properties = editable_properties
        self.non_mlt_editors = non_mlt_editors
        self.non_mlt_properties = non_mlt_properties

        self.select_label = Gtk.Label(label=_("Select Motion Tracking Data:"))
        self.select_label.set_margin_right(4)

        selected_tracking_data = [ep for ep in self.non_mlt_properties if ep.name == "selected_tracking_data"][0].value
        self.data_select_keys, self.data_select_combo = motiontracking.get_tracking_data_select_combo(_("No Tracking Data Available"), selected_tracking_data)

        self.delete_button = Gtk.Button(label=_("Delete"))
        self.delete_button.connect("clicked", self.delete_data)
        self.delete_button.set_margin_left(12)
    
        self.hbox1 = Gtk.HBox()
        self.hbox1.pack_start(self.select_label, False, False, 0) 
        self.hbox1.pack_start(self.data_select_combo, True, True, 0)
        self.hbox1.pack_start(self.delete_button, False, False, 0) 
        self.hbox1.set_margin_bottom(24)

        self.info_label = Gtk.Label("<small>No Tracking Data Applied</small>")
        last_applied_date_str = [ep for ep in self.non_mlt_properties if ep.name == "last_applied_tracking_data"][0].value
        if last_applied_date_str != appconsts.TRACKING_DATA_NOT_SET:
            self.show_last_applied_date(last_applied_date_str)
        self.info_label.set_use_markup(True)
        self.info_label.set_margin_right(4)
        
        self.button = Gtk.Button(label=_("Apply Motion Tracking Data"))
        self.button.connect("clicked", self.apply_tracking)

        hbox2 = Gtk.HBox()
        hbox2.pack_start(self.delete_button, False, False, 0)
        hbox2.pack_start(Gtk.Label(), True, True, 0) 
        hbox2.pack_start(self.info_label, False, False, 0) 
        hbox2.pack_start(self.button, False, False, 0)
        hbox2.set_margin_top(24)
        hbox2.set_margin_bottom(24)
        
        self.widget = Gtk.VBox()
        self.widget.pack_start(self.hbox1, False, False, 0)
        for row in self.non_mlt_editors:
            self.widget.pack_start(row, False, False, 0)
        self.widget.pack_start(hbox2, False, False, 0)

    def apply_tracking(self, button):
        tracking_data_id = self.data_select_keys[self.data_select_combo.get_active()]
        xoff = [ep for ep in self.non_mlt_properties if ep.name == "xoff"][0].value
        yoff = [ep for ep in self.non_mlt_properties if ep.name == "yoff"][0].value
        interpretation = [ep for ep in self.non_mlt_properties if ep.name == "interpretation"][0].value
        size = [ep for ep in self.non_mlt_properties if ep.name == "size"][0].value
        clip_in = self.editable_properties[0].clip.clip_in

        info = utils.get_file_producer_info(self.editable_properties[0].clip)
        source_w = int(info["width"])
        source_h = int(info["height"])
        if self.editable_properties[0].clip.media_type == appconsts.IMAGE:
            graphic_img = Image.open(self.editable_properties[0].clip.path)
            source_w, source_h = graphic_img.size

        motiontracking.apply_tracking(  tracking_data_id, self.filter, self.editable_properties, 
                                        int(float(xoff)), int(float(yoff)), interpretation, size, clip_in,
                                        source_w, source_h)
        
        selected_tracking_data_prop = [ep for ep in self.non_mlt_properties if ep.name == "selected_tracking_data"][0]
        selected_tracking_data_prop.write_value(tracking_data_id)

        date_str = datetime.now().strftime('%y.%m - %H:%M:%S')
        last_applied_tracking_data = [ep for ep in self.non_mlt_properties if ep.name == "last_applied_tracking_data"][0]
        last_applied_tracking_data.write_value(date_str)
        self.show_last_applied_date(date_str)

    def show_last_applied_date(self, date_str):
        self.info_label.set_text("<small>" + _("Last applied ") + date_str + "</small>")
        self.info_label.set_use_markup(True)
        self.info_label.queue_draw()

    def delete_data(self, button):
        used_data = motiontracking.get_used_motion_tracking_data()
        tracking_data_id = self.data_select_keys[self.data_select_combo.get_active()]
        
        if tracking_data_id in used_data:
            self.confirm_delete()
        else:
            self.delete_selected()

    def confirm_delete(self):
        title = _("Confirm Motion Tracking Data Delete")
        text = Gtk.Label(label=_("Current selected motion tracking data was applied somewhere in the project.\n\nDelete anyway?"))
        panel = guiutils.get_left_justified_box([text])
        accept_text = _("Delete")
        dialogutils.panel_ok_cancel_dialog(title, panel, accept_text, self.delete_dialog_callback)

    def delete_dialog_callback(self, dialog, response_id):
        dialog.destroy()
        if response_id == Gtk.ResponseType.ACCEPT:
            self.delete_selected()

    def delete_selected(self):
        tracking_data_id = self.data_select_keys[self.data_select_combo.get_active()]
        if tracking_data_id == None:
            return # no tracking data exists.

        PROJECT().delete_tracking_data(tracking_data_id)

        children = self.hbox1.get_children()
        for child in children:
            self.hbox1.remove(child)

        self.data_select_keys, self.data_select_combo = motiontracking.get_tracking_data_select_combo(_("No Tracking Data Available"), -1)
        self.data_select_combo.show() 

        self.hbox1.pack_start(self.select_label, False, False, 0) 
        self.hbox1.pack_start(self.data_select_combo, True, True, 0)
        self.hbox1.pack_start(self.delete_button, False, False, 0) 
        
        self.widget.queue_draw() 
            

class FilterMaskApplyMotionTrackingEditor:
    def __init__(self, filter, editable_properties, non_mlt_editors, non_mlt_properties):
        self.filter = filter
        self.editable_properties = editable_properties
        self.non_mlt_properties = non_mlt_properties
        self.non_mlt_editors = non_mlt_editors
        
        self.select_label = Gtk.Label(label=_("Select Motion Tracking Data:"))
        self.select_label.set_margin_right(4)

        selected_tracking_data = [ep for ep in self.non_mlt_properties if ep.name == "selected_tracking_data"][0].value
        self.data_select_keys, self.data_select_combo = motiontracking.get_tracking_data_select_combo(_("No Tracking Data Available"), selected_tracking_data)

        self.delete_button = Gtk.Button(label=_("Delete"))
        self.delete_button.connect("clicked", self.delete_data)
        self.delete_button.set_margin_left(12)
        
        self.hbox1 = Gtk.HBox()
        self.hbox1.pack_start(self.select_label, False, False, 0) 
        self.hbox1.pack_start(self.data_select_combo, True, True, 0)
        self.hbox1.pack_start(self.delete_button, False, False, 0) 
        self.hbox1.set_margin_bottom(24)

        self.info_label = Gtk.Label("<small>No Tracking Data Applied</small>")
        last_applied_date_str = [ep for ep in self.non_mlt_properties if ep.name == "last_applied_tracking_data"][0].value
        if last_applied_date_str != appconsts.TRACKING_DATA_NOT_SET:
            self.show_last_applied_date(last_applied_date_str)
        self.info_label.set_use_markup(True)
        self.info_label.set_margin_right(4)

        self.button = Gtk.Button(label=_("Apply Motion Tracking Data"))
        self.button.connect("clicked", self.apply_tracking)

        self.hbox2 = Gtk.HBox()
        self.hbox2.pack_start(Gtk.Label(), True, True, 0) 
        self.hbox2.pack_start(self.info_label, False, False, 0) 
        self.hbox2.pack_start(self.button, False, False, 0)
        self.hbox2.set_margin_top(24)
        self.hbox2.set_margin_bottom(24)
        
        self.widget = Gtk.VBox()
        self.widget.pack_start(self.hbox1, False, False, 0)
        for row in self.non_mlt_editors:
            self.widget.pack_start(row, False, False, 0)
        self.widget.pack_start(self.hbox2, False, False, 0)

    def apply_tracking(self, button):
        tracking_data_id = self.data_select_keys[self.data_select_combo.get_active()]
        clip_in = self.editable_properties[0].clip.clip_in
        xoff = [ep for ep in self.non_mlt_properties if ep.name == "xoff"][0].value
        yoff = [ep for ep in self.non_mlt_properties if ep.name == "yoff"][0].value
        scale = [ep for ep in self.non_mlt_properties if ep.name == "scale"][0].value

        motiontracking.apply_filter_mask_tracking(tracking_data_id, self.filter, self.editable_properties, int(float(xoff)), int(float(yoff)), float(scale) / 100.0, clip_in)
        
        selected_tracking_data_prop = [ep for ep in self.non_mlt_properties if ep.name == "selected_tracking_data"][0]
        selected_tracking_data_prop.write_value(tracking_data_id)

        date_str = datetime.now().strftime('%y.%m - %H:%M:%S')
        last_applied_tracking_data = [ep for ep in self.non_mlt_properties if ep.name == "last_applied_tracking_data"][0]
        last_applied_tracking_data.write_value(date_str)
        self.show_last_applied_date(date_str)

    def show_last_applied_date(self, date_str):
        self.info_label.set_text("<small>" + _("Last applied ") + date_str + "</small>")
        self.info_label.set_use_markup(True)
        self.info_label.queue_draw()

    def delete_data(self, button):
        used_data = motiontracking.get_used_motion_tracking_data()
        tracking_data_id = self.data_select_keys[self.data_select_combo.get_active()]
        
        if tracking_data_id in used_data:
            self.confirm_delete()
        else:
            self.delete_selected()

    def confirm_delete(self):
        title = _("Confirm Motion Tracking Data Delete")
        text = Gtk.Label(label=_("Current selected motion tracking data was applied somewhere in the project.\n\nDelete anyway?"))
        panel = guiutils.get_left_justified_box([text])
        accept_text = _("Delete")
        dialogutils.panel_ok_cancel_dialog(title, panel, accept_text, self.delete_dialog_callback)

    def delete_dialog_callback(self, dialog, response_id):
        dialog.destroy()
        if response_id == Gtk.ResponseType.ACCEPT:
            self.delete_selected()

    def delete_selected(self):
        tracking_data_id = self.data_select_keys[self.data_select_combo.get_active()]
        if tracking_data_id == None:
            return # no tracking data exists.

        PROJECT().delete_tracking_data(tracking_data_id)

        children = self.hbox1.get_children()
        for child in children:
            self.hbox1.remove(child)

        self.data_select_keys, self.data_select_combo = motiontracking.get_tracking_data_select_combo(_("No Tracking Data Available"), -1)
        self.data_select_combo.show() 

        self.hbox1.pack_start(self.select_label, False, False, 0) 
        self.hbox1.pack_start(self.data_select_combo, True, True, 0)
        self.hbox1.pack_start(self.delete_button, False, False, 0) 

        self.widget.queue_draw()
