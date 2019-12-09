import logging

try:
    import urwid
except ImportError:
    urwid_found = False
else:
    urwid_found = True


class Selector:
    def menu(self):
        body = [urwid.Text(self.title), urwid.Divider()]
        for c in self.entries:
            button = urwid.Button(c.name)
            urwid.connect_signal(button, "click", self.item_chosen, c)
            body.append(urwid.AttrMap(button, None, focus_map="reversed"))
        return urwid.ListBox(urwid.SimpleFocusListWalker(body))

    def item_chosen(self, button, choice):
        self._loop.stop()
        self.callback(choice)

    def __init__(self, entries, callback, title="Select a host"):
        self.entries = entries
        self.callback = callback
        self.title = title

        if not urwid_found:
            logging.error("Please install the urwid package.")
            exit(1)

        main = urwid.Padding(self.menu(), left=2, right=2)
        top = urwid.Overlay(
            main,
            urwid.SolidFill(u"\N{MEDIUM SHADE}"),
            align="center",
            width=("relative", 60),
            valign="middle",
            height=("relative", 60),
            min_width=20,
            min_height=9,
        )
        self._loop = urwid.MainLoop(top, palette=[("reversed", "standout", "")])
        self._loop.run()
