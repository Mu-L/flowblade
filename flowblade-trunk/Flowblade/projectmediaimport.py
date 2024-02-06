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

import copy
try:
    import mlt7 as mlt
except:
    import mlt
import locale
import os
import subprocess
import sys
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, Gio
from gi.repository import GLib

import appconsts
import atomicfile
import editorstate
import editorpersistance
import gui
import guiutils
import mltinit
import patternproducer
import persistance
import pickle
import processutils
import respaths
import renderconsumer
import translations
import userfolders
import utils

"""
This module implements media import from another project feature.

The easiest way to do it is to open file in own process and write media paths to disk.
There is so much bolierplate needed for this feature that it was best to create own module for it.
"""

MEDIA_ASSETS_IMPORT_FILE = "media_assets_import_file"
GENERATORS_IMPORT_FILE = "generators_import_file"

_info_window = None
_media_paths_written_to_disk_complete_callback = None

class ProjectLoadThread(threading.Thread):
    def __init__(self, filename):
        threading.Thread.__init__(self)
        self.filename = filename

    def run(self):
        GLib.timeout_add(0, self._update_info_window)
        
        persistance.show_messages = False
        target_project = persistance.load_project(self.filename, False, True)
        
        target_project.c_seq = target_project.sequences[target_project.c_seq_index]

        # Media file media assets and generator assets are handled a differently.
        media_assets = ""
        generator_assets = []

        for media_file_id, media_file in target_project.media_files.items():
            if isinstance(media_file, patternproducer.AbstractBinClip):
                continue
            if  media_file.container_data != None:
                # Generator clone
                generator_assets.append(copy.deepcopy(media_file.container_data))
            elif os.path.isfile(media_file.path):
                # File clone
                media_assets = media_assets + str(media_file.path) + "\n"

        with atomicfile.AtomicFileWriter(_get_assets_file(), "w") as afw:
            f = afw.get_file()
            f.write(media_assets)

        with atomicfile.AtomicFileWriter(_get_generators_file(), "wb") as afw:
            write_file = afw.get_file()
            pickle.dump(generator_assets, write_file)

        _shutdown()

    def _update_info_window(self):
        _info_window.info.set_text("Loading project  " + self.filename + "...\nPlease wait...")
        
class ProcesslauchThread(threading.Thread):
    def __init__(self, filename):
        threading.Thread.__init__(self)
        self.filename = filename

    def run(self):
        _write_files(self.filename)


# ----------------------------------------------------------- interface
def import_media_files(project_file_path, callback):
    
    global _media_paths_written_to_disk_complete_callback
    _media_paths_written_to_disk_complete_callback = callback

    # This or GUI freezes, we really can't do Popen.wait() in a Gtk thread
    process_launch_thread = ProcesslauchThread(project_file_path)
    process_launch_thread.start()

def get_imported_media():
    with open(_get_assets_file()) as f:
        files_list = f.readlines()

    files_list = [x.rstrip("\n") for x in files_list] 
    return files_list
    
def get_imported_generators():
    return utils.unpickle(_get_generators_file())

# ----------------------------------------------------------- data gathering process launch and callback to import files
def _write_files(filename):
    print("Starting media import...")
    FLOG = open(userfolders.get_cache_dir() + "log_media_import", 'w')
    p = subprocess.Popen([sys.executable, respaths.LAUNCH_DIR + "flowblademediaimport", filename], stdin=FLOG, stdout=FLOG, stderr=FLOG)
    p.wait()
    
    GLib.idle_add(_assets_write_complete)

def _assets_write_complete():
    _media_paths_written_to_disk_complete_callback()

# ------------------------------------------------------------ module internal
def _do_assets_write(filename):
    #_create_info_dialog()
    
    global load_thread
    load_thread = ProjectLoadThread(filename)
    load_thread.start()
        
def _get_assets_file():
    return userfolders.get_cache_dir() + MEDIA_ASSETS_IMPORT_FILE

def _get_generators_file():
    return userfolders.get_cache_dir() + GENERATORS_IMPORT_FILE
    
def _create_info_dialog():
    dialog = Gtk.Window(Gtk.WindowType.TOPLEVEL)
    dialog.set_title(_("Loading Media Import Project"))

    info_label = Gtk.Label(label="")
    status_box = Gtk.HBox(False, 2)
    status_box.pack_start(info_label, False, False, 0)
    status_box.pack_start(Gtk.Label(), True, True, 0)

    est_box = Gtk.HBox(False, 2)
    est_box.pack_start(Gtk.Label(label=""),False, False, 0)
    est_box.pack_start(Gtk.Label(), True, True, 0)

    progress_vbox = Gtk.VBox(False, 2)
    progress_vbox.pack_start(status_box, False, False, 0)
    progress_vbox.pack_start(est_box, False, False, 0)

    alignment = guiutils.set_margins(progress_vbox, 12, 12, 12, 12)

    dialog.add(alignment)
    dialog.set_default_size(400, 70)
    dialog.set_position(Gtk.WindowPosition.CENTER)
    dialog.show_all()

    dialog.info = info_label

    global _info_window
    _info_window = dialog


# ----------------------------------------------------------- main
def main(root_path, filename):
    # This the main for launched process, this is reached via 'flowblademediaimport' launcher file
    gtk_version = "%s.%s.%s" % (Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version())
    print("GTK+ version:", gtk_version)
    editorstate.gtk_version = gtk_version
    try:
        editorstate.mlt_version = mlt.LIBMLT_VERSION
    except:
        editorstate.mlt_version = "0.0.99" # magic string for "not found"

    # Read the XDG_* variables etc.
    userfolders.init()
    
    # Set paths.
    respaths.set_paths(root_path)

    # Load editor prefs.
    editorpersistance.load()

    # Create app.
    global _app
    _app = ProjectImportApp()
    _app.filename = filename
    _app.run(None)


class ProjectImportApp(Gtk.Application):
    def __init__(self, *args, **kwargs):
        Gtk.Application.__init__(self, application_id=None,
                                 flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.connect("activate", self.on_activate)

    def on_activate(self, data=None):
        # Themes
        gui.apply_theme(editorpersistance.prefs.theme)

        # Init mlt.
        repo = mltinit.init_with_translations()
        
        _create_info_dialog()
        
        GLib.idle_add(_do_assets_write, self.filename)

        self.add_window(_info_window)
        
def _shutdown():
    _app.quit()
