class ModdingError(Exception):
    """Base class for all Tellius Modding errors."""


class ProjectError(ModdingError):
    """Raised for problems creating, loading, or saving a mod project."""
