"""Tkinter management interface for persistent Company Profiles."""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .company_profile import CompanyProfile
from .company_profile_operations import (
    add_company_profile,
    delete_company_profile,
    edit_company_profile,
    merge_company_profiles,
)
from .company_profile_storage import (
    CompanyProfilesLoadResult,
    company_configuration_path,
    load_company_profiles,
    quarantine_company_configuration,
    save_company_profiles,
)
from .exceptions import CompanyProfileError, CompanyProfileValidationError


_PROFILE_FIELDS = (
    ("display_name", "Display Name"),
    ("company_name", "Company Name"),
    ("company_registration_number", "Company Registration Number"),
    ("company_address_line_1", "Company Address Line 1"),
    ("company_address_line_2", "Company Address Line 2"),
    ("company_postcode", "Company Postcode"),
    ("company_country", "Company Country"),
    ("company_director_1", "Company Director 1"),
    ("company_director_2", "Company Director 2 (optional)"),
    ("company_director_3", "Company Director 3 (optional)"),
)


class CompanyProfileDialog:
    """Modal add/edit dialog that returns one validated profile."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        title: str,
        initial_profile: CompanyProfile | None = None,
    ) -> None:
        self.result: CompanyProfile | None = None
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.resizable(True, False)
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)

        self.values: dict[str, tk.StringVar] = {}
        content = ttk.Frame(self.window, padding=16)
        content.grid(row=0, column=0, sticky="nsew")
        self.window.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)

        first_entry: ttk.Entry | None = None
        initial_values = (
            initial_profile.to_mapping() if initial_profile is not None else {}
        )
        for row_index, (field_name, label) in enumerate(_PROFILE_FIELDS):
            ttk.Label(content, text=label).grid(
                row=row_index,
                column=0,
                sticky="w",
                padx=(0, 12),
                pady=5,
            )
            value = tk.StringVar(value=initial_values.get(field_name, ""))
            self.values[field_name] = value
            entry = ttk.Entry(content, textvariable=value, width=48)
            entry.grid(row=row_index, column=1, sticky="ew", pady=5)
            if first_entry is None:
                first_entry = entry

        button_frame = ttk.Frame(content)
        button_frame.grid(
            row=len(_PROFILE_FIELDS),
            column=0,
            columnspan=2,
            sticky="e",
            pady=(14, 0),
        )
        ttk.Button(button_frame, text="Save", command=self._save).grid(
            row=0,
            column=0,
            padx=(0, 8),
        )
        ttk.Button(button_frame, text="Cancel", command=self._cancel).grid(
            row=0,
            column=1,
        )

        self.window.bind("<Escape>", lambda _event: self._cancel())
        self.window.grab_set()
        self.window.update_idletasks()
        self._centre_on_parent(parent)
        if first_entry is not None:
            first_entry.focus_set()
        parent.wait_window(self.window)

    def _save(self) -> None:
        try:
            self.result = CompanyProfile.from_mapping(
                {
                    field_name: value.get()
                    for field_name, value in self.values.items()
                }
            )
        except CompanyProfileValidationError as error:
            messagebox.showerror(
                "Invalid company profile",
                str(error),
                parent=self.window,
            )
            return
        self.window.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.window.destroy()

    def _centre_on_parent(self, parent: tk.Misc) -> None:
        parent.update_idletasks()
        width = self.window.winfo_reqwidth()
        height = self.window.winfo_reqheight()
        x_position = parent.winfo_rootx() + max(
            0, (parent.winfo_width() - width) // 2
        )
        y_position = parent.winfo_rooty() + max(
            0, (parent.winfo_height() - height) // 2
        )
        self.window.geometry(f"{width}x{height}+{x_position}+{y_position}")


class CompanyManagerWindow:
    """Modal list window for adding, editing, deleting, and recovering profiles."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        on_profiles_changed: Callable[[tuple[CompanyProfile, ...]], None]
        | None = None,
    ) -> None:
        self.parent = parent
        self.on_profiles_changed = on_profiles_changed
        self.profiles: tuple[CompanyProfile, ...] = ()
        self.load_result = CompanyProfilesLoadResult(())

        self.window = tk.Toplevel(parent)
        self.window.title("Manage Companies")
        self.window.geometry("620x430")
        self.window.minsize(520, 360)
        self.window.transient(parent)

        self.status_text = tk.StringVar()
        self._build_interface()
        self._load_profiles()

        self.window.grab_set()
        self.window.focus_set()
        parent.wait_window(self.window)

    def _build_interface(self) -> None:
        content = ttk.Frame(self.window, padding=16)
        content.grid(row=0, column=0, sticky="nsew")
        self.window.rowconfigure(0, weight=1)
        self.window.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)
        content.columnconfigure(0, weight=1)

        ttk.Label(
            content,
            text="Saved companies",
            font=("Segoe UI Semibold", 14),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        list_frame = ttk.Frame(content)
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        self.company_list = tk.Listbox(
            list_frame,
            activestyle="dotbox",
            exportselection=False,
        )
        scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.company_list.yview,
        )
        self.company_list.configure(yscrollcommand=scrollbar.set)
        self.company_list.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.company_list.bind("<<ListboxSelect>>", self._selection_changed)
        self.company_list.bind("<Double-Button-1>", lambda _event: self._edit())

        actions = ttk.Frame(content)
        actions.grid(row=2, column=0, sticky="ew", pady=(10, 8))
        self.add_button = ttk.Button(
            actions,
            text="Add Company",
            command=self._add,
        )
        self.edit_button = ttk.Button(
            actions,
            text="Edit Company",
            command=self._edit,
            state="disabled",
        )
        self.delete_button = ttk.Button(
            actions,
            text="Delete Company",
            command=self._delete,
            state="disabled",
        )
        self.reset_button = ttk.Button(
            actions,
            text="Recover Corrupted File",
            command=self._recover_corrupted_file,
            state="disabled",
        )
        self.import_button = ttk.Button(
            actions,
            text="Import Companies",
            command=self._import_companies,
        )
        self.export_button = ttk.Button(
            actions,
            text="Export Companies",
            command=self._export_companies,
        )
        self.add_button.grid(row=0, column=0, padx=(0, 8))
        self.edit_button.grid(row=0, column=1, padx=(0, 8))
        self.delete_button.grid(row=0, column=2, padx=(0, 8))
        self.import_button.grid(row=1, column=0, padx=(0, 8), pady=(8, 0))
        self.export_button.grid(row=1, column=1, padx=(0, 8), pady=(8, 0))
        self.reset_button.grid(row=1, column=2, pady=(8, 0))

        self.status_label = tk.Label(
            content,
            textvariable=self.status_text,
            anchor="w",
            justify="left",
            wraplength=570,
        )
        self.status_label.grid(row=3, column=0, sticky="ew")

        ttk.Button(content, text="Close", command=self.window.destroy).grid(
            row=4,
            column=0,
            sticky="e",
            pady=(12, 0),
        )

    def _load_profiles(self) -> None:
        self.load_result = load_company_profiles()
        self.profiles = self.load_result.profiles
        self._refresh_list()
        if self.load_result.issue is None:
            self.add_button.configure(state="normal")
            self.import_button.configure(state="normal")
            self.export_button.configure(state="normal")
            self.reset_button.configure(state="disabled")
            self.status_label.configure(foreground="#1f5f2c")
            self.status_text.set(
                f"Loaded {len(self.profiles)} saved company profile(s)."
            )
            return

        self.add_button.configure(state="disabled")
        self.import_button.configure(state="disabled")
        self.export_button.configure(state="disabled")
        self.edit_button.configure(state="disabled")
        self.delete_button.configure(state="disabled")
        self.reset_button.configure(state="normal")
        self.status_label.configure(foreground="#9b1c1c")
        self.status_text.set(self.load_result.issue.user_message)
        messagebox.showerror(
            "Company Profiles unavailable",
            self.load_result.issue.user_message
            + "\n\nThe existing file has not been changed. Use Recover Corrupted "
            "File to preserve it as a recovery copy and start with an empty list.",
            parent=self.window,
        )

    def _refresh_list(self, selected_index: int | None = None) -> None:
        self.company_list.delete(0, tk.END)
        for profile in self.profiles:
            self.company_list.insert(tk.END, profile.display_name)
        if selected_index is not None and self.profiles:
            safe_index = min(selected_index, len(self.profiles) - 1)
            self.company_list.selection_set(safe_index)
            self.company_list.activate(safe_index)
        self._selection_changed()

    def _selected_index(self) -> int | None:
        selection = self.company_list.curselection()
        return selection[0] if selection else None

    def _selection_changed(self, _event: object | None = None) -> None:
        has_selection = (
            self.load_result.issue is None
            and self._selected_index() is not None
        )
        state = "normal" if has_selection else "disabled"
        self.edit_button.configure(state=state)
        self.delete_button.configure(state=state)

    def _add(self) -> None:
        dialog = CompanyProfileDialog(
            self.window,
            title="Add Company",
        )
        if dialog.result is None:
            return
        try:
            updated = add_company_profile(self.profiles, dialog.result)
        except CompanyProfileValidationError as error:
            self._show_validation_error(error)
            return
        self._commit(updated, selected_index=len(updated) - 1)

    def _edit(self) -> None:
        selected_index = self._selected_index()
        if selected_index is None:
            return
        dialog = CompanyProfileDialog(
            self.window,
            title="Edit Company",
            initial_profile=self.profiles[selected_index],
        )
        if dialog.result is None:
            return
        try:
            updated = edit_company_profile(
                self.profiles,
                selected_index,
                dialog.result,
            )
        except CompanyProfileValidationError as error:
            self._show_validation_error(error)
            return
        self._commit(updated, selected_index=selected_index)

    def _delete(self) -> None:
        selected_index = self._selected_index()
        if selected_index is None:
            return
        profile = self.profiles[selected_index]
        confirmed = messagebox.askyesno(
            "Delete company",
            f'Delete the saved company "{profile.display_name}"?\n\n'
            "This action cannot be undone from within the application.",
            icon="warning",
            parent=self.window,
        )
        if not confirmed:
            return
        try:
            updated = delete_company_profile(self.profiles, selected_index)
        except CompanyProfileValidationError as error:
            self._show_validation_error(error)
            return
        self._commit(updated, selected_index=selected_index)

    def _commit(
        self,
        updated_profiles: tuple[CompanyProfile, ...],
        *,
        selected_index: int | None,
    ) -> bool:
        try:
            save_company_profiles(updated_profiles)
        except CompanyProfileError as error:
            messagebox.showerror(
                "Company Profiles not saved",
                str(error),
                parent=self.window,
            )
            return False
        self.profiles = updated_profiles
        self.load_result = CompanyProfilesLoadResult(self.profiles)
        self._refresh_list(selected_index)
        self.status_label.configure(foreground="#1f5f2c")
        self.status_text.set(
            f"Saved {len(self.profiles)} company profile(s)."
        )
        if self.on_profiles_changed is not None:
            self.on_profiles_changed(self.profiles)
        return True

    def _import_companies(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.window,
            title="Import Company Profiles",
            filetypes=(("JSON files", "*.json"),),
        )
        if not selected:
            return
        import_path = Path(selected)
        if import_path.suffix.casefold() != ".json":
            messagebox.showerror(
                "Import failed",
                "Select a JSON Company Profiles export file.",
                parent=self.window,
            )
            return
        if _paths_match(import_path, company_configuration_path()):
            messagebox.showinfo(
                "Nothing to import",
                "The selected file is already the active Company Profiles file.",
                parent=self.window,
            )
            return
        try:
            if not import_path.exists():
                raise OSError
        except OSError:
            messagebox.showerror(
                "Import failed",
                "The selected import file is no longer accessible.",
                parent=self.window,
            )
            return

        result = load_company_profiles(import_path)
        if result.issue is not None:
            messagebox.showerror(
                "Import failed",
                result.issue.user_message,
                parent=self.window,
            )
            return
        if not result.profiles:
            messagebox.showinfo(
                "Nothing to import",
                "The selected file contains no company profiles.",
                parent=self.window,
            )
            return
        try:
            merged_profiles = merge_company_profiles(
                self.profiles,
                result.profiles,
            )
        except CompanyProfileValidationError as error:
            messagebox.showerror(
                "Import failed",
                str(error)
                + "\n\nNo existing Company Profiles were changed.",
                parent=self.window,
            )
            return

        confirmed = messagebox.askyesno(
            "Import Company Profiles",
            f"Import {len(result.profiles)} company profile(s)?\n\n"
            "Existing profiles will be retained. Imported profiles cannot "
            "replace an existing profile with the same display name.",
            parent=self.window,
        )
        if not confirmed:
            return
        if self._commit(
            merged_profiles,
            selected_index=len(self.profiles),
        ):
            messagebox.showinfo(
                "Import complete",
                f"Imported {len(result.profiles)} company profile(s).",
                parent=self.window,
            )

    def _export_companies(self) -> None:
        selected = filedialog.asksaveasfilename(
            parent=self.window,
            title="Export Company Profiles",
            initialfile="companies-export.json",
            defaultextension=".json",
            filetypes=(("JSON files", "*.json"),),
            confirmoverwrite=True,
        )
        if not selected:
            return
        export_path = Path(selected)
        if export_path.suffix.casefold() != ".json":
            messagebox.showerror(
                "Export failed",
                "The export filename must end in .json.",
                parent=self.window,
            )
            return
        if _paths_match(export_path, company_configuration_path()):
            messagebox.showerror(
                "Export failed",
                "Choose a different file. The active Company Profiles file "
                "cannot be used as an export destination.",
                parent=self.window,
            )
            return
        try:
            save_company_profiles(self.profiles, export_path)
        except CompanyProfileError as error:
            messagebox.showerror(
                "Export failed",
                str(error),
                parent=self.window,
            )
            return
        messagebox.showinfo(
            "Export complete",
            f"Exported {len(self.profiles)} company profile(s) successfully.",
            parent=self.window,
        )

    def _recover_corrupted_file(self) -> None:
        confirmed = messagebox.askyesno(
            "Recover Company Profiles",
            "Preserve the current invalid configuration as a recovery copy and "
            "create a new empty Company Profiles file?",
            icon="warning",
            parent=self.window,
        )
        if not confirmed:
            return
        try:
            backup_name = quarantine_company_configuration()
            save_company_profiles(())
        except CompanyProfileError as error:
            messagebox.showerror(
                "Recovery failed",
                str(error),
                parent=self.window,
            )
            return

        self.profiles = ()
        self.load_result = CompanyProfilesLoadResult(())
        self._refresh_list()
        self.add_button.configure(state="normal")
        self.import_button.configure(state="normal")
        self.export_button.configure(state="normal")
        self.reset_button.configure(state="disabled")
        self.status_label.configure(foreground="#1f5f2c")
        recovery_note = (
            f" Recovery copy: {backup_name}."
            if backup_name is not None
            else ""
        )
        self.status_text.set(
            "A new empty Company Profiles file was created." + recovery_note
        )
        if self.on_profiles_changed is not None:
            self.on_profiles_changed(())

    def _show_validation_error(
        self,
        error: CompanyProfileValidationError,
    ) -> None:
        messagebox.showerror(
            "Invalid company profile",
            str(error),
            parent=self.window,
        )


def show_company_manager(
    parent: tk.Misc,
    *,
    on_profiles_changed: Callable[[tuple[CompanyProfile, ...]], None] | None = None,
) -> None:
    """Open the modal Company Profiles management window."""

    CompanyManagerWindow(
        parent,
        on_profiles_changed=on_profiles_changed,
    )


def _paths_match(first: Path, second: Path) -> bool:
    try:
        return first.samefile(second)
    except (FileNotFoundError, OSError):
        first_normalized = os.path.normcase(str(first.resolve(strict=False)))
        second_normalized = os.path.normcase(str(second.resolve(strict=False)))
        return first_normalized == second_normalized
