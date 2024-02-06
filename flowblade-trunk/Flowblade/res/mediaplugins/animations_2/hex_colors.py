"""
    Copyright 2022 Janne Liljeblad, licenced under GPL3. 
    See  <http://www.gnu.org/licenses/> for licence text.
"""

import cairo
import random
import math

import fluxity

# We're using globals instead of fctx.set_data_obj() here for some data.
cols = -1
rows = -1
shape_width = -1
shape_height = -1

def init_script(fctx):
    fctx.set_name("Hex Colors")
    fctx.set_version(1)
    fctx.set_author("Janne Liljeblad")
    
    fctx.add_editor("Hue", fluxity.EDITOR_COLOR, (0.3, 0.3, 0.3, 1.0))
    fctx.add_editor("Hue Change", fluxity.EDITOR_FLOAT_RANGE, (0.2, 0.1, 5.0))
    fctx.add_editor("Speed", fluxity.EDITOR_FLOAT_RANGE, (0.8, 0.1, 5.0))
    fctx.add_editor("Size", fluxity.EDITOR_FLOAT_RANGE, (50.0, 10.0, 300.0))
    fctx.add_editor("Random Seed", fluxity.EDITOR_INT, 42)
    
    # Points used to draw hexagons.
    _points = []
    for i in range(0, 6):
        ang = 2 * math.pi * float(i)/ 6.0 + math.pi / 6.0
        _points.append((math.cos(ang), math.sin(ang)))

    fctx.set_data_obj("points", _points)
    
def init_render(fctx):
    # The script is possibly rendered using multiple prosesses and we need to have the
    # same sequence of random numbers in all processes. If we don't set seed we'll get completely different
    # ball positions, colors and speeds in different rendering processes.
    random.seed(fctx.get_editor_value("Random Seed"))
        
    hue = fctx.get_editor_value("Hue")
    hr, hg, hb, alpha = hue
    fctx.set_data_obj("hue_tuple", hue)
    size = fctx.get_editor_value("Size")

    global shape_width, shape_height, cols, rows
    shape_width = size * 2.0 * math.cos(math.pi / 6.0)
    shape_height = size + size * math.sin(math.pi / 6.0)
    cols = int(fctx.get_profile_property(fluxity.PROFILE_WIDTH) / size + 2)
    rows = int(fctx.get_profile_property(fluxity.PROFILE_HEIGHT) / size + 2)
    number_hex = cols * rows

    middle_hues = []
    color_positions = []
    deltas = []
    delta_size = 0.03 * fctx.get_editor_value("Speed")
    hue_change_size = 0.1 * fctx.get_editor_value("Hue Change")

    for i in range(0, number_hex):
        color_positions.append(random.uniform(-1.0, 1.0))
        d = delta_size if random.uniform(-1.0, 1.0) > 0.0 else -delta_size
        deltas.append(d)

    fctx.set_data_obj("middle_hue", (hr,hg,hb))
    fctx.set_data_obj("color_positions", color_positions)
    fctx.set_data_obj("deltas", deltas)

def render_frame(frame, fctx, w, h):
    cr = fctx.get_frame_cr()

    bg_color = cairo.SolidPattern(*fctx.get_data_obj("hue_tuple"))
    color_positions = fctx.get_data_obj("color_positions")

    size = fctx.get_editor_value("Size")
    points = fctx.get_data_obj("points")
    hr, hg, hb = fctx.get_data_obj("middle_hue")
    color_positions = fctx.get_data_obj("color_positions")
    deltas = fctx.get_data_obj("deltas")

    x0 = -size / 2.0
    y0 = -size / 2.0
    hue_change_anim_range = 0.1 * fctx.get_editor_value("Hue Change")
    
    cr.set_source(bg_color)
    cr.rectangle(0, 0, w, h)
    cr.fill()

    for row in range(0, rows):
        yt = y0 + shape_height * row
        x_row = x0 + shape_width / 2.0  * (float(row) % 2.0)
        for col in range(0, cols):
            index = row * cols + col
            
            # get color for hex
            color_position = color_positions[index]
            delta = deltas[index]
            r = _clamp( hr + color_position * hue_change_anim_range)
            g = _clamp( hg + color_position * hue_change_anim_range)
            b = _clamp( hb + color_position * hue_change_anim_range)
            
            # animate color
            color_position = color_position + delta
            color_positions[index] = color_position
            if abs(color_position) > 1.0:
                if color_position > 1.0:
                    color_position = 1.0 - (color_position - 1.0)
                else:
                    color_position = -1.0 + (color_position + 1.0)
                color_positions[index] = color_position
                delta = -delta
                deltas[index] = delta
                
            # draw hex
            xt = x_row + shape_width * col
            cr.save()
            cr.translate(xt, yt)
            
            x, y = _point_mult(size, *points[0])
            cr.move_to(x, y)
            for i in range(1, 6):
                x, y = _point_mult(size, *points[i])
                cr.line_to(x, y)
            cr.close_path() 
            
            cr.set_source_rgb(r,g,b)
            cr.fill()
            cr.restore()
    

# ----------------------- helper funcs
def _clamp(v):
    return max(min(v, 1.0), 0.0)
    
def _point_mult(size, x, y):
    return (size * x, size * y)

