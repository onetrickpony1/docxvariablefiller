"""Tkinter user interface for the offline DOCX variable filler."""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .company_manager import show_company_manager
from .company_placeholder_mapping import (
    company_placeholder_values,
    detected_company_placeholder_names,
)
from .company_profile import CompanyProfile
from .company_profile_storage import load_company_profiles
from .date_placeholders import (
    DateInputError,
    DatePlaceholderGroup,
    collect_date_replacements,
    detect_date_placeholder_groups,
    format_date_interpretation,
)
from .document_processor import GenerationSummary, process_template, scan_template
from .exceptions import DocxVariableFillerError
from .filename_processor import (
    FilenameResult,
    build_output_filename,
    split_docx_filename,
)
from .rich_text import RichTextValue
from .rich_text_editor import VariableEntryWidget
from .settings import AppSettings, load_settings, save_settings
from .variable_parser import TemplateVariable


APPLICATION_TITLE = "DOCX Variable Filler"


def collect_replacement_values(
    values: Mapping[str, str],
) -> tuple[dict[str, str], tuple[str, ...]]:
    """Return nonblank replacements and the names of blank variables."""

    replacements: dict[str, str] = {}
    blank_names: list[str] = []
    for variable_name, value in values.items():
        if value.strip():
            replacements[variable_name] = value
        else:
            blank_names.append(variable_name)
    return replacements, tuple(blank_names)


def collect_sanitized_characters(result: FilenameResult) -> tuple[str, ...]:
    """Return distinct filename characters changed during sanitization."""

    changed: dict[str, None] = {}
    for sanitization in result.sanitizations:
        for character in sanitization.changed_characters:
            changed.setdefault(character, None)
    return tuple(changed)


def format_filename_notice(result: FilenameResult) -> str:
    """Return a concise preview notice for automatic filename adjustments."""

    notices: list[str] = []
    if result.notes_removed:
        noun = "note" if result.notes_removed == 1 else "notes"
        notices.append(
            f"{result.notes_removed} template filename {noun} will be removed."
        )
    if result.sanitizations:
        notices.append(
            "Some filename characters were adjusted for Windows compatibility. "
            "The final filename shown above will be confirmed before saving."
        )
    return " ".join(notices)


def blank_variables_to_highlight(
    blank_names: tuple[str, ...],
    *,
    highlight_changes: bool,
    leave_blanks_unchanged: bool,
) -> tuple[str, ...]:
    """Return retained blank variables that require review highlighting."""

    if highlight_changes and leave_blanks_unchanged:
        return blank_names
    return ()


def collapse_blank_field_names(
    blank_names: tuple[str, ...],
    date_groups: tuple[DatePlaceholderGroup, ...],
) -> tuple[str, ...]:
    """Collapse related blank date placeholders into one user-facing label."""

    date_labels = {
        placeholder.variable_name: f"{group.display_name} date"
        for group in date_groups
        for placeholder in group.placeholders
    }
    collapsed: dict[str, None] = {}
    for name in blank_names:
        collapsed.setdefault(date_labels.get(name, name), None)
    return tuple(collapsed)


