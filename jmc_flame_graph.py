# Copyright 2017 Justin Forder

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import with_statement

import sys
from Tkinter import Tk, Toplevel, Canvas
from tkFont import Font


# ========== Model ==========

class CallTreeNode:
    """A node in a call tree from CPU sampling."""

    def __init__(self, signature, samples):
        self.signature = signature
        self.samples = samples
        self.children = []

    def add_child(self, call_tree_node):
        self.children.append(call_tree_node)

    def depth(self):
        """Depth of the call tree rooted here."""
        return 1 + max([c.depth() for c in self.children] or [0])


class CallForest:
    """A named forest of call trees from CPU sampling."""

    def __init__(self, name):
        self.name = name
        self.roots = []

    def add_root(self, call_tree_node):
        self.roots.append(call_tree_node)

    def samples(self):
        return sum([r.samples for r in self.roots])

    def depth(self):
        """Depth of deepest call tree."""
        return max([r.depth() for r in self.roots] or [0])


# ========== Parser ==========

class JmcCallTreeLine:
    INDENT_SPACES = 3

    def __init__(self, line):
        self.chunks = line.split('\t')

    def signature(self):
        return self.chunks[0].lstrip()

    def indentation(self):
        return len(self.chunks[0]) - len(self.signature())

    def depth_below_root(self):
        return self.indentation() / self.INDENT_SPACES

    def samples(self):
        return int(self.chunks[1].replace(',', ''))

    def create_call_tree_node(self):
        return CallTreeNode(self.signature(), self.samples())


class CallTreeNodeStack:
    def __init__(self):
        self.stack = []

    def push(self, call_tree_node):
        self.stack.append(call_tree_node)

    def top(self):
        return self.stack[-1]

    def drop_to(self, depth):
        # TODO: raise exception if stack depth < depth
        self.stack = self.stack[:depth]


class JmcCallForestParser:
    def __init__(self, filename):
        self.filename = filename
        self.stack = CallTreeNodeStack()
        self.call_forest = CallForest(filename)

    def parse(self):
        with open(self.filename, 'r') as f:
            for line in f:
                self.process_line(line)
        return self.call_forest

    def process_line(self, line):
        ctl = JmcCallTreeLine(line)
        d = ctl.depth_below_root()
        ctn = ctl.create_call_tree_node()
        self.stack.drop_to(d)
        if d == 0:
            self.call_forest.add_root(ctn)
        else:
            self.stack.top().add_child(ctn)
        self.stack.push(ctn)


# ========== Renderer ==========

class TkFlameGraphRenderer:
    """Renders a call forest to a flame graph using Tk graphics."""

    def __init__(self, call_forest, tk, width, height, colours):
        self.call_forest = call_forest
        self.tk = tk
        self.width = width
        self.height = height
        self.colours = colours
        self.font = ('Courier', 12)
        self.character_width = 0.1 * Font(family='Courier', size=12).measure('mmmmmmmmmm')
        self.min_width_for_text = 3 * self.character_width
        self.min_height_for_text = 10
        self.x_scale = float(width) / call_forest.samples()
        self.y_scale = float(height) / call_forest.depth()
        self.top = Toplevel(tk)
        self.top.title(call_forest.name)
        self.canvas = Canvas(self.top, width=width, height=height)
        self.canvas.pack()

    def render(self):
        x = 2.0  # ************************************
        y = self.height - self.y_scale
        sorted_roots = sorted(self.call_forest.roots, key=lambda n: n.signature)
        for root in sorted_roots:
            self.render_call_tree(root, x, y)
            x += self.x_scale * root.samples
        # Not sure why I need this
        self.canvas.tag_raise('signature')

    def render_call_tree(self, root, x, y):
        self.render_call_tree_node(root, x, y)
        child_x = x
        child_y = y - self.y_scale
        sorted_children = sorted(root.children, key=lambda n: n.signature)
        for child in sorted_children:
            self.render_call_tree(child, child_x, child_y)
            child_x += self.x_scale * child.samples

    def render_call_tree_node(self, node, x, y):
        bbox = self.bounding_box(node, x, y)
        colour = self.colours.colour_for(node)
        id = self.canvas.create_rectangle(bbox, fill=colour)
        self.bind_events(id, node)
        self.text(node, x, y)

    def bounding_box(self, node, x, y):
        left = x
        right = left + self.x_scale * node.samples
        top = y
        bottom = y + self.y_scale
        bbox = (left, top, right, bottom)
        return bbox

    def text(self, node, x, y):
        height = self.y_scale
        width = self.x_scale * node.samples
        if height > self.min_height_for_text and width > self.min_width_for_text:
            sig = node.signature
            i = sig.rfind('.')
            method = sig[i:]
            char_width = int(width / self.character_width)
            chars = method[:char_width] if len(method) >= char_width else sig[-char_width:]
            # chars = node.signature[:char_width]
            id = self.canvas.create_text((x + width / 2, y + height / 2),
                                         text=chars, anchor='center', font=self.font, tags='signature')
            self.bind_events(id, node)

    def bind_events(self, id, node):
        self.canvas.tag_bind(id, '<Enter>', lambda e: self.mouse_enter(e, node))
        self.canvas.tag_bind(id, '<Leave>', self.mouse_leave)
        self.canvas.tag_bind(id, '<Double-Button-1>', lambda e: self.zoom_in(e, node))

    def mouse_enter(self, event, node):
        self.show_tooltip(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y), node)

    def mouse_leave(self, event):
        self.hide_tooltip()

    def zoom_in(self, event, new_root):
        new_call_forest = CallForest(new_root.signature)
        new_call_forest.add_root(new_root)
        new_renderer = TkFlameGraphRenderer(new_call_forest, self.tk, self.width, self.height, self.colours)
        new_renderer.render()

    def show_tooltip(self, x, y, node):
        signature, samples = node.signature, node.samples
        percentage = (100.0 * samples) / self.call_forest.samples()
        text = '{} {} {:.2f}%'.format(signature, samples, percentage)
        c = self.canvas
        y_offset = (-10 if y > 30 else 20)
        anchor = 'sw' if x < self.width * 0.3 else 's' if x < self.width * 0.7 else 'se'
        label = c.create_text((x, y + y_offset), text=text, anchor=anchor, tags='tooltip', font=('Courier', 12))
        bounds = c.bbox(label)
        c.create_rectangle(bounds, fill='white', width=0, tags='tooltip')
        c.tag_raise(label)
        pass

    def hide_tooltip(self):
        self.canvas.delete('tooltip')


class Colours:
    """Provides colours based on prefix of signature."""

    def __init__(self):
        self.prefix_to_colour = [
            ('oracle', 'yellow'),
            ('org.springframework', 'spring green'),
            ('java.io', 'orange'),
            ('com.google', 'gray'),
            ('org.jboss', 'red')]

    def colour_for(self, node):
        for (prefix, colour) in self.prefix_to_colour:
            if node.signature.startswith(prefix):
                return colour
        return 'white'


# ========== Main ==========

def main():
    filename = sys.argv[1]
    if filename:
        parser = JmcCallForestParser(filename)
        call_forest = parser.parse()
        tk = Tk()
        tk.withdraw()  # hide root Tk window - but this prevents shutdown when the last window is closed.
        colours = Colours()
        width, height = 1200, 800
        renderer = TkFlameGraphRenderer(call_forest, tk, width, height, colours)
        renderer.render()
        tk.mainloop()


if __name__ == '__main__':
    main()
