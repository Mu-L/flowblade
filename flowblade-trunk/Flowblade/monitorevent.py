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
Module handles button presses from monitor control buttons row.
"""

import appconsts
import clipeffectseditor
import dialogutils
import editorpersistance
import editorstate
from editorstate import PLAYER
from editorstate import PROJECT
from editorstate import current_sequence
from editorstate import timeline_visible
from editorstate import EDIT_MODE
from editorstate import current_is_move_mode
from editorstate import MONITOR_MEDIA_FILE
import gui
import guipopover
import movemodes
import trimmodes
import updater


FF_REW_SPEED = 3.0


JKL_SPEEDS = [-32.0, -16.0, -8.0, -1.0, -0.35, 0.0, 0.35, 1.0, 1.8, 3.0, 5.0, 8.0]
JKL_STOPPED_INDEX = 5
JKL_SLOWMO_FORWARD_INDEX = 6
JKL_SLOWMO_BACKWARD_INDEX = 4

# ---------------------------------------- playback
# Some events have different meanings depending on edit mode and
# are handled in either movemodes.py or trimmodes.py modules depending
# on edit mode.
def play_pressed():
    if editorstate.current_is_active_trim_mode() and trimmodes.submode != trimmodes.NOTHING_ON:
        return

    PLAYER().start_playback()
    gui.editor_window.player_buttons.show_playing_state(True)

def stop_pressed():
    PLAYER().stop_playback()
    gui.editor_window.player_buttons.show_playing_state(False)
    
    updater.maybe_autocenter()

def play_stop_pressed():
    if PLAYER().is_playing():
        stop_pressed()
    else:
        play_pressed()
            
#------------------------------------------  go to start, end
def start_pressed():
    if current_is_move_mode():
        movemodes.start_pressed()

def end_pressed():
    if current_is_move_mode():
        movemodes.end_pressed()
#------------------------------------------

def next_pressed():
    if current_is_move_mode():
        movemodes.next_pressed()

def prev_pressed():
    if current_is_move_mode():
        movemodes.prev_pressed()

def j_pressed():
    if timeline_visible():
        trimmodes.set_no_edit_trim_mode()
    jkl_index = _get_jkl_speed_index()
    if jkl_index > JKL_STOPPED_INDEX - 1: # JKL_STOPPPED_INDEX - 1 is first backwards speed, any bigger is forward, j starts backwards slow from any forward speed
        jkl_index = JKL_STOPPED_INDEX - 1
    else:
        jkl_index = jkl_index - 1

    if jkl_index < 0:
        jkl_index = 0
    new_speed = JKL_SPEEDS[jkl_index]

    if jkl_index == JKL_SLOWMO_BACKWARD_INDEX:
        fps = float(PROJECT().profile.frame_rate_num()) / float(PROJECT().profile.frame_rate_den())
        PLAYER().start_timer_slowmo_playback(new_speed, fps)
    else:
        PLAYER().start_variable_speed_playback(new_speed)

def k_pressed():
    if timeline_visible():
        trimmodes.set_no_edit_trim_mode()
    PLAYER().stop_playback()
    updater.maybe_autocenter()
    
def l_pressed():
    if timeline_visible():
        trimmodes.set_no_edit_trim_mode()
    jkl_index = _get_jkl_speed_index()
    if jkl_index < JKL_STOPPED_INDEX + 1:# JKL_STOPPPED_INDEX + 1 is first forward speed, any smaller is backward, l starts forward slow from any backwards speed
        jkl_index = JKL_STOPPED_INDEX + 1
    else:
        jkl_index = jkl_index + 1

    if jkl_index == len(JKL_SPEEDS):
        jkl_index = len(JKL_SPEEDS) - 1
        
    new_speed = JKL_SPEEDS[jkl_index]
    
    if jkl_index == JKL_SLOWMO_FORWARD_INDEX:
        fps = float(PROJECT().profile.frame_rate_num()) / float(PROJECT().profile.frame_rate_den())
        PLAYER().start_timer_slowmo_playback(new_speed, fps)
    else:
        PLAYER().start_variable_speed_playback(new_speed)

def _get_jkl_speed_index():
    speed = PLAYER().get_speed()
    if speed  < -8.0:
        return 0

    for i in range(len(JKL_SPEEDS) - 1):
        if speed <= JKL_SPEEDS[i]:
            return i

    return len(JKL_SPEEDS) - 1

# -------------------------------------- marks
def mark_in_pressed():
    mark_in = PLAYER().producer.frame()

    if timeline_visible():
        trimmodes.set_no_edit_trim_mode()
        mark_out_old = PLAYER().producer.mark_out
        PLAYER().producer.mark_in = mark_in
    else:
        mark_out_old = current_sequence().monitor_clip.mark_out
        current_sequence().monitor_clip.mark_in = mark_in

    # Clear illegal old mark out
    if mark_out_old != -1:
        if mark_out_old < mark_in:
            if timeline_visible():
                PLAYER().producer.mark_out = -1
            else:
                current_sequence().monitor_clip.mark_out = -1

    _do_marks_update()
    updater.display_marks_tc()

def mark_out_pressed():
    mark_out = PLAYER().producer.frame()

    if timeline_visible():
        trimmodes.set_no_edit_trim_mode()
        mark_in_old = PLAYER().producer.mark_in
        PLAYER().producer.mark_out = mark_out
    else:
        mark_in_old = current_sequence().monitor_clip.mark_in
        current_sequence().monitor_clip.mark_out = mark_out

    # Clear illegal old mark in
    if mark_in_old > mark_out:
        if timeline_visible():
            PLAYER().producer.mark_in = -1
        else:
            current_sequence().monitor_clip.mark_in = -1

    _do_marks_update()
    updater.display_marks_tc()

def mark_in_clear_pressed():
    if timeline_visible():
        trimmodes.set_no_edit_trim_mode()
        PLAYER().producer.mark_in = -1
    else:
        current_sequence().monitor_clip.mark_in = -1

    _do_marks_update()
    updater.display_marks_tc()

def mark_out_clear_pressed():
    if timeline_visible():
        trimmodes.set_no_edit_trim_mode()
        PLAYER().producer.mark_out = -1
    else:
        current_sequence().monitor_clip.mark_out = -1

    _do_marks_update()
    updater.display_marks_tc()

def marks_clear_pressed():
    if timeline_visible():
        trimmodes.set_no_edit_trim_mode()
        PLAYER().producer.mark_in = -1
        PLAYER().producer.mark_out = -1
    else:
        current_sequence().monitor_clip.mark_in = -1
        current_sequence().monitor_clip.mark_out = -1

    _do_marks_update()
    updater.display_marks_tc()

def to_mark_in_pressed():
    if timeline_visible():
        trimmodes.set_no_edit_trim_mode()
    mark_in = PLAYER().producer.mark_in
    if not timeline_visible():
        mark_in = current_sequence().monitor_clip.mark_in
    if mark_in == -1:
        return
    PLAYER().seek_frame(mark_in)

def to_mark_out_pressed():
    if timeline_visible():
        trimmodes.set_no_edit_trim_mode()
    mark_out = PLAYER().producer.mark_out
    if not timeline_visible():
        mark_out = current_sequence().monitor_clip.mark_out
    if mark_out == -1:
        return
    PLAYER().seek_frame(mark_out)

def _do_marks_update():

    if timeline_visible():
        producer = PLAYER().producer
    else:
        producer = current_sequence().monitor_clip
        MONITOR_MEDIA_FILE().mark_in = producer.mark_in
        MONITOR_MEDIA_FILE().mark_out = producer.mark_out
        gui.media_list_view.widget.queue_draw()

    gui.pos_bar.update_display_from_producer(producer)
    gui.tline_scale.widget.queue_draw()

# ------------------------------------------------------------ clip arrow seeks
def up_arrow_seek_on_monitor_clip():
    current_frame = PLAYER().producer.frame()

    if current_frame < MONITOR_MEDIA_FILE().mark_in:
        PLAYER().seek_frame(MONITOR_MEDIA_FILE().mark_in)
        return

    if current_frame < MONITOR_MEDIA_FILE().mark_out:
        PLAYER().seek_frame(MONITOR_MEDIA_FILE().mark_out)
        return

    PLAYER().seek_frame(PLAYER().producer.get_length() - 1)

def down_arrow_seek_on_monitor_clip():
    current_frame = PLAYER().producer.frame()
    mark_in = MONITOR_MEDIA_FILE().mark_in
    mark_out = MONITOR_MEDIA_FILE().mark_out

    if current_frame > mark_out and mark_out != -1:
        PLAYER().seek_frame(MONITOR_MEDIA_FILE().mark_out)
        return

    if current_frame > mark_in and mark_in != -1:
        PLAYER().seek_frame(MONITOR_MEDIA_FILE().mark_in)
        return

    PLAYER().seek_frame(0)

# -------------------------------------------------- monitor playback interpolation
def set_monitor_playback_interpolation(new_interpolation):
    PLAYER().consumer.set("rescale", str(new_interpolation)) # MLT options "nearest", "bilinear", "bicubic", "hyper" hardcoded into menu items

# -------------------------------------------------- selecting clips for filter editing
def select_next_clip_for_filter_edit():
    if not editorstate.timeline_visible():
        updater.display_sequence_in_monitor()
    tline_frame = PLAYER().tracktor_producer.frame() + 1

    clip, track = current_sequence().find_next_editable_clip_and_track(tline_frame)
    if clip == None:
        return
    
    range_in = track.clips.index(clip)
    frame = track.clip_start(range_in)

    movemodes.select_clip(track.id, range_in)
    PLAYER().seek_frame(frame)

    clipeffectseditor.set_clip(clip, track, range_in)

def select_prev_clip_for_filter_edit():
    if not editorstate.timeline_visible():
        updater.display_sequence_in_monitor()
    tline_frame = PLAYER().tracktor_producer.frame() - 1

    clip, track = current_sequence().find_prev_editable_clip_and_track(tline_frame)
    if clip == None:
        return
    
    range_in = track.clips.index(clip)
    frame = track.clip_start(range_in)

    movemodes.select_clip(track.id, range_in)
    PLAYER().seek_frame(frame)

    clipeffectseditor.set_clip(clip, track, range_in)

# --------------------------------------------------------- trim view
def trim_view_menu_launched(launcher, widget, event):
    guipopover.trim_view_popover_show(launcher, widget, _trim_view_menu_item_activated)

def _trim_view_menu_item_activated(action, new_value_variant):
    msg = new_value_variant.get_string()
        
    if msg == "trimon":
        editorstate.show_trim_view = appconsts.TRIM_VIEW_ON
        editorpersistance.prefs.trim_view_default = appconsts.TRIM_VIEW_ON
        editorpersistance.save()
        if editorpersistance.prefs.trim_view_message_shown == False:
            _show_trimview_info()
    if msg == "trimsingle":
        editorstate.show_trim_view = appconsts.TRIM_VIEW_SINGLE
        editorpersistance.prefs.trim_view_default = appconsts.TRIM_VIEW_SINGLE
        editorpersistance.save()
        if editorpersistance.prefs.trim_view_message_shown == False:
            _show_trimview_info()
    if msg == "trimoff":
        editorstate.show_trim_view = appconsts.TRIM_VIEW_OFF
        editorpersistance.prefs.trim_view_default = appconsts.TRIM_VIEW_OFF
        editorpersistance.save()

    action.set_state(new_value_variant)
    guipopover._trimview_popover.hide()
        
def _show_trimview_info():
    editorpersistance.prefs.trim_view_message_shown = True
    editorpersistance.save()
    primary_txt = _("On some systems Trim View may update slowly")
    secondary_txt = _("<b>Trim View</b> works best with SSDs and relatively powerful processors.\n\n") + \
                    _("Select <b>'Trim View Off'</b> or<b>'Trim View Single Side Edits Only'</b> options\nif performance is not satisfactory.")
    dialogutils.info_message(primary_txt, secondary_txt, gui.editor_window.window)

# --------------------------------------------------------- trim view
def start_marks_looping():
    if PLAYER().looping():
        PLAYER().stop_loop_playback()
    if PLAYER().is_playing():
        PLAYER().stop_playback()

    if timeline_visible():
        mark_in = PLAYER().producer.mark_in
        mark_out = PLAYER().producer.mark_out
    else:
        mark_in = current_sequence().monitor_clip.mark_in
        mark_out = current_sequence().monitor_clip.mark_out
    
    if mark_in == -1 or mark_out == -1:
        return
    
    PLAYER().start_loop_playback_range(mark_in, mark_out)