class DocxVariableFillerApp:
    """Small offline desktop interface for filling DOCX templates."""

    def __init__(
        self,
        root: tk.Tk,
        *,
        restore_remembered_template: bool = True,
    ) -> None:
        self.root = root
        saved_settings = load_settings()
        self.template_path: Path | None = None
        self.detected_variables: tuple[TemplateVariable, ...] = ()
        self.value_variables: dict[str, tk.StringVar] = {}
        self.variable_editors: dict[str, VariableEntryWidget] = {}
        self.date_groups: tuple[DatePlaceholderGroup, ...] = ()
        self.date_group_values: dict[str, tk.StringVar] = {}
        self.date_preview_texts: dict[str, tk.StringVar] = {}
        self._remembered_template_path = saved_settings.last_template_path
        self._remembered_rich_indices = (
            saved_settings.rich_text_variable_indices
        )
        self.company_profiles: tuple[CompanyProfile, ...] = ()
        self.company_selector: ttk.Combobox | None = None
        self.company_selector_status_label: tk.Label | None = None
        self._last_technical_error: BaseException | None = None

        self.selected_path_text = tk.StringVar(value="No template selected")
        self.detected_count_text = tk.StringVar(value="Detected variables")
        self.output_preview_text = tk.StringVar(value="Select a template to begin.")
        self.filename_notice_text = tk.StringVar(value="")
        self.company_selection = tk.StringVar(value="")
        self.company_selector_status_text = tk.StringVar(value="")
        self.highlight_changes = tk.BooleanVar(
            value=saved_settings.highlight_changes
        )
        self.leave_blanks_unchanged = tk.BooleanVar(
            value=saved_settings.leave_blanks_unchanged
        )
        self.status_text = tk.StringVar(
            value="Select a Microsoft Word .docx template."
        )

        self._configure_window()
        self._build_interface()
        self.root.report_callback_exception = self._handle_tk_callback_error
        self.highlight_changes.trace_add("write", self._on_preference_changed)
        self.leave_blanks_unchanged.trace_add(
            "write", self._on_preference_changed
        )
        self.root.protocol("WM_DELETE_WINDOW", self._close_application)
        if restore_remembered_template and saved_settings.last_template_path:
            self.root.after_idle(
                self._restore_remembered_template,
                saved_settings.last_template_path,
            )

    def _configure_window(self) -> None:
        self.root.title(APPLICATION_TITLE)
        self.root.geometry("980x800")
        self.root.minsize(700, 620)
        self.root.option_add("*Font", ("Segoe UI", 10))

        style = ttk.Style(self.root)
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 18))
        style.configure("Section.TLabel", font=("Segoe UI Semibold", 10))
        style.configure("Primary.TButton", font=("Segoe UI Semibold", 10))

    def _build_interface(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=10)

        ttk.Label(
            outer,
            text=APPLICATION_TITLE,
            style="Title.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            outer,
            text="Fill {{variables}} in Word documents without changing the template.",
        ).grid(row=1, column=0, sticky="w", pady=(2, 16))

        selection_frame = ttk.Frame(outer)
        selection_frame.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        selection_frame.columnconfigure(1, weight=1)
        ttk.Button(
            selection_frame,
            text="Select Word Template",
            command=self.select_template,
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Label(
            selection_frame,
            textvariable=self.selected_path_text,
            wraplength=400,
        ).grid(row=0, column=1, sticky="ew")
        ttk.Button(
            selection_frame,
            text="Manage Companies",
            command=self._open_company_manager,
        ).grid(row=0, column=2, sticky="e", padx=(12, 0))

        ttk.Label(
            outer,
            textvariable=self.detected_count_text,
            style="Section.TLabel",
        ).grid(row=3, column=0, sticky="w", pady=(0, 6))

        self.form_border = ttk.Frame(
            outer,
            relief="solid",
            borderwidth=1,
        )
        self.form_border.grid(row=4, column=0, sticky="nsew")
        self.form_border.rowconfigure(0, weight=1)
        self.form_border.columnconfigure(0, weight=1)

        self.form_canvas = tk.Canvas(
            self.form_border,
            highlightthickness=0,
            borderwidth=0,
            height=360,
        )
        form_scrollbar = ttk.Scrollbar(
            self.form_border,
            orient="vertical",
            command=self.form_canvas.yview,
        )
        self.form_canvas.configure(yscrollcommand=form_scrollbar.set)
        self.form_canvas.grid(row=0, column=0, sticky="nsew")
        form_scrollbar.grid(row=0, column=1, sticky="ns")

        self.fields_frame = ttk.Frame(self.form_canvas, padding=12)
        self.fields_frame.columnconfigure(1, weight=1)
        self.fields_window = self.form_canvas.create_window(
            (0, 0),
            anchor="nw",
            window=self.fields_frame,
        )
        self.fields_frame.bind("<Configure>", self._update_scroll_region)
        self.form_canvas.bind("<Configure>", self._resize_fields_frame)
        self.form_canvas.bind("<Enter>", self._enable_mousewheel)
        self.form_canvas.bind("<Leave>", self._disable_mousewheel)
        self._show_empty_form_message()

        options = ttk.Frame(outer)
        options.grid(row=5, column=0, sticky="ew", pady=(8, 6))
        ttk.Checkbutton(
            options,
            text="Highlight changed text for review",
            variable=self.highlight_changes,
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            options,
            text="Leave blank variables unchanged",
            variable=self.leave_blanks_unchanged,
        ).grid(row=0, column=1, sticky="w", padx=(24, 0))

        generation_frame = ttk.Frame(outer)
        generation_frame.grid(row=6, column=0, sticky="ew", pady=(0, 6))
        generation_frame.columnconfigure(0, weight=1)
        preview_frame = ttk.LabelFrame(
            generation_frame,
            text="Proposed output filename",
            padding=8,
        )
        preview_frame.grid(row=0, column=0, sticky="ew")
        preview_frame.columnconfigure(0, weight=1)
        ttk.Label(
            preview_frame,
            textvariable=self.output_preview_text,
            wraplength=690,
        ).grid(row=0, column=0, sticky="w")
        self.filename_notice_label = tk.Label(
            preview_frame,
            textvariable=self.filename_notice_text,
            foreground="#8a4b08",
            anchor="w",
            justify="left",
            wraplength=690,
        )
        self.filename_notice_label.grid(row=1, column=0, sticky="w", pady=(3, 0))

        actions = ttk.Frame(generation_frame)
        actions.grid(row=0, column=1, sticky="e", padx=(10, 0))
        self.generate_button = ttk.Button(
            actions,
            text="Generate Document",
            command=self.generate_document,
            state="disabled",
            style="Primary.TButton",
        )
        self.generate_button.grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Clear", command=self.clear).grid(row=0, column=1)

        status_frame = ttk.LabelFrame(outer, text="Status", padding=8)
        status_frame.grid(row=7, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)
        self.status_label = tk.Label(
            status_frame,
            textvariable=self.status_text,
            anchor="w",
            justify="left",
            wraplength=900,
        )
        self.status_label.grid(row=0, column=0, sticky="ew")

    def select_template(self) -> None:
        """Prompt for a DOCX template and build its variable form."""

        selected = filedialog.askopenfilename(
            parent=self.root,
            title="Select Word Template",
            filetypes=(("Microsoft Word documents", "*.docx"),),
        )
        if not selected:
            return

        self._load_template(Path(selected), show_dialog_errors=True)

    def _load_template(
        self,
        path: Path,
        *,
        show_dialog_errors: bool,
    ) -> None:
        """Scan *path* and populate the form."""

        try:
            variables = scan_template(path)
        except DocxVariableFillerError as error:
            if show_dialog_errors:
                self._show_error(str(error), error)
            else:
                self._show_startup_restore_error(str(error), error)
            return
        except Exception as error:
            message = (
                "The remembered template could not be scanned. Select it again "
                "or choose another DOCX file."
            )
            if show_dialog_errors:
                self._show_error(
                    "The template could not be scanned. Check that it is a valid, "
                    "accessible DOCX file.",
                    error,
                )
            else:
                self._show_startup_restore_error(message, error)
            return

        self.template_path = path
        self.detected_variables = variables
        self.selected_path_text.set(str(path))
        self._build_variable_fields()
        self._save_preferences()

        if not variables:
            self.generate_button.configure(state="disabled")
            self.detected_count_text.set("Detected variables (0)")
            self.output_preview_text.set(path.name)
            message = "No variables were found in the document or filename."
            if show_dialog_errors:
                self._show_warning(message)
            else:
                self.status_label.configure(foreground="#8a4b08")
                self.status_text.set(message)
            return

        self.generate_button.configure(state="normal")
        self.status_label.configure(foreground="#1f5f2c")
        self.status_text.set(
            f"Found {len(variables)} unique variable(s). Enter a value for each one."
        )
        self._update_filename_preview()

    def generate_document(self) -> None:
        """Validate entries, request an output path, and generate the DOCX."""

        if self.template_path is None or not self.detected_variables:
            self._show_warning("Select a template containing variables first.")
            return

        try:
            replacements, filename_replacements, blank_names = (
                self._collect_editor_replacements()
            )
        except DateInputError as error:
            self._show_warning(str(error))
            return
        except (TypeError, ValueError) as error:
            self._show_error(
                "One of the rich text values is invalid or too large.",
                error,
            )
            return
        if blank_names and not self.leave_blanks_unchanged.get():
            display_names = collapse_blank_field_names(
                blank_names,
                self.date_groups,
            )
            formatted_names = "\n".join(
                f"• {name}" for name in display_names
            )
            self._show_warning(
                "Enter a value for the following variables:\n\n" + formatted_names
            )
            return

        try:
            filename_result = build_output_filename(
                self.template_path.name,
                filename_replacements,
            )
        except DocxVariableFillerError as error:
            self._show_error(str(error), error)
            return

        if filename_result.sanitizations:
            proceed = messagebox.askokcancel(
                "Filename adjusted",
                "Some replacement characters are not valid in Windows filenames "
                "and were adjusted.\n\nFinal proposed filename:\n"
                f"{filename_result.filename}",
                parent=self.root,
            )
            if not proceed:
                return

        selected_output = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save Completed Document",
            initialdir=str(self.template_path.parent),
            initialfile=filename_result.filename,
            defaultextension=".docx",
            filetypes=(("Microsoft Word documents", "*.docx"),),
            confirmoverwrite=False,
        )
        if not selected_output:
            return

        output_path = Path(selected_output)
        try:
            split_docx_filename(output_path.name)
        except DocxVariableFillerError as error:
            self._show_error(str(error), error)
            return

        if _paths_match(self.template_path, output_path):
            self._show_error(
                "Choose a different output filename. The original template "
                "will not be overwritten."
            )
            return

        allow_overwrite = False
        if output_path.exists():
            allow_overwrite = messagebox.askyesno(
                "Confirm overwrite",
                "A file with this name already exists.\n\n"
                f"{output_path.name}\n\nOverwrite it?",
                icon="warning",
                parent=self.root,
            )
            if not allow_overwrite:
                return

        sanitized_characters = collect_sanitized_characters(filename_result)
        try:
            summary = process_template(
                self.template_path,
                output_path,
                replacements,
                allow_overwrite=allow_overwrite,
                highlight_changes=self.highlight_changes.get(),
                highlight_unchanged_variables=blank_variables_to_highlight(
                    blank_names,
                    highlight_changes=self.highlight_changes.get(),
                    leave_blanks_unchanged=self.leave_blanks_unchanged.get(),
                ),
                sanitized_filename_characters=sanitized_characters,
            )
        except DocxVariableFillerError as error:
            self._show_error(str(error), error)
            return
        except Exception as error:
            self._show_error(
                "The document could not be generated. The original template "
                "was not changed.",
                error,
            )
            return

        summary_text = format_generation_summary(summary)
        self.status_label.configure(foreground="#1f5f2c")
        self.status_text.set(format_compact_generation_status(summary))
        messagebox.showinfo(
            "Document generated",
            "The completed document was saved successfully.\n\n" + summary_text,
            parent=self.root,
        )

    def clear(self) -> None:
        """Clear the selected template and all values held by the interface."""

        self.template_path = None
        self.detected_variables = ()
        self.value_variables.clear()
        self.variable_editors.clear()
        self.date_groups = ()
        self.date_group_values.clear()
        self.date_preview_texts.clear()
        self.company_profiles = ()
        self.company_selection.set("")
        self._last_technical_error = None
        self.selected_path_text.set("No template selected")
        self.detected_count_text.set("Detected variables")
        self.output_preview_text.set("Select a template to begin.")
        self.filename_notice_text.set("")
        self.highlight_changes.set(False)
        self.leave_blanks_unchanged.set(False)
        self.generate_button.configure(state="disabled")
        self.status_label.configure(foreground="#222222")
        self.status_text.set("Select a Microsoft Word .docx template.")
        self._clear_field_widgets()
        self._show_empty_form_message()
        self._save_preferences()

    def _build_variable_fields(self) -> None:
        self._clear_field_widgets()
        self.value_variables.clear()
        self.variable_editors.clear()
        self.date_group_values.clear()
        self.date_preview_texts.clear()
        self.company_selector = None
        self.company_selection.set("")
        self.company_selector_status_text.set("")
        self.detected_count_text.set(
            f"Detected variables ({len(self.detected_variables)})"
        )

        if not self.detected_variables:
            self._show_empty_form_message()
            return

        company_placeholder_names = detected_company_placeholder_names(
            variable.canonical_name for variable in self.detected_variables
        )
        self.date_groups = detect_date_placeholder_groups(
            variable.canonical_name for variable in self.detected_variables
        )
        date_variable_names = {
            placeholder.variable_name
            for group in self.date_groups
            for placeholder in group.placeholders
        }
        row_offset = 0
        if company_placeholder_names:
            self._build_company_selector(row_offset)
            row_offset += 1
        if self.date_groups:
            self._build_date_group_section(row_offset)
            row_offset += 1

        first_entry: ttk.Entry | None = None
        for row_index, variable in enumerate(self.detected_variables):
            if variable.canonical_name in date_variable_names:
                continue
            editor = VariableEntryWidget(
                self.fields_frame,
                variable_name=variable.canonical_name,
                on_change=self._on_replacement_changed,
                on_mode_change=self._on_rich_mode_changed,
            )
            editor.grid(
                row=row_index + row_offset,
                column=0,
                columnspan=2,
                sticky="ew",
            )
            self.variable_editors[variable.canonical_name] = editor
            self.value_variables[variable.canonical_name] = editor.plain_value
            if self._should_restore_rich_mode(row_index):
                editor.set_rich_enabled(True)
            if first_entry is None:
                first_entry = editor.entry

        self.form_canvas.yview_moveto(0)
        if self.company_selector is not None and self.company_profiles:
            self.company_selector.focus_set()
        elif first_entry is not None:
            first_entry.focus_set()

    def _build_company_selector(self, row: int) -> None:
        selector_frame = ttk.LabelFrame(
            self.fields_frame,
            text="Company Profile",
            padding=10,
        )
        selector_frame.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 10),
        )
        selector_frame.columnconfigure(1, weight=1)
        ttk.Label(selector_frame, text="Company").grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 12),
        )
        self.company_selector = ttk.Combobox(
            selector_frame,
            textvariable=self.company_selection,
            state="disabled",
        )
        self.company_selector.grid(row=0, column=1, sticky="ew")
        self.company_selector.bind(
            "<<ComboboxSelected>>",
            self._company_selected,
        )
        self.company_selector_status_label = tk.Label(
            selector_frame,
            textvariable=self.company_selector_status_text,
            anchor="w",
            justify="left",
            wraplength=570,
        )
        self.company_selector_status_label.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(5, 0),
        )
        self._load_company_selector_profiles()

    def _build_date_group_section(self, row: int) -> None:
        date_frame = ttk.LabelFrame(
            self.fields_frame,
            text="Smart Dates",
            padding=10,
        )
        date_frame.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 10),
        )
        date_frame.columnconfigure(1, weight=1)
        ttk.Label(
            date_frame,
            text=(
                "Enter one date per group as DD/MM/YYYY. A two-digit year "
                "means 2000–2099."
            ),
            foreground="#555555",
        ).grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(0, 7),
        )
        for index, group in enumerate(self.date_groups, start=1):
            value = tk.StringVar()
            preview = tk.StringVar(
                value=format_date_interpretation("")
            )
            self.date_group_values[group.key] = value
            self.date_preview_texts[group.key] = preview
            ttk.Label(
                date_frame,
                text=f"{group.display_name} date",
            ).grid(
                row=index,
                column=0,
                sticky="w",
                padx=(0, 12),
                pady=4,
            )
            ttk.Entry(
                date_frame,
                textvariable=value,
            ).grid(row=index, column=1, sticky="ew", pady=4)
            ttk.Label(
                date_frame,
                textvariable=preview,
                foreground="#555555",
            ).grid(
                row=index,
                column=2,
                sticky="w",
                padx=(12, 0),
                pady=4,
            )
            value.trace_add(
                "write",
                lambda *_args, group_key=group.key: (
                    self._on_date_value_changed(group_key)
                ),
            )

    def _load_company_selector_profiles(self) -> None:
        result = load_company_profiles()
        self.company_profiles = result.profiles
        if (
            self.company_selector is None
            or self.company_selector_status_label is None
        ):
            return
        if result.issue is not None:
            self._last_technical_error = result.issue.technical_error
            self.company_selector.configure(values=(), state="disabled")
            self.company_selector_status_label.configure(
                foreground="#9b1c1c"
            )
            self.company_selector_status_text.set(
                result.issue.user_message
                + " Use Manage Companies to recover the configuration."
            )
            return
        self._refresh_company_selector_options()

    def _company_selected(self, _event: object | None = None) -> None:
        if self.company_selector_status_label is None:
            return
        selected_name = self.company_selection.get()
        selected_profile = next(
            (
                profile
                for profile in self.company_profiles
                if profile.display_name == selected_name
            ),
            None,
        )
        if selected_profile is None:
            self.company_selector_status_label.configure(
                foreground="#8a4b08"
            )
            self.company_selector_status_text.set(
                "Select a valid saved company profile."
            )
            return

        for placeholder_name, value in company_placeholder_values(
            selected_profile
        ).items():
            editor = self.variable_editors.get(placeholder_name)
            if editor is not None:
                editor.set_text(value)
        self.company_selector_status_label.configure(foreground="#1f5f2c")
        self.company_selector_status_text.set(
            "Company values populated. Review and edit them as needed."
        )

    def _refresh_company_selector_options(self) -> None:
        if (
            self.company_selector is None
            or self.company_selector_status_label is None
        ):
            return
        display_names = tuple(
            profile.display_name for profile in self.company_profiles
        )
        self.company_selection.set("")
        self.company_selector.configure(values=display_names)
        if display_names:
            self.company_selector.configure(state="readonly")
            self.company_selector_status_label.configure(
                foreground="#222222"
            )
            self.company_selector_status_text.set(
                "Select a saved company to populate matching fields."
            )
        else:
            self.company_selector.configure(state="disabled")
            self.company_selector_status_label.configure(
                foreground="#8a4b08"
            )
            self.company_selector_status_text.set(
                "No saved companies are available. Use Manage Companies to add one."
            )

    def _clear_field_widgets(self) -> None:
        for widget in self.fields_frame.winfo_children():
            widget.destroy()
        self.company_selector = None
        self.company_selector_status_label = None

    def _show_empty_form_message(self) -> None:
        ttk.Label(
            self.fields_frame,
            text="Variable input fields will appear here.",
        ).grid(row=0, column=0, columnspan=2, sticky="w")

    def _on_replacement_changed(self, *_args: object) -> None:
        self._update_filename_preview()

    def _on_date_value_changed(self, group_key: str) -> None:
        value = self.date_group_values[group_key].get()
        self.date_preview_texts[group_key].set(
            format_date_interpretation(value)
        )
        self._update_filename_preview()

    def _on_rich_mode_changed(self) -> None:
        self._update_filename_preview()
        self._save_preferences()

    def _on_preference_changed(self, *_args: object) -> None:
        self._save_preferences()

    def _open_company_manager(self) -> None:
        show_company_manager(
            self.root,
            on_profiles_changed=self._company_profiles_changed,
        )

    def _company_profiles_changed(
        self,
        profiles: tuple[CompanyProfile, ...],
    ) -> None:
        self.company_profiles = profiles
        self._refresh_company_selector_options()
        self.status_label.configure(foreground="#1f5f2c")
        self.status_text.set(
            f"Company Profiles updated: {len(profiles)} saved company profile(s)."
        )

    def _update_filename_preview(self) -> None:
        if self.template_path is None:
            return
        try:
            _document_replacements, filename_replacements, _blank_names = (
                self._collect_editor_replacements()
            )
            result = build_output_filename(
                self.template_path.name,
                filename_replacements,
            )
        except DateInputError as error:
            self.output_preview_text.set(
                "Correct the smart date to update the filename preview."
            )
            self.filename_notice_text.set(str(error))
            return
        except (DocxVariableFillerError, TypeError, ValueError) as error:
            self.output_preview_text.set("A valid output filename cannot be proposed.")
            self.filename_notice_text.set(str(error))
            return

        self.output_preview_text.set(result.filename)
        self.filename_notice_text.set(format_filename_notice(result))

    def _collect_editor_replacements(
        self,
    ) -> tuple[
        dict[str, str | RichTextValue],
        dict[str, str],
        tuple[str, ...],
    ]:
        document_replacements: dict[str, str | RichTextValue] = {}
        filename_replacements: dict[str, str] = {}
        blank_names: list[str] = []
        date_values = {
            group_key: value.get()
            for group_key, value in self.date_group_values.items()
        }
        date_replacements, blank_dates = collect_date_replacements(
            self.date_groups,
            date_values,
        )
        document_replacements.update(date_replacements)
        filename_replacements.update(date_replacements)
        blank_names.extend(blank_dates)
        for variable_name, editor in self.variable_editors.items():
            replacement = editor.replacement_value()
            is_blank = (
                replacement.is_blank
                if isinstance(replacement, RichTextValue)
                else not replacement.strip()
            )
            if is_blank:
                blank_names.append(variable_name)
                continue
            document_replacements[variable_name] = replacement
            filename_replacements[variable_name] = editor.filename_text()
        return (
            document_replacements,
            filename_replacements,
            tuple(blank_names),
        )

    def _should_restore_rich_mode(self, variable_index: int) -> bool:
        if self.template_path is None or not self._remembered_template_path:
            return False
        if not _paths_match(
            self.template_path,
            Path(self._remembered_template_path),
        ):
            return False
        return variable_index in self._remembered_rich_indices

    def _show_warning(self, message: str) -> None:
        self.status_label.configure(foreground="#8a4b08")
        self.status_text.set(message)
        messagebox.showwarning(APPLICATION_TITLE, message, parent=self.root)

    def _show_error(
        self,
        message: str,
        technical_error: BaseException | None = None,
    ) -> None:
        self._last_technical_error = technical_error
        self.status_label.configure(foreground="#9b1c1c")
        self.status_text.set(message)
        messagebox.showerror(APPLICATION_TITLE, message, parent=self.root)

    def _show_startup_restore_error(
        self,
        message: str,
        technical_error: BaseException,
    ) -> None:
        self._last_technical_error = technical_error
        self.status_label.configure(foreground="#8a4b08")
        self.status_text.set(message)

    def _restore_remembered_template(self, remembered_path: str) -> None:
        self._load_template(
            Path(remembered_path),
            show_dialog_errors=False,
        )

    def _save_preferences(self) -> None:
        rich_text_variable_indices = tuple(
            index
            for index, variable in enumerate(self.detected_variables)
            if (
                editor := self.variable_editors.get(variable.canonical_name)
            ) is not None
            and editor.rich_enabled.get()
        )
        settings = AppSettings(
            last_template_path=(
                str(self.template_path) if self.template_path is not None else None
            ),
            highlight_changes=self.highlight_changes.get(),
            leave_blanks_unchanged=self.leave_blanks_unchanged.get(),
            rich_text_variable_indices=rich_text_variable_indices,
        )
        try:
            save_settings(settings)
            self._remembered_template_path = settings.last_template_path
            self._remembered_rich_indices = rich_text_variable_indices
        except OSError as error:
            self._last_technical_error = error
            self.status_label.configure(foreground="#8a4b08")
            self.status_text.set(
                "Preferences could not be saved. The current session can continue."
            )

    def _close_application(self) -> None:
        self._save_preferences()
        self.root.destroy()

    def _handle_tk_callback_error(
        self,
        _exception_type: type[BaseException],
        exception: BaseException,
        _traceback: object,
    ) -> None:
        self._show_error(
            "An unexpected application error occurred. No document was generated.",
            exception,
        )

    def _update_scroll_region(self, _event: tk.Event[tk.Misc]) -> None:
        self.form_canvas.configure(scrollregion=self.form_canvas.bbox("all"))

    def _resize_fields_frame(self, event: tk.Event[tk.Misc]) -> None:
        self.form_canvas.itemconfigure(self.fields_window, width=event.width)

    def _enable_mousewheel(self, _event: tk.Event[tk.Misc]) -> None:
        self.form_canvas.bind_all("<MouseWheel>", self._scroll_form)

    def _disable_mousewheel(self, _event: tk.Event[tk.Misc]) -> None:
        self.form_canvas.unbind_all("<MouseWheel>")

    def _scroll_form(self, event: tk.Event[tk.Misc]) -> None:
        self.form_canvas.yview_scroll(int(-event.delta / 120), "units")


