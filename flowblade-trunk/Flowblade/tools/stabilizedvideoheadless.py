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

try:
    import mlt7 as mlt
except:
    import mlt
    
import os
import threading
import time

import ccrutils
import mltheadlessutils
import mltprofiles
import renderconsumer

_render_thread = None


# ----------------------------------------------------- module interface with message files
# We are using message files to communicate with application.
def session_render_complete(parent_folder, session_id):
    return ccrutils.session_render_complete(parent_folder, session_id)

def get_session_status(parent_folder, session_id):
    msg = ccrutils.get_session_status_message(parent_folder, session_id)
    if msg == None:
        return None
    fraction, elapsed = msg.split(" ")
    return (fraction, elapsed)
    
def abort_render(parent_folder, session_id):
    ccrutils.abort_render(parent_folder, session_id)

def delete_session_folders(parent_folder, session_id):
     ccrutils.delete_internal_folders(parent_folder, session_id)

# --------------------------------------------------- render thread launch
def main(root_path, session_id, parent_folder, write_file, results_file, 
         profile_desc, encoding_option_index, quality_option_index, source_path):
        
    mltheadlessutils.mlt_env_init(root_path, parent_folder, session_id)

    global _render_thread
    _render_thread = StaxbilizedVideoRenderThread(  write_file, results_file, profile_desc, encoding_option_index,
                                                    quality_option_index, source_path)
    _render_thread.start()

       

class StaxbilizedVideoRenderThread(threading.Thread):

    def __init__(self, write_file, results_file, profile_desc, encoding_option_index,
                                                    quality_option_index, source_path):
        threading.Thread.__init__(self)

        self.write_file = write_file
        self.profile_desc = profile_desc
        self.encoding_option_index = int(encoding_option_index)
        self.quality_option_index = int(quality_option_index)
        self.source_path = source_path
        self.results_file = results_file

        self.abort = False

    def run(self):
        self.start_time = time.monotonic()

        profile = mltprofiles.get_profile(self.profile_desc) 
        producer = mlt.Producer(profile, str(self.source_path)) # this runs 0.5s+ on some clips
        
        stabilize_filter = mlt.Filter(profile, "vidstab")
        stabilize_filter.set("results", str(self.results_file))

        # Add filter to producer.
        producer.attach(stabilize_filter)

        # Create tractor and track to get right length
        tractor = renderconsumer.get_producer_as_tractor(producer, producer.get_length() - 1)
        consumer = renderconsumer.get_render_consumer_for_encoding_and_quality(self.write_file, profile, self.encoding_option_index, self.quality_option_index)
        
        # start and end frames, renderer stop behaviour
        start_frame = 0
        end_frame = producer.get_length() - 1

        # Launch render
        self.render_player = renderconsumer.FileRenderPlayer(self.write_file, tractor, consumer, start_frame, end_frame)
        self.render_player.wait_for_producer_end_stop = True
        self.render_player.start()

        while self.render_player.stopped == False:
            
            self.check_abort_requested()
            
            if self.abort == True:
                self.render_player.shutdown()
                os._exit(0) # We are having some issues with causing processor usage even after reaching here.
                return
            
            fraction = self.render_player.get_render_fraction()
            self.render_update(fraction)

            time.sleep(0.3)

        # Write out completed flag file.
        ccrutils.write_completed_message()

        global _render_thread
        _render_thread = None

        self.render_player.shutdown()        
        os._exit(0) # We are having some issues with causing processor usage even after reaching here.
                
    def check_abort_requested(self):
        self.abort = ccrutils.abort_requested()

    def render_update(self, fraction):
        elapsed = time.monotonic() - self.start_time
        msg = str(fraction) + " " + str(elapsed)
        ccrutils.write_status_message(msg)



