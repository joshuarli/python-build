"""Domain errors shared by catalog adapters and query operations."""


class CatalogError(Exception):
    """Base class for expected catalog failures."""


class DuplicateEntryError(CatalogError):
    """Raised when an identifier is already present in a repository."""


class EntryNotFoundError(CatalogError):
    """Raised when a requested catalog identifier is absent."""


class InvalidQueryError(CatalogError):
    """Raised when query text cannot be represented as a search plan."""


class StorageError(CatalogError):
    """Raised when a persisted catalog cannot be read or written."""


class TransactionError(CatalogError):
    """Raised when a repository transaction cannot be committed."""
