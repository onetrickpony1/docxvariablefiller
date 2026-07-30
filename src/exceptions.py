"""Application-specific exceptions."""


class DocxVariableFillerError(Exception):
    """Base class for errors that can be presented safely to the user."""


class InvalidFilenameError(DocxVariableFillerError):
    """Raised when a safe Windows output filename cannot be produced."""


class DocumentAccessError(DocxVariableFillerError):
    """Raised when a document cannot be read from or written to disk."""


class InvalidDocumentError(DocxVariableFillerError):
    """Raised when a file is not a valid, supported DOCX document."""


class DocumentProcessingError(DocxVariableFillerError):
    """Raised when valid document content cannot be processed safely."""


class OutputFileExistsError(DocxVariableFillerError):
    """Raised when saving would overwrite an existing output file."""


class OriginalOverwriteError(DocxVariableFillerError):
    """Raised when the selected output path is the original template path."""


class CompanyProfileError(DocxVariableFillerError):
    """Base class for safe Company Profile errors."""


class CompanyProfileValidationError(CompanyProfileError):
    """Raised when company data fails validation."""


class CompanyConfigurationError(CompanyProfileError):
    """Raised when Company Profile configuration cannot be saved safely."""
