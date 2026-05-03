"""Device detection utilities for Apple Silicon."""
import torch


def get_available_device() -> str:
    """Get the best available device (mps > cpu)."""
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def verify_mps() -> tuple[bool, str]:
    """
    Verify MPS is available and working.
    
    Returns:
        Tuple of (is_available, message)
    """
    if not torch.backends.mps.is_available():
        return False, "MPS not available - using CPU mode"
    
    try:
        device = torch.device("mps")
        x = torch.randn(3, 3, device=device)
        y = x @ x.T
        return True, "MPS available and working"
    except RuntimeError as e:
        error_msg = str(e)
        if "placeholder" in error_msg.lower():
            return False, f"MPS placeholder error - falling back to CPU: {error_msg}"
        return False, f"MPS error: {error_msg}"


def get_device_with_fallback() -> str:
    """
    Get the best available device with MPS error handling.
    
    Returns:
        Device string ("mps" or "cpu")
    """
    available, msg = verify_mps()
    if available:
        return "mps"
    print(f"⚠ {msg}")
    return "cpu"
