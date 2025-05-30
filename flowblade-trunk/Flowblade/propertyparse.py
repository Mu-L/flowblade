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
Modules provides functions that:
- parse strings to property tuples or argument dicts.
- build value strings from property tuples.
"""
import json

import appconsts
import animatedvalue
from editorstate import current_sequence
from editorstate import PROJECT
import respaths
import utils

PROP_INT = appconsts.PROP_INT
PROP_FLOAT = appconsts.PROP_FLOAT
PROP_EXPRESSION = appconsts.PROP_EXPRESSION

NAME = appconsts.NAME
ARGS = appconsts.ARGS
SCREENSIZE = "SCREENSIZE"                                   # replace with "WIDTHxHEIGHT" of profile screensize in pix
SCREENSIZE2 = "Screensize2"                                 # replace with "WIDTH HEIGHT" of profile screensize in pix
WIPE_PATH = "WIPE_PATH"                                     # path to folder containing wipe resource images
SCREENSIZE_WIDTH = "SCREENSIZE_WIDTH"                       # replace with width of profile screensize in pix
SCREENSIZE_HEIGHT = "SCREENSIZE_HEIGHT"                     # replace with height of profile screensize in pix
VALUE_REPLACEMENT = "value_replacement"                     # attr name for replacing value after clip is known
FADE_IN_REPLAMENT = "fade_in_replament"                     # replace with fade in keyframes
FADE_OUT_REPLAMENT = "fade_out_replament"                   # replace with fade out keyframes
FADE_IN_OUT_REPLAMENT = "fade_in_out_replament"             # replace with fade in and out keyframes
WIPE_IN_REPLAMENT = "wipe_in_replament"


# ------------------------------------------- parse funcs
def node_list_to_properties_array(node_list):
    """
    Returns list of property tuples of type (name, value, type)
    """
    properties = []
    for node in node_list:
        p_name = node.getAttribute(NAME)
        p_value = node.firstChild.nodeValue # If crash here, check if 'exptype' set in string value param args in filters.xml.
        p_type = _property_type(p_value)
        properties.append((p_name, p_value, p_type))
    return properties

def node_to_property(node):
        p_name = node.getAttribute(NAME)
        p_value = node.firstChild.nodeValue
        p_type = _property_type(p_value)
        return (p_name, p_value, p_type)

def node_list_to_non_mlt_properties_array(node_list):
    """
    Returns list of property tuples of type (name, value, type)
    """
    properties = []
    for node in node_list:
        p_name = node.getAttribute(NAME)
        p_value = node.firstChild.nodeValue
        p_type = _property_type(p_value)
        properties.append((p_name, p_value, p_type))
    return properties

def node_list_to_args_dict(node_list):
    """
    Returns dict of type property_name -> property_args_string
    """
    property_args = {}
    for node in node_list:
        p_name = node.getAttribute(NAME)
        p_args = node.getAttribute(ARGS)
        property_args[p_name] = p_args

    return property_args

def node_list_to_extraeditors_array(node_list):
    editors = []
    for node in node_list:
        e_name = node.getAttribute(NAME)
        editors.append(e_name)
    return editors

def node_list_to_extraeditors_args_dict(node_list):
    args_dict = {}
    for node in node_list:
        e_name = node.getAttribute(NAME)
        args = node.getAttribute(ARGS)
        if args == "":
            args = None
        args_dict[e_name] = args

    return args_dict

def args_string_to_args_dict(args_str):
    """
    Returns key->value dict of property args.
    """
    args_dict = {}
    args = args_str.split(" ")
    for arg in args:
        sides = arg.split("=")
        args_dict[sides[0]] = sides[1]
    return args_dict


# ------------------------------------------- key word replace functions
def replace_value_keywords(properties, profile):
    """
    Property value expressions may have keywords in default values that 
    need to be replaced with other expressions or int values when containing
    objects first become active.
    """
    sreensize_expr = str(profile.width()) + "x" + str(profile.height())
    sreensize_expr_2 = str(profile.width()) + " " + str(profile.height())
    sreensize_width = str(profile.width())
    sreensize_height = str(profile.height())
    for i in range(0, len(properties)):
        name, value, prop_type = properties[i]
        if prop_type == PROP_EXPRESSION:
            if SCREENSIZE_WIDTH in value:
                value = value.replace(SCREENSIZE_WIDTH, sreensize_width)
                prop_type = 0 # value is int after replace
            elif SCREENSIZE_HEIGHT in value:
                value = value.replace(SCREENSIZE_HEIGHT, sreensize_height)
                prop_type = 0 # value is int after replace
            elif SCREENSIZE in value:
                value = value.replace(SCREENSIZE, sreensize_expr)
            elif SCREENSIZE2 in value:
                value = value.replace(SCREENSIZE2, sreensize_expr_2)
            elif WIPE_PATH in value:
                value = value.replace(WIPE_PATH, respaths.WIPE_RESOURCES_PATH)

            properties[i] = (name, value, prop_type)

def replace_values_using_clip_data(properties, info, clip):
    """
    Property value expressions may need to be replaced with expressions that can only be created
    with knowing clip.
    """
    replacement_happened = False
    for i in range(0, len(properties)):
        prop_name, value, prop_type = properties[i]
        
        if prop_type == PROP_EXPRESSION:
            args_str = info.property_args[prop_name]
            args_dict = args_string_to_args_dict(args_str)
            
            for arg_name in args_dict:
                if arg_name == VALUE_REPLACEMENT:
                    arg_val = args_dict[arg_name]
                    clip_length = clip.clip_length()
                    fade_length = PROJECT().get_project_property(appconsts.P_PROP_DEFAULT_FADE_LENGTH)
                    
                    if arg_val == FADE_IN_REPLAMENT:
                        frame_1 = clip.clip_in
                        frame_2 = clip.clip_in + fade_length
                        value = ""
                        if frame_1 != 0:
                            value += "0=0;"
                        
                        value += str(frame_1) + "=0;" + str(frame_2) + "=1"

                        properties[i] = (prop_name, value, prop_type)
                        replacement_happened = True
                    elif arg_val == FADE_OUT_REPLAMENT:
                        frame_1 = clip.clip_out - fade_length
                        frame_2 = clip.clip_out
                        
                        if clip_length > fade_length:
                            value = "0=1;" + str(frame_1) + "=1;" + str(frame_2) + "=0"
                        else:
                            value = "0=1;" + str(frame_2) + "=0"
                        properties[i] = (prop_name, value, prop_type)
                        replacement_happened = True
                    elif arg_val == FADE_IN_OUT_REPLAMENT:
                        frame_1 = clip.clip_in
                        frame_2 = clip.clip_in + fade_length
                        frame_3 = clip.clip_out - fade_length
                        frame_4 = clip.clip_out
                        value = ""
                        if frame_1 != 0:
                            value += "0=0;"
                            
                        if clip_length > 40:
                            value += str(frame_1) + "=0;" + str(frame_2) + "=1;"
                            value += str(frame_3) + "=1;" + str(frame_4) + "=0"
                        else:
                            clip_half = int(clip_length//2)
                            value += str(frame_1) + "=0;"  + str(frame_1 + clip_half) + "=1;" + str(frame_4) + "=0"

                        properties[i] = (prop_name, value, prop_type)
                        replacement_happened = True
                    elif arg_val == WIPE_IN_REPLAMENT:
                        frame_1 = clip.clip_in
                        frame_2 = clip.clip_in + int(round(utils.fps())) # Make 1 second the default.
                        value = ""
                        if frame_1 != 0:
                            value += "0=0;"
                        
                        value += str(frame_1) + "=0;" + str(frame_2) + "=100"

                        properties[i] = (prop_name, value, prop_type)
                        replacement_happened = True
    
    return replacement_happened

def get_args_num_value(val_str):
    """
    Returns numerical value for expression in property
    args. 
    """
    try: # attempt int
        return int(val_str)
    except:
        try:# attempt float
            return float(val_str)
        except:
            # attempt expression
            if val_str == SCREENSIZE_WIDTH:
                return current_sequence().profile.width()
            elif val_str == SCREENSIZE_HEIGHT:
                return current_sequence().profile.height()
    return None

# ------------------------------------------ kf editor values strings to kf arrays funcs
def single_value_keyframes_string_to_kf_array(keyframes_str, out_to_in_func):
    new_keyframes = []
    keyframes_str = keyframes_str.strip('"') # expressions have sometimes quotes that need to go away
    kf_tokens = keyframes_str.split(";")
    for token in kf_tokens:
        kf_type, sides = animatedvalue.parse_kf_token(token)

        # Find out saved keyframe type here.
        add_kf = (int(sides[0]), out_to_in_func(float(sides[1])), kf_type) # kf = (frame, value, type)
        new_keyframes.append(add_kf)

    return new_keyframes
    
def geom_keyframes_value_string_to_opacity_kf_array(keyframes_str, out_to_in_func):
    # THIS SHOULD ONLY BE IN DEPRECATED COMPOSITORS
    # Parse "composite:geometry" properties value string into (frame,opacity_value)
    # keyframe tuples.
    new_keyframes = []
    keyframes_str = keyframes_str.strip('"') # expression have sometimes quotes that need to go away
    kf_tokens =  keyframes_str.split(";")
    for token in kf_tokens:
        kf_type, sides = animatedvalue.parse_kf_token(token)
        values = sides[1].split(':')

        add_kf = (int(sides[0]), out_to_in_func(float(values[2])), kf_type) # kf = (frame, opacity, type)
        new_keyframes.append(add_kf)

def geom_keyframes_value_string_to_geom_kf_array(keyframes_str, out_to_in_func):
    # Parse "composite:geometry" properties value string into (frame, source_rect, opacity)
    # keyframe tuples.
    new_keyframes = []
    keyframes_str = keyframes_str.strip('"') # expression have sometimes quotes that need to go away
    kf_tokens =  keyframes_str.split(';')
    for token in kf_tokens:
        kf_type, sides = animatedvalue.parse_kf_token(token)
            
        values = sides[1].split(':')
        pos = values[0].split('/')
        size = values[1].split('x')
        source_rect = [int(pos[0]), int(pos[1]), int(size[0]), int(size[1])] #x,y,width,height
        add_kf = (int(sides[0]), source_rect, out_to_in_func(float(values[2])), kf_type)
        new_keyframes.append(add_kf)
 
    return new_keyframes

def rect_keyframes_value_string_to_geom_kf_array(keyframes_str, out_to_in_func):
    # Parse "composite:geometry" properties value string into (frame, source_rect, opacity, kf_type)
    # keyframe tuples.
    new_keyframes = []
    keyframes_str = keyframes_str.strip('"') # expression have sometimes quotes that need to go away
    kf_tokens =  keyframes_str.split(';')
    for token in kf_tokens:
        kf_type, sides = animatedvalue.parse_kf_token(token)

        values = sides[1].split(' ')
        x = values[0]
        y = values[1]
        w = values[2] 
        h = values[3] 
        source_rect = [int(x), int(y), int(w), int(h)] #x,y,width,height
        add_kf = (int(sides[0]), source_rect, out_to_in_func(float(1)), kf_type)
        new_keyframes.append(add_kf)
    
    return new_keyframes

def rect_NO_keyframes_value_string_to_geom_kf_array(rect_str, out_to_in_func):
    # Parse "x y w h" properties value string into single (0, source_rect, 1.0, appconsts.KEYFRAME_LINEAR)
    # keyframe tuple.
    new_keyframes = []
    value_str = rect_str.strip('"') # expressions have sometimes quotes that need to go away
    values = rect_str.split(' ')
    x = values[0]
    y = values[1]
    w = values[2] 
    h = values[3] 
    source_rect = [int(x), int(y), int(w), int(h)] # x, y, width, height
    add_kf = (0, source_rect, 1.0, appconsts.KEYFRAME_LINEAR)
    new_keyframes.append(add_kf)

    return new_keyframes
    
def rotating_geom_keyframes_value_string_to_geom_kf_array(keyframes_str, out_to_in_func):
    # THIS WAS CREATED FOR frei0r cairoaffineblend FILTER. That filter has to use a very particular parameter values
    # scheme to satisfy the frei0r requirement of all float values being in range 0.0 - 1.0.
    #
    # Parse extraeditor value properties value string into (frame, [x, y, x_scale, y_scale, rotation], opacity)
    # keyframe tuples used by keyframeeditorcanvas.RotatingEditCanvas editor.
    new_keyframes = []
    screen_width = current_sequence().profile.width()
    screen_height = current_sequence().profile.height()
    keyframes_str = keyframes_str.strip('"') # expression have sometimes quotes that need to go away
    kf_tokens =  keyframes_str.split(';')
    for token in kf_tokens:
        kf_type, sides = animatedvalue.parse_kf_token(token)
            
        values = sides[1].split(':')
        frame = int(sides[0])
        # Get values and convert "frei0r.cairoaffineblend" values to editor values
        # This is done because all frei0r plugins require values in range 0 - 1
        x = _get_pixel_pos_from_frei0r_cairo_pos(float(values[0]), screen_width)
        y = _get_pixel_pos_from_frei0r_cairo_pos(float(values[1]), screen_height)
        x_scale = _get_scale_from_frei0r_cairo_scale(float(values[2]))
        y_scale = _get_scale_from_frei0r_cairo_scale(float(values[3]))
        rotation = float(values[4]) * 360
        opacity = float(values[5]) * 100
        source_rect = [x,y,x_scale,y_scale,rotation]
        add_kf = (frame, source_rect, float(opacity), kf_type)
        new_keyframes.append(add_kf)

    return new_keyframes

def filter_rotating_geom_keyframes_value_string_to_geom_kf_array(keyframes_str, out_to_in_func):
    screen_width = current_sequence().profile.width()
    screen_height = current_sequence().profile.height()
    
    new_keyframes = []

    keyframes_str = keyframes_str.strip('"') # expressions have sometimes quotes that need to go away
    kf_tokens =  keyframes_str.split(';')
    for token in kf_tokens:
        frame, value, kf_type = get_token_frame_value_type(token)
        values = value.split(':')

        # keyframecanvas.RotatingEditCanvas editor uses x scale and y scale with normalized values,
        # whereas "affine.transition.rect" uses source image width and height.
        x_scale = float(values[2]) / float(screen_width)
        y_scale = float(values[3]) / float(screen_height)

        # keyframecanvas.RotatingEditCanvas editor considers x anf y values position of
        # anchor point around which image is rotated.
        #
        # MLT property "affine.transition.rect" considers x and y values amount translation
        # and rotate image automatically around its translated center point.
        #
        # So the we need to add half of width and height to mlt values AND 
        # additional linear correction based on applied scaling when creating
        # keyframes for keyframecanvas.RotatingEditCanvas editor.
        x = float(values[0]) + float(screen_width) / 2.0 + \
            ((x_scale * screen_width) - screen_width) / 2.0
        y = float(values[1]) + float(screen_height) / 2.0 + \
            ((y_scale * screen_height) - screen_height) / 2.0

        rotation = float(values[4]) # degrees all around
        opacity = 100 # not edited

        source_rect = [x,y,x_scale,y_scale,rotation]
        add_kf = (int(frame), source_rect, float(opacity), kf_type)
        new_keyframes.append(add_kf)
        
    return new_keyframes

def gradient_tint_geom_keyframes_value_string_to_geom_kf_array(keyframes_str, out_to_in_func):
    screen_width = current_sequence().profile.width()
    screen_height = current_sequence().profile.height()

    new_keyframes = []

    keyframes_str = keyframes_str.strip('"') # expressions have sometimes quotes that need to go away
    kf_tokens =  keyframes_str.split(';')

    for token in kf_tokens:
        frame, value, kf_type = get_token_frame_value_type(token)
        values = value.split(':')
        values_floats = [float(x) for x in values]
        start_x = values_floats[0] * screen_width
        start_y = values_floats[1] * screen_height
        end_x = values_floats[2] * screen_width
        end_y =  values_floats[3] * screen_height
        add_kf = (int(frame), (start_x, start_y, end_x, end_y), kf_type)

        new_keyframes.append(add_kf)
    
    return new_keyframes

def crop_geom_keyframes_value_string_to_geom_kf_array(keyframes_str, out_to_in_func):
    screen_width = current_sequence().profile.width()
    screen_height = current_sequence().profile.height()

    new_keyframes = []

    keyframes_str = keyframes_str.strip('"') # expressions have sometimes quotes that need to go away
    kf_tokens =  keyframes_str.split(';')

    for token in kf_tokens:
        frame, value, kf_type = get_token_frame_value_type(token)
        values = value.split(':')
        values_floats = [float(x) for x in values]
        left = values_floats[0] * screen_width
        right = (1.0 - values_floats[1]) * screen_width
        top = values_floats[2] * screen_height
        bottom = (1.0 - values_floats[3]) * screen_height
        x = left
        y = top
        w = right - left
        h = bottom - top
        dummy_opacity = 1.0 # historical artifat that has not been refactored out, used geom editor 
                            # keyframeditcanvas.BoxEditCanvas assumes opacity to be there.
        add_kf = (int(frame), [x, y, w, h], dummy_opacity,  kf_type)

        new_keyframes.append(add_kf)

    return new_keyframes

def rotomask_json_value_string_to_kf_array(keyframes_str, out_to_in_func):
    new_keyframes = []
    json_obj = json.loads(keyframes_str)
    for kf in json_obj:
        kf_obj = json_obj[kf]
        add_kf = (int(kf), kf_obj, appconsts.KEYFRAME_LINEAR) # Rotomask has own kf system and type KEYFRAME_LINEAR is here just to work with other components.
        new_keyframes.append(add_kf)

    return sorted(new_keyframes, key=lambda kf_tuple: kf_tuple[0]) 

def get_token_frame_value_type(token):
    kf_type, sides = animatedvalue.parse_kf_token(token)

    # returns (frame, value, kf_type)
    return(sides[0], sides[1], kf_type)

# ----------------------------------------------------------------------------- AFFINE BLEND
def _get_roto_geom_frame_value(token):
    kf_type, sides = animatedvalue.parse_kf_token(token)
    
    return(sides[0], sides[1], kf_type)

def _get_eq_str(kf_type):
    return animatedvalue.TYPE_TO_EQ_STRING[kf_type]
    
def rotating_ge_write_out_keyframes(ep, keyframes):
    x_val = ""
    y_val = ""
    x_scale_val = ""
    y_scale_val = ""
    rotation_val = ""
    opacity_val = ""

    for kf in keyframes:
        frame, transf, opacity, kf_type = kf
        x, y, x_scale, y_scale, rotation = transf
        
        eq_str = _get_eq_str(kf_type)
            
        x_val += str(frame) + eq_str + str(get_frei0r_cairo_position(x, ep.profile_width)) + ";"
        y_val += str(frame) + eq_str + str(get_frei0r_cairo_position(y, ep.profile_height)) + ";"
        x_scale_val += str(frame) + eq_str + str(get_frei0r_cairo_scale(x_scale)) + ";"
        y_scale_val += str(frame) + eq_str + str(get_frei0r_cairo_scale(y_scale)) + ";"
        rotation_val += str(frame) + eq_str + str(rotation / 360.0) + ";"
        opacity_val += str(frame) + eq_str + str(opacity / 100.0) + ";"

    x_val = x_val.strip(";")
    y_val = y_val.strip(";")
    x_scale_val = x_scale_val.strip(";")
    y_scale_val = y_scale_val.strip(";")
    rotation_val = rotation_val.strip(";")
    opacity_val = opacity_val.strip(";")
   
    ep.x.write_value(x_val)
    ep.y.write_value(y_val)
    ep.x_scale.write_value(x_scale_val)
    ep.y_scale.write_value(y_scale_val)
    ep.rotation.write_value(rotation_val)
    ep.opacity.write_value(opacity_val)

def rotating_ge_update_prop_value(ep):
    # duck type members
    x_tokens = ep.x.value.split(";")
    y_tokens = ep.y.value.split(";")
    x_scale_tokens = ep.x_scale.value.split(";")
    y_scale_tokens = ep.y_scale.value.split(";")
    rotation_tokens = ep.rotation.value.split(";")
    opacity_tokens = ep.opacity.value.split(";")
    
    value = ""
    for i in range(0, len(x_tokens)): # these better match, same number of keyframes for all values, or this will not work
        frame, x, kf_type = _get_roto_geom_frame_value(x_tokens[i])
        frame, y, kf_type = _get_roto_geom_frame_value(y_tokens[i])
        frame, x_scale, kf_type = _get_roto_geom_frame_value(x_scale_tokens[i])
        frame, y_scale, kf_type = _get_roto_geom_frame_value(y_scale_tokens[i])
        frame, rotation, kf_type = _get_roto_geom_frame_value(rotation_tokens[i])
        frame, opacity, kf_type = _get_roto_geom_frame_value(opacity_tokens[i])

        eq_str = _get_eq_str(kf_type)
        
        frame_str = str(frame) + eq_str + str(x) + ":" + str(y) + ":" + str(x_scale) + ":" + str(y_scale) + ":" + str(rotation) + ":" + str(opacity)
        value += frame_str + ";"

    ep.value = value.strip(";")
         
def _get_pixel_pos_from_frei0r_cairo_pos(value, screen_dim):
    # convert positions from range used by frei0r cairo plugins to pixel values
    return -2.0 * screen_dim + value * 5.0 * screen_dim
    
def _get_scale_from_frei0r_cairo_scale(scale):
    return scale * 5.0

def get_frei0r_cairo_scale(scale):
    return scale / 5.0
    
def get_frei0r_cairo_position(pos, screen_dim):
    pix_range = screen_dim * 5.0
    range_pos = pos + screen_dim * 2.0
    return range_pos / pix_range



#------------------------------------------------------ util funcs
def _property_type(value_str):
    """
    Gets property type from value string by trying to interpret it 
    as int or float, if both fail it is considered an expression.
    """
    try:
        int(value_str)
        return PROP_INT
    except:
        try:
            float(value_str)
            return PROP_FLOAT
        except:
            return PROP_EXPRESSION

def set_property_value(properties, prop_name, prop_value):
    for i in range(0, len(properties)):
        name, value, t = properties[i]
        if prop_name == name:
            properties[i] = (name, prop_value, t)

def get_property_value(properties, prop_name):
    for i in range(0, len(properties)):
        name, value, t = properties[i]
        if prop_name == name:
            return value
    
    return None
