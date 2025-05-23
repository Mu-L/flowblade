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
Module creates EditAction objects that have user input as input
and sequence state changes as output.

Edits, undos and redos are done by creating and calling methods on these 
EditAction objects and placing them on the undo/redo stack.
"""
import copy

import appconsts
import clipeffectseditor
import compositeeditor
import containeractions
import containerclip
from editorstate import current_sequence
from editorstate import get_track
from editorstate import PLAYER
from editorstate import PROJECT
import mltfilters
import movemodes
import mediaplugin
import resync
import trackaction
import trimmodes
import undo
import updater
import utils


# GUI updates are turned off for example when doing resync action
do_gui_update = False

# Flag for doing edits since last save
edit_done_since_last_save = False


# ---------------------------------- atomic edit ops
def append_clip(track, clip, clip_in, clip_out):
    """
    Affects MLT c-struct and python obj values.
    """
    clip.clip_in = clip_in
    clip.clip_out = clip_out
    track.clips.append(clip) # py
    track.append(clip, clip_in, clip_out) # mlt
    resync.clip_added_to_timeline(clip, track)

def _insert_clip(track, clip, index, clip_in, clip_out):
    """
    Affects MLT c-struct and python obj values.
    """
    clip.clip_in = clip_in
    clip.clip_out = clip_out
    track.clips.insert(index, clip) # py
    track.insert(clip, index, clip_in, clip_out) # mlt
    resync.clip_added_to_timeline(clip, track)

def _insert_blank(track, index, length):
    track.insert_blank(index, length - 1) # end inclusive
    blank_clip = track.get_clip(index)
    current_sequence().add_clip_attr(blank_clip)
    blank_clip.clip_in = 0
    blank_clip.clip_out = length - 1 # -1, end inclusive
    blank_clip.is_blanck_clip = True
    track.clips.insert(index, blank_clip)
    
def _remove_clip(track, index):
    """
    Affects MLT c-struct and python obj values.
    """
    track.remove(index)
    clip = track.clips.pop(index)
    resync.clip_removed_from_timeline(clip)
    
    return clip

# -------------------------------- combined edit ops
def _cut(track, index, clip_cut_frame, clip, clip_copy):
    """
    Does cut by removing clip and adding it and copy back
    """
    _remove_clip(track, index)
    second_out = clip.clip_out # save before insert
    _insert_clip(track, clip, index, clip.clip_in, clip_cut_frame - 1)
    _insert_clip(track, clip_copy, index + 1, clip_cut_frame, second_out)

def _cut_blank(track, index, clip_cut_frame, clip):
    """
    Cuts a blank clip in two.
    """
    _remove_clip(track, index)

    clip_one_length = clip_cut_frame
    clip_two_length = clip.clip_out - clip_cut_frame + 1 # +1 == cut frame part of this clip

    track.insert_blank(index, clip_one_length - 1) # -1 MLT api says so 
    track.insert_blank(index + 1, clip_two_length - 1) # -1 MLT api says so 
    
    _add_blank_to_py(track, index, clip_one_length)
    _add_blank_to_py(track, index + 1, clip_two_length)

def _add_blank_to_py(track, index, length):
    """
    Adds clip data to python side structures for clip that
    already exists in MLT data structures
    """
    blank_clip = track.get_clip(index)
    current_sequence().add_clip_attr(blank_clip)
    blank_clip.clip_in = 0
    blank_clip.clip_out = length - 1 # -1, end inclusive
    blank_clip.is_blanck_clip = True
    track.clips.insert(index, blank_clip)
    return blank_clip

# --------------------------------- util methods
def _set_in_out(clip, c_in, c_out):
    """
    Affects MLT c-struct and python obj values.
    """
    clip.clip_in = c_in
    clip.clip_out = c_out
    clip.set_in_and_out(c_in, c_out)
    
def _clip_length(clip): # check if can be removed
    return clip.clip_out - clip.clip_in + 1 # +1, end inclusive

def _frame_on_cut(clip, clip_frame):
    if clip_frame == clip.clip_in:
        return True
    if clip_frame == clip.clip_out + 1: # + 1 out is inclusive
        return True
        
    return False

def _remove_trailing_blanks_undo(self):
    for trailing_blank in self.trailing_blanks:
        track_index, length = trailing_blank 
        track = current_sequence().tracks[track_index]
        _insert_blank(track, track.count(), length)

def _remove_trailing_blanks_redo(self):
    _remove_all_trailing_blanks(self)

def _remove_all_trailing_blanks(self=None):
    if self != None:
        self.trailing_blanks = []
    for i in range(1, len(current_sequence().tracks) - 1): # -1 because hidden track, 1 because black track
        try:
            track = current_sequence().tracks[i]
            last_clip_index = track.count() - 1
            clip = track.clips[last_clip_index]
            if clip.is_blanck_clip:
                length = clip.clip_length()
                _remove_clip(track, last_clip_index)
                if self != None:
                    self.trailing_blanks.append((i, length))
        except:
            pass

def _create_clip_clone(clip):
    if clip.container_data != None:
        new_clip = containerclip.clone_clip(clip)
    elif clip.media_type != appconsts.PATTERN_PRODUCER:
        new_clip = current_sequence().create_file_producer_clip(clip.path, None, False, clip.ttl)
    else:
        new_clip = current_sequence().create_pattern_producer(clip.create_data)
    new_clip.name = clip.name
    new_clip.titler_data = copy.deepcopy(clip.titler_data)
    new_clip.slowmo_data = copy.deepcopy(clip.slowmo_data)
    new_clip.link_seq_data = copy.deepcopy(clip.link_seq_data)
    if clip.sync_data != None:
        new_clip.sync_data = SyncData()
        new_clip.sync_data.pos_offset = clip.sync_data.pos_offset
        new_clip.sync_data.master_clip = clip.sync_data.master_clip
        new_clip.sync_data.master_clip_track = clip.sync_data.master_clip_track
        new_clip.sync_data.sync_state = clip.sync_data.sync_state 
    return new_clip

def _create_mute_volume_filter(seq): 
    return mltfilters.create_mute_volume_filter(seq)
    
def _do_clip_mute(clip, volume_filter):
    mltfilters.do_clip_mute(clip, volume_filter)

def _do_clip_unmute(clip):
    clip.detach(clip.mute_filter.mlt_filter)
    clip.mute_filter = None

def _remove_consecutive_blanks(track, index):
    lengths = []
    while track.clips[index].is_blanck_clip:
        lengths.append(track.clips[index].clip_length())
        _remove_clip(track, index)
        if index == len(track.clips):
            break
    return lengths

#------------------------------------------------------------- overwrite util methods
def _overwrite_cut_track(track, frame, add_cloned_filters=False):
    """
    If frame is on an existing cut, then the method does nothing and returns tuple (-1, -1) 
    to signal that no cut was made.
    
    If frame is in middle of clip or blank, then the method cuts that item in two
    and returns tuple of in and out frames of the clip that was cut as they
    were before the cut, for the purpose of having information to do undo later.
    
    If cut was made it also clones filters to new clip created by cut if requested.
    """
    index = track.get_clip_index_at(frame)
    clip = track.clips[index]
    orig_in_out = (clip.clip_in, clip.clip_out)
    clip_start_in_tline = track.clip_start(index)
    clip_frame = frame - clip_start_in_tline + clip.clip_in
    
    if not _frame_on_cut(clip, clip_frame):
        if clip.is_blank():
            add_clip = _cut_blank(track, index, clip_frame, clip)
        else:
            add_clip = _create_clip_clone(clip)            
            _cut(track, index, clip_frame, clip, add_clip)
            if add_cloned_filters:
                clone_filters = current_sequence().clone_filters(clip)
                add_clip.filters = clone_filters
                _attach_all(add_clip) 
        return orig_in_out
    else:
        return (-1, -1)

def _overwrite_cut_range_out(track, self):
    # self is the EditAction object
    # Cut at out point if not already on cut and out point inside track length
    self.orig_out_clip = None
    if track.get_length() > self.over_out:
        clip_in, clip_out = _overwrite_cut_track(track, self.over_out, True)
        self.out_clip_in = clip_in
        self.out_clip_length = clip_out - clip_in + 1 # Cut blank can't be reconstructed with clip_in data as it is always 0 for blank, so we use this
        if clip_in != -1: # if we did cut we'll need to restore the dut out clip
                          # which is the original clip because 
            orig_index = track.get_clip_index_at(self.over_out - 1)
            self.orig_out_clip = track.clips[orig_index] 
    else:
        self.out_clip_in = -1

def _overwrite_restore_in(track, moved_index, self):
    # self is the EditAction object
    in_clip = _remove_clip(track, moved_index - 1)
    if not in_clip.is_blanck_clip:
        _insert_clip(track, in_clip, moved_index - 1,
                     in_clip.clip_in, self.in_clip_out)
    else: # blanks can't be resized, so put in new blank
        _insert_blank(track, moved_index - 1, self.in_clip_out - in_clip.clip_in + 1)
    self.removed_clips.pop(0)
        
def _overwrite_restore_out(track, moved_index, self):
    # self is the EditAction object

    # If moved clip/s were last in the track and were moved slightly 
    # forward and were still last in track after move
    # this leaves a trailing black that has been removed and this will fail
    try:
        out_clip = _remove_clip(track, moved_index)
        if len(self.removed_clips) > 0: # If overwrite was done inside single clip everything is already in order
            if not out_clip.is_blanck_clip:
                _insert_clip(track, self.orig_out_clip, moved_index,
                         self.out_clip_in, out_clip.clip_out)
            else: # blanks can't be resized, so put in new blank
                _insert_blank(track, moved_index, self.out_clip_length)
            self.removed_clips.pop(-1) 
    except:
        pass


#---------------------------------------------- EDIT ACTION
class EditAction:
    """
    Packages together edit data and methods to make an undoable 
    change to sequence.
    
    data - input is dict with named attributes that correspond
    to usage in undo_func and redo_func
    
    redo_func is written so that it can be called also when edit is first done
    and do_edit() is called.
    """
    def __init__(self, undo_func, redo_func, data):
        # Functions that change state both ways.
        self.undo_func = undo_func
        self.redo_func = redo_func
    
        # Grabs data as object members.
        self.__dict__.update(data)
        
        # Compositor auto follow is saved with each edit and is computed on first do and later done on redo/undo
        self.compositor_autofollow_data = None
        
        # Compositor mode COMPOSITING_MODE_STANDARD_AUTO_FOLLOW required that compositors without parent clips are destroyed
        # when origin clips are destroyed. This functionality probably no longer meaningful.
        self.orphaned_compositors = None
        
        # Other then actual trim edits, attempting all edits exits active trimodes and enters <X>_NO_EDIT trim mode.
        self.exit_active_trimmode_on_edit = True

        # If edit is part of group some updates are only done once for the whole 
        # group.
        self.is_part_of_consolidated_group = False

        # HACK!!!! Overwrite edits crash at redo(sometimes undo) when current frame inside 
        # affected area if consumer running.
        # Remove when fixed in MLT.
        self.stop_for_edit = False 
        self.turn_on_stop_for_edit = False # set true in redo_func for edits that need it

        # NEEDED FOR TRIM CRASH HACK, REMOVE IF FIXED IN MLT
        # Length of the blank on hidden track covering the whole sequence
        # needs to be updated after every edit EXCEPT after trim edits which
        # update the hidden track themselves and this flag "update_hidden_track" to False
        self.update_hidden_track_blank = True
        
        # Clip effects editor can't handle moving clips between tracks and 
        # needs to be clearad when clips are moved to another track.
        self.clear_effects_editor_for_multitrack_edit = False  

        # Pasting filters to clip might not be detected by our quite naive algorithm as
        # clip's filters stack having being changed, so we use this to force update on that edit action. 
        self.force_effects_editor_update = False 
        
    def do_edit(self):
        if self.exit_active_trimmode_on_edit:
            trimmodes.set_no_edit_trim_mode()

        # Tracks autoexpand-on-drop feature needs to be here to avoid caching data.
        tracks_clips_count_before = current_sequence().get_tracks_clips_counts()

        self.redo()
        undo.register_edit(self)

        if self.turn_on_stop_for_edit:
            self.stop_for_edit = True

        global edit_done_since_last_save
        edit_done_since_last_save = True

        trackaction.maybe_do_auto_expand(tracks_clips_count_before)
        
        undo.force_revert_if_cyclic_seq_links(PROJECT())
        
    def undo(self):
        PLAYER().stop_playback()

        movemodes.clear_selected_clips()  # selection not valid after change in sequence
        _remove_trailing_blanks_undo(self)
        _consolidate_all_blanks_undo(self)
    
        self.undo_func(self)

        _remove_all_trailing_blanks(None)

        resync.calculate_and_set_child_clip_sync_states()
        
        if do_gui_update:
            self._update_gui()
            
    def redo(self):
        PLAYER().stop_playback()

        movemodes.clear_selected_clips() # selection is not valid after a change in sequence

        self.redo_func(self)

        _consolidate_all_blanks_redo(self)
        _remove_trailing_blanks_redo(self)

        resync.calculate_and_set_child_clip_sync_states()
                
        # Update GUI.
        if do_gui_update:
            self._update_gui()
        
    def _update_gui(self): # This is copied with small modifications into projectaction.py for sequence imports, update there too if needed.
        updater.update_tline_scrollbar() # Slider needs to adjust to possibly new program length.
                                         # This REPAINTS TIMELINE as a side effect.
                                         
        # Clear or update edit panels that do not target an existing and up-to-date object.
        if self.clear_effects_editor_for_multitrack_edit == False:
            if current_sequence().clip_is_in_sequence(clipeffectseditor.get_edited_clip()) == True:
                updater.update_kf_editors_positions()
                clipeffectseditor.reinit_stack_if_needed(self.force_effects_editor_update)
            elif mediaplugin.panel_is_open() == True:
                if current_sequence().clip_is_in_sequence(mediaplugin.get_clip()) == True:
                    # Keep displaying open Generator properties edit panel 
                    # if the clip is still in sequence. 
                    pass
                else:
                    updater.clear_editor_panel()
            else:
                if compositeeditor.compositor == None:
                    updater.clear_editor_panel()
        else:
            updater.clear_editor_panel()

        current_sequence().update_edit_tracks_length() # Needed for timeline render updates
        if self.update_hidden_track_blank:
            current_sequence().update_hidden_track_for_timeline_rendering() # Needed for timeline render updates
        PLAYER().display_inside_sequence_length(current_sequence().seq_len)

        updater.update_position_bar()
        updater.update_seqence_info_text()



class ConsolidatedEditAction:
    """
    Combines 1 - n EditAction objects in a group so that they are represented 
    in the undo stack as a single un-doable action.
    Edits are assumed to be all of the same type.
    """

    def __init__(self, edit_actions):
        self.edit_actions = edit_actions

    def do_consolidated_edit(self):
        # There is 1 - n edits in these,
        # and they are assumed to be all of the same type.
        # More precisely, they need to have properties:
        #    .exit_active_trimmode_on_edit
        #    .turn_on_stop_for_edit
        # same for all the consolidated edits for this to work reliably.
        if self.edit_actions[0].exit_active_trimmode_on_edit:
            trimmodes.set_no_edit_trim_mode()

        # We only do one gui update.
        global do_gui_update
        do_gui_update = False

        for edit_action in self.edit_actions:
            edit_action.is_part_of_consolidated_group = True
            
            # Tracks autoexpand-on-drop feature needs to be here to avoid caching data.
            tracks_clips_count_before = current_sequence().get_tracks_clips_counts()

            # Some actions like audio splice may need the previous edit_action to 
            # complete before they can be created, so for these we provide a lambda 
            # that cretes the edit action.
            if callable(edit_action) == True:
                new_edit_action = edit_action()
                old_index = self.edit_actions.index(edit_action)
                self.edit_actions[old_index] = new_edit_action
                edit_action = new_edit_action

            # Enable GUI update for last action.
            if edit_action is self.edit_actions[len(self.edit_actions) - 1]:
                do_gui_update = True

            edit_action.redo()

            if edit_action.turn_on_stop_for_edit:
                edit_action = True

            global edit_done_since_last_save
            edit_done_since_last_save = True

            trackaction.maybe_do_auto_expand(tracks_clips_count_before)

        do_gui_update = True
                
        undo.register_edit(self)

        undo.force_revert_if_cyclic_seq_links(PROJECT())
        
    def redo(self):
        # We only do one gui update.
        global do_gui_update
        do_gui_update = False
        
        for edit_action in self.edit_actions:
            if edit_action is self.edit_actions[len(self.edit_actions) - 1]:
                do_gui_update = True

            edit_action.redo()
            
    def undo(self):
        # We only do one gui update.
        global do_gui_update
        do_gui_update = False
        
        for edit_action in reversed(self.edit_actions):
            if edit_action is self.edit_actions[0]:
                do_gui_update = True

            edit_action.undo()




# ---------------------------------------------------- compositor sync methods
def get_full_compositor_sync_data():
    # Returns list of tuples in form (compositor, orig_in, orig_out, clip_start, clip_end)
    # Pair all compositors with their origin clips ids
    comp_clip_pairings = {}
    for compositor in current_sequence().compositors:
        if compositor.origin_clip_id in comp_clip_pairings:
            comp_clip_pairings[compositor.origin_clip_id].append(compositor)
        else:
            comp_clip_pairings[compositor.origin_clip_id] = [compositor]
    
    # Create resync list
    resync_list = []
    orphan_origin_clip_ids = list(comp_clip_pairings.keys())
    for i in range(current_sequence().first_video_index, len(current_sequence().tracks) - 1): # -1, there is a topmost hidden track 
        track = current_sequence().tracks[i] # b_track is source track where origin clip is
        for j in range(0, len(track.clips)):
            clip = track.clips[j]
            if clip.id in comp_clip_pairings:
                compositor_list = comp_clip_pairings[clip.id]
                for compositor in compositor_list:
                    resync_list.append((clip, track, j, compositor))
            if clip.id in orphan_origin_clip_ids:
                orphan_origin_clip_ids.remove(clip.id)
    
    # Create orphan compositors list
    orhan_compositors = []
    if current_sequence().compositing_mode == appconsts.COMPOSITING_MODE_STANDARD_AUTO_FOLLOW:
        for oprhan_comp_origin in orphan_origin_clip_ids:
            orhan_compositors.append(comp_clip_pairings[oprhan_comp_origin][0])

    # Create full data
    full_sync_data = []
    for resync_item in resync_list:
        try:
            clip, track, clip_index, compositor = resync_item
            clip_start = track.clip_start(clip_index)
            clip_end = clip_start + clip.clip_out - clip.clip_in
            
            orig_in = compositor.clip_in
            orig_out = compositor.clip_out
            
            destroy_id = compositor.destroy_id
            
            full_sync_data_item = (destroy_id, orig_in, orig_out, clip_start, clip_end, track.id, compositor.transition.b_track)
            full_sync_data.append(full_sync_data_item)
        except:
            # Clip is probably deleted
            pass

    return (full_sync_data, orhan_compositors)


# ---------------------------------------------------- SYNC DATA
class SyncData:
    """
    Captures sync between two clips, values filled at use sites.
    """
    def __init__(self):
        self.pos_offset = None
        self.clip_in = None
        self.clip_out = None
        self.master_clip = None
        self.master_clip_track = None
        self.master_inframe = None
        self.master_audio_index = None # this does nothing? try to remove.

def _switch_synched_clip(child_clip, child_track, old_child_clip):
    # Set sync data
    resync.clip_added_to_timeline(child_clip, child_track)
    resync.clip_removed_from_timeline(old_child_clip)

def _clone_sync_data(new_clip, clip):
    new_clip.sync_data = SyncData()
    new_clip.sync_data.pos_offset = clip.sync_data.pos_offset
    new_clip.sync_data.master_clip = clip.sync_data.master_clip
    new_clip.sync_data.master_clip_track = clip.sync_data.master_clip_track
    new_clip.sync_data.sync_state = clip.sync_data.sync_state 
    
#-------------------- APPEND CLIP
# "track","clip","clip_in","clip_out"
# Appends clip to track
def append_action(data):
    action = EditAction(_append_undo,_append_redo, data)
    return action

def _append_undo(self):
    self.clip = _remove_clip(self.track, len(self.track.clips) - 1)

def _append_redo(self):
    self.clip.index = self.track.count()
    append_clip(self.track, self.clip, self.clip_in, self.clip_out)

#-------------------- APPEND MULTIPLE CLIPS
# "track","clips"
# Appends clip to track
def append_multiple_action(data):
    action = EditAction(_append_multiple_undo,_append_multiple_redo, data)
    return action

def _append_multiple_undo(self):
    for add_clip in self.clips:
        self.clip = _remove_clip(self.track, self.append_index)

def _append_multiple_redo(self):
    self.append_index = self.track.count()
    for add_clip in self.clips:
        append_clip(self.track, add_clip, add_clip.clip_in, add_clip.clip_out)

#----------------- REMOVE MULTIPLE CLIPS
# "track","from_index","to_index"
def remove_multiple_action(data):
    action = EditAction(_remove_multiple_undo,_remove_multiple_redo, data)
    return action

def _remove_multiple_undo(self):
    clips_count = self.to_index + 1 - self.from_index # + 1 == to_index inclusive
    for i in range(0, clips_count):
        add_clip = self.clips[i]
        index = self.from_index + i
        _insert_clip(self.track, add_clip, index, add_clip.clip_in, \
                     add_clip.clip_out)

def _remove_multiple_redo(self):
    self.clips = []
    for i in range(self.from_index, self.to_index + 1):
        removed_clip = _remove_clip(self.track, self.from_index)
        self.clips.append(removed_clip)

#------------------ COVER DELETE FADE OUT
# "track","clip","index"
def cover_delete_fade_out(data):
    action = EditAction(_cover_delete_fade_out_undo,_cover_delete_fade_out_redo, data)
    return action

def _cover_delete_fade_out_undo(self):
    cover_clip = _remove_clip(self.track, self.index - 1)
    _insert_clip(self.track, cover_clip, self.index - 1,
                 cover_clip.clip_in, self.original_out)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in, self.clip.clip_out)

def _cover_delete_fade_out_redo(self):
    _remove_clip(self.track, self.index)
    cover_clip = _remove_clip(self.track, self.index - 1)
    self.original_out = cover_clip.clip_out
    _insert_clip(self.track, cover_clip, self.index - 1,
                 cover_clip.clip_in, cover_clip.clip_out + self.clip.clip_length())

#------------------ COVER DELETE FADE IN
# "track","clip","index"
def cover_delete_fade_in(data):
    action = EditAction(_cover_delete_fade_in_undo,_cover_delete_fade_in_redo, data)
    return action

def _cover_delete_fade_in_undo(self):
    cover_clip = _remove_clip(self.track, self.index)
    _insert_clip(self.track, cover_clip, self.index,
                 self.original_in,  cover_clip.clip_out)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in, self.clip.clip_out)

def _cover_delete_fade_in_redo(self):
    _remove_clip(self.track, self.index)
    cover_clip = _remove_clip(self.track, self.index)
    self.original_in = cover_clip.clip_in
    _insert_clip(self.track, cover_clip, self.index,
                 cover_clip.clip_in - self.clip.clip_length(), cover_clip.clip_out)

#------------------ COVER DELETE TRANSITION
# "track", "clip","index","to_part","from_part"
def cover_delete_transition(data):
    action = EditAction(_cover_delete_transition_undo, _cover_delete_transition_redo, data)
    return action

def _cover_delete_transition_undo(self):
    cover_clip_from = _remove_clip(self.track, self.index - 1)
    cover_clip_to = _remove_clip(self.track, self.index - 1)

    _insert_clip(self.track, cover_clip_from, self.index - 1,
                 cover_clip_from.clip_in, self.original_from_out)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in, self.clip.clip_out)
    _insert_clip(self.track, cover_clip_to, self.index + 1,
                 self.original_to_in, cover_clip_to.clip_out)

def _cover_delete_transition_redo(self):
    cover_clip_from = _remove_clip(self.track, self.index - 1)
    _remove_clip(self.track, self.index - 1)
    cover_clip_to = _remove_clip(self.track, self.index - 1)
    
    self.original_from_out = cover_clip_from.clip_out
    self.original_to_in = cover_clip_to.clip_in
    
    _insert_clip(self.track, cover_clip_from, self.index - 1,
                 cover_clip_from.clip_in, cover_clip_from.clip_out + self.from_part - 1)
    _insert_clip(self.track, cover_clip_to, self.index,
                 cover_clip_to.clip_in - self.to_part, cover_clip_to.clip_out)

#----------------- LIFT MULTIPLE CLIPS 
# "track","from_index","to_index"
def lift_multiple_action(data):
    action = EditAction(_lift_multiple_undo,_lift_multiple_redo, data)
    action.blank_clip = None
    return action

def _lift_multiple_undo(self):
    # Remove blank
    _remove_clip(self.track, self.from_index)
    
    # Insert clips
    clips_count = self.to_index + 1 - self.from_index # + 1 == to_index inclusive
    for i in range(0, clips_count):
        add_clip = self.clips[i]
        index = self.from_index + i
        _insert_clip(self.track, add_clip, index, add_clip.clip_in, \
                     add_clip.clip_out)

def _lift_multiple_redo(self):
    # Remove clips
    self.clips = []
    removed_length = 0
    for i in range(self.from_index, self.to_index + 1): # + 1 == to_index inclusive
        removed_clip = _remove_clip(self.track, self.from_index)
        self.clips.append(removed_clip)
        removed_length += _clip_length(removed_clip)

    # Insert blank
    _insert_blank(self.track, self.from_index, removed_length)


#----------------- CUT CLIP 
# "track","clip","index","clip_cut_frame"
# Cuts clip at frame by creating two clips and setting ins and outs.
def cut_action(data):
    action = EditAction(_cut_undo,_cut_redo, data)
    return action

def _cut_undo(self):
    _remove_clip(self.track, self.index)
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index, self.clip.clip_in, \
                 self.new_clip.clip_out)

def _cut_redo(self):
    # Create new second clip if does not exist
    if(not hasattr(self, "new_clip")):
        self.new_clip = _create_clip_clone(self.clip)
        current_sequence().copy_filters(self.clip, self.new_clip )
        self.new_clip.markers = copy.deepcopy(self.clip.markers)
        current_sequence().clone_mute_state(self.clip, self.new_clip)
    
    _cut(self.track, self.index, self.clip_cut_frame, self.clip, \
         self.new_clip)

#----------------- CUT ALL TRACKS
# "tracks_cut_data" which is a list of [{"track","clip","index","clip_cut_frame"}] objects, list of cut data for all tracks
def cut_all_action(data):
    action = EditAction(_cut_all_undo,_cut_all_redo, data)
    return action

def _cut_all_undo(self):    
    for i in range(0, len(self.tracks_cut_data)):
        track_cut_data = self.tracks_cut_data[i]
        if track_cut_data == None: # not all tracks are cut
            continue
        new_clip = self.new_clips[i]
        _remove_clip(track_cut_data["track"], track_cut_data["index"])
        _remove_clip(track_cut_data["track"], track_cut_data["index"])
        _insert_clip(track_cut_data["track"], track_cut_data["clip"],  
                     track_cut_data["index"], track_cut_data["clip"].clip_in,
                     new_clip.clip_out)

def _cut_all_redo(self):
    # Create new second clips list if does not exist
    if(not hasattr(self, "new_clips")):
        self.new_clips = []
        first_redo = True
    else:
        first_redo = False

    for i in range(0, len(self.tracks_cut_data)):
        track_cut_data = self.tracks_cut_data[i]
        
        if track_cut_data == None: # not all tracks are cut
            if first_redo == True:
                self.new_clips.append(None)
            continue
                
        if first_redo == True:
            new_clip = _create_clip_clone(track_cut_data["clip"])
            current_sequence().copy_filters(track_cut_data["clip"], new_clip)
            new_clip.markers = copy.deepcopy(track_cut_data["clip"].markers)
            current_sequence().clone_mute_state(track_cut_data["clip"], new_clip)
            self.new_clips.append(new_clip)
        else:
            new_clip = self.new_clips[i]
            
        _cut(track_cut_data["track"], track_cut_data["index"],
             track_cut_data["clip_cut_frame"], track_cut_data["clip"],
             new_clip)


#----------------- INSERT CLIP
# "track","clip","index","clip_in","clip_out"
# Inserts clip at index into track
def insert_action(data):
    action = EditAction(_insert_undo,_insert_redo, data)
    return action

def _insert_undo(self):
    _remove_clip(self.track, self.index)

def _insert_redo(self):
    _insert_clip(self.track, self.clip, self.index, self.clip_in, self.clip_out)


#----------------- 3 POINT OVERWRITE
# "track","clip", "clip_in","clip_out","in_index","out_index"
def three_point_overwrite_action(data):
    action = EditAction(_three_over_undo, _three_over_redo, data)
    return action
    
def _three_over_undo(self):
    _remove_clip(self.track, self.in_index)
    
    clips_count = self.out_index + 1 - self.in_index # + 1 == to_index inclusive
    for i in range(0, clips_count):
        add_clip = self.clips[i]
        index = self.in_index + i
        _insert_clip(self.track, add_clip, index, add_clip.clip_in, add_clip.clip_out)

def _three_over_redo(self):
    # Remove and replace
    self.clips = []
    for i in range(self.in_index, self.out_index + 1): # + 1 == out_index inclusive
        removed_clip = _remove_clip(self.track, i)
        self.clips.append(removed_clip)

    _insert_clip(self.track, self.clip, self.in_index, self.clip_in, self.clip_out)

#----------------- SYNC OVERWRITE
#"track","clip","clip_in","clip_out","frame"
def sync_overwrite_action(data):
    action = EditAction(_sync_over_undo, _sync_over_redo, data)
    return action
    
def _sync_over_undo(self):
    # Remove overwrite clip
    track = self.track
    _remove_clip(track, self.in_index)
    
    # Fix in clip and remove cut created clip if in was cut
    if self.in_clip_out != -1:
        in_clip = _remove_clip(track, self.in_index - 1)
        copy_clip = _create_clip_clone(in_clip) 
        _insert_clip(track, copy_clip, self.in_index - 1,
                     in_clip.clip_in, self.in_clip_out)
        self.removed_clips.pop(0) # The end half of insert cut
    
    # Fix out clip and remove cut created clip if out was cut
    if self.out_clip_in != -1:
        try:
            out_clip = _remove_clip(track, self.out_index)
            copy_clip = _create_clip_clone(out_clip)
            if len(self.removed_clips) > 0: # If overwrite was done inside single clip 
                                            # we don' need to put end half of out clip back in 
                _insert_clip(track, copy_clip, self.out_index,
                         self.out_clip_in, out_clip.clip_out)
                self.removed_clips.pop(-1) # Front half of out clip
        except:
            pass
    
    # Put back old clips
    for i in range(0, len(self.removed_clips)):
        clip = self.removed_clips[i]
        _insert_clip(self.track, clip, self.in_index + i, clip.clip_in,
                     clip.clip_out)

def _sync_over_redo(self):
    # Cut at in point if not already on cut
    track = self.track
    in_clip_in, in_clip_out = _overwrite_cut_track(track, self.frame)
    self.in_clip_out = in_clip_out # out frame of the clip *previous* to overwritten clip after cut
    self.over_out = self.frame + self.clip_out - self.clip_in + 1 # +1 out frame incl.
    
    # If out point in track area we need to cut out point too
    if track.get_length() > self.over_out:
        out_clip_in, out_clip_out = _overwrite_cut_track(track, self.over_out)
        self.out_clip_in = out_clip_in
    else:
        self.out_clip_in = -1

    # Splice out clips in overwrite range
    self.removed_clips = []
    self.in_index = track.get_clip_index_at(self.frame)
    self.out_index = track.get_clip_index_at(self.over_out)
    for i in range(self.in_index, self.out_index):
        removed_clip = _remove_clip(track, self.in_index)
        self.removed_clips.append(removed_clip)

#------------------------------------- GAP APPEND
#"track","clip","clip_in","clip_out","frame"
def gap_append_action(data):
    action = EditAction(_gap_append_undo, _gap_append_redo, data)
    return action

def _gap_append_undo(self):
    pass

def _gap_append_redo(self):
    pass
        
#----------------- TWO_ROLL_TRIM
# "track","index","from_clip","to_clip","delta","edit_done_callback"
# "cut_frame"
def tworoll_trim_action(data):
    action = EditAction(_tworoll_trim_undo,_tworoll_trim_redo, data)
    action.exit_active_trimmode_on_edit = False
    action.update_hidden_track_blank = False
    return action

def _tworoll_trim_undo(self):
    _remove_clip(self.track, self.index)
    _remove_clip(self.track, self.index - 1)
    if self.non_edit_side_blank == False:
        _insert_clip(self.track, self.from_clip, self.index - 1, \
                     self.from_clip.clip_in, \
                     self.from_clip.clip_out - self.delta)
        _insert_clip(self.track, self.to_clip, self.index, \
                     self.to_clip.clip_in - self.delta, \
                     self.to_clip.clip_out )
    elif self.to_clip.is_blanck_clip:
        _insert_clip(self.track, self.from_clip, self.index - 1, \
                     self.from_clip.clip_in, \
                     self.from_clip.clip_out - self.delta)
        _insert_blank(self.track, self.index, self.to_length)
    else: # from clip is blank
        _insert_blank(self.track, self.index - 1, self.from_length)
        _insert_clip(self.track, self.to_clip, self.index, \
                     self.to_clip.clip_in - self.delta, \
                     self.to_clip.clip_out )
    
def _tworoll_trim_redo(self):
    _remove_clip(self.track, self.index)
    _remove_clip(self.track, self.index - 1)
    if self.non_edit_side_blank == False:
        _insert_clip(self.track, self.from_clip, self.index - 1, \
                     self.from_clip.clip_in, \
                     self.from_clip.clip_out + self.delta)
        _insert_clip(self.track, self.to_clip, self.index, \
                     self.to_clip.clip_in + self.delta, \
                     self.to_clip.clip_out )
    elif self.to_clip.is_blanck_clip:
        _insert_clip(self.track, self.from_clip, self.index - 1, \
                     self.from_clip.clip_in, \
                     self.from_clip.clip_out + self.delta)
        self.to_length = self.to_clip.clip_out - self.to_clip.clip_in + 1 # + 1 out incl
        _insert_blank(self.track, self.index, self.to_length - self.delta)
    else: # from clip is blank
        self.from_length = self.from_clip.clip_out - self.from_clip.clip_in + 1  # + 1 out incl
        _insert_blank(self.track, self.index - 1, self.from_length + self.delta )
        _insert_clip(self.track, self.to_clip, self.index, \
                     self.to_clip.clip_in + self.delta, \
                     self.to_clip.clip_out )

    if self.first_do == True:
        self.first_do = False
        self.edit_done_callback(True, self.cut_frame, self.delta, self.track, self.to_side_being_edited)

#----------------- SLIDE_TRIM
# "track","clip","delta","index","first_do","first_do_callback","start_frame_being_viewed"
def slide_trim_action(data):

    action = EditAction(_slide_trim_undo,_slide_trim_redo, data)
    action.exit_active_trimmode_on_edit = False
    action.update_hidden_track_blank = False
    return action

def _slide_trim_undo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in - self.delta, self.clip.clip_out - self.delta)

def _slide_trim_redo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in + self.delta, self.clip.clip_out + self.delta)

    # Reinit one roll trim 
    if self.first_do == True:
        self.first_do = False
        self.first_do_callback(self.track, self.clip, self.index, self.start_frame_being_viewed)

#-------------------- INSERT MOVE
# "track","insert_index","selected_range_in","selected_range_out"
# "move_edit_done_func"
# Splices out clips in range and splices them in at given index
def insert_move_action(data):
    action = EditAction(_insert_move_undo,_insert_move_redo, data)
    return action

def _insert_move_undo(self):    
    # remove clips
    for i in self.clips:
        _remove_clip(self.track, self.real_insert_index)

    # insert clips
    for i in range(0, len(self.clips)):
        clip = self.clips[i]
        _insert_clip(self.track, clip, self.selected_range_in + i, \
                     clip.clip_in, clip.clip_out )

    self.move_edit_done_func(self.clips)

def _insert_move_redo(self):
    self.clips = []

    self.real_insert_index = self.insert_index
    clips_length = self.selected_range_out - self.selected_range_in + 1

    # if insert after range it is different when clips removed
    if self.real_insert_index > self.selected_range_out:
        self.real_insert_index -= clips_length
    
    # remove and save clips
    for i in range(0, clips_length):
        removed_clip = _remove_clip(self.track, self.selected_range_in)
        self.clips.append(removed_clip)
    
    # insert clips
    for i in range(0, clips_length):
        clip = self.clips[i]
        _insert_clip(self.track, clip, self.real_insert_index + i, \
                     clip.clip_in, clip.clip_out )

    self.move_edit_done_func(self.clips)

# --------------------------------------- INSERT MULTIPLE
# "track","clips","index"
def insert_multiple_action(data):
    action = EditAction(_insert_multiple_undo, _insert_multiple_redo, data)
    return action

def _insert_multiple_undo(self):
    for i in range(0, len(self.clips)):
        _remove_clip(self.track, self.index)

def _insert_multiple_redo(self):
    for i in range(0, len(self.clips)):
        add_clip = self.clips[i]
        index = self.index + i
        if isinstance(add_clip, int): # blanks, are these represented as int's
            _insert_blank(self.track, index, add_clip)
        else: # media clips
            _insert_clip(self.track, add_clip, index, add_clip.clip_in, add_clip.clip_out)

# --------------------------------------- INSERT MULTIPLE AFTER TRACK END
# "track","clips","blank_length"
def insert_multiple_after_end_action(data):
    action = EditAction(_insert_multiple_after_end_undo, _insert_multiple_after_end_redo, data)
    return action

def _insert_multiple_after_end_undo(self):
    for i in range(0, len(self.clips)):
        _remove_clip(self.track, self.index)

    _remove_clip(self.track, self.index)
        
def _insert_multiple_after_end_redo(self):
    self.index = len(self.track.clips)
    _insert_blank(self.track, self.index, self.blank_length)
    
    for i in range(0, len(self.clips)):
        add_clip = self.clips[i]
        index = self.index + i + 1
        if isinstance(add_clip, int): # blanks, these are represented as int's
            _insert_blank(self.track, index, add_clip)
        else: # media clips
            _insert_clip(self.track, add_clip, index, add_clip.clip_in, add_clip.clip_out)

# --------------------------------------- INSERT MULTIPLE ON BLANK
# "track","clips","index","blank_cut_frame"
def insert_multiple_on_blank_action(data):
    action = EditAction(_insert_multiple_on_blank_undo, _insert_multiple_on_blank_redo, data)
    return action

def _insert_multiple_on_blank_undo(self):
    for i in range(0, len(self.clips)):
        _remove_clip(self.track, self.index + 1)

    # Remove cut blank halves
    _remove_clip(self.track, self.index)
    _remove_clip(self.track, self.index)

    _insert_blank(self.track, self.index, self.orig_blank_length)
        
def _insert_multiple_on_blank_redo(self):
    blank_clip = self.track.clips[self.index]
    self.orig_blank_length = blank_clip.clip_out - blank_clip.clip_in
    _cut_blank(self.track, self.index, self.blank_cut_frame, blank_clip)
    
    for i in range(0, len(self.clips)):
        add_clip = self.clips[i]
        index = self.index + i + 1
        if isinstance(add_clip, int): # blanks, these are represented as int's
            _insert_blank(self.track, index, add_clip)
        else: # media clips
            _insert_clip(self.track, add_clip, index, add_clip.clip_in, add_clip.clip_out)
            
#-------------------- MULTITRACK INSERT MOVE
# "track","to_track","insert_index","selected_range_in","selected_range_out"
# "move_edit_done_func"
# Splices out clips in range and splices them in at given index
def multitrack_insert_move_action(data):
    action = EditAction(_multitrack_insert_move_undo,_multitrack_insert_move_redo, data)
    action.clear_effects_editor_for_multitrack_edit = True  
    return action

def _multitrack_insert_move_undo(self):    
    # remove clips
    for i in self.clips:
        _remove_clip(self.to_track, self.insert_index)

    # insert clips
    for i in range(0, len(self.clips)):
        clip = self.clips[i]
        _insert_clip(self.track, clip, self.selected_range_in + i, \
                     clip.clip_in, clip.clip_out )

    self.move_edit_done_func(self.clips)

def _multitrack_insert_move_redo(self):
    self.clips = []

    clips_length = self.selected_range_out - self.selected_range_in + 1
    
    # remove clips
    for i in range(0, clips_length):
        removed_clip = _remove_clip(self.track, self.selected_range_in)
        self.clips.append(removed_clip)
    
    # insert clips
    for i in range(0, clips_length):
        clip = self.clips[i]
        _insert_clip(self.to_track, clip, self.insert_index + i, \
                     clip.clip_in, clip.clip_out )

    self.move_edit_done_func(self.clips)
    

#----------------- OVERWRITE MOVE
# "track","over_in","over_out","selected_range_in"
# "selected_range_out","move_edit_done_func"
# Lifts clips from track and overwrites part of track with them
def overwrite_move_action(data):
    action = EditAction(_overwrite_move_undo, _overwrite_move_redo, data)
    return action

def _overwrite_move_undo(self):
    track = self.track
        
    # Remove moved clips
    moved_clips_count = self.selected_range_out - self.selected_range_in + 1 # + 1 == out inclusive
    moved_index = track.get_clip_index_at(self.over_in)
    for i in range(0, moved_clips_count):
        _remove_clip(track, moved_index)
        
    # Fix in clip and remove cut created clip if in was cut
    if self.in_clip_out != -1:
        _overwrite_restore_in(track, moved_index, self)

    # Fix out clip and remove cut created clip if out was cut
    if self.out_clip_in != -1:
        _overwrite_restore_out(track, moved_index, self)

    # Put back old clips
    for i in range(0, len(self.removed_clips)):
        clip = self.removed_clips[i]
        _insert_clip(track, clip, moved_index + i, clip.clip_in,
                     clip.clip_out)
    
    # Remove blank from lifted clip
    # if moved clip/s were last in track, the clip were trying to remove
    # has already been removed so this will fail
    try:
        _remove_clip(track, self.selected_range_in)
    except:
        pass

    # Put back lifted clips
    for i in range(0, len(self.moved_clips)):
        clip = self.moved_clips[i]
        _insert_clip(track, clip, self.selected_range_in + i, clip.clip_in,
                     clip.clip_out)

def _overwrite_move_redo(self):
    self.moved_clips = []
    track = self.track
    
    # Lift moved clips and insert blank in their place
    for i in range(self.selected_range_in, self.selected_range_out + 1): # + 1 == out inclusive
        removed_clip = _remove_clip(track, self.selected_range_in)
        self.moved_clips.append(removed_clip)

    removed_length = self.over_out - self.over_in
    _insert_blank(track, self.selected_range_in, removed_length)

    # Find out if overwrite starts after or on track end and pad track with blank if so.
    if self.over_in >= track.get_length():
        self.starts_after_end = True
        gap = self.over_out - track.get_length()
        _insert_blank(track, len(track.clips), gap)
    else:
        self.starts_after_end = False
    
    # Cut at in point if not already on cut
    clip_in, clip_out = _overwrite_cut_track(track, self.over_in)
    self.in_clip_out = clip_out

    # Cut at out point if not already on cut and out point inside track length
    _overwrite_cut_range_out(track, self)
    
    # Splice out clips in overwrite range
    self.removed_clips = []
    in_index = track.get_clip_index_at(self.over_in)
    out_index = track.get_clip_index_at(self.over_out)

    for i in range(in_index, out_index):
        removed_clip = _remove_clip(track, in_index)
        self.removed_clips.append(removed_clip)

    # Insert overwrite clips
    for i in range(0, len(self.moved_clips)):
        clip = self.moved_clips[i]
        _insert_clip(track, clip, in_index + i, clip.clip_in, clip.clip_out)

    # HACK, see EditAction for details
    self.turn_on_stop_for_edit = True


#----------------- BOX OVERWRITE MOVE
# "box_selection_data","delta"
# Lifts clips from track and overwrites part of track with them for multiple tracks
# Move  compositors contained by selection too.
def box_overwrite_move_action(data):
    action = EditAction(_box_overwrite_move_undo, _box_overwrite_move_redo, data)
    action.turn_on_stop_for_edit = True
    return action

def _box_overwrite_move_undo(self):
    
    # Do track move edits
    for move_data in self.track_moves:
        action_object = DummyOverWriteMove(move_data)

        _overwrite_move_undo(action_object)

    # Move compositors
    for comp in self.box_selection_data.selected_compositors:
        comp.move(-self.delta)


# This exists to avoid hitting object being mapping proxy when doing __dict__.update
class DummyOverWriteMove:
    def __init__(self, move_data):
        # Grabs data as object members.
        self.__dict__.update(move_data)


def _box_overwrite_move_redo(self):
    # Create data for track overwrite moves
    if not hasattr(self, "track_moves"):
        self.track_moves = []
        for track_selection in self.box_selection_data.track_selections:
            if track_selection.range_frame_in != -1:
                track_move_data = {"track":current_sequence().tracks[track_selection.track_id],
                                    "over_in":track_selection.range_frame_in + self.delta,
                                    "over_out":track_selection.range_frame_out + self.delta,
                                    "selected_range_in":track_selection.selected_range_in,
                                    "selected_range_out":track_selection.selected_range_out,
                                    "move_edit_done_func":None}

                self.track_moves.append(track_move_data)

    else:
        # This may not be necessary...but its going in to make sure move_data is always same
        for move_data in self.track_moves:
            move_data.pop("removed_clips")

    # Do track move edits
    for move_data in self.track_moves:
        action_object = utils.EmptyClass()
        action_object.__dict__.update(move_data)

        _overwrite_move_redo(action_object)
        
        # Copy data created in _overwrite_move_redo() that is needed in _overwrite_move_undo
        move_data.update(action_object.__dict__)
                
    # Move compositors
    for comp in self.box_selection_data.selected_compositors:
        comp.move(self.delta)


#----------------- BOX SPLICE OUT
# "box_selection_data"
def box_splice_out_action(data):
    action = EditAction(_box_splice_out_undo, _box_splice_out_redo, data)
    action.turn_on_stop_for_edit = True
    return action

def _box_splice_out_undo(self):
    # Do track splice edits
    for splice_data in self.track_splices:
        for clip in splice_data["removed_clips"]:
            _insert_clip(splice_data["track"], clip, splice_data["selected_range_in"],
                         clip.clip_in, clip.clip_out)

def _box_splice_out_redo(self):
    # Create data for track splice outs
    if not hasattr(self, "track_splices"):
        self.track_splices = []
        for track_selection in self.box_selection_data.track_selections:
            if track_selection.range_frame_in != -1:
                track_splice_data = {"track":current_sequence().tracks[track_selection.track_id],
                                    "selected_range_in":track_selection.selected_range_in,
                                    "selected_range_out":track_selection.selected_range_out,
                                    "removed_clips":[]}

                self.track_splices.append(track_splice_data)

    # Do track splice edits
    for splice_data in self.track_splices:
        range_length = splice_data["selected_range_out"] - splice_data["selected_range_in"] + 1
        splice_data["removed_clips"] = []
        for i in range(splice_data["selected_range_in"], splice_data["selected_range_in"] + range_length):
            clip = _remove_clip(splice_data["track"], splice_data["selected_range_in"])
            splice_data["removed_clips"].append(clip)

#----------------- BOX LIFT OUT
# "box_selection_data"
def box_lift_action(data):
    action = EditAction(_box_lift_undo, _box_lift_redo, data)
    action.turn_on_stop_for_edit = True
    return action

def _box_lift_undo(self):
    # Do track splice edits
    for splice_data in self.track_splices:
        _remove_clip(splice_data["track"], splice_data["selected_range_in"])
        for clip in splice_data["removed_clips"]:
            _insert_clip(splice_data["track"], clip, splice_data["selected_range_in"],
                         clip.clip_in, clip.clip_out)

def _box_lift_redo(self):
    # Create data for track splice outs
    if not hasattr(self, "track_splices"):
        self.track_splices = []
        for track_selection in self.box_selection_data.track_selections:
            if track_selection.range_frame_in != -1:
                track_splice_data = {"track":current_sequence().tracks[track_selection.track_id],
                                    "selected_range_in":track_selection.selected_range_in,
                                    "selected_range_out":track_selection.selected_range_out,
                                    "removed_clips":[]}

                self.track_splices.append(track_splice_data)

    # Do track splice edits
    for splice_data in self.track_splices:
        blank_length = 0
        range_length = splice_data["selected_range_out"] - splice_data["selected_range_in"] + 1
        splice_data["removed_clips"] = []
        for i in range(splice_data["selected_range_in"], splice_data["selected_range_in"] + range_length):
            clip = _remove_clip(splice_data["track"], splice_data["selected_range_in"])
            splice_data["removed_clips"].append(clip)
            blank_length += clip.clip_out - clip.clip_in + 1
        _insert_blank(splice_data["track"], splice_data["selected_range_in"], blank_length)


#----------------- MULTITRACK OVERWRITE MOVE
# "track","to_track","over_in","over_out","selected_range_in"
# "selected_range_out","move_edit_done_func"
# Lifts clips from track and overwrites part of track with them
def multitrack_overwrite_move_action(data):
    action = EditAction(_multitrack_overwrite_move_undo, _multitrack_overwrite_move_redo, data)
    action.clear_effects_editor_for_multitrack_edit = True
    return action

def _multitrack_overwrite_move_undo(self):    
    track = self.track
    to_track = self.to_track

    # Remove moved clips
    moved_clips_count = self.selected_range_out - self.selected_range_in + 1 # + 1 == out inclusive
    moved_index = to_track.get_clip_index_at(self.over_in)
    for i in range(0, moved_clips_count):
        _remove_clip(to_track, moved_index)

    # Fix in clip and remove cut created clip if in was cut
    if self.in_clip_out != -1:
        _overwrite_restore_in(to_track, moved_index, self)

    # Fix out clip and remove cut created clip if out was cut
    if self.out_clip_in != -1:
        _overwrite_restore_out(to_track, moved_index, self)

    # Put back old clips
    for i in range(0, len(self.removed_clips)):
        clip = self.removed_clips[i]
        _insert_clip(to_track, clip, moved_index + i, clip.clip_in,
                     clip.clip_out)

    # Remove blank from lifted clip
    # if moved clip/s were last in track, the clip were trying to remove
    # has already been removed so this will fail
    try:
        _remove_clip(track, self.selected_range_in)
    except:
        pass

    # Put back lifted clips
    for i in range(0, len(self.moved_clips)):
        clip = self.moved_clips[i]
        _insert_clip(track, clip, self.selected_range_in + i, clip.clip_in,
                     clip.clip_out)

def _multitrack_overwrite_move_redo(self):
    self.moved_clips = []
    track = self.track
    to_track = self.to_track

    # Lift moved clips and insert blank
    for i in range(self.selected_range_in, self.selected_range_out + 1): # + 1 == out inclusive
        removed_clip = _remove_clip(track, self.selected_range_in) # THIS LINE BUGS SOMETIMES FIND OUT WHY
        self.moved_clips.append(removed_clip)

    removed_length = self.over_out - self.over_in
    _insert_blank(track, self.selected_range_in, removed_length)

    # Find out if overwrite starts after track end and pad track with blank if so
    if self.over_in >= to_track.get_length():
        self.starts_after_end = True
        gap = self.over_out - to_track.get_length()
        _insert_blank(to_track, len(to_track.clips), gap)
    else:
        self.starts_after_end = False

    # Cut at in point if not already on cut
    clip_in, clip_out = _overwrite_cut_track(to_track, self.over_in)
    self.in_clip_out = clip_out

    # Cut at out point if not already on cut
    _overwrite_cut_range_out(to_track, self)

    # Splice out clips in overwrite range
    self.removed_clips = []
    in_index = to_track.get_clip_index_at(self.over_in)
    out_index = to_track.get_clip_index_at(self.over_out)

    for i in range(in_index, out_index):
        removed_clip = _remove_clip(to_track, in_index)
        self.removed_clips.append(removed_clip)

    # Insert overwrite clips
    for i in range(0, len(self.moved_clips)):
        clip = self.moved_clips[i]
        _insert_clip(to_track, clip, in_index + i, clip.clip_in, clip.clip_out)
    
    # HACK, see EditAction for details
    self.turn_on_stop_for_edit = True

#-------------------------------------------- MULTI MOVE
# "multi_data", "edit_delta"
# self.multi_data is multimovemode.MultimoveData
def multi_move_action(data):
    action = EditAction(_multi_move_undo, _multi_move_redo, data)
    return action

def _multi_move_undo(self):
    track_moved = self.multi_data.track_affected    
    tracks = current_sequence().tracks
    for i in range(1, len(tracks) - 1):
        if not track_moved[i - 1]:
            continue
        track = tracks[i]
        edit_op = self.multi_data.track_edit_ops[i - 1]        
        trim_blank_index = self.multi_data.trim_blank_indexes[i - 1]
        
        if edit_op == appconsts.MULTI_NOOP:
            continue
        elif edit_op == appconsts.MULTI_TRIM:
            blank_length = track.clips[trim_blank_index].clip_length()
            _remove_clip(track, trim_blank_index) 
            _insert_blank(track, trim_blank_index, blank_length - self.edit_delta)
        elif edit_op == appconsts.MULTI_ADD_TRIM:
            _remove_clip(track, trim_blank_index) 
        elif edit_op == appconsts.MULTI_TRIM_REMOVE:
            if self.edit_delta != -self.multi_data.max_backwards:
                _remove_clip(track, trim_blank_index) 
                
            _insert_blank(track, trim_blank_index, self.orig_length)

    tracks_compositors = _get_tracks_compositors_list()
    for i in range(1, len(tracks) - 1):
        if not track_moved[i - 1]:
            continue
        track_comp = tracks_compositors[i - 1]
        for comp in track_comp:
            if comp.clip_in >= self.multi_data.first_moved_frame + self.edit_delta:
                comp.move(-self.edit_delta)

def _multi_move_redo(self):
    tracks = current_sequence().tracks
    track_moved = self.multi_data.track_affected

    # Move clips          
    for i in range(1, len(tracks) - 1):
        if not track_moved[i - 1]:
            continue
        track = tracks[i]
        edit_op = self.multi_data.track_edit_ops[i - 1]        
        trim_blank_index = self.multi_data.trim_blank_indexes[i - 1]
        
        if edit_op == appconsts.MULTI_NOOP:
            continue
        elif edit_op == appconsts.MULTI_TRIM:
            blank_length = track.clips[trim_blank_index].clip_length()
            _remove_clip(track, trim_blank_index) 
            _insert_blank(track, trim_blank_index, blank_length + self.edit_delta)
        elif edit_op == appconsts.MULTI_ADD_TRIM:
            _insert_blank(track, trim_blank_index, self.edit_delta)
        elif edit_op == appconsts.MULTI_TRIM_REMOVE:
            self.orig_length = track.clips[trim_blank_index].clip_length()
            _remove_clip(track, trim_blank_index) 
            if self.edit_delta != -self.multi_data.max_backwards:
                _insert_blank(track, trim_blank_index, self.orig_length + self.edit_delta)

    # Move compositors
    tracks_compositors = _get_tracks_compositors_list()
    for i in range(1, len(tracks) - 1):
        if not track_moved[i - 1]:
            continue
        track_comp = tracks_compositors[i - 1]
        for comp in track_comp:
            if comp.clip_in >= self.multi_data.first_moved_frame:
                comp.move(self.edit_delta)

def _get_tracks_compositors_list():
    tracks_list = []
    tracks = current_sequence().tracks
    compositors = current_sequence().compositors
    for track_index in range(1, len(tracks) - 1):
        track_compositors = []
        for j in range(0, len(compositors)):
            comp = compositors[j]
            if comp.transition.b_track == track_index:
                track_compositors.append(comp)
        tracks_list.append(track_compositors)
    
    return tracks_list

#-------------------------------------------- RIPPLE TRIM END
# "track","clip","index","edit_delta","first_do","multi_data"
# self.multi_data is trimmodes.RippleData
def ripple_trim_end_action(data):
    action = EditAction(_ripple_trim_end_undo, _ripple_trim_end_redo, data)
    action.exit_active_trimmode_on_edit = False
    action.update_hidden_track_blank = False
    return action

def _ripple_trim_end_undo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in, self.clip.clip_out - self.edit_delta)
    
    _ripple_trim_blanks_undo(self)
        
def _ripple_trim_end_redo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in, self.clip.clip_out + self.edit_delta)

    _ripple_trim_blanks_redo(self)
     
    # Reinit one roll trim
    if self.first_do == True:
        self.first_do = False
        self.undo_done_callback(self.track, self.index + 1, False)

#-------------------------------------------- RIPPLE TRIM START
# "track","clip","index","edit_delta","first_do","multi_data"
# self.multi_data is trimmodes.RippleData
def ripple_trim_start_action(data):
    action = EditAction(_ripple_trim_start_undo,_ripple_trim_start_redo, data)
    action.exit_active_trimmode_on_edit = False
    action.update_hidden_track_blank = False
    return action

def _ripple_trim_start_undo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in - self.edit_delta, self.clip.clip_out)

    _ripple_trim_blanks_undo(self, True)

def _ripple_trim_start_redo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in + self.edit_delta, self.clip.clip_out)

    _ripple_trim_blanks_redo(self, True)
    
    # Reinit one roll trim, when used with clip start drag this is not needed
    if  hasattr(self, "first_do") and self.first_do == True:
        self.first_do = False
        self.undo_done_callback(self.track, self.index, True)

#------------------ RIPPLE TRIM LAST CLIP END
# "track","clip","index","edit_delta","first_do","multi_data"
# self.multi_data is trimmodes.RippleData
def ripple_trim_last_clip_end_action(data): 
    action = EditAction(_ripple_trim_last_clip_end_undo,_ripple_trim_last_clip_end_redo, data)
    action.exit_active_trimmode_on_edit = False
    action.update_hidden_track_blank = False
    return action

def _ripple_trim_last_clip_end_undo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in, self.clip.clip_out - self.edit_delta)

    _ripple_trim_blanks_undo(self)

def _ripple_trim_last_clip_end_redo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in, self.clip.clip_out + self.edit_delta)

    _ripple_trim_blanks_redo(self)
    
    # Reinit one roll trim for continued trim mode, whenused with clip end drag this is not needed
    if hasattr(self, "first_do") and self.first_do == True:
        self.first_do = False
        self.undo_done_callback(self.track)
        
# ----------------------------- RIPPLE TRIM BLANK UPDATE METHODS
def _ripple_trim_blanks_undo(self, reverse_comp_delta=False):
    track_moved = self.multi_data.track_affected    
    tracks = current_sequence().tracks

    applied_delta = self.edit_delta
        
    for i in range(1, len(tracks) - 1):
        if not track_moved[i - 1]:
            continue
        if self.track.id == i:
            continue

        track = tracks[i]
        edit_op = self.multi_data.track_edit_ops[i - 1]        
        trim_blank_index = self.multi_data.trim_blank_indexes[i - 1]
        
        if edit_op == appconsts.MULTI_NOOP:
            continue
        elif edit_op == appconsts.MULTI_TRIM:
            blank_length = track.clips[trim_blank_index].clip_length()
            _remove_clip(track, trim_blank_index) 
            _insert_blank(track, trim_blank_index, blank_length - applied_delta)
        elif edit_op == appconsts.MULTI_ADD_TRIM:
            _remove_clip(track, trim_blank_index) 
        elif edit_op == appconsts.MULTI_TRIM_REMOVE:
            if reverse_comp_delta:
                if -self.edit_delta != -self.multi_data.max_backwards:
                    _remove_clip(track, trim_blank_index) 
            else:
                if self.edit_delta != -self.multi_data.max_backwards:
                    _remove_clip(track, trim_blank_index) 
                
            _insert_blank(track, trim_blank_index, self.orig_length)

    if reverse_comp_delta:
        applied_delta = -applied_delta
    _ripple_trim_compositors_move(self, -applied_delta)

def _ripple_trim_blanks_redo(self, reverse_delta=False):
    tracks = current_sequence().tracks
    track_moved = self.multi_data.track_affected
    
    applied_delta = self.edit_delta
    if reverse_delta:
        applied_delta = -applied_delta
               
    for i in range(1, len(tracks) - 1):
        if not track_moved[i - 1]:
            continue
        if self.track.id == i:
            continue
            
        track = tracks[i]
        edit_op = self.multi_data.track_edit_ops[i - 1]        
        trim_blank_index = self.multi_data.trim_blank_indexes[i - 1]
        
        if edit_op == appconsts.MULTI_NOOP: # no blank clip on this track is not changed
            continue
        elif edit_op == appconsts.MULTI_TRIM: #longer available blank than max_backwards, length is changed
            blank_length = track.clips[trim_blank_index].clip_length()
            _remove_clip(track, trim_blank_index) 
            _insert_blank(track, trim_blank_index, blank_length + applied_delta)
        elif edit_op == appconsts.MULTI_ADD_TRIM:# no blank to trim available, only possibnle edit is to add blank
            _insert_blank(track, trim_blank_index, applied_delta)
        elif edit_op == appconsts.MULTI_TRIM_REMOVE: # blank is trimmed if not max length triom, if so, blank is removed
            self.orig_length = track.clips[trim_blank_index].clip_length()
            _remove_clip(track, trim_blank_index)
            if applied_delta != -self.multi_data.max_backwards:
                _insert_blank(track, trim_blank_index, self.orig_length + applied_delta)

    _ripple_trim_compositors_move(self, applied_delta)

def _ripple_trim_compositors_move(self, delta):
    comp_ids = self.multi_data.moved_compositors_destroy_ids
    tracks_compositors = _get_tracks_compositors_list()
    track_moved = self.multi_data.track_affected

    for i in range(1, len(current_sequence().tracks) - 1):
        if not track_moved[i - 1]:
            continue
        track_comps = tracks_compositors[i - 1]
        for comp in track_comps:
            if comp.destroy_id in comp_ids:
                comp.move(delta)


#------------------ TRIM CLIP START
# "track","clip","index","delta","first_do"
# "undo_done_callback" <- THIS IS REALLY BADLY NAMED, IT SHOULD BE FIRST DO CALLBACK
# Trims start of clip
def trim_start_action(data):
    action = EditAction(_trim_start_undo,_trim_start_redo, data)
    action.exit_active_trimmode_on_edit = False
    action.update_hidden_track_blank = False
    return action

def _trim_start_undo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in - self.delta, self.clip.clip_out)

def _trim_start_redo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in + self.delta, self.clip.clip_out)

    # Reinit one roll trim, when used with clip start drag this is not needed
    if  hasattr(self, "first_do") and self.first_do == True:
        self.first_do = False
        self.undo_done_callback(self.track, self.index, True)

#------------------ TRIM CLIP END
# "track","clip","index","delta", "first_do"
# "undo_done_callback" <- THIS IS REALLY BADLY NAMED, IT SHOULD BE FIRST DO CALLBACK
# Trims end of clip
def trim_end_action(data):
    action = EditAction(_trim_end_undo,_trim_end_redo, data)
    action.exit_active_trimmode_on_edit = False
    action.update_hidden_track_blank = False
    return action

def _trim_end_undo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in, self.clip.clip_out - self.delta)
    
def _trim_end_redo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in, self.clip.clip_out + self.delta)

    # Reinit one roll trim
    if self.first_do == True:
        self.first_do = False
        self.undo_done_callback(self.track, self.index + 1, False)

#------------------ TRIM LAST CLIP END
# "track","clip","index","delta", "first_do"
# "undo_done_callback" <- THIS IS BADLY NAMED, IT SHOULD BE FIRST DO CALLBACK
def trim_last_clip_end_action(data): 
    action = EditAction(_trim_last_clip_end_undo,_trim_last_clip_end_redo, data)
    action.exit_active_trimmode_on_edit = False
    return action

def _trim_last_clip_end_undo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in, self.clip.clip_out - self.delta)

def _trim_last_clip_end_redo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in, self.clip.clip_out + self.delta)

    # Reinit one roll trim for continued trim mode
    if hasattr(self, "first_do") and self.first_do == True:
        self.first_do = False
        self.undo_done_callback(self.track)

#------------------ TRIM IMAGE BEYOND CURRENT LENGTH
def trim_image_end_beyond_max_length_action(data):
    action = EditAction(_trim_image_end_beyond_max_length_undo,_trim_image_end_beyond_max_length_redo, data)
    action.exit_active_trimmode_on_edit = False
    return action

def _trim_image_end_beyond_max_length_undo(self):
    _remove_clip(self.track, self.index)
    self.clip.set("length", int(self.old_length))
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in, self.clip.clip_out - self.delta)

def _trim_image_end_beyond_max_length_redo(self):
    self.old_length = self.clip.get_length()
    new_length = self.clip.clip_out + self.delta
    _remove_clip(self.track, self.index)
    self.clip.set("length", int(new_length))
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in, self.clip.clip_out + self.delta)

#------------------ SET CLIP LENGTH
# "track","clip","index","length"
# Trims end of clip
def set_clip_length_action(data):
    action = EditAction(_set_clip_length_undo,_set_clip_length_redo, data)
    return action

def _set_clip_length_undo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in, self.orig_clip_out)
    
def _set_clip_length_redo(self):
    self.orig_clip_out = self.clip.clip_out
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in,  self.clip.clip_in + self.length - 1) # -1, out is inclusive and we're using length here

# ----------------------------------- CLIP END DRAG ON BLANK
# "track","index","clip","blank_clip_length","delta"
def clip_end_drag_on_blank_action(data):
    action = EditAction(_clip_end_drag_on_blank_undo, _clip_end_drag_on_blank_redo, data)
    return action

def _clip_end_drag_on_blank_undo(self):
    _remove_clip(self.track, self.index)
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in, self.orig_out)
    _insert_blank(self.track, self.index + 1, self.blank_clip_length)
    
def _clip_end_drag_on_blank_redo(self):
    _remove_clip(self.track, self.index)
    _remove_clip(self.track, self.index)
    self.orig_out = self.clip.clip_out
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in, self.clip.clip_out + self.delta)
    _insert_blank(self.track, self.index + 1, self.blank_clip_length - self.delta)

# ----------------------------------- CLIP END DRAG REPLACE BLANK
# "track","index","clip","blank_clip_length","delta"
def clip_end_drag_replace_blank_action(data):
    action = EditAction(_clip_end_drag_replace_blank_undo, _clip_end_drag_replace_blank_redo, data)
    return action

def _clip_end_drag_replace_blank_undo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in, self.orig_out)
    _insert_blank(self.track, self.index + 1, self.blank_clip_length)
    
def _clip_end_drag_replace_blank_redo(self):
    _remove_clip(self.track, self.index)
    _remove_clip(self.track, self.index)
    self.orig_out = self.clip.clip_out
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in, self.clip.clip_out + self.delta)

# ----------------------------------- CLIP START DRAG ON BLANK
# "track","index","clip","blank_clip_length","delta"
def clip_start_drag_on_blank_action(data):
    action = EditAction(_clip_start_drag_on_blank_undo, _clip_start_drag_on_blank_redo, data)
    return action

def _clip_start_drag_on_blank_undo(self):
    _remove_clip(self.track, self.index - 1)
    _remove_clip(self.track, self.index - 1)
    _insert_blank(self.track, self.index - 1, self.blank_clip_length)
    _insert_clip(self.track, self.clip, self.index,
                 self.orig_in, self.clip.clip_out)

def _clip_start_drag_on_blank_redo(self):
    _remove_clip(self.track, self.index - 1)
    _remove_clip(self.track, self.index - 1)
    self.orig_in = self.clip.clip_in
    _insert_blank(self.track, self.index - 1, self.blank_clip_length + self.delta)
    _insert_clip(self.track, self.clip, self.index,
                 self.clip.clip_in + self.delta, self.clip.clip_out)

# ----------------------------------- CLIP START DRAG REPLACE BLANK
# "track","index","clip","blank_clip_length","delta"
def clip_start_drag_replace_blank_action(data):
    action = EditAction(_clip_start_drag_replace_blank_undo, _clip_start_drag_replace_blank_redo, data)
    return action

def _clip_start_drag_replace_blank_undo(self):
    _remove_clip(self.track, self.index - 1)
    _insert_blank(self.track, self.index - 1, self.blank_clip_length)
    _insert_clip(self.track, self.clip, self.index,
                 self.orig_in, self.clip.clip_out)

def _clip_start_drag_replace_blank_redo(self):
    _remove_clip(self.track, self.index - 1)
    _remove_clip(self.track, self.index - 1)
    self.orig_in = self.clip.clip_in
    _insert_clip(self.track, self.clip, self.index - 1,
                 self.clip.clip_in + self.delta, self.clip.clip_out)
                 
#------------------- ADD FILTER
# "clip","filter_info","filter_edit_done_func"
# Adds filter to clip.
def add_filter_action(data):
    action = EditAction(_add_filter_undo,_add_filter_redo, data)
    return action

def _add_filter_undo(self):
    self.clip.detach(self.filter_object.mlt_filter)
    index = self.clip.filters.index(self.filter_object)
    self.clip.filters.pop(index)

    self.filter_edit_done_func(self.clip, len(self.clip.filters) - 1) # updates effect stack gui

def _add_filter_redo(self):
    try: # is redo, fails for first
        self.clip.attach(self.filter_object.mlt_filter)
        self.clip.filters.append(self.filter_object)
    except: # First do
        self.filter_object = current_sequence().create_filter(self.filter_info)
        self.filter_object.replace_values(self.clip)
        self.clip.attach(self.filter_object.mlt_filter)
        self.clip.filters.append(self.filter_object)
        
    self.filter_edit_done_func(self.clip, len(self.clip.filters) - 1) # updates effect stack gui

#------------------- ADD FILTER MULTI
# "clips","filter_info","filter_edit_done_func"
# Adds filter to clip.
def add_filter_multi_action(data):
    action = EditAction(_add_filter_multi_undo, _add_filter_multi_redo, data)
    return action

def _add_filter_multi_undo(self):
    blank_clips = 0
    for i in range(0, len(self.clips)):
        clip = self.clips[i]
        if clip.is_blanck_clip == True:
            blank_clips += 1
            continue
        filter_object = self.filter_objects[i - blank_clips] # there are less filters then clips if some of the clips are blanks
        clip.detach(filter_object.mlt_filter)
        index = clip.filters.index(filter_object)
        clip.filters.pop(index)

    self.filter_edit_done_func(self.clips) # updates effect stack gui

def _add_filter_multi_redo(self):
    blank_clips = 0
    for i in range(0, len(self.clips)):
        clip = self.clips[i]
        if clip.is_blanck_clip == True:
            blank_clips += 1
            continue
        try: # is redo, fails for first
            filter_object = self.filter_objects[i - blank_clips] # there are less filters then clips if some of the clips are blanks
            clip.attach(filter_object.mlt_filter)
            clip.filters.append(filter_object)
        except: # First do
            if not hasattr(self, "filter_objects"):
                self.filter_objects = []
            filter_object = current_sequence().create_filter(self.filter_info)
            filter_object.replace_values(clip)
            clip.attach(filter_object.mlt_filter)
            clip.filters.append(filter_object)
            self.filter_objects.append(filter_object)
    
    self.filter_edit_done_func(self.clips) # updates effect stack gui

#------------------- ADD TWO FILTERS
# NOTE: Using this requires that index_2 > index_1
# "clip","filter_info_1",filter_info_2","index_1","index_2","filter_edit_done_func"
# Adds filter to clip.
def add_two_filters_action(data):
    action = EditAction(_add_two_filters_undo, _add_two_filters_redo, data)
    return action

def _add_two_filters_undo(self):
    _detach_all(self.clip)
    
    self.clip.filters.pop(self.index_2)
    self.clip.filters.pop(self.index_1)
    
    _attach_all(self.clip)

    self.filter_edit_done_func(self.clip, len(self.clip.filters) - 1) # updates effect stack gui

def _add_two_filters_redo(self):
    _detach_all(self.clip)
    
    try: # is redo, fails for first because no new filters have been created
        self.clip.filters.insert(self.index_1, self.filter_object_1)
        self.clip.filters.insert(self.index_2, self.filter_object_2)
    except: # First do
        self.filter_object_1 = current_sequence().create_filter(self.filter_info_1)
        self.filter_object_2 = current_sequence().create_filter(self.filter_info_2)
        self.clip.filters.insert(self.index_1, self.filter_object_1)
        self.clip.filters.insert(self.index_2, self.filter_object_2)
        
    _attach_all(self.clip)
            
    self.filter_edit_done_func(self.clip, len(self.clip.filters) - 1) # updates effect stack gui


#------------------- ADD MULTIPART FILTER
# "clip","filter_info","filter_edit_done_func"
# Adds filter to clip.
def add_multipart_filter_action(data):
    action = EditAction(_add_multipart_filter_undo,_add_multipart_filter_redo, data)
    return action

def _add_multipart_filter_undo(self):
    self.filter_object.detach_all_mlt_filters(self.clip)
    index = self.clip.filters.index(self.filter_object)
    self.clip.filters.pop(index)

    self.filter_edit_done_func(self.clip, len(self.clip.filters) - 1) # updates effect stack

def _add_multipart_filter_redo(self):
    try: # if redo, fails for first
        self.filter_object.attach_filters(self.clip)
        self.clip.filters.append(self.filter_object)
    except: # First do
        self.filter_object = current_sequence().create_multipart_filter(self.filter_info, self.clip)
        self.filter_object.attach_all_mlt_filters(self.clip)
        self.clip.filters.append(self.filter_object)
        
    self.filter_edit_done_func(self.clip, len(self.clip.filters) - 1) # updates effect stack

#------------------- REMOVE FILTER
# "clip","index","filter_edit_done_func"
# Adds filter to clip.
def remove_filter_action(data):
    action = EditAction(_remove_filter_undo,_remove_filter_redo, data)
    return action

def _remove_filter_undo(self):
    _detach_all(self.clip)
    try:
        self.clip.filters.insert(self.index, self.filter_object)
    except:
        self.clip.filters.append(self.filter_object)

    _attach_all(self.clip)
        
    self.filter_edit_done_func(self.clip, self.index) # updates effect stack gui if needed

def _remove_filter_redo(self):
    _detach_all(self.clip)
    self.filter_object = self.clip.filters.pop(self.index)
    _attach_all(self.clip)

    self.filter_edit_done_func(self.clip, len(self.clip.filters) - 1)# updates effect stack gui

#------------------- REMOVE TWO FILTER
# "clip","index_1", "index_2","filter_edit_done_func"
# We need that index_2 > index_1
def remove_two_filters_action(data):
    action = EditAction(_remove_two_filters_undo, _remove_two_filters_redo, data)
    return action

def _remove_two_filters_undo(self):
    _detach_all(self.clip)
    
    try:
        self.clip.filters.insert(self.index_1, self.filter_object_1)
        self.clip.filters.insert(self.index_2, self.filter_object_2)
    except:
        self.clip.filters.append(self.filter_object)

    _attach_all(self.clip)
        
    self.filter_edit_done_func(self.clip, len(self.clip.filters) - 1) # updates effect stack gui if needed

def _remove_two_filters_redo(self):
    _detach_all(self.clip)
    
    self.filter_object_2 = self.clip.filters.pop(self.index_2)
    self.filter_object_1 = self.clip.filters.pop(self.index_1)
    
    _attach_all(self.clip)

    self.filter_edit_done_func(self.clip, len(self.clip.filters) - 1)# updates effect stack gui
    
#------------------- MOVE FILTER
# "clip",""insert_index","delete_index"","filter_edit_done_func"
# Moves filter in filter stack filter to clip.
def move_filter_action(data):
    action = EditAction(_move_filter_undo,_move_filter_redo, data)
    return action

def _move_filter_undo(self):
    _detach_all(self.clip)

    for i in range(0, len(self.filters_orig)):
        self.clip.filters.pop(0)

    for i in range(0, len(self.filters_orig)):
        self.clip.filters.append(self.filters_orig[i])

    """
    if self.delete_index < self.insert_index:
        active_index = self.delete_index
    else:
        active_index = self.delete_index - 1
    """

    _attach_all(self.clip)

    self.filter_edit_done_func(self.clip)

def _move_filter_redo(self):
    _detach_all(self.clip)
    
    # Copy filters in original order for undo
    self.filters_orig = []
    for i in range(0, len(self.clip.filters)):
        self.filters_orig.append(self.clip.filters[i])
       
    if self.delete_index < self.insert_index:
        # Moving up
        moved_filter = self.clip.filters[self.delete_index]
        _filter_move_insert(self.clip.filters, moved_filter, self.insert_index + 1)
        self.clip.filters.pop(self.delete_index)
    else:
        # Moving down
        moved_filter = self.clip.filters[self.delete_index]
        _filter_move_insert(self.clip.filters, moved_filter, self.insert_index)
        self.clip.filters.pop(self.delete_index + 1)
    
    _attach_all(self.clip)

    self.filter_edit_done_func(self.clip)
    
def _detach_all(clip):
    mltfilters.detach_all_filters(clip)

def _attach_all(clip):
    mltfilters.attach_all_filters(clip)

def _filter_move_insert(filters_list, f, insert_index):
    try:
        filters_list.insert(insert_index, f)
    except:
        filters_list.append(insert_index, f)
        
#------------------- REMOVE MULTIPLE FILTERS
# "clips"
# Adds filter to clip.
def remove_multiple_filters_action(data):
    action = EditAction(_remove_multiple_filters_undo,_remove_multiple_filters_redo, data)
    return action

def _remove_multiple_filters_undo(self):
    for clip, clip_filters in zip(self.clips, self.clip_filters):
        clip.filters = clip_filters
        _attach_all(clip)

def _remove_multiple_filters_redo(self):
    self.clip_filters = []
    for clip in self.clips:
        _detach_all(clip)
        self.clip_filters.append(clip.filters)
        clip.filters = []
        updater.clear_clip_from_editors(clip)

# -------------------------------------- CLONE FILTERS
# "clip","clone_source_clip"
def clone_filters_action(data):
    action = EditAction(_clone_filters_undo, _clone_filters_redo, data)
    return action

def _clone_filters_undo(self):
    _detach_all(self.clip)
    self.clip.filters = self.old_filters
    _attach_all(self.clip)
    
def _clone_filters_redo(self):
    if not hasattr(self, "clone_filters"):
        self.clone_filters = current_sequence().clone_filters(self.clone_source_clip)
        self.old_filters = self.clip.filters

    _detach_all(self.clip)
    self.clip.filters = self.clone_filters
    _attach_all(self.clip)

# -------------------------------------- PASTE FILTERS
# "clip","clone_source_clip"
def paste_filters_action(data):
    action = EditAction(_paste_filters_undo, _paste_filters_redo, data)
    action.force_effects_editor_update = True
    return action

def _paste_filters_undo(self):
    _detach_all(self.clip)
    self.clip.filters = self.old_filters
    _attach_all(self.clip)
    
def _paste_filters_redo(self):
    if not hasattr(self, "clone_filters"):
        candidate_filters = current_sequence().clone_filters(self.clone_source_clip)
        self.clone_filters = []
        for i in range(0, len(self.clone_source_clip.filters)):
            old_filter = self.clone_source_clip.filters[i]
            clone_filter = candidate_filters[i]
            if old_filter.active == True:
                self.clone_filters.append(clone_filter)
        self.old_filters = self.clip.filters

    _detach_all(self.clip)
    new_filters = self.old_filters + self.clone_filters
    self.clip.filters = new_filters
    _attach_all(self.clip)
    
# -------------------------------------- ADD COMPOSITOR ACTION
# "origin_clip_id",in_frame","out_frame","compositor_type","a_track","b_track", "clip"
def add_compositor_action(data):
    action = EditAction(_add_compositor_undo, _add_compositor_redo, data)
    action.first_do = True
    return action

def _add_compositor_undo(self):
    current_sequence().remove_compositor(self.compositor)
    current_sequence().restack_compositors()
    
    self.old_compositor = self.compositor # maintain compositor property values though full undo/redo sequence
    compositeeditor.maybe_clear_editor(self.compositor)
    self.compositor = None

def _add_compositor_redo(self):    
    self.compositor = current_sequence().create_compositor(self.compositor_type)
    if hasattr(self, "old_compositor"): # maintain compositor property values though full undo/redo sequence
        self.compositor.clone_properties(self.old_compositor)
    self.compositor.transition.set_tracks(self.a_track, self.b_track)
    self.compositor.set_in_and_out(self.in_frame, self.out_frame)
    self.compositor.origin_clip_id = self.origin_clip_id

    # Compositors are recreated continually in sequence.restack_compositors() and cannot be identified for undo/redo using object identity 
    # so these ids must be  preserved for all successive versions of a compositor
    if self.first_do == True:
        self.destroy_id = self.compositor.destroy_id
        self.first_do = False
    else:
        self.compositor.destroy_id = self.destroy_id

    current_sequence().add_compositor(self.compositor)
    current_sequence().restack_compositors()
    
    compositeeditor.set_compositor(self.compositor)

# -------------------------------------- DELETE COMPOSITOR ACTION
# "compositor"
def delete_compositor_action(data):
    action = EditAction(_delete_compositor_undo, _delete_compositor_redo, data)
    action.first_do = True
    return action

def _delete_compositor_undo(self):
    old_compositor = self.compositor 
    
    self.compositor = current_sequence().create_compositor(old_compositor.type_id)
    self.compositor.clone_properties(old_compositor)
    self.compositor.set_in_and_out(old_compositor.clip_in, old_compositor.clip_out)
    self.compositor.transition.set_tracks(old_compositor.transition.a_track, old_compositor.transition.b_track)

    current_sequence().add_compositor(self.compositor)
    current_sequence().restack_compositors()

    compositeeditor.set_compositor(self.compositor)

def _delete_compositor_redo(self):
    # Compositors are recreated continually in sequence.restack_compositors() and cannot be identified for undo/redo using object identity 
    # so these ids must be  preserved for all successive versions of a compositor.
    if self.first_do == True:
        self.destroy_id = self.compositor.destroy_id
        self.first_do = False
    else:
        self.compositor = current_sequence().get_compositor_for_destroy_id(self.destroy_id)
        
    current_sequence().remove_compositor(self.compositor)
    current_sequence().restack_compositors()
        
    compositeeditor.maybe_clear_editor(self.compositor)

#--------------------------------------------------- MOVE COMPOSITOR
# "compositor","clip_in","clip_out"
def move_compositor_action(data):
    action = EditAction(_move_compositor_undo, _move_compositor_redo, data)
    action.first_do = True
    return action  

def _move_compositor_undo(self):
    move_compositor = current_sequence().get_compositor_for_destroy_id(self.destroy_id)
    move_compositor.set_in_and_out(self.orig_in, self.orig_out)

    compositeeditor.set_compositor(self.compositor) # This is different to updating e.g filter kfeditors, those are done in EditAction._update_gui()

def _move_compositor_redo(self):
    # Compositors are recreated continually in sequence.restack_compositors() and cannot be identified for undo/redo using object identity 
    # so these ids must be  preserved for all successive versions of a compositor.
    if self.first_do == True:
        self.destroy_id = self.compositor.destroy_id
        self.orig_in = self.compositor.clip_in
        self.orig_out = self.compositor.clip_out
        self.first_do = False

    move_compositor = current_sequence().get_compositor_for_destroy_id(self.destroy_id)
    move_compositor.set_in_and_out(self.clip_in, self.clip_out)

    compositeeditor.set_compositor(self.compositor) # This is different to updating e.g filter kfeditors, those are done in EditAction._update_gui()

#----------------- AUDIO SPLICE
# "parent_clip", "audio_clip", "track", "to_track"
def audio_splice_action(data):
    action = EditAction(_audio_splice_undo, _audio_splice_redo, data)
    return action

def _audio_splice_undo(self):
    to_track = self.to_track

    # Remove add audio clip
    in_index = to_track.get_clip_index_at(self.over_in)
    _remove_clip(to_track, in_index)
        
    # Fix in clip and remove cut created clip if in was cut
    if self.in_clip_out != -1:
        in_clip = _remove_clip(to_track, in_index - 1)
        _insert_clip(to_track, in_clip, in_index - 1,
                     in_clip.clip_in, self.in_clip_out)
        self.removed_clips.pop(0)

    # Fix out clip and remove cut created clip if out was cut
    if self.out_clip_in != -1:
        # If moved clip/s were last in the track and were moved slightly 
        # forward and were still last in track after move
        # this leaves a trailing black that has been removed and this will fail
        try:
            out_clip = _remove_clip(to_track, in_index)
            if len(self.removed_clips) > 0: # If overwrite was done inside single clip everything is already in order
                _insert_clip(to_track, out_clip, in_index,
                         self.out_clip_in, out_clip.clip_out)
                self.removed_clips.pop(-1) 
        except:
            pass
    
    # Put back old clips
    for i in range(0, len(self.removed_clips)):
        clip = self.removed_clips[i]
        _insert_clip(to_track, clip, in_index + i, clip.clip_in,
                     clip.clip_out)

    _do_clip_unmute(self.parent_clip)
    
    #_remove_trailing_blanks(to_track)

def _audio_splice_redo(self):
    # Get shorter name for readability
    to_track = self.to_track
    
    # Find out if overwrite starts after track end and pad track with blank if so.
    if self.over_in >= to_track.get_length():
        self.starts_after_end = True
        gap = self.over_out - to_track.get_length()
        _insert_blank(to_track, len(to_track.clips), gap)
    else:
        self.starts_after_end = False

    # Cut at in frame of overwrite range. 
    clip_in, clip_out = _overwrite_cut_track(to_track, self.over_in)
    self.in_clip_out = clip_out

    # Cut at out frame of overwrite range 
    if to_track.get_length() > self.over_out:
        clip_in, clip_out = _overwrite_cut_track(to_track, self.over_out)
        self.out_clip_in = clip_in
    else:
        self.out_clip_in = -1
    
    # Splice out clips in overwrite range
    self.removed_clips = []
    in_index = to_track.get_clip_index_at(self.over_in)
    out_index = to_track.get_clip_index_at(self.over_out)

    for i in range(in_index, out_index):
        self.removed_clips.append(_remove_clip(to_track, in_index))

    # Insert audio clip
    _insert_clip(to_track, self.audio_clip, in_index, self.parent_clip.clip_in, self.parent_clip.clip_out)

    filter = _create_mute_volume_filter(current_sequence())
    _do_clip_mute(self.parent_clip, filter)
    
#----------------- AUDIO SPLICE SYNCHED
# "parent_clip", "audio_clip", "track", "to_track"
def audio_synched_splice_action(data):
    action = EditAction(_audio_synched_splice_undo, _audio_synched_splice_redo, data)
    return action

def _audio_synched_splice_undo(self):
    to_track = self.to_track

    # Remove add audio clip
    in_index = to_track.get_clip_index_at(self.over_in)
    _remove_clip(to_track, in_index)
        
    # Fix in clip and remove cut created clip if in was cut
    if self.in_clip_out != -1:
        in_clip = _remove_clip(to_track, in_index - 1)
        _insert_clip(to_track, in_clip, in_index - 1,
                     in_clip.clip_in, self.in_clip_out)
        self.removed_clips.pop(0)

    # Fix out clip and remove cut created clip if out was cut
    if self.out_clip_in != -1:
        # If moved clip/s were last in the track and were moved slightly 
        # forward and were still last in track after move
        # this leaves a trailing black that has been removed and this will fail
        try:
            out_clip = _remove_clip(to_track, in_index)
            if len(self.removed_clips) > 0: # If overwrite was done inside single clip everything is already in order
                _insert_clip(to_track, out_clip, in_index,
                         self.out_clip_in, out_clip.clip_out)
                self.removed_clips.pop(-1) 
        except:
            pass
    
    # Put back old clips
    for i in range(0, len(self.removed_clips)):
        clip = self.removed_clips[i]
        _insert_clip(to_track, clip, in_index + i, clip.clip_in,
                     clip.clip_out)

    _do_clip_unmute(self.parent_clip)
    
    child_clip = self.audio_clip
     
    # Clear child sync data
    child_clip.sync_data = None

    # Clear resync data
    resync.clip_sync_cleared(child_clip)

def _audio_synched_splice_redo(self):
    # Get shorter name for readability
    to_track = self.to_track
    
    # Find out if overwrite starts after track end and pad track with blank if so.
    if self.over_in >= to_track.get_length():
        self.starts_after_end = True
        gap = self.over_out - to_track.get_length()
        _insert_blank(to_track, len(to_track.clips), gap)
    else:
        self.starts_after_end = False

    # Cut at in frame of overwrite range. 
    clip_in, clip_out = _overwrite_cut_track(to_track, self.over_in)
    self.in_clip_out = clip_out

    # Cut at out frame of overwrite range 
    if to_track.get_length() > self.over_out:
        clip_in, clip_out = _overwrite_cut_track(to_track, self.over_out)
        self.out_clip_in = clip_in
    else:
        self.out_clip_in = -1
    
    # Splice out clips in overwrite range
    self.removed_clips = []
    in_index = to_track.get_clip_index_at(self.over_in)
    out_index = to_track.get_clip_index_at(self.over_out)

    for i in range(in_index, out_index):
        self.removed_clips.append(_remove_clip(to_track, in_index))

    # Insert audio clip
    _insert_clip(to_track, self.audio_clip, in_index, self.parent_clip.clip_in, self.parent_clip.clip_out)

    filter = _create_mute_volume_filter(current_sequence())
    _do_clip_mute(self.parent_clip, filter)

    # "parent_clip", "audio_clip", "track", "to_track"
    child_clip = self.audio_clip
    parent_clip = self.parent_clip
    child_track = to_track
    parent_track = self.track
    child_index = child_track.clips.index(child_clip)
    parent_index = parent_track.clips.index(parent_clip)

    # Get offset
    child_clip_start = child_track.clip_start(child_index) - child_clip.clip_in
    parent_clip_start = parent_track.clip_start(parent_index) - parent_clip.clip_in
    pos_offset = child_clip_start - parent_clip_start
    
    # Set sync data
    child_clip.sync_data = SyncData()
    child_clip.sync_data.pos_offset = pos_offset
    child_clip.sync_data.master_clip = parent_clip
    child_clip.sync_data.master_clip_track = parent_track
    child_clip.sync_data.sync_state = appconsts.SYNC_CORRECT

    resync.clip_added_to_timeline(child_clip, child_track)

# ------------------------------------------------- RESYNC CLIP
# "clips"
def resync_clip_action(data):
    action = EditAction(_resync_clip_undo, _resync_clip_redo, data)
    return action

def _resync_clip_undo(self):
    self.action.undo_func(self.action)
        
def _resync_clip_redo(self):
    if hasattr(self, "action"):
        # Action has already been created, this a is redo.
        self.action.redo_func(self.action)
        return

    resync_data = resync.get_resync_data_list_for_clip_list(self.clips)
    # Here we always only have one item in the list.
    self.action = _create_and_do_sync_action(resync_data[0])

def _create_and_do_sync_action(resync_data_list_item):
    clip, track, index, child_clip_start, pos_offset = resync_data_list_item

    # If we're in sync, do nothing.
    # Note that we get no-op undo redo if user tries to sync clip that is 
    # already in sync, maybe fix later.
    if pos_offset == clip.sync_data.pos_offset:
        return None

    # Get new in and out frames for clip
    diff = pos_offset - clip.sync_data.pos_offset
    over_in = track.clip_start(index) - diff
    over_out = over_in + (clip.clip_out - clip.clip_in + 1)
    data = {"track":track,
            "over_in":over_in,
            "over_out":over_out,
            "selected_range_in":index,
            "selected_range_out":index,
            "move_edit_done_func":None}
    
    action = overwrite_move_action(data)
    action.redo_func(action)

    return action


#----------------- RESYNC TRACK
# "track", "resync_clips_data_list"
def resync_track_action(data):
    action = EditAction(_resync_track_undo, _resync_track_redo, data)
    return action

def _resync_track_undo(self):        
    clip, track = self.resync_clips_data_list[0]
    for synched_clip in self.synched_track:
        _remove_clip(track, 0)

    for orig_clip in self.orig_track:
         append_clip(track, orig_clip, orig_clip.clip_in, orig_clip.clip_out)

def _resync_track_redo(self):
    if not hasattr(self, "orig_track"):
        
        # List of tuples (clip, track, index, child_clip_start, pos_off)
        resync_data = resync.get_resync_data_list_for_clip_list(self.resync_clips_data_list)

        # Lift resync clips and insert blank in their place
        for data_item in resync_data: 
            clip, track, index, child_clip_start, pos_off = data_item
            
            # Do copy of original track on first iteration.
            if not hasattr(self, "orig_track"):
                self.orig_track = copy.copy(track.clips)
        
            _remove_clip(track, index)
            removed_length = clip.clip_out - clip.clip_in + 1 # + 1 == out inclusive
            _insert_blank(track, index, removed_length)

        # Put resync clips in synched positions.
        for data_item in resync_data:
            clip, track, index, child_clip_start, pos_offset = data_item
            
            diff = pos_offset - clip.sync_data.pos_offset
            over_in = child_clip_start - diff
            over_out = over_in + (clip.clip_out - clip.clip_in + 1)
        
            # Find out if overwrite starts after or on track end and pad track with blank if so.
            if over_in >= track.get_length():
                gap = over_out - track.get_length()
                _insert_blank(track, len(track.clips), gap)
            
            # Cut at in point if not already on cut
            clip_in, clip_out = _overwrite_cut_track(track, over_in)
            in_clip_out = clip_out
                
            # Cut at out point if not already on cut and out point inside track length.
            self.over_out = over_out # _overwrite_cut_range_out() gets this data from 'self' 
            _overwrite_cut_range_out(track, self)
            
            # Splice out clips in overwrite range
            in_index = track.get_clip_index_at(over_in)
            out_index = track.get_clip_index_at(over_out)

            for i in range(in_index, out_index):
                _remove_clip(track, in_index)

            _insert_clip(track, clip, in_index, clip.clip_in, clip.clip_out)

        # Do copy of original track on first iteration.
        self.synched_track = copy.copy(track.clips)
                
        # HACK, see EditAction for details
        self.turn_on_stop_for_edit = True
    else:
        # This is a redo. We have data to do just simple track contents replacement.
        clip, track = self.resync_clips_data_list[0]
        for orig_clip in self.orig_track:
            _remove_clip(track, 0)

        for synched_clip in self.synched_track:
             append_clip(track, synched_clip, synched_clip.clip_in, synched_clip.clip_out)


# ------------------------------------------------- SET SYNC
# "child_index","child_track","parent_index","parent_track"
def set_sync_action(data):
    action = EditAction(_set_sync_undo, _set_sync_redo, data)
    return action
    
def _set_sync_undo(self):
    # Get clips
    child_clip = self.child_track.clips[self.child_index]
     
    # Clear child sync data
    child_clip.sync_data = None

    # Clear resync data
    resync.clip_sync_cleared(child_clip)
    
def _set_sync_redo(self):
    # Get clips
    child_clip = self.child_track.clips[self.child_index]
    parent_clip = get_track(self.parent_track.id).clips[self.parent_index]

    # Get offset
    child_clip_start = self.child_track.clip_start(self.child_index) - child_clip.clip_in
    parent_clip_start = self.parent_track.clip_start(self.parent_index) - parent_clip.clip_in
    pos_offset = child_clip_start - parent_clip_start
    
    # Set sync data
    child_clip.sync_data = SyncData()
    child_clip.sync_data.pos_offset = pos_offset
    child_clip.sync_data.master_clip = parent_clip
    child_clip.sync_data.master_clip_track = self.parent_track
    child_clip.sync_data.sync_state = appconsts.SYNC_CORRECT

    resync.clip_added_to_timeline(child_clip, self.child_track)

# -------------------------------------------- SET TRACK SYNC
"child_track", "orig_sync_data", "new_sync_data"
def set_track_sync_action(data):
    return EditAction(_set_track_sync_undo, _set_track_sync_redo, data)

def _set_track_sync_undo(self):
    for child_clip in self.child_track.clips:
        resync.clip_removed_from_timeline(child_clip)
        try:
            # "orig_sync_data" created in resync.get_track_all_resync_action_data()
            sync_data = self.orig_sync_data[child_clip]
            child_clip.sync_data = sync_data
        except:
            pass
            
        resync.clip_added_to_timeline(child_clip, self.child_track)

def _set_track_sync_redo(self):
    for child_clip in self.child_track.clips:
        resync.clip_removed_from_timeline(child_clip)
        try:
            # "new_sync_data" created in resync.get_track_all_resync_action_data()
            pos_offset, parent_clip, parent_track = self.new_sync_data[child_clip]
            
            child_clip.sync_data = SyncData()
            child_clip.sync_data.pos_offset = pos_offset
            child_clip.sync_data.master_clip = parent_clip
            child_clip.sync_data.master_clip_track = parent_track
            child_clip.sync_data.sync_state = appconsts.SYNC_CORRECT
        except:
            pass
            
        resync.clip_added_to_timeline(child_clip, self.child_track)

# -------------------------------------------- SET BOX SELECTION SYNC
"orig_sync_data", "new_sync_data"
def set_box_selection_sync_action(data):
    return EditAction(_set_box_selection_sync_undo, _set_box_selection_sync_redo, data)

def _set_box_selection_sync_undo(self):
    for track_orig_sync_data in self.orig_sync_data:
        track_selection, track_sync_data = track_orig_sync_data
        child_track = current_sequence().tracks[track_selection.track_id]

        for clip in track_sync_data.keys():
            resync.clip_removed_from_timeline(clip)
            try:
                # "orig_sync_data" created in resync.get_track_all_resync_action_data()
                sync_data = track_sync_data[clip]
                clip.sync_data = sync_data
            except:
                pass
                
            resync.clip_added_to_timeline(clip, child_track)

def _set_box_selection_sync_redo(self):
    for track_new_sync_data in self.new_sync_data:
        track_selection, sync_data = track_new_sync_data
        child_track = current_sequence().tracks[track_selection.track_id]

        for clip in sync_data.keys():
            resync.clip_removed_from_timeline(clip)
            try:
                # "new_sync_data" created in resync.get_track_all_resync_action_data()
                pos_offset, parent_clip, parent_track = sync_data[clip]
                
                clip.sync_data = SyncData()
                clip.sync_data.pos_offset = pos_offset
                clip.sync_data.master_clip = parent_clip
                clip.sync_data.master_clip_track = parent_track
                clip.sync_data.sync_state = appconsts.SYNC_CORRECT
            except:
                pass
                
            resync.clip_added_to_timeline(clip, child_track)
        
# -------------------------------------------- CLEAR TRACK SYNC
"child_track", "orig_sync_data"
def clear_track_sync_action(data):
    return EditAction(_clear_track_sync_undo, _clear_track_sync_redo, data)

def _clear_track_sync_undo(self):
    for child_clip in self.child_track.clips:
        resync.clip_removed_from_timeline(child_clip)
        try:
            # "orig_sync_data" created in resync.get_track_all_resync_action_data()
            sync_data = self.orig_sync_data[child_clip]
            child_clip.sync_data = sync_data
        except:
            pass
            
        resync.clip_added_to_timeline(child_clip, self.child_track)

    self.child_track.parent_track = self.orig_parent_track
    
def _clear_track_sync_redo(self):
    for child_clip in self.child_track.clips:
        resync.clip_removed_from_timeline(child_clip)
        child_clip.sync_data = None

    self.orig_parent_track = self.child_track.parent_track
    self.child_track.parent_track = None

# ------------------------------------------------- CLEAR SYNC
# "child_clip","child_track"
def clear_sync_action(data):
    action = EditAction(_clear_sync_undo, _clear_sync_redo, data)
    return action
    
def _clear_sync_undo(self):
    # Reset child sync data
    self.child_clip.sync_data = self.sync_data

    # Save data resync data for doing resyncs and sync state gui updates
    resync.clip_added_to_timeline(self.child_clip, self.child_track)

def _clear_sync_redo(self):
    # Save sync data
    self.sync_data = self.child_clip.sync_data

    # Clear child sync data
    self.child_clip.sync_data = None

    # Clear resync data
    resync.clip_sync_cleared(self.child_clip)
    
# --------------------------------------- MUTE CLIP
# "clip"
def mute_clip(data):
    action = EditAction(_mute_clip_undo,_mute_clip_redo, data)
    return action

def _mute_clip_undo(self):
    _do_clip_unmute(self.clip)

def _mute_clip_redo(self):
    mute_filter = _create_mute_volume_filter(current_sequence())
    _do_clip_mute(self.clip, mute_filter)

# --------------------------------------- UNMUTE CLIP
# "clip"
def unmute_clip(data):
    action = EditAction(_unmute_clip_undo,_unmute_clip_redo, data)
    return action

def _unmute_clip_undo(self):
    mute_filter = _create_mute_volume_filter(current_sequence())
    _do_clip_mute(self.clip, mute_filter)

def _unmute_clip_redo(self):
    _do_clip_unmute(self.clip)


# ----------------------------------------- TRIM END OVER BLANKS
#"track","clip","clip_index"
def trim_end_over_blanks(data):
    action = EditAction(_trim_end_over_blanks_undo, _trim_end_over_blanks_redo, data)
    action.exit_active_trimmode_on_edit = False
    action.update_hidden_track_blank = False
    return action 

def _trim_end_over_blanks_undo(self):
    # put back blanks
    total_length = 0
    for i in range(0, len(self.removed_lengths)):
        length = self.removed_lengths[i]
        _insert_blank(self.track, self.clip_index + 1 + i, length)
        total_length = total_length + length

    # trim clip
    _remove_clip(self.track, self.clip_index)
    _insert_clip(self.track, self.clip, self.clip_index, self.clip.clip_in, self.clip.clip_out - total_length) 

def _trim_end_over_blanks_redo(self):
    # Remove blanks
    self.removed_lengths = _remove_consecutive_blanks(self.track, self.clip_index + 1) # +1, we're stretching clip over blank are starting at NEXT index
    total_length = 0
    for length in self.removed_lengths:
        total_length = total_length + length

    # trim clip
    _remove_clip(self.track, self.clip_index)
    _insert_clip(self.track, self.clip, self.clip_index, self.clip.clip_in, self.clip.clip_out + total_length) 

# ----------------------------------------- TRIM START OVER BLANKS
# "track","clip","blank_index"
def trim_start_over_blanks(data):
    action = EditAction(_trim_start_over_blanks_undo, _trim_start_over_blanks_redo, data)
    action.exit_active_trimmode_on_edit = False
    action.update_hidden_track_blank = False
    return action

def _trim_start_over_blanks_undo(self):
    # trim clip
    _remove_clip(self.track, self.blank_index)
    _insert_clip(self.track, self.clip, self.blank_index, self.clip.clip_in + self.total_length, self.clip.clip_out)

    # put back blanks
    for i in range(0, len(self.removed_lengths)):
        length = self.removed_lengths[i]
        _insert_blank(self.track, self.blank_index + i, length)

def _trim_start_over_blanks_redo(self):
    # Remove blanks
    self.removed_lengths = _remove_consecutive_blanks(self.track, self.blank_index)
    self.total_length = 0
    for length in self.removed_lengths:
        self.total_length = self.total_length + length

    # trim clip
    _remove_clip(self.track, self.blank_index)
    _insert_clip(self.track, self.clip, self.blank_index, self.clip.clip_in - self.total_length, self.clip.clip_out) 

# ----------------------------------------- CLIP DROPPED AFTER TRACK END APPEND
#"track","clip","blank_length", "index","clip_in", "clip_out"
def dnd_after_track_end_action(data):
    action = EditAction(_dnd_after_track_end_undo, _dnd_after_track_end_redo, data)
    return action

def _dnd_after_track_end_undo(self):
    _remove_clip(self.track, self.index)
    _remove_clip(self.track, self.index)

def _dnd_after_track_end_redo(self):
    _insert_blank(self.track, self.index, self.blank_length)
    _insert_clip(self.track, self.clip, self.index + 1, self.clip_in, self.clip_out)

# ----------------------------------------- CLIP DROPPED ON START PART OF BLANK
# "track","clip","blank_length","index","clip_in","clip_out"
def dnd_on_blank_start_action(data):
    action = EditAction(_dnd_on_blank_start_undo, _dnd_on_blank_start_redo, data)
    return action

def _dnd_on_blank_start_undo(self):
    _remove_clip(self.track, self.index)
    _remove_clip(self.track, self.index)
    _insert_blank(self.track, self.index, self.blank_length)

def _dnd_on_blank_start_redo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index, 
                 self.clip_in, self.clip_out)
    last_blank_length = self.blank_length - (self.clip_out - self.clip_in + 1) 
    _insert_blank(self.track, self.index + 1, last_blank_length)

# ----------------------------------------- CLIP DROPPED ON END PART OF BLANK
# "track","clip","overwritten_blank_length","blank_length","index","clip_in","clip_out"
def dnd_on_blank_end_action(data):
    action = EditAction(_dnd_on_blank_end_undo, _dnd_on_blank_end_redo, data)
    return action
    
def _dnd_on_blank_end_undo(self):
    _remove_clip(self.track, self.index)
    _remove_clip(self.track, self.index)
    _insert_blank(self.track, self.index, self.blank_length)
    
def _dnd_on_blank_end_redo(self):
    _remove_clip(self.track, self.index)
    _insert_blank(self.track, self.index, self.overwritten_blank_length)
    clip_length = self.blank_length - self.overwritten_blank_length - 1
    _insert_clip(self.track, self.clip, self.index + 1, 
                 self.clip_in, self.clip_in + clip_length)

# ----------------------------------------- CLIP DROPPED ON MIDDLE OF BLANK
# "track","clip","overwritten_start_frame","blank_length","index","clip_in","clip_out"
def dnd_on_blank_middle_action(data):
    action = EditAction(_dnd_on_blank_middle_undo, _dnd_on_blank_middle_redo, data)
    return action
    
def _dnd_on_blank_middle_undo(self):
    _remove_clip(self.track, self.index)
    _remove_clip(self.track, self.index)
    _remove_clip(self.track, self.index)
    _insert_blank(self.track, self.index, self.blank_length)

def _dnd_on_blank_middle_redo(self):
    _remove_clip(self.track, self.index)
    _insert_blank(self.track, self.index, self.overwritten_start_frame)
    _insert_clip(self.track, self.clip, self.index + 1, 
                 self.clip_in, self.clip_out)
    last_blank_length = self.blank_length - self.overwritten_start_frame - (self.clip_out - self.clip_in + 1) 
    _insert_blank(self.track, self.index + 2, last_blank_length)

# ----------------------------------------- CLIP DROPPED TO REPLACE FULL BLANK LENGTH
# "track","clip","blank_length","index","clip_in"
def dnd_on_blank_replace_action(data):
    action = EditAction(_dnd_on_blank_replace_undo, _dnd_on_blank_replace_redo, data)
    return action

def _dnd_on_blank_replace_undo(self):
    _remove_clip(self.track, self.index)
    _insert_blank(self.track, self.index, self.blank_length)

def _dnd_on_blank_replace_redo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.clip, self.index, 
                 self.clip_in,  self.clip_in + self.blank_length - 1)

# ---------------------------------------- CONSOLIDATE SELECTED BLANKS
# "track","index"
def consolidate_selected_blanks(data):
    action = EditAction(_consolidate_selected_blanks_undo,_consolidate_selected_blanks_redo, data)
    return action 

def _consolidate_selected_blanks_undo(self):
    _remove_clip(self.track, self.index)
    for i in range(0, len(self.removed_lengths)):
        length = self.removed_lengths[i]
        _insert_blank(self.track, self.index + i, length)

def _consolidate_selected_blanks_redo(self):
    self.removed_lengths = _remove_consecutive_blanks(self.track, self.index)
    total_length = 0
    for length in self.removed_lengths:
        total_length = total_length + length
    _insert_blank(self.track, self.index, total_length)

#----------------------------------- CONSOLIDATE ALL BLANKS
def consolidate_all_blanks(data):
    action = EditAction(_consolidate_all_blanks_undo,_consolidate_all_blanks_redo, data)
    return action     

def _consolidate_all_blanks_undo(self):
    self.consolidate_actions.reverse()
    for c_action in  self.consolidate_actions:
        track, index, removed_lengths = c_action
        _remove_clip(track, index)
        for i in range(0, len(removed_lengths)):
            length = removed_lengths[i]
            _insert_blank(track, index + i, length)
        
def _consolidate_all_blanks_redo(self):
    self.consolidate_actions = []
    for i in range(1, len(current_sequence().tracks) - 1): # -1 because hidden track, 1 because black track
        track = current_sequence().tracks[i]
        consolidaded_indexes = []
        try_do_next = True
        while(try_do_next == True):
            if len(track.clips) == 0:
                try_do_next = False
            for i in range(0, len(track.clips)):
                if i == len(track.clips) - 1:
                    try_do_next = False
                clip = track.clips[i]
                if clip.is_blanck_clip == False:
                    continue
                try:
                    consolidaded_indexes.index(i)
                    continue
                except:
                    pass

                # Now consolidate from clip in index i
                consolidaded_indexes.append(i)
                removed_lengths = _remove_consecutive_blanks(track, i)
                total_length = 0
                for length in removed_lengths:
                    total_length = total_length + length
                _insert_blank(track, i, total_length)
                self.consolidate_actions.append((track, i, removed_lengths))
                break

#----------------- RANGE OVERWRITE 
# "track","clip","clip_in","clip_out","mark_in_frame","mark_out_frame"
def range_overwrite_action(data):
    action = EditAction(_range_over_undo, _range_over_redo, data)
    return action

def _range_over_undo(self):
    _remove_clip(self.track, self.track_extract_data.in_index)

    _track_put_back_range(self.mark_in_frame, 
                          self.track, 
                          self.track_extract_data)
    
def _range_over_redo(self):
    self.track_extract_data = _track_extract_range(self.mark_in_frame, 
                                                   self.mark_out_frame, 
                                                   self.track)
    _insert_clip(self.track,        
                 self.clip, 
                 self.track_extract_data.in_index,
                 self.clip_in, 
                 self.clip_out)

    # HACK, see EditAction for details
    self.turn_on_stop_for_edit = True


#----------------- RANGE DELETE 
# "tracks","mark_in_frame","mark_out_frame"
def range_delete_action(data):
    action = EditAction(_range_delete_undo, _range_delete_redo, data)
    action.stop_for_edit = True
    return action

def _range_delete_undo(self):
    for i in range(0, len(self.tracks)): # -1 because hidden track, 1 because black track
        track = self.tracks[i]
        track_extract_data = self.tracks_extract_data[i]

        _track_put_back_range(self.mark_in_frame, 
                              track, 
                              track_extract_data)
    
def _range_delete_redo(self):
    self.tracks_extract_data = []
    for track in self.tracks: # -1 because hidden track, 1 because black track
        track_extracted = _track_extract_range(self.mark_in_frame, 
                                               self.mark_out_frame, 
                                               track)
        self.tracks_extract_data.append(track_extracted)
    
    # HACK, see EditAction for details
    self.turn_on_stop_for_edit = True


#----------------- RIPPLE DELETE 
# "track","from_index","to_index"
def ripple_delete_action(data):
    action = EditAction(_ripple_delete_undo, _ripple_delete_redo, data)
    action.stop_for_edit = True
    return action

def _ripple_delete_undo(self):
    _multi_move_undo(self)
    _lift_multiple_undo(self)
    
def _ripple_delete_redo(self):
    _lift_multiple_redo(self)
    _multi_move_redo(self)


#------------------- ADD CENTERED TRANSITION
# "transition_clip","transition_index", "from_clip","to_clip","track","from_in","to_out", "length_fix"
def add_centered_transition_action(data):
    action = EditAction(_add_centered_transition_undo, _add_centered_transition_redo, data)
    return action

def _add_centered_transition_undo(self):
    index = self.transition_index
    track = self.track
    from_clip = self.from_clip
    to_clip = self.to_clip

    for i in range(0, 3): # from, trans, to
        _remove_clip(track, index - 1)
    
    _insert_clip(track, from_clip, index - 1, 
                 from_clip.clip_in, self.orig_from_clip_out)
    _insert_clip(track, to_clip, index, 
                 self.orig_to_clip_in, to_clip.clip_out)

def _add_centered_transition_redo(self):
    # get shorter refs
    transition_clip = self.transition_clip
    index = self.transition_index
    track = self.track
    from_clip = self.from_clip
    to_clip = self.to_clip
    
    # Save from and to clip in/out points before adding transition
    self.orig_from_clip_out = from_clip.clip_out
    self.orig_to_clip_in = to_clip.clip_in

    # Shorten from clip    
    _remove_clip(track, index - 1)
    _insert_clip(track, from_clip, index - 1, 
                 from_clip.clip_in, self.from_in) # self.from_in == transition start on from clip
    # Shorten to clip 
    _remove_clip(track, index)
    _insert_clip(track, to_clip, index, 
                         self.to_out + 1, to_clip.clip_out)  # self.to_out == transition end on to clip
                                                             # + 1  == because frame is part of inserted transition
    # Insert transition
    _insert_clip(track, transition_clip, 
                 self.transition_index, 1, # first frame is dropped as it is 100% from clip
                 transition_clip.get_length() - 1 - self.length_fix)


#------------------- REPLACE CENTERED TRANSITION
# "track", "transition_clip","transition_index"
def replace_centered_transition_action(data):
    action = EditAction(_replace_centered_transition_undo, _replace_centered_transition_redo, data)
    return action

def _replace_centered_transition_undo(self):
    # Remove new
    _remove_clip(self.track, self.transition_index)

    # Insert old 
    _insert_clip(self.track, self.removed_clip, 
                 self.transition_index, 1, # first frame is dropped as it is 100% from clip
                 self.removed_clip.clip_out)

def _replace_centered_transition_redo(self):
    # Remove old   
    self.removed_clip = _remove_clip(self.track, self.transition_index)
    
    # Insert new 
    _insert_clip(self.track, self.transition_clip, 
                 self.transition_index, 1, # first frame is dropped as it is 100% from clip
                 self.transition_clip.clip_out)
                    

# -------------------------------------------------------- REPLACE RENDERED FADE
# "fade_clip", "index", "track", "length"
def replace_rendered_fade_action(data):
    action = EditAction(_replace_rendered_fade_undo, _replace_rendered_fade_redo, data)
    return action

def _replace_rendered_fade_undo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track,  self.orig_fade, self.index, 0, self.length - 1)

def _replace_rendered_fade_redo(self):
    self.orig_fade = _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.fade_clip, self.index, 0, self.length - 1)


# -------------------------------------------------------- RENDERED FADE IN
# "fade_clip", "clip_index", "track", "length"
def add_rendered_fade_in_action(data):
    action = EditAction(_add_rendered_fade_in_undo, _add_rendered_fade_in_redo, data)
    return action

def _add_rendered_fade_in_undo(self):
    _remove_clip(self.track, self.index)
    _remove_clip(self.track, self.index)
    _insert_clip(self.track,  self.orig_clip, self.index, self.orig_clip_in, self.orig_clip.clip_out)

def _add_rendered_fade_in_redo(self):
    self.orig_clip = _remove_clip(self.track, self.index)
    self.orig_clip_in = self.orig_clip.clip_in 
    _insert_clip(self.track, self.fade_clip, self.index, 0, self.length - 1)
    _insert_clip(self.track,  self.orig_clip, self.index + 1, self.orig_clip.clip_in + self.length, self.orig_clip.clip_out)


# -------------------------------------------------------- RENDERED FADE OUT
# "fade_clip", "clip_index", "track", "length"
def add_rendered_fade_out_action(data):
    action = EditAction(_add_rendered_fade_out_undo, _add_rendered_fade_out_redo, data)
    return action

def _add_rendered_fade_out_undo(self):
    _remove_clip(self.track, self.index)
    _remove_clip(self.track, self.index)
    _insert_clip(self.track,  self.orig_clip, self.index, self.orig_clip.clip_in, self.orig_clip_out)

def _add_rendered_fade_out_redo(self):
    self.orig_clip = _remove_clip(self.track, self.index)
    self.orig_clip_out = self.orig_clip.clip_out 
    _insert_clip(self.track,  self.orig_clip, self.index, self.orig_clip.clip_in, self.orig_clip.clip_out - self.length)
    _insert_clip(self.track, self.fade_clip, self.index + 1, 0, self.length - 1)


# -------------------------------------------------------- MEDIA RELOAD CLIP REPLACE
# "old_clip", "new_clip", "track", "index"
def reload_replace(data):
    action = EditAction(_reload_replace_undo, _reload_replace_redo, data)
    return action

def _reload_replace_undo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.old_clip, self.index, self.old_clip.clip_in, self.old_clip.clip_out)
    
def _reload_replace_redo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.new_clip, self.index, self.old_clip.clip_in, self.old_clip.clip_out)

# -------------------------------------------------------- MEDIA RELOAD CLIP REPLACE
# "old_clip", "new_clip", "clip_in", "clip_out", "track", "index"
def clip_replace(data):
    action = EditAction(_clip_replace_undo, _clip_replace_redo, data)
    return action

def _clip_replace_undo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.old_clip, self.index, self.old_clip.clip_in, self.old_clip.clip_out)
    
def _clip_replace_redo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.new_clip, self.index, self.clip_in, self.clip_out)
    
# -------------------------------------------------------- CONTAINER CLIP FULL RENDER MEDIA REPLACE
# "old_clip", "new_clip","rendered_media_path","track", "index", "do_filters_clone"
def container_clip_full_render_replace(data):
    action = EditAction(_container_clip_full_render_replace_undo, _container_clip_full_render_replace_redo, data)
    return action

def _container_clip_full_render_replace_undo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.old_clip, self.index, self.old_clip.clip_in, self.old_clip.clip_out)

    if self.do_filters_clone == True:
        _detach_all(self.new_clip)
        self.new_clip.filters = []

    if self.old_clip.sync_data != None:
        _switch_synched_clip(self.old_clip, self.track, self.new_clip)
        
def _container_clip_full_render_replace_redo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.new_clip, self.index, self.old_clip.clip_in, self.old_clip.clip_out)

    if self.new_clip.container_data == None:
        self.new_clip.container_data = copy.deepcopy(self.old_clip.container_data)

    if not hasattr(self, "clone_filters") and self.do_filters_clone == True:
        self.clone_filters = current_sequence().clone_filters(self.old_clip)

    if self.do_filters_clone == True:
        _detach_all(self.new_clip)
        self.new_clip.filters = self.clone_filters
        _attach_all(self.new_clip)

    self.new_clip.container_data.rendered_media = self.rendered_media_path
    self.new_clip.container_data.rendered_media_range_in = 0
    self.new_clip.container_data.rendered_media_range_out = self.old_clip.container_data.unrendered_length

    self.new_clip.link_seq_data = self.old_clip.link_seq_data

    if self.old_clip.sync_data != None:
        if self.new_clip.sync_data == None:
            _clone_sync_data(self.new_clip, self.old_clip)
    
        _switch_synched_clip(self.new_clip, self.track, self.old_clip)
 
# -------------------------------------------------------- CONTAINER CLIP CLIP RENDER MEDIA REPLACE
# "old_clip", "new_clip","rendered_media_path","track", "index", "do_filters_clone"
def container_clip_clip_render_replace(data):
    action = EditAction(_container_clip_clip_render_replace_undo, _container_clip_clip_render_replace_redo, data)
    return action

def _container_clip_clip_render_replace_undo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.old_clip, self.index, self.old_clip.clip_in, self.old_clip.clip_out)

    if self.do_filters_clone == True:
        _detach_all(self.new_clip)
        self.new_clip.filters = []

    if self.old_clip.sync_data != None:
        _switch_synched_clip(self.old_clip, self.track, self.new_clip)
        
def _container_clip_clip_render_replace_redo(self):
    _remove_clip(self.track, self.index)
    new_out = self.old_clip.clip_out - self.old_clip.clip_in
    _insert_clip(self.track, self.new_clip, self.index, 0, new_out)

    if self.new_clip.container_data == None:
        self.new_clip.container_data = copy.deepcopy(self.old_clip.container_data)
        
    if not hasattr(self, "clone_filters") and self.do_filters_clone == True:
        self.clone_filters = current_sequence().clone_filters(self.old_clip)

    if self.do_filters_clone == True:
        _detach_all(self.new_clip)
        self.new_clip.filters = self.clone_filters
        _attach_all(self.new_clip)

    self.new_clip.container_data.rendered_media = self.rendered_media_path
    self.new_clip.container_data.rendered_media_range_in = self.old_clip.clip_in
    self.new_clip.container_data.rendered_media_range_out = self.old_clip.clip_out

    self.new_clip.link_seq_data = self.old_clip.link_seq_data

    if self.old_clip.sync_data != None:
        if self.new_clip.sync_data == None:
            _clone_sync_data(self.new_clip, self.old_clip)
    
        _switch_synched_clip(self.new_clip, self.track, self.old_clip)
        
# -------------------------------------------------------- CONTAINER CLIP SWITCH TO UNRENDERED CLIP MEDIA REPLACE
# "old_clip", "new_clip", "track", "index", "do_filters_clone"
def container_clip_switch_to_unrendered_replace(data):
    action = EditAction(_container_clip_switch_to_unrendered_replace_undo, _container_clip_switch_to_unrendered_replace_redo, data)
    return action

def _container_clip_switch_to_unrendered_replace_undo(self):
    _remove_clip(self.track, self.index)
    _insert_clip(self.track, self.old_clip, self.index, self.old_clip.clip_in, self.old_clip.clip_out)

    if self.do_filters_clone == True:
        _detach_all(self.new_clip)
        self.new_clip.filters = []

    if self.old_clip.sync_data != None:
        _switch_synched_clip(self.old_clip, self.track, self.new_clip)

def _container_clip_switch_to_unrendered_replace_redo(self):
    _remove_clip(self.track, self.index)
    
    if self.old_clip.container_data.last_render_type == containeractions.CLIP_LENGTH_RENDER:
        old_clip_edited_length = self.old_clip.clip_out - self.old_clip.clip_in
        _insert_clip(   self.track, self.new_clip, self.index, 
                        self.old_clip.container_data.rendered_media_range_in + self.old_clip.clip_in, 
                        self.old_clip.container_data.rendered_media_range_in + self.old_clip.clip_in + old_clip_edited_length)
    else:
        _insert_clip(self.track, self.new_clip, self.index, self.old_clip.clip_in, self.old_clip.clip_out)

    if self.new_clip.container_data == None:
        self.new_clip.container_data = copy.deepcopy(self.old_clip.container_data)

    if not hasattr(self, "clone_filters") and self.do_filters_clone == True:
        self.clone_filters = current_sequence().clone_filters(self.old_clip)

    if self.do_filters_clone == True:
        _detach_all(self.new_clip)
        self.new_clip.filters = self.clone_filters
        _attach_all(self.new_clip)

    self.new_clip.name = self.old_clip.name
    self.new_clip.link_seq_data = self.old_clip.link_seq_data
    
    self.new_clip.container_data.clear_rendered_media()

    if self.old_clip.sync_data != None:
        if self.new_clip.sync_data == None:
            _clone_sync_data(self.new_clip, self.old_clip)
    
        _switch_synched_clip(self.new_clip, self.track, self.old_clip)

#-------------------- APPEND MEDIA LOG
# "track","clips"
def append_media_log_action(data):
    action = EditAction(_append_media_log_undo,_append_media_log_redo, data)
    return action

def _append_media_log_undo(self):
    for i in range(0, len(self.clips)):
        _remove_clip(self.track, len(self.track.clips) - 1)
    
def _append_media_log_redo(self):
    for i in range(0, len(self.clips)):
        clip = self.clips[i]
        append_clip(self.track, clip, clip.clip_in, clip.clip_out)


# --------------------------------------------- help funcs for "range over" and "range splice out" edits
def _track_put_back_range(over_in, track, track_extract_data):
    # get index for first clip that was removed
    moved_index = track.get_clip_index_at(over_in)

    # Fix in clip and remove cut created clip if in was cut
    if track_extract_data.in_clip_out != -1:
        in_clip = _remove_clip(track, moved_index - 1)
        if in_clip.is_blanck_clip != True:
            _insert_clip(track, in_clip, moved_index - 1,
                         in_clip.clip_in, track_extract_data.in_clip_out)
        else: # blanks can't be resized, so must put in new blank
            _insert_blank(track, moved_index - 1, track_extract_data.in_clip_out - in_clip.clip_in + 1)

        track_extract_data.removed_clips.pop(0)

    # Fix out clip and remove cut created clip if out was cut
    if track_extract_data.out_clip_in != -1:
        try:
            out_clip = _remove_clip(track, moved_index)
            if len(track_extract_data.removed_clips) > 0: # If overwrite was done inside single clip everything is already in order
                                                          # because setting in_clip back to its original length restores original state
                if out_clip.is_blanck_clip != True:
                    _insert_clip(track, track_extract_data.orig_out_clip, moved_index,
                             track_extract_data.out_clip_in, out_clip.clip_out)
                else: # blanks can't be resized, so must put in new blank
                    _insert_blank(track, moved_index, track_extract_data.out_clip_length)

                track_extract_data.removed_clips.pop(-1)
        except:
            # If moved clip/s were last in the track and were moved slightly 
            # forward and were still last in track after move
            # this leaves a trailing black that has been removed and this will fail
            pass

    # Put back old clips
    for i in range(0, len(track_extract_data.removed_clips)):
        clip = track_extract_data.removed_clips[i]
        _insert_clip(track, clip, moved_index + i, clip.clip_in,
                     clip.clip_out)
                     
    #_remove_trailing_blanks(track)

def _track_extract_range(over_in, over_out, track):
    track_extract_data = utils.EmptyClass()

    # Find out if overwrite starts after track end and pad track with blank if so
    if over_in >= track.get_length():
        track_extract_data.starts_after_end = True
        gap = over_out - track.get_length()
        _insert_blank(track, len(track.clips), gap)
    else:
        track_extract_data.starts_after_end = False
    
    # Cut at in point if not already on cut
    clip_in, clip_out = _overwrite_cut_track(track, over_in)
    track_extract_data.in_clip_out = clip_out

    # Cut at out point if not already on cut
    track_extract_data.orig_out_clip = None
    if track.get_length() > over_out:
        clip_in, clip_out = _overwrite_cut_track(track, over_out,  True)
        track_extract_data.out_clip_in = clip_in
        track_extract_data.out_clip_length = clip_out - clip_in + 1 # Cut blank can't be reconstructed with clip_in data as it is always 0 for blank, so we use this
        if clip_in != -1: # if we did cut we'll need to restore the dut out clip
                          # which is the original clip because 
            orig_index = track.get_clip_index_at(over_out - 1)
            track_extract_data.orig_out_clip = track.clips[orig_index] 
    else:
        track_extract_data.out_clip_in = -1
        
    # Splice out clips in overwrite range
    track_extract_data.removed_clips = []
    track_extract_data.in_index = track.get_clip_index_at(over_in)
    out_index = track.get_clip_index_at(over_out)

    for i in range(track_extract_data.in_index, out_index):
        removed_clip = _remove_clip(track, track_extract_data.in_index)
        track_extract_data.removed_clips.append(removed_clip)

    return track_extract_data

# ------------------------------------------------ SLOW/FAST MOTION
# "track","clip","clip_index","speed":speed}
def replace_with_speed_changed_clip(data):
    action = EditAction(_replace_with_speed_changed_clip_undo, _replace_with_speed_changed_clip_redo, data)
    return action

def _replace_with_speed_changed_clip_undo(self):
    pass

def _replace_with_speed_changed_clip_redo(self):
    # Create slowmo clip if it does not exists
    if not hasattr(self, "new_clip"):
        self.new_clip = current_sequence().create_slowmotion_producer(self.clip.path, self.speed)
    current_sequence().clone_clip_and_filters(self.clip, self.new_clip)
    
    _remove_clip(self.track, self.clip_index)
    _insert_clip(self.track, self.new_clip, self.clip_index, self.clip.clip_in, self.clip.clip_out)


    
