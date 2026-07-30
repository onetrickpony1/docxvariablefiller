"""Tkinter widget for optional, in-memory rich replacement editing."""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Callable

from .rich_text import RichTextParagraph, RichTextRun, RichTextValue


_BOLD_TAG = "character_bold"
_ITALIC_TAG = "character_italic"
_BOLD_ITALIC_TAG = "character_bold_italic"
_UNDERLINE_TAG = "character_underline"
_BULLET_TAG = "paragraph_bullet"
_NUMBER_TAG = "paragraph_number"
_NUMBER_PREFIX_PATTERN = re.compile(r"^[0-9]+\. ")


class VariableEntryWidget(ttk.Frame):
    """One labelled plain entry that can expand into a rich text editor."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        variable_name: str,
        on_change: Callable[[], None],
        on_mode_change: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.variable_name = variable_name
        self.on_change = on_change
        self.on_mode_change = on_mode_change
        self.plain_value = tk.StringVar()
        self.rich_enabled = tk.BooleanVar(value=False)
        self._rich_initialized = False
        self._changing_text = False

        self.columnconfigure(1, weight=1)
        ttk.Label(self, text=variable_name).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 12),
            pady=5,
        )
        self.entry = ttk.Entry(self, textvariable=self.plain_value)
        self.entry.grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Checkbutton(
            self,
            text="Rich text editor",
            variable=self.rich_enabled,
            command=self._rich_mode_toggled,
        ).grid(row=0, column=2, sticky="w", padx=(10, 0), pady=5)

        self.rich_frame = ttk.Frame(self)
        self.rich_frame.columnconfigure(0, weight=1)
        self._build_toolbar()
        self.text = tk.Text(
            self.rich_frame,
            height=9,
            wrap="word",
            undo=True,
            exportselection=False,
            font=("Segoe UI", 10),
            padx=8,
            pady=8,
        )
        scrollbar = ttk.Scrollbar(
            self.rich_frame,
            orient="vertical",
            command=self.text.yview,
        )
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        ttk.Label(
            self.rich_frame,
            text=(
                "Select text before applying B, I, or U. Put list variables "
                "alone in their Word paragraph."
            ),
            foreground="#555555",
        ).grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(4, 0),
        )
        self._configure_text_tags()
        self.text.bind("<<Modified>>", self._text_modified)
        self.text.bind("<Control-b>", self._keyboard_bold)
        self.text.bind("<Control-i>", self._keyboard_italic)
        self.text.bind("<Control-u>", self._keyboard_underline)
        self.text.bind("<Return>", self._continue_list)
        self.plain_value.trace_add("write", self._plain_value_changed)

    def _build_toolbar(self) -> None:
        toolbar = ttk.Frame(self.rich_frame)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        ttk.Button(
            toolbar,
            text="B",
            width=3,
            command=lambda: self._toggle_character_format("bold"),
        ).grid(row=0, column=0, padx=(0, 4))
        ttk.Button(
            toolbar,
            text="I",
            width=3,
            command=lambda: self._toggle_character_format("italic"),
        ).grid(row=0, column=1, padx=(0, 4))
        ttk.Button(
            toolbar,
            text="U",
            width=3,
            command=lambda: self._toggle_character_format("underline"),
        ).grid(row=0, column=2, padx=(0, 10))
        ttk.Button(
            toolbar,
            text="Bullets",
            command=lambda: self._toggle_list("bullet"),
        ).grid(row=0, column=3, padx=(0, 4))
        ttk.Button(
            toolbar,
            text="Numbering",
            command=lambda: self._toggle_list("number"),
        ).grid(row=0, column=4)

    def _configure_text_tags(self) -> None:
        base_font = tkfont.Font(font=self.text.cget("font"))
        bold_font = base_font.copy()
        bold_font.configure(weight="bold")
        italic_font = base_font.copy()
        italic_font.configure(slant="italic")
        bold_italic_font = base_font.copy()
        bold_italic_font.configure(weight="bold", slant="italic")
        self._tag_fonts = (base_font, bold_font, italic_font, bold_italic_font)
        self.text.tag_configure(_BOLD_TAG, font=bold_font)
        self.text.tag_configure(_ITALIC_TAG, font=italic_font)
        self.text.tag_configure(_BOLD_ITALIC_TAG, font=bold_italic_font)
        self.text.tag_configure(_UNDERLINE_TAG, underline=True)
        self.text.tag_configure(_BULLET_TAG, lmargin1=12, lmargin2=30)
        self.text.tag_configure(_NUMBER_TAG, lmargin1=12, lmargin2=30)

    def set_text(self, value: str) -> None:
        """Set plain content, resetting any hidden rich formatting."""

        self._rich_initialized = False
        self.plain_value.set(value)
        if self.rich_enabled.get():
            self._set_editor_text(value)
            self._rich_initialized = True

    def set_rich_enabled(self, enabled: bool) -> None:
        """Set editor mode without reporting a user preference change."""

        self.rich_enabled.set(enabled)
        self._show_selected_editor_mode()

    def replacement_value(self) -> str | RichTextValue:
        """Return the current generic document replacement value."""

        if not self.rich_enabled.get():
            return self.plain_value.get()
        return self._build_rich_value()

    def filename_text(self) -> str:
        """Return the formatting-free value used for filename replacement."""

        replacement = self.replacement_value()
        if isinstance(replacement, RichTextValue):
            return replacement.filename_text()
        return replacement

    def is_blank(self) -> bool:
        """Return whether this entry lacks a replacement value."""

        replacement = self.replacement_value()
        if isinstance(replacement, RichTextValue):
            return replacement.is_blank
        return not replacement.strip()

    def _rich_mode_toggled(self) -> None:
        self._show_selected_editor_mode()
        self.on_mode_change()

    def _show_selected_editor_mode(self) -> None:
        if self.rich_enabled.get():
            if not self._rich_initialized:
                self._set_editor_text(self.plain_value.get())
                self._rich_initialized = True
            self.entry.grid_remove()
            self.rich_frame.grid(
                row=1,
                column=1,
                columnspan=2,
                sticky="nsew",
                pady=(0, 8),
            )
            self.text.focus_set()
        else:
            if self._rich_initialized:
                self.plain_value.set(self._build_rich_value().filename_text())
            self.rich_frame.grid_remove()
            self.entry.grid()
            self.entry.focus_set()
        self.on_change()

    def _set_editor_text(self, value: str) -> None:
        self._changing_text = True
        try:
            self.text.delete("1.0", "end")
            self.text.insert("1.0", value)
            self.text.edit_modified(False)
        finally:
            self._changing_text = False

    def _plain_value_changed(self, *_args: object) -> None:
        if not self.rich_enabled.get():
            self.on_change()

    def _text_modified(self, _event: object | None = None) -> None:
        if self._changing_text or not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        self.on_change()

    def _selected_range(self) -> tuple[str, str] | None:
        try:
            return self.text.index("sel.first"), self.text.index("sel.last")
        except tk.TclError:
            self.text.bell()
            return None

    def _toggle_character_format(self, attribute: str) -> None:
        selected = self._selected_range()
        if selected is None:
            return
        start, end = selected
        character_indices = self._character_indices(start, end)
        if not character_indices:
            return
        desired_state = not all(
            self._character_format_at(index, attribute)
            for index in character_indices
        )
        for index in character_indices:
            next_index = self.text.index(f"{index}+1c")
            bold = self._character_format_at(index, "bold")
            italic = self._character_format_at(index, "italic")
            underline = self._character_format_at(index, "underline")
            if attribute == "bold":
                bold = desired_state
            elif attribute == "italic":
                italic = desired_state
            else:
                underline = desired_state
            for tag_name in (
                _BOLD_TAG,
                _ITALIC_TAG,
                _BOLD_ITALIC_TAG,
                _UNDERLINE_TAG,
            ):
                self.text.tag_remove(tag_name, index, next_index)
            if bold and italic:
                self.text.tag_add(_BOLD_ITALIC_TAG, index, next_index)
            elif bold:
                self.text.tag_add(_BOLD_TAG, index, next_index)
            elif italic:
                self.text.tag_add(_ITALIC_TAG, index, next_index)
            if underline:
                self.text.tag_add(_UNDERLINE_TAG, index, next_index)
        self.on_change()

    def _character_indices(self, start: str, end: str) -> tuple[str, ...]:
        indices: list[str] = []
        current = self.text.index(start)
        while self.text.compare(current, "<", end):
            if self.text.get(current, f"{current}+1c") != "\n":
                indices.append(current)
            current = self.text.index(f"{current}+1c")
        return tuple(indices)

    def _character_format_at(self, index: str, attribute: str) -> bool:
        tags = set(self.text.tag_names(index))
        if attribute == "bold":
            return _BOLD_TAG in tags or _BOLD_ITALIC_TAG in tags
        if attribute == "italic":
            return _ITALIC_TAG in tags or _BOLD_ITALIC_TAG in tags
        return _UNDERLINE_TAG in tags

    def _toggle_list(self, list_style: str) -> None:
        line_numbers = self._selected_line_numbers()
        tag_name = _BULLET_TAG if list_style == "bullet" else _NUMBER_TAG
        remove_style = all(
            tag_name in self.text.tag_names(f"{line_number}.0")
            for line_number in line_numbers
        )
        for ordinal, line_number in enumerate(line_numbers, start=1):
            self._remove_list_prefix(line_number)
            self.text.tag_remove(
                _BULLET_TAG,
                f"{line_number}.0",
                f"{line_number}.end+1c",
            )
            self.text.tag_remove(
                _NUMBER_TAG,
                f"{line_number}.0",
                f"{line_number}.end+1c",
            )
            if remove_style:
                continue
            prefix = "• " if list_style == "bullet" else f"{ordinal}. "
            self.text.insert(f"{line_number}.0", prefix)
            self.text.tag_add(
                tag_name,
                f"{line_number}.0",
                f"{line_number}.end+1c",
            )
        self.on_change()

    def _selected_line_numbers(self) -> tuple[int, ...]:
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            line_number = int(self.text.index("insert").split(".")[0])
            return (line_number,)
        start_line = int(start.split(".")[0])
        end_line, end_column = (int(value) for value in end.split("."))
        if end_column == 0 and end_line > start_line:
            end_line -= 1
        return tuple(range(start_line, end_line + 1))

    def _remove_list_prefix(self, line_number: int) -> None:
        line_text = self.text.get(f"{line_number}.0", f"{line_number}.end")
        if line_text.startswith("• "):
            self.text.delete(f"{line_number}.0", f"{line_number}.2")
            return
        match = _NUMBER_PREFIX_PATTERN.match(line_text)
        if match:
            self.text.delete(
                f"{line_number}.0",
                f"{line_number}.{match.end()}",
            )

    def _continue_list(self, _event: tk.Event[tk.Misc]) -> str | None:
        line_number = int(self.text.index("insert").split(".")[0])
        tags = set(self.text.tag_names(f"{line_number}.0"))
        if _BULLET_TAG not in tags and _NUMBER_TAG not in tags:
            return None
        if _BULLET_TAG in tags:
            tag_name = _BULLET_TAG
            prefix = "• "
        else:
            tag_name = _NUMBER_TAG
            line_text = self.text.get(f"{line_number}.0", f"{line_number}.end")
            match = _NUMBER_PREFIX_PATTERN.match(line_text)
            number = int(match.group(0).split(".")[0]) + 1 if match else 1
            prefix = f"{number}. "
        self.text.insert("insert", "\n" + prefix)
        new_line = line_number + 1
        self.text.tag_add(
            tag_name,
            f"{new_line}.0",
            f"{new_line}.end+1c",
        )
        self.on_change()
        return "break"

    def _keyboard_bold(self, _event: tk.Event[tk.Misc]) -> str:
        self._toggle_character_format("bold")
        return "break"

    def _keyboard_italic(self, _event: tk.Event[tk.Misc]) -> str:
        self._toggle_character_format("italic")
        return "break"

    def _keyboard_underline(self, _event: tk.Event[tk.Misc]) -> str:
        self._toggle_character_format("underline")
        return "break"

    def _build_rich_value(self) -> RichTextValue:
        final_index = self.text.index("end-1c")
        final_line = int(final_index.split(".")[0])
        paragraphs: list[RichTextParagraph] = []
        for line_number in range(1, final_line + 1):
            list_style = self._list_style_at(line_number)
            prefix_length = self._list_prefix_length(line_number, list_style)
            line_end = self.text.index(f"{line_number}.end")
            start = self.text.index(f"{line_number}.{prefix_length}")
            runs = self._rich_runs_between(start, line_end)
            paragraphs.append(
                RichTextParagraph(runs=runs, list_style=list_style)
            )
        return RichTextValue(tuple(paragraphs))

    def _list_style_at(self, line_number: int) -> str | None:
        tags = set(self.text.tag_names(f"{line_number}.0"))
        if _BULLET_TAG in tags:
            return "bullet"
        if _NUMBER_TAG in tags:
            return "number"
        return None

    def _list_prefix_length(
        self,
        line_number: int,
        list_style: str | None,
    ) -> int:
        line_text = self.text.get(f"{line_number}.0", f"{line_number}.end")
        if list_style == "bullet" and line_text.startswith("• "):
            return 2
        if list_style == "number":
            match = _NUMBER_PREFIX_PATTERN.match(line_text)
            if match:
                return match.end()
        return 0

    def _rich_runs_between(
        self,
        start: str,
        end: str,
    ) -> tuple[RichTextRun, ...]:
        runs: list[RichTextRun] = []
        current = self.text.index(start)
        while self.text.compare(current, "<", end):
            character = self.text.get(current, f"{current}+1c")
            formatting = (
                self._character_format_at(current, "bold"),
                self._character_format_at(current, "italic"),
                self._character_format_at(current, "underline"),
            )
            if runs and (
                runs[-1].bold,
                runs[-1].italic,
                runs[-1].underline,
            ) == formatting:
                previous = runs[-1]
                runs[-1] = RichTextRun(
                    previous.text + character,
                    bold=previous.bold,
                    italic=previous.italic,
                    underline=previous.underline,
                )
            else:
                runs.append(
                    RichTextRun(
                        character,
                        bold=formatting[0],
                        italic=formatting[1],
                        underline=formatting[2],
                    )
                )
            current = self.text.index(f"{current}+1c")
        return tuple(runs)