def format_generation_summary(summary: GenerationSummary) -> str:
    """Format a non-sensitive completion summary for display."""

    highlight_status = "Enabled" if summary.review_highlighting_enabled else "Disabled"
    sanitized = (
        ", ".join(
            _display_character(character)
            for character in summary.sanitized_filename_characters
        )
        if summary.sanitized_filename_characters
        else "None"
    )
    return (
        f"Output filename: {summary.output_filename}\n"
        f"Save location: {summary.save_location}\n"
        f"Unique variables replaced: {summary.unique_variables_replaced}\n"
        f"Document replacements: {summary.total_replacements}\n"
        f"Yellow review highlighting: {highlight_status}\n"
        f"Sanitized filename characters: {sanitized}"
    )


def format_compact_generation_status(summary: GenerationSummary) -> str:
    """Format a concise, non-sensitive status line for the main window."""

    highlight_status = (
        "Enabled" if summary.review_highlighting_enabled else "Disabled"
    )
    sanitized = (
        ", ".join(
            _display_character(character)
            for character in summary.sanitized_filename_characters
        )
        if summary.sanitized_filename_characters
        else "None"
    )
    return (
        f"Saved {summary.output_filename} to {summary.save_location}  |  "
        f"Variables: {summary.unique_variables_replaced}  |  "
        f"Replacements: {summary.total_replacements}  |  "
        f"Review highlighting: {highlight_status}  |  "
        f"Sanitized characters: {sanitized}"
    )


def _display_character(character: str) -> str:
    if character == " ":
        return "[space]"
    if character == "\t":
        return "[tab]"
    if character in {"\r", "\n"}:
        return "[line break]"
    return character


def _paths_match(first: Path, second: Path) -> bool:
    try:
        return first.samefile(second)
    except (FileNotFoundError, OSError):
        first_path = os.path.normcase(str(first.resolve(strict=False)))
        second_path = os.path.normcase(str(second.resolve(strict=False)))
        return first_path == second_path


def run_application(*, smoke_test: bool = False) -> None:
    """Create and run the Tkinter application.

    A smoke test constructs the complete interface and exits without showing a
    window or accessing any user files.
    """

    root = tk.Tk()
    DocxVariableFillerApp(
        root,
        restore_remembered_template=not smoke_test,
    )
    if smoke_test:
        root.withdraw()
        root.update_idletasks()
        root.destroy()
        return
    root.mainloop()
