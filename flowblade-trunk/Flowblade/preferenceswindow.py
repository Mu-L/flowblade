"""
    Flowblade Movie Editor is a nonlinear video editor.
    Copyright 2013 Janne Liljeblad.

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

import multiprocessing
import os

from gi.repository import Gtk

import appconsts
import databridge
import dialogutils
import editorpersistance
import gui
import guiutils
import gtkbuilder
import mltprofiles
import utilsgtk


PREFERENCES_WIDTH = 730
PREFERENCES_HEIGHT = 440
PREFERENCES_LEFT = 410

def preferences_dialog():

    dialog = Gtk.Dialog(_("Editor Preferences"), None,
                    None,
                    (_("Cancel"), Gtk.ResponseType.REJECT,
                    _("OK"), Gtk.ResponseType.ACCEPT))

    gen_opts_panel, gen_opts_widgets = _general_options_panel()
    edit_prefs_panel, edit_prefs_widgets = _edit_prefs_panel()
    playback_prefs_panel, playback_prefs_widgets  = _playback_prefs_panel()
    view_pres_panel, view_pref_widgets = _view_prefs_panel()
    performance_panel, performance_widgets = _performance_panel()
    jog_shuttle_panel, jog_shuttle_widgets = _jog_shuttle_panel()

    notebook = Gtk.Notebook()
    notebook.set_size_request(PREFERENCES_WIDTH, PREFERENCES_HEIGHT)
    notebook.append_page(gen_opts_panel, Gtk.Label(label=_("General")))
    notebook.append_page(edit_prefs_panel, Gtk.Label(label=_("Editing")))
    notebook.append_page(playback_prefs_panel, Gtk.Label(label=_("Playback")))
    notebook.append_page(view_pres_panel, Gtk.Label(label=_("View")))
    notebook.append_page(performance_panel, Gtk.Label(label=_("Performance")))
    notebook.append_page(jog_shuttle_panel, Gtk.Label(label=_("Jog/Shuttle")))
    guiutils.set_margins(notebook, 4, 24, 6, 0)

    dialog.connect('response', _preferences_dialog_callback, 
                    (gen_opts_widgets, edit_prefs_widgets, playback_prefs_widgets, 
                    view_pref_widgets, performance_widgets, jog_shuttle_widgets))

    dialog.vbox.pack_start(notebook, True, True, 0)
    dialogutils.set_outer_margins(dialog.vbox)
    dialogutils.default_behaviour(dialog)
    dialog.set_transient_for(gui.editor_window.window)
    dialog.show_all()

    notebook.set_current_page(0) # gen_opts_widgets


def _preferences_dialog_callback(dialog, response_id, all_widgets):
    if response_id == Gtk.ResponseType.ACCEPT:
        editorpersistance.update_prefs_from_widgets(all_widgets)
        editorpersistance.save()
        dialog.destroy()
        primary_txt = _("Restart required for some setting changes to take effect.")
        secondary_txt = _("If requested change is not in effect, restart application.")
        dialogutils.info_message(primary_txt, secondary_txt, gui.editor_window.window)
        return

    dialog.destroy()

def _general_options_panel():
    prefs = editorpersistance.prefs

    # Widgets
    open_in_last_opened_check = Gtk.CheckButton()
    open_in_last_opened_check.set_active(prefs.open_in_last_opended_media_dir)

    open_in_last_rendered_check = Gtk.CheckButton()
    open_in_last_rendered_check.set_active(prefs.remember_last_render_dir)

    default_profile_combo = Gtk.ComboBoxText()
    profiles = mltprofiles.get_profiles()
    for profile in profiles:
        default_profile_combo.append_text(profile[0])
    default_profile_combo.set_active(mltprofiles.get_default_profile_index())
    spin_adj = Gtk.Adjustment(value=prefs.undos_max, lower=editorpersistance.UNDO_STACK_MIN, upper=editorpersistance.UNDO_STACK_MAX, step_increment=1)
    undo_max_spin = Gtk.SpinButton.new_with_range(editorpersistance.UNDO_STACK_MIN, editorpersistance.UNDO_STACK_MAX, 1)
    undo_max_spin.set_adjustment(spin_adj)
    undo_max_spin.set_numeric(True)

    autosave_combo = Gtk.ComboBoxText()
    # Aug-2019 - SvdB - AS - This is now initialized in app.main
    # Using editorpersistance.prefs.AUTO_SAVE_OPTS as source
    # AUTO_SAVE_OPTS = ((-1, _("No Autosave")),(1, _("1 min")),(2, _("2 min")),(5, _("5 min")))

    for i in range(0, len(editorpersistance.prefs.AUTO_SAVE_OPTS)):
        time, desc = editorpersistance.prefs.AUTO_SAVE_OPTS[i]
        autosave_combo.append_text(desc)
    autosave_combo.set_active(prefs.auto_save_delay_value_index)

    load_order_combo  = Gtk.ComboBoxText()
    load_order_combo.append_text(_("Absolute paths first, relative second"))
    load_order_combo.append_text(_("Relative paths first, absolute second"))
    load_order_combo.append_text(_("Absolute paths only"))
    load_order_combo.set_active(prefs.media_load_order)

    render_folder_select = gtkbuilder.get_file_chooser_button(_("Select Default Render Folder"), Gtk.FileChooserAction.SELECT_FOLDER)
    if prefs.default_render_directory == None or prefs.default_render_directory == appconsts.USER_HOME_DIR \
        or (not os.path.exists(prefs.default_render_directory)) \
        or (not os.path.isdir(prefs.default_render_directory)):
        render_folder_select.set_current_folder(os.path.expanduser("~") + "/")
    else:
        render_folder_select.set_current_folder(prefs.default_render_directory)

    disk_cache_warning_combo = Gtk.ComboBoxText()
    disk_cache_warning_combo.append_text(_("Off"))
    disk_cache_warning_combo.append_text(_("500 MB"))
    disk_cache_warning_combo.append_text(_("1 GB"))
    disk_cache_warning_combo.append_text(_("2 GB"))
    disk_cache_warning_combo.set_active(prefs.disk_space_warning)
    
    # Layout
    row1 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Default Profile:")), default_profile_combo, PREFERENCES_LEFT))
    row2 = _row(guiutils.get_checkbox_row_box(open_in_last_opened_check, Gtk.Label(label=_("Remember last media directory"))))
    row3 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Undo stack size:")), undo_max_spin, PREFERENCES_LEFT))
    row5 = _row(guiutils.get_checkbox_row_box(open_in_last_rendered_check, Gtk.Label(label=_("Remember last render directory"))))
    row6 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Autosave for crash recovery every:")), autosave_combo, PREFERENCES_LEFT))
    row9 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Media look-up order on load:")), load_order_combo, PREFERENCES_LEFT))
    row10 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Default render directory:")), render_folder_select, PREFERENCES_LEFT))
    row11 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Warning on Disk Cache Size:")), disk_cache_warning_combo, PREFERENCES_LEFT))

    vbox = Gtk.VBox(False, 2)
    vbox.pack_start(row1, False, False, 0)
    vbox.pack_start(row6, False, False, 0)
    vbox.pack_start(row2, False, False, 0)
    vbox.pack_start(row10, False, False, 0)
    vbox.pack_start(row5, False, False, 0)
    vbox.pack_start(row3, False, False, 0)
    vbox.pack_start(row9, False, False, 0)
    vbox.pack_start(row11, False, False, 0)
    vbox.pack_start(Gtk.Label(), True, True, 0)

    guiutils.set_margins(vbox, 12, 0, 12, 12)

    # Aug-2019 - SvdB - AS - Added autosave_combo
    return vbox, ( default_profile_combo, open_in_last_opened_check, open_in_last_rendered_check,
                    undo_max_spin, load_order_combo, autosave_combo, render_folder_select, disk_cache_warning_combo)

def _edit_prefs_panel():
    prefs = editorpersistance.prefs

    # Widgets
    spin_adj = Gtk.Adjustment(value=prefs.default_grfx_length, lower=1, upper=15000, step_increment=1)
    gfx_length_spin = Gtk.SpinButton()
    gfx_length_spin.set_adjustment(spin_adj)
    gfx_length_spin.set_numeric(True)

    cover_delete = Gtk.CheckButton()
    cover_delete.set_active(prefs.trans_cover_delete)

    active = 0
    if prefs.mouse_scroll_action_is_zoom == False:
        active = 1
    mouse_scroll_action = Gtk.ComboBoxText()
    mouse_scroll_action.append_text(_("Zoom, Control to Scroll Horizontal"))
    mouse_scroll_action.append_text(_("Scroll Horizontal, Control to Zoom"))
    mouse_scroll_action.set_active(active)

    active = 0
    if prefs.scroll_horizontal_dir_up_forward == False:
        active = 1
    hor_scroll_dir = Gtk.ComboBoxText()
    hor_scroll_dir.append_text(_("Scroll Up Forward"))
    hor_scroll_dir.append_text(_("Scroll Down Forward"))
    hor_scroll_dir.set_active(active)

    active = 0
    if prefs.single_click_effects_editor_load == True:
        active = 1
    effects_editor_clip_load = Gtk.ComboBoxText()
    effects_editor_clip_load.append_text(_("On Double Click"))
    effects_editor_clip_load.append_text(_("On Single Click"))
    effects_editor_clip_load.set_active(active)

    hide_file_ext_button = Gtk.CheckButton()
    if hasattr(prefs, 'hide_file_ext'):
        hide_file_ext_button.set_active(prefs.hide_file_ext)

    auto_render_plugins = Gtk.CheckButton()
    auto_render_plugins.set_active(prefs.auto_render_media_plugins)

    dnd_action = Gtk.ComboBoxText()
    dnd_action.append_text(_("Always Overwrite Blanks"))
    dnd_action.append_text(_("Overwrite Blanks on non-V1 Tracks"))
    dnd_action.append_text(_("Always Insert"))
    dnd_action.set_active(editorpersistance.prefs.dnd_action) # appconsts values correspond with order here.

    row17 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Drag-and-Drop Action:")), dnd_action, PREFERENCES_LEFT))
    row4 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Graphics default length:")), gfx_length_spin, PREFERENCES_LEFT))
    row9 = _row(guiutils.get_checkbox_row_box(cover_delete, Gtk.Label(label=_("Cover Transition/Fade clips on delete if possible"))))
    # Jul-2016 - SvdB - For play_pause button
    row11 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Mouse Middle Button Scroll Action:")), mouse_scroll_action, PREFERENCES_LEFT))
    row13 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Mouse Horizontal Scroll Direction:")), hor_scroll_dir, PREFERENCES_LEFT))
    row12 = _row(guiutils.get_checkbox_row_box(hide_file_ext_button, Gtk.Label(label=_("Hide file extensions when importing Clips"))))
    row15 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Open Clip in Effects Editor")), effects_editor_clip_load, PREFERENCES_LEFT))
    row16 = _row(guiutils.get_checkbox_row_box(auto_render_plugins, Gtk.Label(label=_("Autorender Generators"))))
    
    vbox = Gtk.VBox(False, 2)
    vbox.pack_start(row17, False, False, 0)
    vbox.pack_start(row4, False, False, 0)
    vbox.pack_start(row9, False, False, 0)
    vbox.pack_start(row11, False, False, 0)
    vbox.pack_start(row13, False, False, 0)
    vbox.pack_start(row12, False, False, 0)
    vbox.pack_start(row15, False, False, 0)
    vbox.pack_start(row16, False, False, 0)
    vbox.pack_start(Gtk.Label(), True, True, 0)

    guiutils.set_margins(vbox, 12, 0, 12, 12)

    # Jul-2016 - SvdB - Added play_pause_button
    # Apr-2017 - SvdB - Added ffwd / rev values
    return vbox, (gfx_length_spin, cover_delete,
                  mouse_scroll_action, hide_file_ext_button, hor_scroll_dir,
                  effects_editor_clip_load, auto_render_plugins, dnd_action)

def _playback_prefs_panel():
    prefs = editorpersistance.prefs

    # Widgets
    auto_center_on_stop = Gtk.CheckButton()
    auto_center_on_stop.set_active(prefs.auto_center_on_play_stop)

    auto_center_on_updown = Gtk.CheckButton()
    auto_center_on_updown.set_active(prefs.center_on_arrow_move)

    follow_move_range = Gtk.CheckButton()
    follow_move_range.set_active(prefs.playback_follow_move_tline_range)

    if hasattr(prefs, 'ffwd_rev_shift'):
        spin_adj = Gtk.Adjustment(value=prefs.ffwd_rev_shift, lower=1, upper=10, step_increment=1)
    else:
        spin_adj = Gtk.Adjustment(value=1, lower=1, upper=10, step_increment=1)
    ffwd_rev_shift_spin = Gtk.SpinButton()
    ffwd_rev_shift_spin.set_adjustment(spin_adj)
    ffwd_rev_shift_spin.set_numeric(True)

    if hasattr(prefs, 'ffwd_rev_caps'):
        spin_adj = Gtk.Adjustment(value=prefs.ffwd_rev_caps, lower=1, upper=10, step_increment=1)
    else:
        spin_adj = Gtk.Adjustment(value=1, lower=1, upper=10, step_increment=1)
    ffwd_rev_caps_spin = Gtk.SpinButton()
    ffwd_rev_caps_spin.set_adjustment(spin_adj)
    ffwd_rev_caps_spin.set_numeric(True)

    loop_clips = Gtk.CheckButton()
    loop_clips.set_active(prefs.loop_clips)

    row2 = _row(guiutils.get_checkbox_row_box(auto_center_on_stop, Gtk.Label(label=_("Center Current Frame on Playback Stop"))))
    row13 = _row(guiutils.get_checkbox_row_box(auto_center_on_updown, Gtk.Label(label=_("Center Current Frame after Up/Down Arrow"))))
    row14 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Fast Forward / Reverse Speed for Shift Key:")), ffwd_rev_shift_spin, PREFERENCES_LEFT))
    row14.set_tooltip_text(_("Speed of Forward / Reverse will be multiplied by this value if Shift Key is held (Only using KEYS).\n" \
        "Enabling multiple modifier keys will multiply the set values.\n" \
        "E.g. if Shift is set to " + str(prefs.ffwd_rev_shift) + " and Ctrl to " + str(prefs.ffwd_rev_ctrl) + \
        ", holding Shift + Ctrl will result in up to " + str(prefs.ffwd_rev_shift * prefs.ffwd_rev_ctrl) + "x speed.\n" \
        "(Effective maximum speed depends on underlying software and/or hardware limitations)"))
    row16 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Fast Forward / Reverse Speed for Caps Lock Key:")), ffwd_rev_caps_spin, PREFERENCES_LEFT))
    row16.set_tooltip_text(_("Speed of Forward / Reverse will be multiplied by this value if Caps Lock is set (Only using KEYS)."))
    row17 = _row(guiutils.get_checkbox_row_box(follow_move_range, Gtk.Label(label=_("Move Timeline to follow Playback"))))
    row18 = _row(guiutils.get_checkbox_row_box(loop_clips, Gtk.Label(label=_("Loop Media Clips on Monitor"))))

    vbox = Gtk.VBox(False, 2)
    vbox.pack_start(row17, False, False, 0)
    vbox.pack_start(row18, False, False, 0)
    vbox.pack_start(row2, False, False, 0)
    vbox.pack_start(row13, False, False, 0)
    vbox.pack_start(row14, False, False, 0)
    vbox.pack_start(row16, False, False, 0)

    vbox.pack_start(Gtk.Label(), True, True, 0)

    guiutils.set_margins(vbox, 12, 0, 12, 12)

    return vbox, (auto_center_on_stop, auto_center_on_updown, ffwd_rev_shift_spin,
                  ffwd_rev_caps_spin, follow_move_range, loop_clips)

def _view_prefs_panel():
    prefs = editorpersistance.prefs

    # Widgets
    force_english_check = Gtk.CheckButton()
    force_english_check.set_active(prefs.use_english_always)

    force_language_combo = Gtk.ComboBoxText()
    force_language_combo.append_text(_("None"))
    force_language_combo.append_text(_("English"))
    force_language_combo.append_text(_("Chinese, Simplified"))
    force_language_combo.append_text(_("Chinese, Traditional"))
    force_language_combo.append_text(_("Czech"))
    force_language_combo.append_text(_("French"))
    force_language_combo.append_text(_("German"))
    force_language_combo.append_text(_("Hungarian"))
    force_language_combo.append_text(_("Italian"))
    force_language_combo.append_text(_("Polish"))
    force_language_combo.append_text(_("Russian"))
    force_language_combo.append_text(_("Spanish"))
    force_language_combo.append_text(_("Ukrainian"))
    # THIS NEEDS TO BE UPDATED WHEN LANGUAGES ARE ADDED!!!
    lang_list = ["None","English","zh_CN","zh_TW","cs","fr","de","hu","it","pl","ru","es","uk"]
    active_index = lang_list.index(prefs.force_language)
    force_language_combo.set_active(active_index)
    force_language_combo.lang_codes = lang_list

    show_full_file_names = Gtk.CheckButton()
    show_full_file_names.set_active(prefs.show_full_file_names)

    window_mode_combo = Gtk.ComboBoxText()
    window_mode_combo.append_text(_("Single Window"))
    window_mode_combo.append_text(_("Two Windows"))
    if prefs.global_layout == appconsts.SINGLE_WINDOW:
        window_mode_combo.set_active(0)
    else:
        window_mode_combo.set_active(1)

    tracks_combo = Gtk.ComboBoxText()
    tracks_combo.append_text(_("Default - 50px, 25px"))
    tracks_combo.append_text(_("1.5 x - 75px, 37px"))
    tracks_combo.append_text(_("2 x - 100px, 50px"))
    tracks_combo.set_active(prefs.tracks_scale)

    monitors_data = utilsgtk.get_display_monitors_size_data()
    layout_monitor = Gtk.ComboBoxText()

    combined_w, combined_h = utilsgtk.get_combined_monitors_size()
            
    layout_monitor.append_text(_("Full Display area: ") + str(combined_w) + " x " + str(combined_h))
    if len(monitors_data) >= 2:
        for monitor_index in range(0, len(monitors_data)):
            monitor_w, monitor_h = monitors_data[monitor_index]
            layout_monitor.append_text(_("Monitor ") + str(monitor_index) + ": " + str(monitor_w) + " x " + str(monitor_h))
    layout_monitor.set_active(prefs.layout_display_index)

    spin_adj = Gtk.Adjustment(value=prefs.filter_select_width, lower=editorpersistance.FILTER_SELECT_WIDTH_MIN, upper=editorpersistance.FILTER_SELECT_WIDTH_MAX, step_increment=1)
    filter_select_width_spin = Gtk.SpinButton.new_with_range(editorpersistance.FILTER_SELECT_WIDTH_MIN, editorpersistance.FILTER_SELECT_WIDTH_MAX, 1)
    filter_select_width_spin.set_adjustment(spin_adj)
    filter_select_width_spin.set_numeric(True)

    spin_adj = Gtk.Adjustment(value=prefs.project_panel_width, lower=editorpersistance.PROJECT_PANEL_WIDTH_MIN, upper=editorpersistance.PROJECT_PANEL_WIDTH_MAX, step_increment=1)
    project_panel_width_spin = Gtk.SpinButton.new_with_range(editorpersistance.PROJECT_PANEL_WIDTH_MIN, editorpersistance.PROJECT_PANEL_WIDTH_MAX, 1)
    project_panel_width_spin.set_adjustment(spin_adj)
    project_panel_width_spin.set_numeric(True)

    spin_adj = Gtk.Adjustment(value=prefs.editor_panel_width, lower=editorpersistance.EDIT_PANEL_WIDTH_MIN, upper=editorpersistance.EDIT_PANEL_WIDTH_MAX, step_increment=1)
    edit_panel_width_spin = Gtk.SpinButton.new_with_range(editorpersistance.EDIT_PANEL_WIDTH_MIN, editorpersistance.EDIT_PANEL_WIDTH_MAX, 1)
    edit_panel_width_spin.set_adjustment(spin_adj)
    edit_panel_width_spin.set_numeric(True)

    spin_adj = Gtk.Adjustment(value=prefs.media_panel_width, lower=editorpersistance.MEDIA_PANEL_WIDTH_MIN, upper=editorpersistance.MEDIA_PANEL_WIDTH_MAX, step_increment=1)
    media_panel_width_spin = Gtk.SpinButton.new_with_range(editorpersistance.MEDIA_PANEL_WIDTH_MIN, editorpersistance.MEDIA_PANEL_WIDTH_MAX, 1)
    media_panel_width_spin.set_adjustment(spin_adj)
    media_panel_width_spin.set_numeric(True)
    
    row00 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Application window mode:")), window_mode_combo, PREFERENCES_LEFT))
    row9 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Force Language:")), force_language_combo, PREFERENCES_LEFT))
    row6 = _row(guiutils.get_checkbox_row_box(show_full_file_names, Gtk.Label(label=_("Show Full File names"))))
    row7 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Tracks Heights:")), tracks_combo, PREFERENCES_LEFT))

    row10 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Do GUI layout based on:")), layout_monitor, PREFERENCES_LEFT))
    row13 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Edit panel width:")), edit_panel_width_spin, PREFERENCES_LEFT))
    row12 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Project panel width:")), project_panel_width_spin, PREFERENCES_LEFT))
    row11 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Filter Select panel width:")), filter_select_width_spin, PREFERENCES_LEFT))
    row14 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Media panel width:")), media_panel_width_spin, PREFERENCES_LEFT))
    
    vbox = Gtk.VBox(False, 2)
    vbox.pack_start(row00, False, False, 0)
    vbox.pack_start(row10, False, False, 0)
    vbox.pack_start(row9, False, False, 0)
    vbox.pack_start(row6, False, False, 0)
    vbox.pack_start(row7, False, False, 0)
    vbox.pack_start(row14, False, False, 0)
    vbox.pack_start(row13, False, False, 0)
    vbox.pack_start(row12, False, False, 0)
    vbox.pack_start(row11, False, False, 0)
    vbox.pack_start(Gtk.Label(), True, True, 0)
    
    guiutils.set_margins(vbox, 12, 0, 12, 12)

    return vbox, (force_language_combo, window_mode_combo, show_full_file_names,
                  tracks_combo, project_panel_width_spin, edit_panel_width_spin, media_panel_width_spin,
                  layout_monitor, filter_select_width_spin)




def _performance_panel():
    # Jan-2017 - SvdB
    # Add a panel for performance settings. The first setting is allowing multiple threads to render
    # the files. This is used for the real_time parameter to mlt in renderconsumer.py.
    # The effect depends on the computer running the program.
    # Max. number of threads is set to number of CPU cores. Default is 1.
    # Allow Frame Dropping should help getting real time output on low performance computers.
    prefs = editorpersistance.prefs

    warning_icon = Gtk.Image.new_from_icon_name("dialog-warning", Gtk.IconSize.DIALOG)
    warning_label = Gtk.Label(label=_("Changing these values may cause problems with playback and rendering.\nThe safe values are Render Threads:1, Allow Frame Dropping: No."))

    spin_adj = Gtk.Adjustment(value=prefs.perf_render_threads, lower=1, upper=multiprocessing.cpu_count(), step_increment=1)
    perf_render_threads = Gtk.SpinButton(adjustment=spin_adj)
    #perf_render_threads.set_adjustment(spin_adj)
    perf_render_threads.set_numeric(True)

    perf_drop_frames = Gtk.CheckButton()
    perf_drop_frames.set_active(prefs.perf_drop_frames)

    # Tooltips
    perf_render_threads.set_tooltip_text(_("Between 1 and the number of CPU Cores"))
    perf_drop_frames.set_tooltip_text(_("Allow Frame Dropping for real-time rendering, when needed"))

    # Layout
    row0 = _row(guiutils.get_left_justified_box([warning_icon, warning_label]))
    row1 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Render Threads:")), perf_render_threads, PREFERENCES_LEFT))
    row2 = _row(guiutils.get_checkbox_row_box(perf_drop_frames, Gtk.Label(label=_("Allow Frame Dropping"))))

    vbox = Gtk.VBox(False, 2)
    vbox.pack_start(row0, False, False, 0)
    vbox.pack_start(guiutils.pad_label(12, 12), False, False, 0)
    vbox.pack_start(row1, False, False, 0)
    vbox.pack_start(row2, False, False, 0)
    vbox.pack_start(Gtk.Label(), True, True, 0)

    guiutils.set_margins(vbox, 12, 0, 12, 12)

    return vbox, (perf_render_threads, perf_drop_frames)

def _jog_shuttle_panel():
    prefs = editorpersistance.prefs

    # Widgets

    # usbhid_enabled
    usbhid_enabled_check = Gtk.CheckButton()
    usbhid_enabled_check.set_active(prefs.usbhid_enabled)

    # usbhid_config
    # stored as a base name equal to what is in usbhid_config_metadata.device_config_name
    # we generate a combo select box with "None" as index 0, and everything else starting
    # from index 1.
    usbhid_config = prefs.usbhid_config
    usbhid_config_combo_index = 0
    usbhid_config_combo_selected_index = 0

    usbhid_config_combo = Gtk.ComboBoxText()
    usbhid_config_combo.append_text("None")
    for usbhid_config_metadata in databridge.usbhid_get_usb_hid_device_config_metadata_list():
        usbhid_config_combo_index += 1
        usbhid_config_combo.append_text(usbhid_config_metadata.name)

        # if this is the config that was already selected in the prefs,
        # highlight it as the selected option in the combo box
        if usbhid_config is not None:
            if usbhid_config == usbhid_config_metadata.device_config_name:
                usbhid_config_combo_selected_index = usbhid_config_combo_index

    usbhid_config_combo.set_active(usbhid_config_combo_selected_index)

    # Layout
    row1 = _row(guiutils.get_checkbox_row_box(usbhid_enabled_check, Gtk.Label(label=_("USB Jog/Shuttle Enabled"))))
    row2 = _row(guiutils.get_two_column_box(Gtk.Label(label=_("Device")), usbhid_config_combo, PREFERENCES_LEFT))

    vbox = Gtk.VBox(False, 2)
    vbox.pack_start(row1, False, False, 0)
    vbox.pack_start(row2, False, False, 0)

    guiutils.set_margins(vbox, 12, 0, 12, 12)

    return vbox, (usbhid_enabled_check, usbhid_config_combo)

def _row(row_cont):
    row_cont.set_size_request(10, 26)
    return row_cont
