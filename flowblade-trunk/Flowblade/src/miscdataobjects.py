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

import appconsts

"""
Module for project data objects used my multiple modules and objects here are part of save files.

NOTE: IMPORTANT!!! We can't rename or remove anything here without BREAKING USER SAVE FILES!!!!!

NOTE: Do not use any external modules other then appconsts.
"""

import appconsts

TRANSCODE_ENCODING = appconsts.TRANSCODE_ENCODING
TRANSCODE_RELATIONS = appconsts.TRANSCODE_RELATIONS
INGEST_ACTION = appconsts.INGEST_ACTION

TRANSCODE_SELECTED_VARIABLEFR = appconsts.TRANSCODE_SELECTED_VARIABLEFR
TRANSCODE_SELECTED_IMGSEQ = appconsts.TRANSCODE_SELECTED_IMGSEQ
TRANSCODE_SELECTED_INTERLACED = appconsts.TRANSCODE_SELECTED_INTERLACED

TRANSCODE_ENCODING_NOT_SET = appconsts.TRANSCODE_ENCODING_NOT_SET
INGEST_ACTION_NOTHING = appconsts.INGEST_ACTION_NOTHING
INGEST_ACTION_TRANSCODE_SELECTED = appconsts.INGEST_ACTION_TRANSCODE_SELECTED
INGEST_ACTION_TRANSCODE_ALL = appconsts.INGEST_ACTION_TRANSCODE_ALL


class ProjectProxyEditingData:
    
    def __init__(self):
        self.proxy_mode = appconsts.USE_ORIGINAL_MEDIA
        self.create_rules = None # not impl.
        self.encoding = 0 # default is first found encoding
        self.size = 1 # default is half project size


class IngestTranscodeData:
    
    def __init__(self):
        self.data = {}
        self.data[TRANSCODE_ENCODING] = 0
        self.data[TRANSCODE_RELATIONS] = {}
        self.data[INGEST_ACTION] = 0

        self.data[TRANSCODE_SELECTED_VARIABLEFR] = True
        self.data[TRANSCODE_SELECTED_IMGSEQ] = True
        self.data[TRANSCODE_SELECTED_INTERLACED] = True

    def set_default_encoding(self, def_enc):
        self.data[INGEST_ENCODING] = def_enc
        
    def get_default_encoding(self):
        return self.data[TRANSCODE_ENCODING]

    def set_default_encoding(self, def_enc):
        self.data[TRANSCODE_ENCODING] = def_enc

    def get_action(self):
        return self.data[INGEST_ACTION]

    def set_action(self, action):
        self.data[INGEST_ACTION] = action
