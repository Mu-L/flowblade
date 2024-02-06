"""
    Copyright 2022 Janne Liljeblad, licenced under GPL3. 
    See  <http://www.gnu.org/licenses/> for licence text.
"""

from gi.repository import Pango

import fluxity


ANIMATION_BY_LETTER = 0
ANIMATION_BY_WORD = 1
ANIMATION_BY_LINE = 2


def init_script(fctx):
    fctx.set_name("TypeWriter")
    fctx.set_version(1)
    fctx.set_author("Janne Liljeblad")
    fctx.add_editor("Text", fluxity.EDITOR_TEXT_AREA, "Lorem ipsum dolor sit amet,\nconsectetur adipiscing elit.\nAliquam non condimentum magna.")
    fctx.add_editor("Pos X", fluxity.EDITOR_INT, 100)
    fctx.add_editor("Pos Y", fluxity.EDITOR_INT, 100)
    fctx.add_editor("Centering", fluxity.EDITOR_OPTIONS, (0, ["Off", "Center", "Center Horizontal", "Center Vertical"]))
    fctx.add_editor("Animation Type", fluxity. EDITOR_OPTIONS, (0,["Letters", "Words", "Lines"]))
    fctx.add_editor("Steps Per Frame", fluxity.EDITOR_FLOAT, 0.5)
    fctx.add_editor("Font", fluxity.EDITOR_PANGO_FONT, fluxity.EDITOR_PANGO_FONT_DEFAULT_VALUES)
    fctx.add_editor("Line Gap", fluxity.EDITOR_INT, 5)
    
def init_render(fctx):
    # Get editor values
    font_data = fctx.get_editor_value("Font")
    text = fctx.get_editor_value("Text")
    step_speed = fctx.get_editor_value("Steps Per Frame")
    animation_type = fctx.get_editor_value("Animation Type")
    line_gap = fctx.get_editor_value("Line Gap")
    
    # Create typewriter object
    typewriter = TypeWriter(text, font_data, animation_type, step_speed, line_gap)
    fctx.set_data_obj("typewriter", typewriter)
    
def render_frame(frame, fctx, w, h):
    cr = fctx.get_frame_cr()
    x = fctx.get_editor_value("Pos X")
    y = fctx.get_editor_value("Pos Y") 
    typewriter = fctx.get_data_obj("typewriter")
    typewriter.draw_text(fctx, frame, cr, x, y)


class TypeWriter:

    CONSTRAINT_OFF = 0   
    CONSTRAINT_CENTER = 1
    CONSTRAINT_HORIZONTAL = 2
    CONSTRAINT_VERTICAL = 3
    
    def __init__(self, text, font_data, animation_type, step_speed, line_gap):
        self.text = text
        self.lines = text.splitlines()
        self.font_data = font_data
        self.animation_type = animation_type

        self.line_gap = line_gap
        self.step_speed = step_speed
        
    def draw_text(self, fctx, frame, cr, x, y):
        # Create line layouts.
        self.line_layouts = []
        for line_text in self.lines:
            line_layout = fctx.create_text_layout(self.font_data)
            line_layout.create_pango_layout(cr, line_text) # add text now that we have cairo context
            self.line_layouts.append(line_layout)
        
        if len(self.line_layouts) == 0:
            return

        max_width, height = self.get_text_area_size()
        # Moves text area top left to constrained position
        x, y = self.get_constrained_pos(fctx, x, y, max_width, height)

        # Compute line positions.
        pango_alignment = self.line_layouts[0].get_pango_alignment() # all lines have the same alignment
        line_positions = []
        if pango_alignment == Pango.Alignment.LEFT:
            for line_layout in self.line_layouts:
                w, h = line_layout.get_pixel_size()
                line_positions.append((x, y))
                y = y + h + self.line_gap
        elif pango_alignment == Pango.Alignment.CENTER:
            max_width, height = self.get_text_area_size()
            for line_layout in self.line_layouts:
                w, h = line_layout.get_pixel_size()
                line_positions.append((x + max_width/2 - w/2, y))
                y = y + h + self.line_gap
        else: # Pango.Alignment.RIGHT
            max_width, height = self.get_text_area_size()
            for line_layout in self.line_layouts:
                w, h = line_layout.get_pixel_size()
                line_positions.append((x + max_width - w, y))
                y = y + h + self.line_gap
        
        # Create line texts.
        line_texts = []
        if self.animation_type == ANIMATION_BY_LETTER:
            last_letter = int(frame * self.step_speed)

            line_first_char = 0
            for line_text in self.lines:
                line_last_char = line_first_char + len(line_text)
                if line_last_char < last_letter:
                    line_texts.append(line_text)
                elif line_first_char > last_letter:
                    line_texts.append("")
                else:
                    line_texts.append(line_text[0:last_letter - line_first_char])
                line_first_char = line_last_char
            
        elif self.animation_type == ANIMATION_BY_LINE:
            frame_steps = int(frame * self.step_speed)
            step = 0
            for line_text in self.lines:
                if frame_steps > step:
                    line_texts.append(line_text)
                else:
                    line_texts.append("")
                step += 1

        else: # ANIMATION_BY_WORD
            frame_steps = int(frame * self.step_speed)
            step = 0
            for line_text in self.lines:
                words = line_text.split(" ")
                line_text = ""
                for word in words:
                    if frame_steps > step:
                        line_text = line_text + word + " "
                    step += 1
            
                line_texts.append(line_text)    

        # Draw texts.
        for i in range(0, len(self.line_layouts)):
            line_layout = self.line_layouts[i]
            x, y = line_positions[i]
            txt = line_texts[i]
            line_layout.draw_layout(fctx, txt, cr, x, y)
    
    def get_text_area_size(self):
        max_width = 0
        height = 0
        for line_layout in self.line_layouts:
            w, h = line_layout.get_pixel_size()
            if w > max_width:
                max_width = w
            height = height + h + self.line_gap
        return (max_width, height)

    def get_constrained_pos(self, fctx, x, y, w, h):
         # Returns area position with centering applied.
         screen_w = fctx.get_profile_property(fluxity.PROFILE_WIDTH)
         screen_h = fctx.get_profile_property(fluxity.PROFILE_HEIGHT)
         constraints = fctx.get_editor_value("Centering")
         if constraints == TypeWriter.CONSTRAINT_CENTER or constraints == TypeWriter.CONSTRAINT_HORIZONTAL:
             x = round(screen_w / 2 - w / 2)
         if constraints == TypeWriter.CONSTRAINT_CENTER or constraints == TypeWriter.CONSTRAINT_VERTICAL:
             y = round(screen_h / 2 - h / 2)

         return (x, y)
